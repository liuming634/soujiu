"""flow 主文件：自动链路总调度（FreeRTOS 式轮询框架）。

结构（2026-10-18 口述定稿）：监视线程持续监控、**直接修改** RuntimeData
状态量；一个 while 大循环只读状态量、三层 if 分发；每个接口处理只改
状态与记账，动作在下一轮轮询里由新状态驱动。

监视线程（生产者，start_flow 启动）：
  1. STM32 回传接收（复用 auto/actuator：start_receiving）——0x02 机构
     状态帧 → actuator_state 镜像，0x03 IMU 帧 → imu_state 镜像
  2. 接收机判飞行线程 _receiver_flight_loop —— 层1 auto_flight_state
     （主源 = 接收机；与 IMU / 图像光流判定并列，同形态换源）
  3. 机构监视线程 _mech_monitor_loop —— 层2 auto_mech_state（低频采样
     入长队列，收样当场判，抓/放角度差大可直接判脱落）
  4. YOLO 任务判定线程 _yolo_task_loop —— yolo_task（识别结果直接定
     任务，四类别；只被大循环的落地链路消费）
  5. 相机取帧线程 _camera_loop —— current_frame

大循环 _main_loop（消费者/调度）：
  层1 飞行状况 → 层2 机构状况 → 层3 任务记账 / YOLO 任务判定。
  单轮异常只打印跳过，不拖垮流程。处理前提：正常比赛流程——飞手按
  规则来回飞行，复飞同样满足。

状态量与记账字段在 RuntimeData（两层状态 / yolo_task / task_memo /
计数 N 等），可调参数在 auto/params.py 的 flow 段。
"""
import threading
import time
from collections import deque

from common.core.config import config
from common.core.runtime_data import (
    RuntimeData,
    AUTO_FLYING, AUTO_LANDED,
    MECH_IDLE, MECH_HOLD, MECH_PROCESS,
    TASK_GRAB_CUBE, TASK_GRAB_BALL, TASK_DROP_CUBE, TASK_DROP_BALL,
    MEMO_GRAB_SENT, MEMO_DROP_SENT,
    GRABBER_HOLDING_CUBE, GRABBER_HOLDING_BALL, GRABBER_EMPTY,
)
from common.logic.coordinate_mapper import PixelToPlaneMapper

from auto import params
from auto.actuator.grabber import judge_grabber
from auto.actuator.link import open_comm, start_receiving, stop_receiving
from auto.detection.detector import detect
from auto.landing.monitor import start_landing_monitor, stop_landing_monitor
from auto.region.grab_range import filter_grabbable, overlap_ok, point_in_range
from auto.scoring.scorer import score_cubes, score_balls


# ── 监视线程（生产者：直改状态量） ──────────────────────────────────

def _receiver_flight_loop(data: RuntimeData, running: threading.Event) -> None:
    """层1 飞行状况监视线程（主源 = 接收机）：直改 auto_flight_state

    收到遥控器信号 = flying；没收到 = landed。与 IMU 判定（landing
    监视线程）、图像光流判定并列——三者同形态：监视线程持续判定、直改
    同一个状态量，换主源 = 换线程，大循环与字段不动。
    TODO(电控)：接收机数据源未接入，_receiver_signal_active 占位恒 False
    （恒判落地）；接入后按口径（链路在线 / 通道值变化）实现。
    """
    while running.is_set():
        data.auto_flight_state = (AUTO_FLYING if _receiver_signal_active(data)
                                  else AUTO_LANDED)
        time.sleep(params.RECEIVER_POLL_INTERVAL)


def _receiver_signal_active(data: RuntimeData) -> bool:
    """接收机信号判定（占位）：数据源待电控接入，接入前恒判没信号（落地）

    参考口径（伪代码 §1.4）：落地后人工基本不再操作遥控器 → 超时收不到
    信号即判落地；可用 data.receiver_last_time（读数线程刷新）做超时口径。
    """
    return False


def _mech_monitor_loop(data: RuntimeData, running: threading.Event) -> None:
    """层2 机构状况监视线程：收样本入队列 + 当场判定 + 直改 auto_mech_state

    采样 params.MECH_SAMPLE_INTERVAL（0.05~0.1s 及时响应）；抓取/放开
    角度差别大，收到样本就能直接判出是否脱落；长队列存历史数据，捕捉
    夹着(hold)→空了(idle) 的转变 = process（老样本滑出队列自然退回
    idle，过程窗长 = 队列长）。瞬时角度分档用 judge_grabber（角度范围
    params.GRAB_SERVO_*，占位待标定）；运动中 None 样本维持原状态。
    """
    queue = deque(maxlen=params.MECH_QUEUE_LEN)
    while running.is_set():
        sample = judge_grabber(data.actuator_state)   # 'cube'/'ball'/'empty'/None
        queue.append(sample)

        prev = data.auto_mech_state
        if sample in (GRABBER_HOLDING_CUBE, GRABBER_HOLDING_BALL):
            data.auto_mech_state = MECH_HOLD          # 收到夹着样本 → 抓取状态
        elif sample == GRABBER_EMPTY:
            if any(s in (GRABBER_HOLDING_CUBE, GRABBER_HOLDING_BALL)
                   for s in queue):
                data.auto_mech_state = MECH_PROCESS   # 现在空了、之前夹着 → 过程态
            else:
                data.auto_mech_state = MECH_IDLE      # 一直空爪 → 静止常态
        # None（运动中）：维持原状态

        if prev == MECH_PROCESS and data.auto_mech_state != MECH_PROCESS:
            data.process_handled = False              # 离开过程态 → 事件标记复位

        time.sleep(params.MECH_SAMPLE_INTERVAL)


def _yolo_task_loop(data: RuntimeData, running: threading.Event) -> None:
    """YOLO 任务判定线程：识别结果直接定任务，直改 yolo_task

    识别到什么 ≈ 该执行什么任务，四类别：抓魔方 / 抓球 / 投放魔方（盆
    可投）/ 投放球（桶可投）；没识别出任务 → None。只被大循环落地链路
    消费（飞行状态不走 YOLO 链路，执行动作都在落地后做）。模型懒加载
    （首次推理自动 load_model），权重未就位时提示一次并保持空结果。
    """
    warn_shown = False
    while running.is_set():
        frame = data.current_frame
        cubes, balls, pan, bucket = [], [], None, None
        if frame is not None:
            try:
                cubes, balls, pan, bucket = detect(frame)
                warn_shown = False
            except Exception as e:
                if not warn_shown:
                    print(f"[flow] YOLO 推理不可用（{e}），任务判定暂停")
                    warn_shown = True

        if pan is not None and overlap_ok(pan.bbox, frame):
            data.yolo_task = TASK_DROP_CUBE           # 识别到盆（可投）→ 投放魔方
        elif bucket is not None and point_in_range(*bucket.center, frame):
            data.yolo_task = TASK_DROP_BALL           # 识别到桶（可投）→ 投放球
        elif cubes:
            data.yolo_task = TASK_GRAB_CUBE           # 识别到魔方 → 抓魔方
        elif balls:
            data.yolo_task = TASK_GRAB_BALL           # 识别到球 → 抓球
        else:
            data.yolo_task = None

        time.sleep(params.YOLO_TASK_INTERVAL)


def _camera_loop(camera, data: RuntimeData, running: threading.Event) -> None:
    """相机取帧线程：持续读帧刷新 RuntimeData（断线 connected=False，
    重连由 CameraManager 内部处理）"""
    while running.is_set():
        ok, frame = camera.read_frame()
        data.set_camera_connected(ok)
        if ok:
            data.set_frame(frame)
        time.sleep(params.FLOW_LOOP_INTERVAL)


# ── 大循环用的工具（提示 / 品类 / 坐标换算 / 发指令） ────────────────

def _notify(msg: str) -> None:
    """人工提示（框架用 print，接 GUI/日志时换实现）"""
    print(f"[flow][提示] {msg}")


def _current_category(data: RuntimeData) -> str:
    """本轮品类：N 从 0 计，偶→魔方、奇→球；掉落一次 = N+1 且奇偶映射
    翻转一次（翻转后偶→球、奇→魔方，下一轮仍抓同一品类，顺序不乱）；
    球尽后全抓魔方（魔方数满在主循环开头收尾，不会走到这）"""
    if data.ball_done >= params.BALL_DONE_MAX:
        return params.DETECT_CUBE_CLASS
    even = (data.N % 2 == 0)
    if data.parity_flip:
        even = not even
    return params.DETECT_CUBE_CLASS if even else params.DETECT_BALL_CLASS


def _pixel_to_plane(frame, center: tuple[int, int]) -> tuple[float, float] | None:
    """像素 → 现实平面坐标（common PixelToPlaneMapper，单应性标定文件）

    路径经 config.resolve_path 解析（配置里存的是项目相对路径）。
    """
    global _mapper, _mapper_failed
    if frame is None or _mapper_failed:
        return None
    if _mapper is None:
        try:
            _mapper = PixelToPlaneMapper(config.resolve_path(config.homography_file))
        except Exception as e:
            print(f"[flow] 坐标映射器初始化失败（{e}），抓取坐标无法换算")
            _mapper_failed = True
            return None
    _mapper.ensure_image_size(frame.shape[1], frame.shape[0])
    x, y = _mapper.pixel_to_plane(center[0], center[1])
    return None if x is None else (x, y)


def _send_grab_command(data: RuntimeData, plane) -> bool:
    """发抓取指令：目标现实坐标发给下位机

    TODO(电控)：X/Y/N/RX 在抓取动作里的语义（发什么值代表"到这个坐标
    抓取"、单发还是连发）——定稿后在这里组帧（走 flow 持有的 SerialComm.
    send_data，米→毫米换算参考 InteractionManager）。框架阶段只打印占位。
    """
    if plane is None:
        print("[flow] 坐标换算失败，未发抓取指令")
        return False
    print(f"[flow] 发抓取指令（占位）：plane=({plane[0]:.3f}, {plane[1]:.3f}) m")
    return True


def _send_drop_command(data: RuntimeData) -> bool:
    """发投放指令

    TODO(电控)：投放指令的协议语义（发什么值代表"投放"、单发还是连发）
    ——定稿后在这里组帧。框架阶段只打印占位。
    """
    print("[flow] 发投放指令（占位）")
    return True


# ── while 大循环（消费者/调度） ────────────────────────────────────

def _main_tick(data: RuntimeData) -> None:
    """大循环单轮：读状态量 → 三层 if 分发（接口处理只改状态与记账，
    动作在下一轮轮询里由新状态驱动）"""
    # 层1 auto_flight_state / 层2 auto_mech_state / yolo_task 均由
    # 监视线程直改，这里只读不判定

    # ── 完赛判定 ──
    if data.cube_done >= params.CUBE_DONE_MAX:
        _notify("任务完成（魔方已投满 15 个）")
        raise StopIteration

    category = _current_category(data)

    # ═══ 第一层 if：飞行状况 ═══
    if data.auto_flight_state == AUTO_FLYING:
        # 飞行段不走 YOLO 判定链路，抓取/投放执行都在落地后做
        if data.auto_mech_state == MECH_HOLD:
            if data.auto_grabbed is None:
                data.auto_grabbed = category   # 兜底补账（正常已在地面收口）
        elif data.auto_mech_state == MECH_PROCESS:
            # 飞行中掉落：N+1 且奇偶映射翻转一次 → 下一轮仍抓同一品类，
            # 连续掉落连续这样处理，后续抓取顺序与逻辑不受影响
            if data.auto_grabbed is not None and not data.process_handled:
                data.N += 1
                data.parity_flip = not data.parity_flip
                data.auto_grabbed = None       # 清标记（品类消耗不+1）
                data.task_memo = None
                data.process_handled = True    # 一次性处理，防每轮重发
                _notify("飞行中掉落，请重新飞回抓取")
        # MECH_IDLE：空爪飞行，等落地

    elif data.auto_flight_state == AUTO_LANDED:

        # ═══ 第二层 if：机构状况 ═══
        if data.auto_mech_state == MECH_IDLE:
            # 空爪落地 → 只做抓取的两个链路
            # ── 第三层 if：抓取任务进度（指令已发等验证）──
            if data.task_memo == MEMO_GRAB_SENT:
                if time.time() - data.task_memo_time > params.GRAB_VERIFY_TIMEOUT:
                    data.grab_fail_cnt += 1
                    data.task_memo = None      # 回 YOLO 重新选靶
                    if data.grab_fail_cnt >= params.GRAB_FAIL_MAX:
                        _notify("连续抓取失败，请重新起飞")
            # ── 第三层 if：YOLO 任务判定（识别线程直改）──
            elif data.yolo_task in (TASK_GRAB_CUBE, TASK_GRAB_BALL):
                frame = data.current_frame
                if frame is None:
                    _notify("无画面，等待")
                else:
                    cubes, balls, _, _ = detect(frame)
                    targets = (cubes if category == params.DETECT_CUBE_CLASS
                               else balls)
                    in_circle = filter_grabbable(targets, frame)
                    if in_circle:
                        # ── 第四层：既有评分 API 选靶 → 发指令记账 ──
                        if category == params.DETECT_CUBE_CLASS:
                            ranked = score_cubes(in_circle, frame, all_cubes=cubes)
                        else:
                            ranked = score_balls(in_circle, frame, all_cubes=cubes)
                        if ranked:
                            plane = _pixel_to_plane(frame, ranked[0].target.center)
                            if _send_grab_command(data, plane):
                                data.task_memo = MEMO_GRAB_SENT
                                data.task_memo_time = time.time()
                    else:
                        _notify("无本轮品类目标，请重新起飞")  # TODO 防重发
            # else：没识别出可抓任务 → 原地等

        elif data.auto_mech_state == MECH_HOLD:
            # 夹着东西：抓取成功收口 → 等起飞 → 投放链路
            # ── 第三层 if：抓取成功收口 = 爪里夹着但账上没记 ──
            # （auto_grabbed 只在收口写、投放完成清：夹着+没账 = 刚抓上；
            #   "等起飞 vs 找容器投放"不用记账区分——投放只认 yolo_task，
            #   没识别到可投容器就安静等）
            if data.auto_grabbed is None:
                data.auto_grabbed = category
                data.task_memo = None          # 清抓取验证记账
                data.grab_fail_cnt = 0
                _notify("抓取成功，请起飞转场")
            elif data.task_memo == MEMO_DROP_SENT:
                pass    # 等机构松开（落地 process 收尾）；TODO 投放超时提示
            elif data.yolo_task == (TASK_DROP_CUBE
                                    if data.auto_grabbed == params.DETECT_CUBE_CLASS
                                    else TASK_DROP_BALL):
                # 直接用 yolo_task：识别到对应容器（可投）→ 发投放指令
                if _send_drop_command(data):
                    data.task_memo = MEMO_DROP_SENT
                    data.task_memo_time = time.time()
            # else：没识别到可投容器 → 等（等起飞 / 投放点等识别）

        elif data.auto_mech_state == MECH_PROCESS:
            # 落地松开（主动投放 / 落地掉落）= 本轮投放完成：N+1、计消耗
            if data.auto_grabbed is not None and not data.process_handled:
                data.N += 1
                if data.auto_grabbed == params.DETECT_CUBE_CLASS:
                    data.cube_done += 1
                else:
                    data.ball_done += 1
                data.auto_grabbed = None
                data.task_memo = None
                data.process_handled = True    # 一次性处理，防重复记账
                _notify("投放完成，请飞回抓取区")


def _main_loop(data: RuntimeData, running: threading.Event) -> None:
    """大循环线程：轮询 _main_tick；单轮异常打印跳过，不拖垮流程"""
    while running.is_set():
        try:
            _main_tick(data)
        except StopIteration:
            break                    # 完赛：正常收尾
        except Exception as e:
            print(f"[flow] 大循环本轮异常（已跳过）：{e}")
        time.sleep(params.FLOW_LOOP_INTERVAL)


# ── 启停管理（模块级单例组，与 start_receiving / start_landing_monitor 同款） ──

_threads: list[threading.Thread] = []
_running = threading.Event()
_comm = None            # flow 打开的串口（接收；协议定稿后发送也走它）
_camera = None          # flow 自建的相机（退出时统一释放）
_mapper = None          # 像素→现实坐标映射器（懒加载）
_mapper_failed = False  # 映射器初始化失败标记（不再重试）


def start_flow(data: RuntimeData, with_camera: bool = False) -> None:
    """启动自动链路：全部监视线程 + while 大循环（重复调用无副作用）

    - STM32 接收：open_comm 按 config 开串口；下位机没接时提示并跳过，
      其余线程照常运行（接上后重启流程即可）
    - 接收机判飞行 / 机构监视 / YOLO 任务判定 / 大循环：始终启动
    - 相机取帧：with_camera=True 时由 flow 自建 CameraManager 启动
      （树莓派部署开，纯调试不开）
    """
    global _comm, _camera
    if _running.is_set():
        return
    _running.set()

    # 1. STM32 回传接收（串口打开失败容忍：接上下位机后重启流程）
    try:
        _comm = open_comm()
        start_receiving(_comm, data)
    except Exception as e:
        _comm = None
        print(f"[flow] 串口打开失败（{e}），接收线程未启动；接上下位机后重启流程")

    # 2. IMU 落地判定监视（层1 并列备选源：判定结果进 RuntimeData 备用）
    start_landing_monitor(data)

    # 3. 监视线程（层1 接收机 / 层2 机构 / YOLO 任务判定）
    for target, name in ((_receiver_flight_loop, "flow-receiver"),
                         (_mech_monitor_loop, "flow-mech"),
                         (_yolo_task_loop, "flow-yolo")):
        t = threading.Thread(target=target, args=(data, _running),
                             name=name, daemon=True)
        t.start()
        _threads.append(t)

    # 4. while 大循环
    t = threading.Thread(target=_main_loop, args=(data, _running),
                         name="flow-main", daemon=True)
    t.start()
    _threads.append(t)

    # 5. 相机取帧
    if with_camera:
        from common.hardware.camera import CameraManager
        _camera = CameraManager()
        t = threading.Thread(target=_camera_loop, args=(_camera, data, _running),
                             name="flow-camera", daemon=True)
        t.start()
        _threads.append(t)


def stop_flow() -> None:
    """停止 flow 全部线程并回收资源（与 start_flow 配对）"""
    global _threads, _comm, _camera
    _running.clear()
    for t in _threads:
        t.join(timeout=2)
    _threads = []
    stop_landing_monitor()
    stop_receiving()
    if _comm is not None:
        _comm.close()
        _comm = None
    if _camera is not None:
        _camera.release()
        _camera = None

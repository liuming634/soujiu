"""flow 主文件：自动链路总调度。

当前内容：持续线程装配层——flow 启动时初始化所有"必须时刻开着"的
线程，数据统一进 RuntimeData（启动权在 flow，auto/开发约束.md 约束 2）：

  1. STM32 回传接收（复用 auto/actuator：start_receiving）——0x02 机构
     状态帧 → actuator_queue + actuator_state 镜像，0x03 IMU 帧 →
     imu_queue + imu_state 镜像。存储方式已按之前定义好在 RuntimeData，
     这里只负责初始化线程，不新建存储单位。
  2. IMU 落地判定监视（复用 auto/landing：start_landing_monitor）——
     持续判定落地冲击写 RuntimeData.landing_imu_hit / landing_imu_hit_time，
     监视线程只判定、不切状态。
  3. 状态监视（flow 自有线程 _state_loop）——组合监视，管"飞行 /
     降落 / 做动作"三段推进 + 抓取机构舵机状况：
       舵机监视：每轮按抓取舵机角度判定当前夹着什么（judge_grabber）
               → 刷 RuntimeData.auto_grabber_status（'empty'/'ball'/
               'cube'/None）——"抓着东西飞 / 空着飞 / 飞行中掉落"等
               细化状况的判定材料
       状态推进：
       flying：新鲜度窗口内的落地冲击（landing 监视线程判好的结果）
               → 切 landed（消费触发，防同一次冲击重复切换）
       landed：按已抓物品标记（RuntimeData.auto_grabbed）路由
               → grab（未抓）/ drop（已抓）
     抓取/投放系列内部的状态回切（成功/完成 → flying）由流程逻辑做，
     不在这个线程。
  4. 相机取帧（flow 自有线程 _camera_loop）——CameraManager 持续读帧
     → RuntimeData.current_frame + camera_connected。自动链路的帧输入
     端（B5 拍板：直接用 common hardware 的图像数据接口，无新增存储）。

其他监视线程盘点（为什么现在没有）：
  - 舵机状态监视（G2 机构异常 / G3 脱落）：判定依据 = A3 三舵机角度
    判定工具（未移植），工具到位后按"状态机 + 线程监视"形态加
  - 接收机失联监视：硬件未接入（receiver_last_time 生产者空缺），
    接入后加读数线程
"""
import threading
import time

from common.core.runtime_data import (RuntimeData, AUTO_STATE_FLYING,
                                      AUTO_STATE_LANDED, AUTO_STATE_GRAB,
                                      AUTO_STATE_DROP)

from auto import params
from auto.actuator.grabber import judge_grabber
from auto.actuator.link import open_comm, start_receiving, stop_receiving
from auto.landing.monitor import start_landing_monitor, stop_landing_monitor


# ── flow 自有线程 ──────────────────────────────────────────────────

def _state_loop(data: RuntimeData, running: threading.Event) -> None:
    """状态监视线程：抓取机构舵机监视 + 状态位推进（组合监视）

    舵机监视：每轮按抓取舵机角度判定实时抓取状况，刷 RuntimeData.
    auto_grabber_status（'empty'/'ball'/'cube'/None）——流程逻辑据此
    判"抓着东西飞 / 空着飞 / 飞行中掉落（夹着→空爪）"等状况。
    状态推进：信号驱动的状态位修改（飞行中 → 降落 → 做动作）。
    """
    while running.is_set():
        # ── 抓取机构舵机监视（全程，范围参数在 auto/params.py） ──
        data.auto_grabber_status = judge_grabber(data.actuator_state)

        # ── 状态位推进 ──
        state = data.auto_state
        if state == AUTO_STATE_FLYING:
            # 落地信号：landing 监视线程已持续判定进 RuntimeData，这里只认
            # 新鲜度窗口内的冲击（超窗 = 起飞等旧冲击，下一次落地必有新冲击）
            hit_time = data.landing_imu_hit_time
            if hit_time is not None and \
                    (time.time() - hit_time) <= params.FLOW_IMU_HIT_FRESH:
                data.clear_landing_hit()      # 先消费触发，防重复切换
                data.set_auto_state(AUTO_STATE_LANDED)
        elif state == AUTO_STATE_LANDED:
            # 路由点：按已抓物品标记分流（标记由抓取成功后写入）
            if data.auto_grabbed is None:
                data.set_auto_state(AUTO_STATE_GRAB)
            else:
                data.set_auto_state(AUTO_STATE_DROP)
        time.sleep(params.FLOW_LOOP_INTERVAL)


def _camera_loop(camera, data: RuntimeData, running: threading.Event) -> None:
    """相机取帧线程：持续读帧刷新 RuntimeData（断线时 connected=False，
    重连由 CameraManager 内部处理）"""
    while running.is_set():
        ok, frame = camera.read_frame()
        data.set_camera_connected(ok)
        if ok:
            data.set_frame(frame)
        time.sleep(params.FLOW_LOOP_INTERVAL)


# ── 启停管理（模块级单例组，与 start_receiving / start_landing_monitor 同款） ──

_threads: list[threading.Thread] = []
_running = threading.Event()
_comm = None        # flow 打开的串口（退出时统一关闭）
_camera = None      # flow 自建的相机（退出时统一释放）


def start_flow_threads(data: RuntimeData, with_camera: bool = False) -> None:
    """启动自动链路的全部持续线程（重复调用无副作用）

    - STM32 接收：open_comm 按 config 开串口；下位机没接时提示并跳过，
      其余线程照常运行（接上后重启流程即可）
    - IMU 落地判定监视 + 状态监视：始终启动
    - 相机取帧：with_camera=True 时由 flow 自建 CameraManager 启动
      （树莓派部署开，纯调试不开）
    """
    global _comm, _camera
    if _running.is_set():
        return
    _running.set()

    # 1. STM32 回传接收（存储 = RuntimeData 已定义的两条队列 + 最新镜像）
    try:
        _comm = open_comm()
        start_receiving(_comm, data)
    except Exception as e:
        _comm = None
        print(f"[flow] 串口打开失败（{e}），接收线程未启动；接上下位机后重启流程")

    # 2. IMU 落地判定监视（判定结果进 RuntimeData，状态切换在 _state_loop）
    start_landing_monitor(data)

    # 3. 状态监视（舵机状况 + 状态位推进）
    t = threading.Thread(target=_state_loop, args=(data, _running),
                         name="flow-state", daemon=True)
    t.start()
    _threads.append(t)

    # 4. 相机取帧（帧输入端 → RuntimeData.current_frame）
    if with_camera:
        from common.hardware.camera import CameraManager
        _camera = CameraManager()
        t = threading.Thread(target=_camera_loop, args=(_camera, data, _running),
                             name="flow-camera", daemon=True)
        t.start()
        _threads.append(t)


def stop_flow_threads() -> None:
    """停止 flow 启动的全部持续线程并回收资源（与 start_flow_threads 配对）"""
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

"""auto/flow/伪代码.py —— flow 全量伪代码（.py 载体：按代码形状梳理逻辑）

不可运行、不参与导入。定稿后照此骨架翻译成正式代码：改英文名、搬进
对应模块、补 import 与实现体。标 ★ 的分支是按旧决议/理解填的占位，
等用户逐条修改拍板。

调度口径（2026-10-18 口述定稿）：FreeRTOS 式结构——监视线程持续监控、
直接修改 RuntimeData 状态量；一个 while 大循环只读状态量轮询分发，三层 if：
    层1 飞行状况（flying / landed）——飞行判定监视线程直改
        （主源 = 接收机，与 IMU / 图像光流判定并列，同形态换源）
  → 层2 机构状况（idle / hold / process）——机构监视线程直改
        （低频收样本入队列，收样当场判，抓/放角度差大可直接判脱落）
  → 层3 任务记账 / YOLO 任务判定（落地链路）——大循环分发处理
        （yolo_task 由 YOLO 任务判定线程直改：识别结果直接定任务，
        四类别 = 抓魔方 / 抓球 / 投放魔方 / 投放球；飞行状态不走 YOLO 链路）
每个接口处理只改状态与记账，动作在下一轮轮询里由新状态驱动。

用到的现有接口（定稿时 import，此处直接按名字调用）：
    judge_grabber(...)          # auto/actuator/grabber：瞬时角度→empty/cube/ball/None
    detect(frame)               # auto/detection/detector：一次推理四类
    filter_grabbable(...)       # auto/region/grab_range：ROI 中点在抓取圈内过滤
    overlap_ok / point_in_range # auto/region：盆重合面积 / 桶中点在圈
    score_cubes / score_balls   # auto/scoring/scorer：评分选靶排序
    common 坐标映射 + 串口协议   # 像素→现实坐标、发抓取/投放指令
"""
import time
from collections import deque

# from auto import params  # 定稿时补；下述 params.* 键随实现加进 auto/params.py

# ═══════════════ 状态值与 RuntimeData 新增字段草案 ═══════════════

FLYING, LANDED = 'flying', 'landed'                # 层1：飞行状况（一个变量）
IDLE, HOLD, PROCESS = 'idle', 'hold', 'process'    # 层2：机构状况（一个变量）

# RuntimeData 新增字段草案（状态修改 = 改变量值；定稿时声明）：
#   auto_flight_state ∈ {flying, landed}                  # 层1（接收机判定）
#   auto_mech_state  ∈ {idle, hold, process}              # 层2（长队列判定）
#   auto_grabbed     ∈ {None, 'cube', 'ball'}             # 已有：夹的是什么（记账位）
#   task_memo        ∈ {None, 'grab_sent', 'drop_sent'}   # 指令已发待验证
#   task_memo_time / grab_fail_cnt / process_handled
#   yolo_task        ∈ {None, 'grab_cube', 'grab_ball', 'drop_cube', 'drop_ball'}
#                   # YOLO 任务判定线程直改：识别结果直接定任务（落地链路消费）
#   receiver_last_time                            # ★仅当层1判定要失联超时缓冲才需要
#   N / cube_done / ball_done / parity_flip              # N 从0计：偶→魔方奇→球；
#                   # 掉落一次 = N+1 且 parity_flip 翻转一次（品类顺序不乱）


# ═══════════════ 线程装配（监视线程直接改状态量，start 时启动）═══════════════
# STM32 接收线程 / 相机取帧线程照旧（供数据）；
# 层1 主源 = 接收机判飞行线程；并列备选 = IMU / 图像光流（同形态换源）；
# 层2 = 机构监视线程；YOLO 任务判定线程 → yolo_task（只在落地链路消费）；
# IMU 落地监视线程去留★

def 接收机判飞行线程(data, running):
    """层1 飞行状况监视线程（主源 = 接收机）：直接修改 auto_flight_state

    接收到遥控器信号 = flying；没收到 = landed。
    与 IMU 判定、图像光流判定并列——三者同形态：监视线程持续判定、
    直接改这同一个状态量；换主源 = 换线程，大循环与字段不动。
    """
    while running.is_set():
        if 收到遥控器数据():                        # ★数据源待电控接入；
                                                    # 口径（要不要失联超时缓冲）待定
            data.auto_flight_state = FLYING         # 有信号 = 在飞行
        else:
            data.auto_flight_state = LANDED         # 没信号 = 已降落
        time.sleep(params.RECEIVER_POLL_INTERVAL)


def 机构监视线程(data, running):
    """层2 机构状况监视线程（随时监控）：收样本入队列 + 当场判定
    + 直接修改 auto_mech_state——收数、判定、改状态都在这一个线程里

    监视频率 params.MECH_SAMPLE_INTERVAL（★0.05~0.1s 收一个样本，及时响应）；
    抓取角度与放开角度差别大，收到样本时就能直接判出是否脱落；
    长队列的意义 = 存之前的数据，捕捉 抓着(hold) → 空了(idle) 的转变
    = process；老样本滑出队列后自然退回 idle（过程窗长 = 队列长）。
    """
    队列 = deque(maxlen=params.MECH_QUEUE_LEN)
    while running.is_set():
        样本 = judge_grabber(data.actuator_state)   # 'empty'/'cube'/'ball'/None
        队列.append(样本)

        # ── 判定（糅合在线程里）：当前样本 + 队列里的历史，直接改状态量 ──
        旧状态 = data.auto_mech_state
        if 样本 in ('cube', 'ball'):
            data.auto_mech_state = HOLD             # 收到夹着样本 → 抓取状态
        elif 样本 == 'empty':
            if any(s in ('cube', 'ball') for s in 队列):
                data.auto_mech_state = PROCESS      # 现在空了、之前夹着 → 脱落/松开
            else:
                data.auto_mech_state = IDLE         # 一直空爪 → 静止常态
        # ★运动中样本(None)：正在动，维持原状态不动（要不要防抖待定）

        if 旧状态 == PROCESS and data.auto_mech_state != PROCESS:
            data.process_handled = False            # 离开过程态 → 一次性事件标记复位

        time.sleep(params.MECH_SAMPLE_INTERVAL)     # ★0.05~0.1s 收一个


def YOLO任务判定线程(data, running):
    """YOLO 识别 → 任务判定线程：识别结果直接定任务，直改 RuntimeData.yolo_task

    任务四类别：抓魔方 / 抓球 / 投放魔方（识别到盆）/ 投放球（识别到桶）；
    没识别出任务 → None。识别到什么 ≈ 该执行什么任务。
    消费端：只在大循环的落地链路里用——飞行状态不走 YOLO 判定链路，
    抓取/投放的执行动作都在落地后才做。
    ★判定口径与层级（要不要只在落地时跑推理）——看完再定
    """
    while running.is_set():
        frame = data.current_frame
        if frame is None:
            data.yolo_task = None
        else:
            cubes, balls, pans, buckets = detect(frame)
            # 识别结果 → 四类任务（盆可投=重合面积达标 / 桶可投=中点在圈内）
            if pans and 盆可投(pans, frame):
                data.yolo_task = 'drop_cube'        # 识别到盆（可投）→ 投放魔方
            elif buckets and 桶可投(buckets, frame):
                data.yolo_task = 'drop_ball'        # 识别到桶（可投）→ 投放球
            elif cubes:
                data.yolo_task = 'grab_cube'        # 识别到魔方 → 抓魔方
            elif balls:
                data.yolo_task = 'grab_ball'        # 识别到球 → 抓球
            else:
                data.yolo_task = None
        time.sleep(params.YOLO_TASK_INTERVAL)


# ═══════════════ while 大循环（消费者/调度）═══════════════
# 定稿落点：flow/main.py（_state_loop 重写为此循环；线程装配同文件组装）



# 处理前提（口述）：以下处理基于正常比赛流程——飞手按规则来回飞行，
# 复飞也在规则范围内，同样满足本处理。
def 大循环(data, running):
    """主循环：读监视线程直改好的状态量 → 三层 if 分发 → sleep 轮询间隔"""
    while running.is_set():
        # 层1 auto_flight_state / 层2 auto_mech_state 均由监视线程直接修改
        # （见线程装配：接收机判飞行线程 / 机构监视线程），大循环只读不判定

        # ═══ 完赛判定 ═══
        if data.cube_done >= 15:                    # ★魔方15 → 进 params
            提示人工("任务完成")                     # ★G1 收尾形态：提示后停循环?
            break

        品类 = 本轮品类(data)

        # ═════════ 第一层 if：飞行状况 ═════════
        if data.auto_flight_state == FLYING:

            # ─────── 第二层 if：机构状况 ───────
            #（这里实际上落地之后的所有的对应的反应那些处理的行为都直接基于yolo的识别的结果来做就可以了
            # ，所以我打算要不再做一个线程来做yolo的识别，但是实际上
            #是没有意义的因为我们是落地之后只需要yolo识别那些的而已剩下的时间用似乎不是很合适，不过也不冲突
            #直接用多个条件判定就可以了，毕竟我们可以叠加if判断的层级，所以现在我的打算就是再飞行的时候不走yolo的识别结果的判定，
            #也就是在飞行状态的时候yolo识别的结果链路不在飞行的状态里面写只在落地状态里面写
            #所以现在继续套一层yolo的识别结果的判定就可以了，这个在我的这个实现里面做成另一个线程然后修改状态就可以了，我们这里实际上yolo识别的
            #返回的任务是四个类别抓球抓魔方投放魔方投放球这几个，这个做第三层的判定就可以了或者是第四层吧我后面看完了决定怎么做，这个也是再runtimedata
            #里面做一个数据来修改它就可以了）
            if data.auto_mech_state == IDLE:
                # 情况1 空爪飞行：飞行段不走 YOLO 判定链路；抓取执行落地后才做
                #（识别到抓球/抓魔方 → 执行链路：识别坐标→发指令，写在 landed+idle）
                pass

            elif data.auto_mech_state == HOLD:
                # 情况2 抓着转场：无动作等落地（投放链路只在落地后走）
                if data.auto_grabbed is None:
                    data.auto_grabbed = 品类   # 兜底补账（正常已在地面收口）

            elif data.auto_mech_state == PROCESS:
                # 情况3 飞行中掉落（空中 抓着→空）
                # 口述规则：N 从 0 计，偶→魔方、奇→球；掉落 = N+1 且奇偶映射
                # 翻转一次（翻转后偶→球、奇→魔方）→ 下一轮仍抓同一品类；
                # 连续掉落就连续这样处理，后续抓取顺序与逻辑不受影响
                if data.auto_grabbed is not None and not data.process_handled:
                    data.N += 1
                    data.parity_flip = not data.parity_flip
                    data.auto_grabbed = None        # 清标记（品类消耗不+1）
                    data.task_memo = None
                    data.process_handled = True     # 一次性处理，防每轮重发
                    提示人工("飞行中掉落，重新飞回抓取")

        elif data.auto_flight_state == LANDED:

            # ─────── 第二层 if：机构状况 ───────
            if data.auto_mech_state == IDLE:
                # 空爪落地 → 只做抓取的两个链路；直接用 yolo_task（识别线程
                # 直改）做任务判定，识别坐标后用对应函数发数据

                # ─── 第三层 if：抓取任务进度记账（判定是否抓取成功）───
                if data.task_memo == 'grab_sent':
                    # 抓取指令已发 → 等验证（机构一夹住翻到 hold，在 hold 侧收口）
                    if time.time() - data.task_memo_time > params.GRAB_VERIFY_TIMEOUT:
                        data.grab_fail_cnt += 1
                        data.task_memo = None       # 回 YOLO 重新选靶
                        if data.grab_fail_cnt >= 3:            # ★3 次上限（旧决议）
                            提示人工("连续抓取失败，重新飞")    # N 不变
                            # ★失败计数何时清零（重新落地时?）待定

                # ─── 第三层 if：YOLO 任务判定（yolo_task 识别线程直改）───
                elif data.yolo_task in ('grab_cube', 'grab_ball'):
                    # ─── 第四层：N 定奇偶 → 本轮品类 → 既有判定/评分 API ───
                    # 用 N 算奇偶定抓什么目标，再做目标选择：既有判定方法 +
                    # 评分流程算抓哪一个（和之前写的一样，直接调用那些 API）
                    frame = data.current_frame
                    if frame is None:
                        提示人工("无画面，等待")            # ★相机断线只提示?
                    else:
                        cubes, balls, pans, buckets = detect(frame)
                        本轮目标 = cubes if 品类 == 'cube' else balls
                        圈内 = filter_grabbable(本轮目标, frame)
                        if 圈内:
                            # 情况4a 可抓 → 评分选靶 → 发指令（记账，下一轮验证）
                            if 品类 == 'cube':
                                排序 = score_cubes(圈内, frame, cubes)  # 密集含圈外
                            else:
                                排序 = score_balls(圈内, frame, balls)
                            靶 = 排序[0]                        # ScoredTarget，并列编号小在前
                            发抓取指令(像素转现实坐标(靶.中点))
                            data.task_memo = 'grab_sent'
                            data.task_memo_time = time.time()
                        else:
                            # 情况4b 不可抓（识别到的任务与 N 品类对不上也落到这）
                            提示人工("无本轮品类目标，重新飞")   # ★防重发待定
                # else：没识别出可抓任务 → 原地等（★要不要提示重飞，与防重发一起定）

            elif data.auto_mech_state == HOLD:
                # ─── 第三层 if：抓取成功收口 → 投放链路 ───
                # 收口判据 = 爪里夹着但账上没记（auto_grabbed 只在收口写、
                # 投放完成清）：夹着+没账 = 刚抓上的，写账即抓取成功；
                # "等起飞 vs 找容器投放"不用记账区分——投放只认 yolo_task，
                # 没识别到可投容器就安静等（等起飞 / 投放点等识别）
                if data.auto_grabbed is None:
                    data.auto_grabbed = 品类            # 写账 = 抓取成功收口
                    data.task_memo = None               # 清抓取验证记账
                    data.grab_fail_cnt = 0
                    提示人工("抓取成功，请起飞转场")
                elif data.task_memo == 'drop_sent':
                    pass    # 等机构松开（层2→process 由情况6收尾）；★超时提示待定
                elif data.yolo_task == ('drop_cube' if data.auto_grabbed == 'cube'
                                        else 'drop_ball'):
                    # 直接用 yolo_task：识别到对应容器（可投）→ 投放到对应位置
                    发投放指令()
                    data.task_memo = 'drop_sent'
                    data.task_memo_time = time.time()
                # else：没识别到可投容器 → 等

            elif data.auto_mech_state == PROCESS:
                # 情况6 落地松开中（主动投放松开 / 落地自发掉落 都到这）
                # 叠加投放完成判定：落地时 抓着→空 = 投放完成（★旧决议：都算完成）
                if data.auto_grabbed is not None and not data.process_handled:
                    data.N += 1
                    if data.auto_grabbed == 'cube':
                        data.cube_done += 1
                    else:
                        data.ball_done += 1
                    data.auto_grabbed = None
                    data.task_memo = None
                    data.process_handled = True     # 一次性处理，防重复记账
                    提示人工("投放完成，飞回抓取区")

        time.sleep(params.FLOW_LOOP_INTERVAL)


def 本轮品类(data):
    """★N 规则（口述更新）：N 从 0 计，偶→魔方、奇→球；掉落一次 = N+1 且
    奇偶映射翻转一次（翻转后偶→球、奇→魔方，下一轮仍抓同一品类，顺序不乱）；
    球尽（ball_done≥6）后全抓魔方；魔方 15 完赛。★阈值进 params
    """
    if data.cube_done >= 15:                        # ★进 params
        return 'done'
    if data.ball_done >= 6:                         # ★进 params
        return 'cube'
    偶数轮 = (data.N % 2 == 0)
    if data.parity_flip:
        偶数轮 = not 偶数轮                         # 掉落翻转位：翻转后偶→球、奇→魔方
    return 'cube' if 偶数轮 else 'ball'


# ═══════════════ 伪代码占位函数（定稿时换真实实现）═══════════════

def 提示人工(msg):
    """日志 / GUI 提示（具体通道待定）"""
    ...


def 收到遥控器数据():
    """★接收机数据源待电控接入；口径待定：链路在线 or 通道值有变化"""
    ...


def 发抓取指令(现实坐标):
    """common 串口协议（X/Y/N/RX 语义待电控确认）"""
    ...


def 发投放指令():
    """common 串口协议（单发/连发待电控确认）"""
    ...


def 像素转现实坐标(中点):
    """common PixelToPlaneMapper（单应性标定文件）"""
    ...


def 盆可投(盆列表, frame):
    """盆 ROI 与抓取圈重合面积 ≥ 阈值——region.overlap_ok"""
    ...


def 桶可投(桶列表, frame):
    """桶 ROI 中点在抓取圈内——region.point_in_range"""
    ...


# ═══════════════ ★ 待拍板清单（对应文内 ★ 标记）═══════════════
#  1. 机构监视：None(运动中)样本维持原状态对不对；process 窗长=队列长
#     （老样本滑出自然退回 idle）行不行；单样本直判要不要加防抖
#  2. 接收机口径：有信号=飞行/没信号=落地（已按直改状态写）；要不要
#     失联超时缓冲（防瞬间丢包误判落地）
#  3. YOLO 任务判定线程：四类同时识别到时的优先级、抓取类要不要要求
#     目标在抓取圈内、要不要只在落地时跑推理
#  4. 落地+idle：yolo_task 是抓取任务就进链路、链路内按 N 品类选靶——
#     识别到的任务与 N 品类对不上时自然走"无目标"提示，口径行不行
#  5. 情况4b/5b 提示防重发（每轮提示 or 提示一次挂标记）
#  6. GRAB_VERIFY_TIMEOUT 与 3 次失败上限；失败计数清零时机
#  7. drop_sent 要不要独立超时（DROP_VERIFY_TIMEOUT）
#  8. 情况6 守卫：auto_grabbed 非空才记账（防空爪误判）——确认
#  9. process_handled 复位：监视线程里"离开过程态即复位"行不行
# 10. 完赛形态（提示后 break？）
# 11. IMU 监视线程去留（并列备选保留 or 停用）
#
# 参数挂账（auto/params.py）：MECH_QUEUE_LEN（队列长=过程窗长）/
# MECH_SAMPLE_INTERVAL（★0.05~0.1s）/ RECEIVER_POLL_INTERVAL /
# YOLO_TASK_INTERVAL / GRAB_VERIFY_TIMEOUT / （如需）DROP_VERIFY_TIMEOUT；
# 已有 FLOW_LOOP_INTERVAL；RECEIVER_LOST_TIMEOUT（仅当层1要超时缓冲）

"""
运行时数据中心 - 统一管理所有内存态数据

设计原则：
  1. 所有运行时数据集中于此，不分散在各模块
  2. "刷新"模式：标量直接覆盖，列表有界截断
  3. 防内存泄漏：列表数据有最大长度限制
  4. 不涉及文件持久化（配置持久化在 config.py）

使用方式：
  data = RuntimeData()           # 全局唯一实例
  data.set_frame(frame)          # 刷新写入
  data.reset_all()               # 全部重置
"""
import time
from collections import deque

# 自动链路接收队列长度（接收线程入队、处理端消费；满了丢最旧、保留最新）
# 机构状态：回传约 50~100Hz，16 帧 ≈ 0.2~0.3s，够判稳做帧间比较
ACTUATOR_QUEUE_SIZE = 16
# IMU：落地判定需要 ≥200Hz 连续采样，128 帧 ≈ 0.6s@200Hz，覆盖 0.5s 确认窗
IMU_QUEUE_SIZE = 128
# 识别结果队列：每项 = 一帧推理的该品类目标列表（调用方按帧放入，防抖/评分取用）
DETECT_QUEUE_SIZE = 16

# ── 自动链路状态位（四态，检测到对应信号后切换，下游链路按状态启动） ──
AUTO_STATE_FLYING = "flying"   # 飞行中：等待落地信号（landing 监视中）
AUTO_STATE_LANDED = "landed"   # 已着陆：落地判定通过，抓取链路待启动
AUTO_STATE_GRAB = "grab"       # 抓取态：正在执行抓取
AUTO_STATE_DROP = "drop"       # 投放态：正在执行投放
AUTO_STATES = (AUTO_STATE_FLYING, AUTO_STATE_LANDED,
               AUTO_STATE_GRAB, AUTO_STATE_DROP)


class RuntimeData:
    """统一运行时数据管理"""

    def __init__(self):
        # ============================================================
        # 帧数据（每帧刷新覆盖）
        # ============================================================
        self.current_frame = None

        # ============================================================
        # 设备状态（每帧刷新）
        # ============================================================
        self.camera_connected: bool = False

        # ============================================================
        # 交互状态（刷新覆盖，无累积）
        # ============================================================
        self.last_click_pos: tuple[float, float] | None = None
        self.last_plane_coords: tuple[float, float] = (0.0, 0.0)
        self.rotated_plane_coords: tuple[float, float] = (0.0, 0.0)
        self.key_number: int | None = None

        # 右键坐标（供 GUI 显示）
        self.right_click_coords: tuple[float, float] = (0.0, 0.0)

        # 最近一次协议发送数据（供 GUI 显示）
        self.last_sent_proto: tuple[int, int, int, int] | None = None  # (x, y, n, rx)

        # 待发送数据缓存（打包后按空格确认发送）
        self.pending_proto: tuple[int, int, int, int] | None = None  # (x, y, n, rx)

        # ============================================================
        # 自动链路：下位机回传数据（接收线程持续写入，处理端从队列取）
        # 时间戳打在数据对象自己的 time 字段里（接收线程入队前打）
        # ============================================================
        self.actuator_state = None             # ActuatorState 最新一帧镜像（auto/actuator/state.py）
        self.imu_state = None                  # ImuData 最新一帧镜像（auto/actuator/state.py）
        self.actuator_queue = deque(maxlen=ACTUATOR_QUEUE_SIZE)  # 机构状态队列
        self.imu_queue = deque(maxlen=IMU_QUEUE_SIZE)            # IMU 队列

        # 识别结果队列（detection 的 detect() 结果由调用方按帧放入，非接收线程写）
        self.cube_queue = deque(maxlen=DETECT_QUEUE_SIZE)   # 每项 = 一帧的魔方目标列表
        self.ball_queue = deque(maxlen=DETECT_QUEUE_SIZE)   # 每项 = 一帧的球目标列表

        # ============================================================
        # 自动链路状态位（检测到对应信号后切换；下游链路按状态启动）
        # ============================================================
        self.auto_state: str = AUTO_STATE_FLYING   # 当前状态（set_auto_state 切换）

        # ============================================================
        # 落地判定结果（landing 监视线程 / 调用方刷新，flow 确认窗取用）
        # ============================================================
        self.landing_imu_hit: bool = False                  # 最近一次 IMU 跳变判定（监视线程持续刷新）
        self.landing_imu_hit_time: float | None = None      # 最近一次判定命中的时刻（帧时间戳）
        self.landing_frame_still: bool | None = None        # 最近一次光流画面静止判定（调用方按帧喂图后回写）
        self.receiver_last_time: float | None = None        # 接收机最近一次收到遥控器信号的时刻（读数接入后刷新）

    # ──────────────────────── 帧数据 ────────────────────────

    def set_frame(self, frame):
        """刷新当前帧（替换旧引用，无累积）"""
        self.current_frame = frame

    def set_camera_connected(self, connected: bool):
        """刷新相机连接状态"""
        self.camera_connected = connected

    # ──────────────────────── 交互状态 ────────────────────────

    def set_last_click(self, x: float, y: float,
                       plane_x: float, plane_y: float):
        """刷新点击位置和映射坐标"""
        self.last_click_pos = (x, y)
        self.last_plane_coords = (plane_x, plane_y)

    def set_rotated_coords(self, x: float, y: float):
        """存储左键点击的参考点世界坐标"""
        self.rotated_plane_coords = (x, y)

    def set_key(self, n: int | None):
        """刷新按键号"""
        self.key_number = n

    # ──────────────────────── 右键坐标（供 GUI 显示） ────────────────────────

    def set_right_click_coords(self, raw_x: float, raw_y: float):
        """存储右键点击的原始坐标"""
        self.right_click_coords = (raw_x, raw_y)

    def set_last_sent_proto(self, x: int, y: int, n: int, rx: int):
        """记录最近一次发送的协议数据"""
        self.last_sent_proto = (x, y, n, rx)

    def set_pending_proto(self, x: int, y: int, n: int, rx: int):
        """缓存待发送的协议数据"""
        self.pending_proto = (x, y, n, rx)

    def clear_pending_proto(self):
        """清除待发送数据缓存"""
        self.pending_proto = None

    # ──────────────────────── 自动链路：下位机回传数据 ────────────────────────

    def set_actuator_state(self, state):
        """刷新执行机构状态最新一帧镜像（时间戳在数据对象的 time 字段里）"""
        self.actuator_state = state

    def set_imu_state(self, state):
        """刷新 IMU 数据最新一帧镜像（时间戳在数据对象的 time 字段里）"""
        self.imu_state = state

    # ──────────────────────── 自动链路状态位 ────────────────────────

    def set_auto_state(self, state: str):
        """切换自动链路状态位（非法状态抛 ValueError）

        约定：landing 监视检测到落地信号 → 切 landed（接线逻辑后面
        在 flow 写）；抓取/投放态的切换由 flow 编排。状态切了，下游
        链路才按状态启动。
        """
        if state not in AUTO_STATES:
            raise ValueError(f"未知自动链路状态: {state!r}，可选: {list(AUTO_STATES)}")
        self.auto_state = state

    # ──────────────────────── 落地判定结果 ────────────────────────

    def set_landing_imu(self, hit: bool, hit_time: float | None = None):
        """刷新 IMU 跳变判定结果（landing 监视线程写；未命中不覆盖命中时刻）"""
        self.landing_imu_hit = hit
        if hit and hit_time is not None:
            self.landing_imu_hit_time = hit_time

    def set_landing_frame_still(self, still: bool | None):
        """刷新光流画面静止判定结果（调用方按帧喂图判定后写）"""
        self.landing_frame_still = still

    def set_receiver_signal(self, ts: float):
        """刷新接收机最近信号时刻（接收机读数接入后由其线程写）"""
        self.receiver_last_time = ts

    # ──────────────────────── 全局重置 ────────────────────────

    def reset_all(self):
        """重置所有运行时数据"""
        self.current_frame = None
        self.camera_connected = False
        self.last_click_pos = None
        self.last_plane_coords = (0.0, 0.0)
        self.rotated_plane_coords = (0.0, 0.0)
        self.key_number = None

        self.right_click_coords = (0.0, 0.0)

        self.last_sent_proto = None
        self.pending_proto = None

        self.actuator_state = None
        self.imu_state = None
        self.actuator_queue.clear()
        self.imu_queue.clear()
        self.cube_queue.clear()
        self.ball_queue.clear()

        self.landing_imu_hit = False
        self.landing_imu_hit_time = None
        self.landing_frame_still = None
        self.receiver_last_time = None
        self.auto_state = AUTO_STATE_FLYING

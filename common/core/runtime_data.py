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
        # 自动链路：下位机执行机构状态（实时覆盖，无缓存）
        # ============================================================
        self.actuator_state = None             # ActuatorState（auto/actuator/state.py）
        self.actuator_state_time: float = 0.0  # 最近一帧入库时间戳（入库时打）

        # ============================================================
        # 自动链路：识别结果（每次抓取行为前刷新覆盖）
        # ============================================================
        self.cube_list: list = []         # 识别到的魔方（DetectedObject，按ROI中点x从左到右编号从1开始）
        self.ball_list: list = []         # 识别到的球（编号规则同上，与魔方分开编号）
        self.detection_time: float = 0.0  # 最近一次识别入库时间戳（入库时打）

        # ============================================================
        # 自动链路：投放桶识别结果（球投放用，识别一次刷新一次）
        # ============================================================
        self.bucket_list: list = []    # 识别到的投放桶（BucketObject：bbox/center）
        self.bucket_time: float = 0.0  # 最近一次桶识别入库时间戳（入库时打）

        # ============================================================
        # 自动链路：抓取范围过滤结果（评分的待抓取对象）
        # ============================================================
        self.grabbable_cube_list: list = []  # 范围内魔方（识别列表保留全部结果，这里只存可抓取的）
        self.grabbable_ball_list: list = []  # 范围内球
        self.grabbable_time: float = 0.0     # 最近一次过滤入库时间戳（入库时打）

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

    # ──────────────────────── 自动链路：下位机执行机构状态 ────────────────────────

    def set_actuator_state(self, state):
        """刷新下位机执行机构状态（五项一帧整体覆盖；存入时统一打时间戳）"""
        self.actuator_state = state
        self.actuator_state_time = time.time()

    # ──────────────────────── 自动链路：识别结果 ────────────────────────

    def set_detections(self, cube_list: list, ball_list: list):
        """刷新识别结果（魔方/球两个列表整体覆盖；存入时统一打时间戳）"""
        self.cube_list = cube_list
        self.ball_list = ball_list
        self.detection_time = time.time()

    def set_buckets(self, bucket_list: list):
        """刷新投放桶识别结果（整体覆盖；存入时统一打时间戳）"""
        self.bucket_list = bucket_list
        self.bucket_time = time.time()

    def set_grabbable(self, cube_list: list, ball_list: list):
        """刷新抓取范围过滤结果（两份列表整体覆盖；存入时统一打时间戳）"""
        self.grabbable_cube_list = cube_list
        self.grabbable_ball_list = ball_list
        self.grabbable_time = time.time()

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
        self.actuator_state_time = 0.0

        self.cube_list = []
        self.ball_list = []
        self.detection_time = 0.0

        self.bucket_list = []
        self.bucket_time = 0.0

        self.grabbable_cube_list = []
        self.grabbable_ball_list = []
        self.grabbable_time = 0.0

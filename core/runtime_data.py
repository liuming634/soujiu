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

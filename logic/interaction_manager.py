"""
交互管理器 - 合并事件处理、数据存储、坐标映射

数据统一由 RuntimeData 管理，本模块只聚焦业务逻辑。
"""
from dataclasses import dataclass
from typing import Optional

from core.config import config
from core.utils import log_error
from hardware.serial_protocol import SerialComm
from logic.coordinate_mapper import PixelToPlaneMapper
from core.runtime_data import RuntimeData

import sys
_WARN_COLOR = "\033[93m" if not sys.platform.startswith("win") else ""
_WARN_RESET = "\033[0m" if not sys.platform.startswith("win") else ""


@dataclass
class InteractionState:
    """一次性返回给 UI 的所有交互状态（从 RuntimeData 读取）"""
    plane_coords: tuple[float, float] = (0.0, 0.0)
    right_click_coords: tuple[float, float] = (0.0, 0.0)
    key_number: Optional[int] = None
    last_sent_text: str = "发送: --"
    comm_status: str = "串口: --"
    last_click_pos: Optional[tuple[float, float]] = None
    camera_connected: bool = False


class InteractionManager:
    """交互管理器

    合并了三个旧模块的职责：
    - 鼠标/键盘事件处理
    - 像素→平面坐标映射（持有 mapper 实例）
    - 串口发送（持有 comm 实例）

    数据统一由 RuntimeData 管理，不从本类直接持有。
    """

    def __init__(self, data: RuntimeData,
                 mapper: Optional[PixelToPlaneMapper],
                 comm: Optional[SerialComm]):
        """
        Args:
            data: 运行时数据中心（外部创建，注入使用）
            mapper: 坐标映射器（可为 None，映射不可用）
            comm: 串口通信器（可为 None，串口不可用）
        """
        self.data = data
        self.mapper = mapper
        self.comm = comm
        self._flash_warning: str | None = None

    # ─────── 帧数据输入 ───────

    def update_frame(self, frame):
        """刷新帧缓存（委托 RuntimeData）"""
        self.data.set_frame(frame)

    # ─────── 鼠标点击处理 ───────

    def handle_click(self, button: str, x: float, y: float):
        """统一处理左/右/中键点击"""
        label = '左' if button == 'left' else ('右' if button == 'right' else '中')
        print(f"🖱️  鼠标{label}键点击位置: ({x:.2f}, {y:.2f})")

        # 检查标定状态
        if self.mapper is None:
            warn = "标定未就绪，请先标定映射"
            print(f"  {_WARN_COLOR}[WARNING] {warn}{_WARN_RESET}")
            self._flash_warning = warn
            return

        # 坐标映射
        x_plane, y_plane = self._map_coords(x, y)

        # 左键：设参考点
        if button == 'left':
            self.data.set_last_click(x, y, x_plane or 0.0, y_plane or 0.0)
            if x_plane is not None:
                self.data.set_rotated_coords(x_plane, y_plane)
                print(f"   📍 左键: X={x_plane:.4f}m, Y={y_plane:.4f}m")

        # 右键：存储坐标供 GUI 显示
        elif button == 'right':
            if x_plane is not None:
                self.data.set_right_click_coords(x_plane, y_plane)
                print(f"   📍 右键坐标: X={x_plane:.4f}m, Y={y_plane:.4f}m")

    def _map_coords(self, x: float, y: float) -> tuple:
        """像素→平面坐标映射"""
        if self.mapper is None:
            return None, None
        try:
            x_plane, y_plane = self.mapper.pixel_to_plane(x, y)
            if x_plane is not None:
                print(f"   映射坐标: X={x_plane:.4f}m, Y={y_plane:.4f}m")
            else:
                print("[WARNING] 坐标映射失败")
            return x_plane, y_plane
        except Exception as e:
            log_error(e, "坐标映射失败")
            return None, None

    # ─────── 键盘事件处理 ───────

    def handle_key(self, n: int):
        """数字键处理：打包数据（不发送，需按空格确认）"""
        if self.mapper is None:
            msg = "标定未就绪，无法打包数据"
            print(f"  {_WARN_COLOR}[WARNING] {msg}{_WARN_RESET}")
            self._flash_warning = msg
            return
        if not (0 <= n <= 9):
            print(f"[WARNING] 无效的数字键: {n}")
            return
        print(f"🔢 按下数字键 {n}")

        x_world, y_world = self.data.rotated_plane_coords
        print(f"   📌 参考点世界坐标: X={x_world:.4f}m, Y={y_world:.4f}m")

        # 计算协议值：映射坐标(米) → 毫米，偏差修正(mm)直接叠加在发送数据上
        scale, offset = config.coordinate_scale, config.coordinate_offset
        x_proto = int(round(x_world * scale + offset + config.coord_offset_x_mm))
        y_proto = int(round(y_world * scale + offset + config.coord_offset_y_mm))
        x_proto = max(0, min(config.protocol_max_value, x_proto))
        y_proto = max(0, min(config.protocol_max_value, y_proto))

        # 右键 X 协议值（同X编码方式，同样叠加 X 偏差）
        rx, _ = self.data.right_click_coords
        rx_proto = int(round(rx * scale + offset + config.coord_offset_x_mm))
        rx_proto = max(0, min(config.protocol_max_value, rx_proto))

        # 缓存待发送数据（不立即发送）
        self.data.set_pending_proto(x_proto, y_proto, n, rx_proto)
        print(f"   已打包: X={x_proto}, Y={y_proto}, N={n} (按空格发送)")

    def confirm_send(self):
        """空格键确认：发送缓存的待发送数据"""
        pending = self.data.pending_proto
        if pending is None:
            msg = "没有待发数据，请先按数字键打包"
            print(f"  {_WARN_COLOR}[WARNING] {msg}{_WARN_RESET}")
            self._flash_warning = msg
            return
        x_proto, y_proto, n, rx_proto = pending

        self.data.set_last_sent_proto(x_proto, y_proto, n, rx_proto)
        self.data.clear_pending_proto()

        if self.comm:
            self.comm.send_data(x_proto, y_proto, n, rx_proto)
            print(f"   串口发送: X={x_proto}, Y={y_proto}, N={n}, 右键X={rx_proto}")
        else:
            print(f"   [串口不可用] 协议数据: X={x_proto}, Y={y_proto}, N={n}, 右键X={rx_proto}")

    # ─────── 状态输出（从 RuntimeData 读取） ───────

    def get_state(self) -> InteractionState:
        """一次性拉取所有显示状态"""
        d = self.data
        sent_text = self._build_sent_text()
        fw = self._flash_warning
        self._flash_warning = None
        return InteractionState(
            plane_coords=d.last_plane_coords,
            right_click_coords=d.right_click_coords,
            key_number=d.key_number,
            last_sent_text=f"{sent_text}\n⚠ {fw}" if fw else sent_text,
            comm_status=self._build_comm_status(),
            last_click_pos=d.last_click_pos,
            camera_connected=d.camera_connected,
        )

    def _build_comm_status(self) -> str:
        if self.comm is None:
            return "串口: ✗"
        try:
            return "串口: ✓" if self.comm.is_connected() else "串口: ✗ 已断开"
        except Exception:
            return "串口: ✗"

    def _build_sent_text(self) -> str:
        d = self.data
        if d.pending_proto is not None:
            x, y, n, rx = d.pending_proto
            pending = f"待发: X={x} Y={y} 右键X={rx} N={n}"
        else:
            pending = "待发: --"
        if d.last_sent_proto is not None:
            x, y, n, rx = d.last_sent_proto
            sent = f"已发: X={x} Y={y} 右键X={rx} N={n}"
        else:
            sent = "已发: --"
        return f"{pending}\n{sent}"

    # ─────── 数据操作（委托 RuntimeData） ───────

    def reset(self):
        """重置所有运行时数据（保留 mapper 和 comm 引用）"""
        self.data.reset_all()

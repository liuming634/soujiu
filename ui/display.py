"""
GUI 显示模块 - PyQt5 视频显示界面
"""
import time
import re
import cv2
from PyQt5.QtWidgets import (QWidget, QLabel, QVBoxLayout,
                             QHBoxLayout, QPushButton, QGridLayout,
                             QSizePolicy, QDialog, QSlider, QCheckBox,
                             QDoubleSpinBox)
from PyQt5.QtCore import Qt, QRect, QPoint, QTimer
from PyQt5.QtGui import QImage, QPixmap, QFont, QIcon, QPainter, QPen, QColor
from core.config import config
from core.utils import log_error, px_to_ratio
from logic.interaction_manager import InteractionState

# QuickPopup 自动关闭延迟（毫秒）
_POPUP_AUTO_CLOSE_MS = 750


class QuickPopup(QDialog):
    """无边框自动关闭提示窗 — 居中显示"""
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setStyleSheet("background-color: #222; border: 2px solid #ff6666; border-radius: 6px;")
        label = QLabel(f"⚠ {text}")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: #ff6666; font-size: 16px; font-weight: bold; padding: 12px 24px;")
        layout = QVBoxLayout()
        layout.addWidget(label)
        self.setLayout(layout)
        self.adjustSize()
        # 居中于父窗口
        if parent:
            cp = parent.geometry().center()
            self.move(cp.x() - self.width() // 2, cp.y() - self.height() // 2)
        self.show()
        QTimer.singleShot(_POPUP_AUTO_CLOSE_MS, self.close)


class FieldDiagram(QWidget):
    """倒U路径路线图 — 静态线图，编号①~⑥"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(140, 170)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        m = 15

        # 六个点坐标 (逆时针 ①→⑥)
        mid_y = h * 55 // 100
        pts = [
            (m, h - m),        # ① 左下(起降)
            (m, mid_y),        # ② 左中
            (m, m + 8),        # ③ 左上(物资)
            (w - m, m + 8),    # ④ 右上(待救)
            (w - m, mid_y),    # ⑤ 右中
            (w - m, h - m),    # ⑥ 右下(降落)
        ]

        # 框线 (白色细线)
        p.setPen(QPen(QColor(180, 180, 180), 1))
        for i in range(len(pts) - 1):
            p.drawLine(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])

        # 编号圆圈（编号随 GUI 模式预设切换）
        nums = config.GUI_PRESETS[config.gui_mode]["field_nums"]
        font = QFont("Monospace", 8)
        p.setFont(font)
        for i, (x, y) in enumerate(pts):
            p.setBrush(QColor(60, 60, 60))
            p.setPen(QPen(QColor(180, 180, 180), 1))
            p.drawEllipse(x - 8, y - 8, 16, 16)
            p.setPen(QColor(180, 180, 180))
            p.drawText(x - 4, y + 4, str(nums[i]))

        # 底部 "飞手"
        p.setPen(QColor(140, 140, 140))
        p.setFont(QFont("Monospace", 10))
        p.drawText(0, h - 16, w, 16, Qt.AlignCenter, "飞手")


class GrabRangeBar(QWidget):
    """抓取范围可视化调节条 — X原点 / Y原点 / 半径 三个水平滑块"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #1a1a1a;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(6)

        self.value_labels = {}

        # 叠加线总开关（范围圆 + 十字准星），供标定时关闭保持画面干净
        self.show_checkbox = QCheckBox("范围圆")
        self.show_checkbox.setToolTip("显示/隐藏 范围圆与十字准星（标定时建议关闭）")
        self.show_checkbox.setStyleSheet("color: #ddd; font-size: 12px;")
        layout.addWidget(self.show_checkbox)

        for key, text in (("x", "X原点"), ("y", "Y原点"), ("r", "半径")):
            lbl = QLabel(text)
            lbl.setStyleSheet("color: #bbb; font-size: 12px;")
            layout.addWidget(lbl)

            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 100)
            slider.setSingleStep(1)
            slider.setFixedHeight(20)
            slider.setStyleSheet(
                "QSlider::groove:horizontal { height: 4px; background: #444; border-radius: 2px; }"
                "QSlider::handle:horizontal { width: 14px; margin: -5px 0; border-radius: 7px;"
                " background: #66ff66; }"
            )
            layout.addWidget(slider, 1)

            val = QLabel("--")
            val.setFixedWidth(48)
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            val.setStyleSheet("color: #ffcc66; font-size: 12px; font-weight: bold;")
            layout.addWidget(val)

            setattr(self, f"{key}_slider", slider)
            self.value_labels[key] = val

    def update_value_labels(self, x, y, r):
        """同步三个滑块的数值显示"""
        self.value_labels["x"].setText(str(x))
        self.value_labels["y"].setText(str(y))
        self.value_labels["r"].setText(str(r))


class VideoDisplay(QWidget):
    """
    视频显示组件
    - 左侧截图格区 + 顶部状态栏 + 系统按钮
    - 右侧显示视频帧（保持原始比例）
    - 支持鼠标左键、右键、中键自定义回调
    """

    STATUS_BAR_HEIGHT = 210
    ROI_PREVIEW_SIZE = (240, 170)   # ROI 预览标签尺寸

    def __init__(self, title="视频显示", parent=None, show_fps=True):
        super().__init__(parent)
        self._base_title = title
        self.setWindowTitle(title)

        # 主布局：水平布局，左侧按钮，右侧视频
        self.main_layout = QHBoxLayout()
        self.setLayout(self.main_layout)

        self._build_left_panel()
        self._build_right_panel()

        self.main_layout.addWidget(self.right_panel, 1)

        # 帧率统计
        self.show_fps = show_fps
        self.frame_count = 0
        self.last_time = time.time()

        # 标志：是否已根据第一帧调整窗口大小
        self.first_frame = True

        # ----- 鼠标事件相关 -----
        self._mouse_callbacks = {}

        # 记录当前显示区域信息（用于坐标转换）
        self.original_width = 0
        self.original_height = 0
        self.display_rect = None

        # ----- 键盘事件相关 -----
        self.keyboard_callback = None

        # 开启键盘焦点，确保能收到按键事件
        self.setFocusPolicy(Qt.StrongFocus)

        # 禁用右键默认菜单
        self.setContextMenuPolicy(Qt.NoContextMenu)

        self._flash_message = None
        self._flash_time = 0
        self._prev_camera = None
        self._prev_comm = None

    def _build_left_panel(self):
        """左侧面板：模式切换按钮 + 截图格子区"""
        self.button_widget = QWidget()
        self.button_layout = QVBoxLayout()
        self.button_widget.setLayout(self.button_layout)
        self.button_layout.setContentsMargins(0, 0, 0, 0)
        self.button_widget.setFixedWidth(config.gui_button_panel_width)
        self.main_layout.addWidget(self.button_widget)

        # 截图格子区域（随 GUI 模式整体切换）
        self.mode_btn = QPushButton()
        self.mode_btn.setFixedHeight(28)
        self.mode_btn.setStyleSheet(
            "font-size: 12px; background-color: #333; color: #ddd; border: 1px solid #666;"
        )
        self.mode_btn.clicked.connect(self._toggle_grid_mode)
        self.button_layout.addWidget(self.mode_btn)

        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(4)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_widget.setLayout(self.grid_layout)

        self.grid_buttons = []
        self._build_grid()

        self.button_layout.addWidget(self.grid_widget)

        # 格子点击回调
        self.grid_click_callback = None

    def _build_right_panel(self):
        """右侧面板：顶部状态栏 + 抓取条 + 画面显示区 + 偏差输入框"""
        self.right_panel = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        self.right_panel.setLayout(right_layout)

        self._build_status_area(right_layout)
        self._build_grab_bar(right_layout)

        # 画面显示控件（填满状态栏下方的剩余区域）
        self.label = QLabel()
        self.label.setScaledContents(False)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("background-color: black;")
        right_layout.addWidget(self.label, 1)

        # 偏差修正输入框（叠加在视频画面左上角，实时生效并持久化）
        self._create_offset_inputs()

    def _build_status_area(self, right_layout):
        """顶部状态栏：状态文本 + ROI 预览 + 路线图 + 规则 + 系统按钮"""
        self.status_container = QWidget()
        self.status_container.setStyleSheet("background-color: black;")
        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        self.status_container.setLayout(outer_layout)
        self.status_container.setFixedHeight(self.STATUS_BAR_HEIGHT)

        # 状态文本 + ROI + 系统按钮（2列竖排）
        info_row = QWidget()
        info_layout = QHBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(0)
        info_row.setLayout(info_layout)

        self.status_bar = QLabel("📷 --")
        self.status_bar.setTextFormat(Qt.RichText)
        self.status_bar.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.status_bar.setWordWrap(True)
        self.status_bar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.status_bar.setStyleSheet(
            "color: #ccc; padding: 4px 6px; font-size: 14px;"
        )
        sb_font = QFont("Monospace", 13)
        self.status_bar.setFont(sb_font)
        info_layout.addWidget(self.status_bar)

        self.roi_preview_label = QLabel()
        self.roi_preview_label.setFixedSize(*self.ROI_PREVIEW_SIZE)
        self.roi_preview_label.setAlignment(Qt.AlignCenter)
        self.roi_preview_label.setStyleSheet("background-color: #333;")
        info_layout.addWidget(self.roi_preview_label)

        # ── 路线图 ──
        self.field_diagram = FieldDiagram()
        info_layout.addWidget(self.field_diagram)

        # ── 抓取规则 + 分值 (合并宽条) ──
        self.rules_label = QLabel()
        self.rules_label.setFixedSize(700, 100)
        self.rules_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.rules_label.setStyleSheet("color: #ccc; background-color: #2a2a2a; padding: 6px;")
        self.rules_label.setFont(QFont("Monospace", 11))
        self.rules_label.setText(
            "抓取: 魔方🔄台球交替(台球完→全魔方)   │  魔→a:10  │  b区:黄20 绿30 棕40\n"
            "若抓错→本次无效 重新按顺序来           │  蓝50 粉60 黑70"
        )
        info_layout.addWidget(self.rules_label)

        self.sys_button_panel = QWidget()
        self.sys_button_grid = QGridLayout()
        self.sys_button_grid.setContentsMargins(4, 4, 4, 4)
        self.sys_button_grid.setHorizontalSpacing(48)
        self.sys_button_grid.setVerticalSpacing(4)
        self.sys_button_panel.setLayout(self.sys_button_grid)
        info_layout.addWidget(self.sys_button_panel)
        info_layout.addStretch(1)

        self._sys_btn_count = 0
        self._sys_btn_cols = 2

        outer_layout.addWidget(info_row)
        right_layout.addWidget(self.status_container)

    def _build_grab_bar(self, right_layout):
        """抓取范围调节条（状态栏与画面之间）"""
        self.grab_bar = GrabRangeBar()
        self.grab_bar.x_slider.valueChanged.connect(lambda v: self._on_grab_slider("x", v))
        self.grab_bar.y_slider.valueChanged.connect(lambda v: self._on_grab_slider("y", v))
        self.grab_bar.r_slider.valueChanged.connect(lambda v: self._on_grab_slider("r", v))
        self.grab_bar.x_slider.sliderReleased.connect(self._save_grab_config)
        self.grab_bar.y_slider.sliderReleased.connect(self._save_grab_config)
        self.grab_bar.r_slider.sliderReleased.connect(self._save_grab_config)
        self._last_grab_size = None
        self._syncing_sliders = False
        self._show_overlays = config.show_overlays
        self.grab_bar.show_checkbox.setChecked(self._show_overlays)
        self.grab_bar.show_checkbox.toggled.connect(self._on_toggle_overlays)
        right_layout.addWidget(self.grab_bar)

    def flash_message(self, msg):
        """在状态栏显示临时消息（3秒后消失）"""
        self._flash_message = msg
        self._flash_time = time.time()

    def add_sys_button(self, text, callback, tooltip=None):
        """在顶部状态栏添加一个系统按钮（自动排列为2列）"""
        try:
            btn = QPushButton(text)
            btn.setFixedHeight(38)
            btn.setStyleSheet(
                "font-size: 12px; padding: 0 10px; background-color: #444; "
                "color: #ddd; border: 1px solid #666;"
            )
            if tooltip:
                btn.setToolTip(tooltip)
            btn.clicked.connect(callback)
            row = self._sys_btn_count // self._sys_btn_cols
            col = 1 - (self._sys_btn_count % self._sys_btn_cols)
            self.sys_button_grid.addWidget(btn, row, col)
            self._sys_btn_count += 1
        except Exception as e:
            log_error(e, f"添加系统按钮 '{text}' 失败")

    def set_mouse_callback(self, button, callback):
        """设置鼠标按键点击回调

        Args:
            button: 'left' / 'right' / 'middle'
            callback: 接收 (x, y) 的可调用对象
        """
        self._mouse_callbacks[button] = callback

    def set_keyboard_callback(self, callback):
        """设置键盘事件回调

        Args:
            callback: 接收 (event_type, key, text, modifiers) 的可调用对象
                      event_type: 'press' 或 'release'
                      key: Qt.Key 枚举值
                      text: 按键文本
                      modifiers: Qt.KeyboardModifiers
        """
        self.keyboard_callback = callback

    def update_frame(self, frame):
        """
        显示一帧图像，保持原始比例

        Args:
            frame: numpy.ndarray, BGR 格式（OpenCV 默认格式）
        """
        try:
            if frame is None or frame.size == 0:
                return

            # 记录原始摄像头分辨率（用于鼠标坐标映射）
            cam_h, cam_w = frame.shape[:2]
            self.original_height, self.original_width = cam_h, cam_w

            # 在副本上绘制叠加线，保证传入帧（data.current_frame）始终干净
            frame = frame.copy()

            # 抓取范围圆：缩放前在原始分辨率上绘制（圆心/半径与滑块、鼠标同坐标空间）
            self._draw_grab_range(frame)
            self._update_grab_ranges(cam_w, cam_h)

            # 先缩放到显示尺寸，避免后续在全分辨率上做颜色转换和渲染
            label_size = self.label.size()
            if label_size.width() > 0 and label_size.height() > 0:
                scale = min(label_size.width() / cam_w, label_size.height() / cam_h)
                disp_w, disp_h = int(cam_w * scale), int(cam_h * scale)
                frame = cv2.resize(frame, (disp_w, disp_h), interpolation=cv2.INTER_LINEAR)

            # 在图像上绘制十字线（定位用）
            self._draw_crosshair(frame)

            # 显示尺寸（缩放后，用于计算居中偏移）
            disp_h, disp_w = frame.shape[:2]

            # 将 BGR 转换为 QPixmap（此时已是显示尺寸）
            pixmap = self._bgr_to_pixmap(frame)

            # 首次显示：调整窗口大小（按缩放后的显示尺寸，与原行为一致）
            if self.first_frame:
                self.first_frame = False
                self._adjust_window_size(disp_w, disp_h)

            # 设置 pixmap（已为显示尺寸，无需再缩放）
            self.label.setPixmap(pixmap)

            # 重新获取 label 尺寸以计算居中偏移
            ls = self.label.size()
            if ls.width() > 0 and ls.height() > 0:
                ox = (ls.width() - disp_w) // 2
                oy = (ls.height() - disp_h) // 2
                self.display_rect = QRect(ox, oy, disp_w, disp_h)
            else:
                self.display_rect = None

            # 帧率统计
            if self.show_fps:
                self._update_fps()

        except Exception as e:
            log_error(e, "更新视频帧失败")

    def _bgr_to_pixmap(self, frame, w=None, h=None):
        """BGR numpy 帧 → QPixmap（画面显示/格子图标/ROI 预览共用）

        注意：必须用 rgb.data（零拷贝 memoryview）而非 rgb.tobytes()，
        tobytes() 每帧多一次整帧拷贝会严重拖低帧率（实测 0.7ms → 15ms）。
        QPixmap.fromImage 会复制像素，QImage 引用 numpy 缓冲区是安全的。
        """
        if w is None or h is None:
            h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        qimage = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888)
        return QPixmap.fromImage(qimage)

    def _adjust_window_size(self, video_width, video_height):
        """根据视频尺寸调整窗口大小"""
        margins = self.layout().contentsMargins()
        spacing = self.layout().spacing()
        button_width = config.gui_button_panel_width

        # 右侧视频等比压缩到最大显示宽度（画面不拉伸变形）
        if video_width > config.gui_video_max_width:
            scale = config.gui_video_max_width / float(video_width)
            video_width = config.gui_video_max_width
            video_height = int(video_height * scale)

        total_width = (button_width + video_width +
                       margins.left() + margins.right() +
                       spacing + 20)  # 窗口边框估算
        total_height = (self.STATUS_BAR_HEIGHT + video_height +
                        margins.top() + margins.bottom() + 40)  # 标题栏估算

        self.resize(total_width, total_height)

    def _update_fps(self):
        """更新帧率统计并显示在窗口标题中"""
        self.frame_count += 1
        now = time.time()
        if now - self.last_time >= 1.0:
            fps = self.frame_count
            self.setWindowTitle(f"{self._base_title}  |  FPS: {fps}")
            self.frame_count = 0
            self.last_time = now

    def _draw_crosshair(self, frame):
        """
        在图像上绘制十字线（定位准星）

        画一条竖直线和一条水平线贯穿图像中心。
        颜色：亮绿色 (BGR)。
        """
        if not self._show_overlays:
            return
        if frame is None or frame.size == 0:
            return
        h, w = frame.shape[:2]
        cx, cy = w // 2, h // 2

        # 线宽 1px
        color = (255, 255, 255)

        # 竖直线 (从顶到底)
        cv2.line(frame, (cx, 0), (cx, h - 1), color, 1)
        # 水平线 (从左到右)
        cv2.line(frame, (0, cy), (w - 1, cy), color, 1)

    def _draw_grab_range(self, frame):
        """
        在原图上绘制抓取范围圆（细线圆环 + 圆心点）

        圆心/半径按配置比例 × 当前帧尺寸现场换算为像素，因此分辨率变化
        或断线占位帧都不影响圆的相对位置/大小。圆超出画面范围的部分由
        cv2.circle 在数组边界处自动裁剪，只显示画面内的弧段。
        """
        if not self._show_overlays:
            return
        try:
            h, w = frame.shape[:2]
            cx = int(round(config.grab_range_x_ratio * (w - 1)))
            cy = int(round(config.grab_range_y_ratio * (h - 1)))
            r = int(round(config.grab_range_radius_ratio * w))
            if r <= 0:
                return
            color = (255, 255, 255)  # 白色 BGR
            cv2.circle(frame, (cx, cy), r, color, 1)
            cv2.circle(frame, (cx, cy), 3, color, -1)
        except Exception as e:
            log_error(e, "绘制抓取范围失败")

    def _update_grab_ranges(self, w, h):
        """按实际帧尺寸更新滑块范围与位置（仅尺寸变化时执行一次）"""
        if (w, h) == self._last_grab_size:
            return
        self._last_grab_size = (w, h)

        self.grab_bar.x_slider.setRange(0, max(1, w - 1))
        self.grab_bar.y_slider.setRange(0, max(1, h - 1))
        self.grab_bar.r_slider.setRange(0, max(1, w))

        # 配置比例 × 当前帧尺寸 → 滑块像素值
        cx = int(round(config.grab_range_x_ratio * (w - 1)))
        cy = int(round(config.grab_range_y_ratio * (h - 1)))
        r = int(round(config.grab_range_radius_ratio * w))

        self._syncing_sliders = True
        try:
            self.grab_bar.x_slider.setValue(cx)
            self.grab_bar.y_slider.setValue(cy)
            self.grab_bar.r_slider.setValue(r)
        finally:
            self._syncing_sliders = False
        self.grab_bar.update_value_labels(cx, cy, r)

    def _on_grab_slider(self, key, value):
        """滑块移动 → 像素换算为比例写入配置（程序同步时跳过）"""
        if self._syncing_sliders:
            return
        self.grab_bar.value_labels[key].setText(str(value))
        if key == "x":
            config.grab_range_x_ratio = px_to_ratio(value, self.original_width)
        elif key == "y":
            config.grab_range_y_ratio = px_to_ratio(value, self.original_height)
        else:
            config.grab_range_radius_ratio = px_to_ratio(value, self.original_width)

    def _save_grab_config(self):
        """滑块松开 → 持久化一次到 camera_params.yaml"""
        config.save()

    # ─────── 偏差修正输入框（叠加在视频画面左上角，累加模式） ───────

    def _create_offset_inputs(self):
        """在视频画面左上角叠加偏差修正输入框（累加模式）

        - 左侧标签实时显示当前已加载的总偏差（mm，只读）
        - 右侧两个输入框输入的是「增量」：回车/失焦/点箭头后累加到总偏差，
          输入框自动清零，下次输入仍为增量，并即时持久化到 YAML。
        - 坐标映射器每次调用实时读取 config，累加后下一次点击立即生效。
        """
        overlay = QWidget(self.label)
        layout = QHBoxLayout(overlay)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        # 当前已加载总偏差（只读显示）
        self.offset_total_label = QLabel()
        self.offset_total_label.setStyleSheet(
            "color: #ffcc66; font-size: 12px; font-weight: bold; background: transparent;")
        layout.addWidget(self.offset_total_label)

        spin_style = (
            "QDoubleSpinBox { background-color: rgba(0,0,0,160); color: #ffcc66;"
            " border: 1px solid #555; border-radius: 3px; font-size: 12px;"
            " padding: 1px 2px; }"
        )

        for text, key in (("X", "coord_offset_x_mm"), ("Y", "coord_offset_y_mm")):
            lbl = QLabel(text)
            lbl.setStyleSheet("color: #ddd; font-size: 12px; background: transparent;")
            layout.addWidget(lbl)

            spin = QDoubleSpinBox()
            spin.setRange(-10000.0, 10000.0)
            spin.setDecimals(2)
            spin.setSingleStep(1.0)
            spin.setFixedWidth(80)
            spin.setFixedHeight(22)
            spin.setStyleSheet(spin_style)
            spin.setToolTip("输入增量(mm)，回车/失焦/点箭头后累加到发送数据的偏差")
            # 关闭键盘追踪：输入过程中不触发，回车/失焦/箭头时才提交一次
            spin.setKeyboardTracking(False)
            spin.valueChanged.connect(
                lambda v, s=spin, k=key: self._apply_offset_delta(s, k))
            layout.addWidget(spin)

            setattr(self, f"offset_{text.lower()}_edit", spin)

        overlay.move(8, 8)
        self._sync_offset_total()

    def _sync_offset_total(self):
        """把当前已加载的总偏差刷新到标签（只读显示）"""
        self.offset_total_label.setText(
            f"偏差 X={config.coord_offset_x_mm:.2f} Y={config.coord_offset_y_mm:.2f} mm")
        self._offset_total_shown = (config.coord_offset_x_mm, config.coord_offset_y_mm)

    def _apply_offset_delta(self, spin, key):
        """输入框提交 → 增量累加到已加载总值，清零输入框并持久化"""
        delta = spin.value()
        spin.setValue(0.0)  # 累加后清零，下次输入仍为增量
        if delta == 0.0:
            return
        setattr(config, key, getattr(config, key) + delta)
        self._sync_offset_total()
        config.save()

    def _on_toggle_overlays(self, checked):
        """范围圆/十字准星 开关 → 立即生效并持久化"""
        self._show_overlays = checked
        config.show_overlays = checked
        config.save()

    def _get_image_coordinates(self, event):
        """
        从鼠标事件中提取图像内的坐标

        Returns:
            tuple: (x, y) 图像坐标，如果不在图像区域内则返回 (None, None)
        """
        try:
            pos = event.pos()
            # 获取 label 在顶层窗口中的位置（label 在 right_panel 内）
            label_pos = self.label.mapTo(self, QPoint(0, 0))
            label_size = self.label.size()
            label_rect = QRect(label_pos, label_size)

            if not label_rect.contains(pos):
                return None, None

            # 转换为label内的相对坐标
            label_x = pos.x() - label_pos.x()
            label_y = pos.y() - label_pos.y()

            if (self.display_rect is None or
                self.original_width == 0 or
                self.original_height == 0):
                return None, None

            # 检查点击是否在显示区域内
            if not self.display_rect.contains(label_x, label_y):
                return None, None

            # 计算在显示区域内的相对坐标
            img_x = label_x - self.display_rect.x()
            img_y = label_y - self.display_rect.y()

            # 映射回原始图像坐标（保留浮点精度，实现亚像素）
            scale_x = self.original_width / self.display_rect.width()
            scale_y = self.original_height / self.display_rect.height()
            original_x = img_x * scale_x
            original_y = img_y * scale_y

            # 边界保护（保留浮点值）
            original_x = max(0.0, min(float(self.original_width - 1), original_x))
            original_y = max(0.0, min(float(self.original_height - 1), original_y))

            return original_x, original_y

        except Exception as e:
            log_error(e, "获取图像坐标失败")
            return None, None

    def mousePressEvent(self, event):
        """重写鼠标按下事件"""
        try:
            x, y = self._get_image_coordinates(event)
            if x is None or y is None:
                return

            button = event.button()
            btn_map = {Qt.LeftButton: 'left', Qt.RightButton: 'right', Qt.MiddleButton: 'middle'}
            cb = self._mouse_callbacks.get(btn_map.get(button))
            if cb:
                cb(x, y)
        except Exception as e:
            log_error(e, "鼠标事件处理失败")

    def keyPressEvent(self, event):
        """重写键盘按下事件"""
        try:
            key = event.key()
            text = event.text()
            modifiers = event.modifiers()

            if self.keyboard_callback:
                self.keyboard_callback('press', key, text, modifiers)

            super().keyPressEvent(event)
        except Exception as e:
            log_error(e, "键盘按下事件处理失败")

    def set_grid_click_callback(self, callback):
        """设置格子点击回调: callback(row, col)"""
        self.grid_click_callback = callback

    def _build_grid(self):
        """按当前 gui_mode 预设重建截图格子 + 刷新路线图编号"""
        preset = config.GUI_PRESETS[config.gui_mode]
        config.gui_button_panel_width = preset["gui_button_panel_width"]
        config.gui_grid_rows = preset["gui_grid_rows"]
        config.gui_grid_cols = preset["gui_grid_cols"]

        for btn in self.grid_buttons:
            self.grid_layout.removeWidget(btn)
            btn.deleteLater()
        self.grid_buttons = []

        self.button_widget.setFixedWidth(config.gui_button_panel_width)

        bw, bh = self._grid_button_size()
        for row in range(config.gui_grid_rows):
            for col in range(config.gui_grid_cols):
                btn = QPushButton(f"{row + 1}")
                btn.setFixedSize(bw, bh)
                btn.setStyleSheet(
                    "background-color: #555; border: 2px solid #888; color: white; font-size: 16px;"
                )
                btn.clicked.connect(lambda checked, r=row, c=col: self._on_grid_click(r, c))
                self.grid_layout.addWidget(btn, row, col)
                self.grid_buttons.append(btn)

        self._update_mode_button()
        if getattr(self, "field_diagram", None):
            self.field_diagram.update()

    def _grid_button_size(self):
        """截图格子按钮尺寸（按当前面板宽度计算）"""
        bw = config.gui_button_panel_width - 4
        return bw, bw * 9 // 16

    def _update_mode_button(self):
        """更新模式切换按钮文字（显示将切换到的模式）"""
        self.mode_btn.setText("→ 六格模式" if config.gui_mode == "3" else "→ 三格模式")

    def _toggle_grid_mode(self):
        """切换三格/六格 GUI 模式：重建格子 + 刷新路线图 + 持久化 + 重算窗口"""
        config.gui_mode = "6" if config.gui_mode == "3" else "3"
        self._build_grid()
        config.save()
        if self.original_width and self.original_height:
            self._adjust_window_size(self.original_width, self.original_height)

    def _on_grid_click(self, row, col):
        """格子按钮被点击"""
        if self.grid_click_callback:
            self.grid_click_callback(row, col)

    def set_grid_image(self, row, col, frame):
        """从 frame 截取中心区域并设置为格子图标"""
        if frame is None or frame.size == 0:
            return
        h, w = frame.shape[:2]
        ratio = config.grid_crop_ratio
        crop_w = int(w * ratio)
        crop_h = int(h * ratio)
        x1 = (w - crop_w) // 2
        y1 = (h - crop_h) // 2
        crop = frame[y1:y1 + crop_h, x1:x1 + crop_w]

        pixmap = self._bgr_to_pixmap(crop, crop_w, crop_h)
        bw, bh = self._grid_button_size()
        scaled = pixmap.scaled(bw, bh, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        btn = self.grid_buttons[row * config.gui_grid_cols + col]
        btn.setIcon(QIcon(scaled))
        btn.setIconSize(scaled.size())
        btn.setText("")

    def update_roi_preview(self, frame, cx, cy, size=200):
        """
        从 frame 中截取以 (cx, cy) 为中心的 size×size 区域，缩放后显示在预览标签中

        Args:
            frame: 原始帧（BGR 格式）
            cx: 中心点 x 坐标（像素）
            cy: 中心点 y 坐标（像素）
            size: 截取区域边长（默认 200）
        """
        try:
            if frame is None or frame.size == 0:
                return

            h, w = frame.shape[:2]
            half = size // 2

            # 计算截取区域（带边界保护）
            x1 = max(0, int(cx) - half)
            y1 = max(0, int(cy) - half)
            x2 = min(w, x1 + size)
            y2 = min(h, y1 + size)

            # 如果区域被边界裁剪，调整起点保持 size 大小
            if x2 - x1 < size:
                x1 = max(0, x2 - size)
            if y2 - y1 < size:
                y1 = max(0, y2 - size)

            roi = frame[y1:y2, x1:x2]
            if roi.size == 0:
                return

            # 缩放到 ROI 标签宽度
            preview_w = self.roi_preview_label.width()
            if preview_w < 10:
                preview_w = self.ROI_PREVIEW_SIZE[0]
            roi_h, roi_w = roi.shape[:2]
            scale = preview_w / roi_w
            preview_h = int(roi_h * scale)
            roi = cv2.resize(roi, (preview_w, preview_h), interpolation=cv2.INTER_LINEAR)

            # BGR → QPixmap → 缩放
            pixmap = self._bgr_to_pixmap(roi)
            scaled = pixmap.scaled(*self.ROI_PREVIEW_SIZE,
                                   Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.roi_preview_label.setPixmap(scaled)

        except Exception as e:
            log_error(e, "更新 ROI 预览失败")

    def update_all(self, state: InteractionState):
        """批量更新所有显示状态"""

        if self._flash_message and time.time() - self._flash_time < 1.0:
            flash = f">>> {self._flash_message} <<<"
        else:
            self._flash_message = None
            flash = ""

        # 断开弹窗检测
        if self._prev_camera is not None and self._prev_camera and not state.camera_connected:
            QuickPopup("相机已断开", self.window())
        if self._prev_comm is not None and self._prev_comm and "✗" in state.comm_status:
            QuickPopup("串口已断开", self.window())
        self._prev_camera = state.camera_connected
        self._prev_comm = "✓" in state.comm_status

        cam_icon = "📷 <span style='color:#ff6666'>✗</span>" if not state.camera_connected else "📷 <span style='color:#66ff66'>✓</span>"
        comm_st = state.comm_status.replace("✗", "<span style='color:#ff6666'>✗</span>").replace("✓", "<span style='color:#66ff66'>✓</span>")
        kn_str = str(state.key_number) if state.key_number is not None else "-"
        px, py = state.plane_coords
        rx, ry = state.right_click_coords
        line1 = f"{cam_icon}  {comm_st}  按键: <span style='color:#ff6666'>{kn_str}</span>"
        line2 = (
            f"参考点 X=<span style='color:#ff6666'>{px:.4f}</span> "
            f"Y=<span style='color:#ff6666'>{py:.4f}</span>  "
            f"右键 X=<span style='color:#ff6666'>{rx:.4f}</span> "
            f"Y=<span style='color:#ff6666'>{ry:.4f}</span>"
        )
        sent_lines = state.last_sent_text.split("\n")
        sent_part = "  ".join(sent_lines) if sent_lines else state.last_sent_text
        sent_part = re.sub(r'(\d+)', r"<span style='color:#ff6666'>\1</span>", sent_part)
        line4 = "⌨ [左]设参考点 [右]查坐标 [格1~3]截画面 [0-9]打包 [空格]发"
        line5 = "[1]抓球 [2]抓方 [3]指定地点放 [4]直接放 [5]旋180°"
        sep = "<br>"
        if flash:
            text = f"{flash}{sep}{line1}{sep}{line2}{sep}{sent_part}{sep}{line4}{sep}{line5}"
        else:
            text = f"{line1}{sep}{line2}{sep}{sent_part}{sep}{line4}{sep}{line5}"
        # 偏差总值标签与外部修改（设置对话框/重启）保持同步
        cur_off = (config.coord_offset_x_mm, config.coord_offset_y_mm)
        if cur_off != self._offset_total_shown:
            self._sync_offset_total()
        self.status_bar.setText(text)

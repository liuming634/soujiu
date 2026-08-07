"""
设置对话框 - GUI 配置管理
允许用户在运行时修改串口、相机等配置项，无需编辑代码
"""
import sys
from PyQt5.QtWidgets import (
    QDialog, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QSpinBox, QComboBox, QPushButton,
    QCheckBox, QFormLayout, QFileDialog, QDialogButtonBox,
    QDoubleSpinBox
)


class SettingsDialog(QDialog):
    """系统设置对话框

    只负责 UI 展示和配置值收集，不直接操作硬件。
    调用方在 dialog.exec_() 后读取 collected_values 自行处理。
    """

    def __init__(self, parent=None):
        """
        Args:
            parent: 父窗口
        """
        super().__init__(parent)
        self.setWindowTitle("系统设置")
        self.setMinimumWidth(560)
        self.setMinimumHeight(440)

        self._file_edits = {}           # 标定路径输入框 {key: QLineEdit}
        self._modified = False          # 标记是否有未保存的修改

        self._init_ui()
        self._load_from_config()

    # ──────────────────────────── UI 构建 ────────────────────────────

    def _init_ui(self):
        """初始化界面"""
        main_layout = QVBoxLayout(self)

        # 选项卡
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        self._create_camera_tab()
        self._create_serial_tab()
        self._create_calibration_tab()
        self._create_general_tab()
        self._create_grab_range_tab()

        # 底部按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
            | QDialogButtonBox.Apply | QDialogButtonBox.Reset
        )
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self._on_apply)
        buttons.button(QDialogButtonBox.Reset).clicked.connect(self._load_from_config)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

    def _create_camera_tab(self):
        """相机设置选项卡"""
        tab = QWidget()
        layout = QFormLayout(tab)

        # ── 信号源 ──
        self.source_combo = QComboBox()
        self.source_combo.addItem("USB 摄像头", "usb")
        self.source_combo.addItem("FPV 图传 (RTL8812AU)", "fpv")
        layout.addRow("信号源:", self.source_combo)

        # ── 相机索引 ──
        self.camera_id_spin = QSpinBox()
        self.camera_id_spin.setRange(0, 99)
        layout.addRow("相机索引:", self.camera_id_spin)

        # ── 分辨率 ──
        res_layout = QHBoxLayout()
        self.cam_w_spin = QSpinBox()
        self.cam_w_spin.setRange(160, 7680)
        self.cam_w_spin.setSingleStep(10)
        res_layout.addWidget(self.cam_w_spin)
        res_layout.addWidget(QLabel("×"))
        self.cam_h_spin = QSpinBox()
        self.cam_h_spin.setRange(120, 4320)
        self.cam_h_spin.setSingleStep(10)
        res_layout.addWidget(self.cam_h_spin)
        layout.addRow("分辨率:", res_layout)

        # ── 预设分辨率快捷按钮 ──
        preset_layout = QHBoxLayout()
        from core.config import config
        for label, w, h in config.resolution_presets:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked, w=w, h=h: self._set_resolution(w, h))
            preset_layout.addWidget(btn)
        layout.addRow("预设:", preset_layout)

        # ── USB 摄像头额外参数 ──
        self.camera_fps_spin = QSpinBox()
        self.camera_fps_spin.setRange(1, 120)
        layout.addRow("USB 帧率:", self.camera_fps_spin)

        self.camera_fourcc_combo = QComboBox()
        self.camera_fourcc_combo.addItem("MJPG", "MJPG")
        self.camera_fourcc_combo.addItem("YUYV", "YUYV")
        layout.addRow("USB 编码:", self.camera_fourcc_combo)

        # ── FPV 参数 ──
        sep = QLabel("──── FPV 图传参数 ────")
        sep.setStyleSheet("color: gray;")
        layout.addRow("", sep)

        self.fpv_channel_spin = QSpinBox()
        self.fpv_channel_spin.setRange(1, 200)
        layout.addRow("FPV 信道:", self.fpv_channel_spin)

        self.fpv_cw_combo = QComboBox()
        self.fpv_cw_combo.addItem("20 MHz", 20)
        self.fpv_cw_combo.addItem("40 MHz", 40)
        self.fpv_cw_combo.addItem("80 MHz", 80)
        layout.addRow("信道宽度:", self.fpv_cw_combo)

        self.fpv_key_edit = QLineEdit()
        self.fpv_key_edit.setPlaceholderText("gs.key 文件路径")
        layout.addRow("密钥文件:", self.fpv_key_edit)

        self.fpv_link_id_spin = QSpinBox()
        self.fpv_link_id_spin.setRange(0, 99999999)
        layout.addRow("链路 ID:", self.fpv_link_id_spin)

        self.fpv_codec_combo = QComboBox()
        self.fpv_codec_combo.addItem("H.265", "h265")
        self.fpv_codec_combo.addItem("H.264", "h264")
        layout.addRow("FPV 编码:", self.fpv_codec_combo)

        self.fpv_w_spin = QSpinBox()
        self.fpv_w_spin.setRange(320, 3840)
        self.fpv_w_spin.setSingleStep(16)
        layout.addRow("FPV 宽度:", self.fpv_w_spin)

        self.fpv_h_spin = QSpinBox()
        self.fpv_h_spin.setRange(240, 2160)
        self.fpv_h_spin.setSingleStep(16)
        layout.addRow("FPV 高度:", self.fpv_h_spin)

        self.fpv_fps_spin = QSpinBox()
        self.fpv_fps_spin.setRange(30, 240)
        layout.addRow("FPV 帧率:", self.fpv_fps_spin)

        self.tabs.addTab(tab, "相机")

    def _create_serial_tab(self):
        """串口设置选项卡"""
        tab = QWidget()
        layout = QFormLayout(tab)

        # ── 串口端口 ──
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self._add_common_ports()
        layout.addRow("串口:", self.port_combo)

        # ── 波特率 ──
        self.baudrate_combo = QComboBox()
        for rate in [9600, 19200, 38400, 57600, 115200, 230400]:
            self.baudrate_combo.addItem(str(rate), rate)
        self.baudrate_combo.setEditable(True)
        layout.addRow("波特率:", self.baudrate_combo)

        # ── 超时 ──
        self.timeout_spin = QDoubleSpinBox()
        self.timeout_spin.setRange(0.01, 10.0)
        self.timeout_spin.setSingleStep(0.05)
        self.timeout_spin.setDecimals(2)
        self.timeout_spin.setValue(0.1)
        self.timeout_spin.setSuffix(" 秒")
        layout.addRow("超时:", self.timeout_spin)

        # ── 协议前缀 ──
        self.prefix_edit = QLineEdit()
        self.prefix_edit.setPlaceholderText("例如: 0x5678")
        layout.addRow("协议前缀(hex):", self.prefix_edit)

        self.tabs.addTab(tab, "串口")

    def _create_calibration_tab(self):
        """标定文件路径选项卡"""
        tab = QWidget()
        layout = QFormLayout(tab)

        self._add_file_row(layout, "单应性矩阵:", "homography_file",
                           "calibration_data/homography.npy")
        self._add_file_row(layout, "相机内参:", "camera_matrix_file",
                           "calibration_data/camera_matrix.npy")
        self._add_file_row(layout, "畸变系数:", "dist_coeffs_file",
                           "calibration_data/dist_coeffs.npy")

        self.tabs.addTab(tab, "标定路径")

    def _create_general_tab(self):
        """通用设置选项卡"""
        tab = QWidget()
        layout = QFormLayout(tab)

        self.timer_spin = QSpinBox()
        self.timer_spin.setRange(10, 1000)
        self.timer_spin.setSuffix(" ms")
        layout.addRow("计时器间隔:", self.timer_spin)

        self.scale_spin = QSpinBox()
        self.scale_spin.setRange(1, 100000)
        layout.addRow("坐标缩放因子:", self.scale_spin)

        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(0, 99999)
        layout.addRow("坐标偏移量:", self.offset_spin)

        self.fps_check = QCheckBox("显示帧率")
        layout.addRow("", self.fps_check)

        self.grid_crop_spin = QDoubleSpinBox()
        self.grid_crop_spin.setRange(0.1, 1.0)
        self.grid_crop_spin.setSingleStep(0.05)
        self.grid_crop_spin.setDecimals(2)
        layout.addRow("截图裁剪比:", self.grid_crop_spin)

        self.tabs.addTab(tab, "通用")

    def _create_grab_range_tab(self):
        """抓取范围圆设置选项卡"""
        tab = QWidget()
        layout = QFormLayout(tab)

        hint = QLabel("圆心/半径为占画面宽高的比例（0~1），不随画面分辨率变化。半径 0 表示不显示。")
        hint.setStyleSheet("color: gray;")
        hint.setWordWrap(True)
        layout.addRow("", hint)

        self.grab_x_spin = QDoubleSpinBox()
        self.grab_x_spin.setRange(0.0, 1.0)
        self.grab_x_spin.setSingleStep(0.01)
        self.grab_x_spin.setDecimals(3)
        layout.addRow("圆心 X 比例:", self.grab_x_spin)

        self.grab_y_spin = QDoubleSpinBox()
        self.grab_y_spin.setRange(0.0, 1.0)
        self.grab_y_spin.setSingleStep(0.01)
        self.grab_y_spin.setDecimals(3)
        layout.addRow("圆心 Y 比例:", self.grab_y_spin)

        self.grab_r_spin = QDoubleSpinBox()
        self.grab_r_spin.setRange(0.0, 1.0)
        self.grab_r_spin.setSingleStep(0.01)
        self.grab_r_spin.setDecimals(3)
        layout.addRow("半径比例(×宽):", self.grab_r_spin)

        self.tabs.addTab(tab, "抓取范围")

    # ──────────────────────────── 辅助方法 ────────────────────────────

    def _add_file_row(self, layout, label, key, default):
        """添加一行文件路径选择"""
        row = QHBoxLayout()
        edit = QLineEdit(default)
        row.addWidget(edit)
        btn = QPushButton("浏览...")
        btn.clicked.connect(lambda: self._browse_file(edit))
        row.addWidget(btn)
        layout.addRow(label, row)
        self._file_edits[key] = edit

    def _browse_file(self, edit):
        """打开文件选择对话框"""
        path, _ = QFileDialog.getOpenFileName(self, "选择文件", edit.text())
        if path:
            edit.setText(path)

    def _set_resolution(self, w, h):
        """设置分辨率预设值"""
        self.cam_w_spin.setValue(w)
        self.cam_h_spin.setValue(h)

    def _add_common_ports(self, current=""):
        """按平台列出常用端口到下拉框"""
        from core.config import config
        common_ports = []
        if sys.platform.startswith("win"):
            common_ports = config.serial_ports_windows
        else:
            common_ports = config.serial_ports_linux

        for p in common_ports:
            if self.port_combo.findText(p) == -1:
                self.port_combo.addItem(p)

        # 恢复之前选中的项
        idx = self.port_combo.findText(current)
        if idx >= 0:
            self.port_combo.setCurrentIndex(idx)

    # ──────────────────────────── 配置读写 ────────────────────────────

    def _load_from_config(self):
        """从全局 config 加载当前值到界面"""
        self._modified = False
        from core.config import config

        # 信号源
        src_idx = self.source_combo.findData(config.camera_source)
        if src_idx >= 0:
            self.source_combo.setCurrentIndex(src_idx)

        # 相机
        self.camera_id_spin.setValue(config.camera_id)
        self.cam_w_spin.setValue(config.camera_width)
        self.cam_h_spin.setValue(config.camera_height)
        self.camera_fps_spin.setValue(config.camera_fps)
        fourcc_idx = self.camera_fourcc_combo.findData(config.camera_fourcc)
        if fourcc_idx >= 0:
            self.camera_fourcc_combo.setCurrentIndex(fourcc_idx)

        # FPV
        self.fpv_channel_spin.setValue(config.fpv_channel)
        cw_idx = self.fpv_cw_combo.findData(config.fpv_channel_width)
        if cw_idx >= 0:
            self.fpv_cw_combo.setCurrentIndex(cw_idx)
        self.fpv_key_edit.setText(config.fpv_key)
        self.fpv_link_id_spin.setValue(config.fpv_link_id)
        codec_idx = self.fpv_codec_combo.findData(config.fpv_codec)
        if codec_idx >= 0:
            self.fpv_codec_combo.setCurrentIndex(codec_idx)
        self.fpv_w_spin.setValue(config.fpv_width)
        self.fpv_h_spin.setValue(config.fpv_height)
        self.fpv_fps_spin.setValue(config.fpv_fps)

        # 串口
        port_idx = self.port_combo.findText(config.serial_port)
        if port_idx >= 0:
            self.port_combo.setCurrentIndex(port_idx)
        else:
            self.port_combo.setEditText(config.serial_port)

        baud_idx = self.baudrate_combo.findText(str(config.serial_baudrate))
        if baud_idx >= 0:
            self.baudrate_combo.setCurrentIndex(baud_idx)
        else:
            self.baudrate_combo.setEditText(str(config.serial_baudrate))

        self.timeout_spin.setValue(config.serial_timeout)

        # 协议前缀
        self.prefix_edit.setText(hex(config.serial_prefix))

        # 标定路径
        self._file_edits["homography_file"].setText(config.homography_file)
        self._file_edits["camera_matrix_file"].setText(config.camera_matrix_file)
        self._file_edits["dist_coeffs_file"].setText(config.dist_coeffs_file)

        # 通用
        self.timer_spin.setValue(config.timer_interval)
        self.scale_spin.setValue(config.coordinate_scale)
        self.offset_spin.setValue(config.coordinate_offset)
        self.fps_check.setChecked(config.fps_display)
        self.grid_crop_spin.setValue(config.grid_crop_ratio)

        # 抓取范围
        self.grab_x_spin.setValue(config.grab_range_x_ratio)
        self.grab_y_spin.setValue(config.grab_range_y_ratio)
        self.grab_r_spin.setValue(config.grab_range_radius_ratio)

    def _collect_values(self):
        """收集对话框中所有配置值，返回 dict"""
        return {
            # 信号源
            "camera_source": self.source_combo.currentData(),
            # 相机
            "camera_id": self.camera_id_spin.value(),
            "camera_width": self.cam_w_spin.value(),
            "camera_height": self.cam_h_spin.value(),
            "camera_fps": self.camera_fps_spin.value(),
            "camera_fourcc": self.camera_fourcc_combo.currentData(),
            # FPV
            "fpv_channel": self.fpv_channel_spin.value(),
            "fpv_channel_width": self.fpv_cw_combo.currentData(),
            "fpv_key": self.fpv_key_edit.text().strip(),
            "fpv_link_id": self.fpv_link_id_spin.value(),
            "fpv_codec": self.fpv_codec_combo.currentData(),
            "fpv_width": self.fpv_w_spin.value(),
            "fpv_height": self.fpv_h_spin.value(),
            "fpv_fps": self.fpv_fps_spin.value(),
            # 串口
            "serial_port": self.port_combo.currentText().strip(),
            "serial_baudrate": int(self.baudrate_combo.currentData()
                                   or self.baudrate_combo.currentText()),
            "serial_timeout": self.timeout_spin.value(),
            "serial_prefix": int(self.prefix_edit.text().strip(), 16) if self.prefix_edit.text().strip() else 0x5678,
            # 标定路径
            "homography_file": self._file_edits["homography_file"].text().strip(),
            "camera_matrix_file": self._file_edits["camera_matrix_file"].text().strip(),
            "dist_coeffs_file": self._file_edits["dist_coeffs_file"].text().strip(),
            # 通用
            "timer_interval": self.timer_spin.value(),
            "coordinate_scale": self.scale_spin.value(),
            "coordinate_offset": self.offset_spin.value(),
            "fps_display": self.fps_check.isChecked(),
            "grid_crop_ratio": self.grid_crop_spin.value(),
            # 抓取范围
            "grab_range_x_ratio": self.grab_x_spin.value(),
            "grab_range_y_ratio": self.grab_y_spin.value(),
            "grab_range_radius_ratio": self.grab_r_spin.value(),
        }

    # ──────────────────────────── 事件处理 ────────────────────────────

    def _on_apply(self):
        """应用按钮：标记修改（不直接操作硬件）"""
        self._modified = True

    def _on_ok(self):
        """确定按钮：接受并关闭（硬件操作由调用方处理）"""
        self._modified = True
        self.accept()

    @property
    def is_modified(self):
        """是否有修改被应用"""
        return self._modified

    @property
    def collected_values(self):
        """获取对话框中配置值（调用方在 accept 后读取）"""
        return self._collect_values()

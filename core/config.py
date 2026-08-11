"""
配置管理模块 - 集中管理所有配置项
"""
import copy
import os
import re
import sys
import yaml

# 项目根目录（基于 core/config.py 的位置自动计算得到 souiju12/）
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


class Config:
    """系统配置管理类"""

    # 棋盘格标定参数（一处修改，全局生效）
    CHESSBOARD_PATTERN = (11, 8)       # 内角点数 (列, 行)
    CHESSBOARD_SQUARE_SIZE = 0.03      # 方格边长（米）

    # 标定算法参数 (四) - cornerSubPix 窗口/迭代
    CORNER_SUBPIX_WIN_SIZE = (11, 11)        # 亚像素角点优化窗口大小
    CORNER_SUBPIX_ZERO_ZONE = (-1, -1)       # 亚像素搜索零区
    CALIB_CRITERIA_MAX_ITER = 30             # 标定迭代终止次数
    CALIB_CRITERIA_EPS = 0.001               # 标定迭代终止精度

    # 算法阈值 (六)
    HOMOGRAPHY_DIV_EPS = 1e-9                # 齐次坐标除零保护阈值
    SIGN_CORRECTION_THRESHOLD = 0.5          # 符号校正像素偏离阈值

    # 可持久化到 YAML 的配置项白名单（与 GUI 设置对话框保持同步）
    _YAML_PERSIST_KEYS = {
        "serial_port", "serial_baudrate", "serial_timeout", "serial_prefix",
        "camera_id", "camera_width", "camera_height",
        "camera_fps", "camera_fourcc", "grid_crop_ratio",
        "camera_vflip", "camera_hflip",
        "camera_source", "fpv_channel", "fpv_channel_width", "fpv_key", "fpv_link_id",
        "fpv_codec", "fpv_width", "fpv_height", "fpv_fps",
        "homography_file", "camera_matrix_file", "dist_coeffs_file",
        "timer_interval", "coordinate_scale", "coordinate_offset",
        "fps_display",
        "grab_range_x_ratio", "grab_range_y_ratio", "grab_range_radius_ratio",
        "show_overlays",
        "gui_mode",
        "coord_offset_x_mm", "coord_offset_y_mm",
    }

    # Windows 盘符绝对路径，如 d:/code/...（在 Linux 上 os.path.isabs 判断为 False）
    _WIN_DRIVE_RE = re.compile(r'^[a-zA-Z]:[\\/]')

    # 文件路径默认值（相对路径，运行时统一解析为基于 PROJECT_ROOT 的绝对路径）
    _DEFAULT_FILE_PATHS = {
        "homography_file": "calibration_data/homography.npy",
        "camera_matrix_file": "calibration_data/camera_matrix.npy",
        "dist_coeffs_file": "calibration_data/dist_coeffs.npy",
        "fpv_key": "gs.key",
    }

    def __init__(self, config_file=None):
        """
        初始化配置

        Args:
            config_file: 配置文件路径 (YAML格式)
        """
        # 检测操作系统
        self.is_windows = sys.platform.startswith("win")

        # 项目根目录（全局可访问，用于解析相对路径）
        self.PROJECT_ROOT = PROJECT_ROOT

        # 默认配置（根据系统自动适配）
        if self.is_windows:
            self.serial_port = "COM10"
            self.camera_id = 0  # Windows 默认摄像头
            self.camera_vflip = True   # Windows 下采集卡画面上下翻转，需修正
            self.camera_hflip = False
        else:
            self.serial_port = "/dev/ttyUSB0"
            self.camera_id = 0  # Ubuntu USB相机
            self.camera_vflip = False
            self.camera_hflip = False

        self.serial_baudrate = 9600
        self.serial_timeout = 0.1
        self.serial_prefix = 0x5678
        self.coordinate_scale = 1000      # 米→毫米缩放因子
        self.coordinate_offset = 5000      # 偏移量，使负坐标映射到协议的正数范围
        self.camera_width = 1920  # 摄像头宽度
        self.camera_height = 1080  # 摄像头高度

        # ── 摄像头额外参数 (二) ──
        self.camera_fps = 30                     # 目标帧率
        self.camera_scan_max_index = 10          # 枚举摄像头时的最大扫描索引
        self.camera_fallback_width = 640         # 无摄像头时回退画面宽度
        self.camera_fallback_height = 480        # 无摄像头时回退画面高度
        self.camera_fourcc = 'MJPG'              # 视频编码格式

        # ── FPV 参数 ──
        self.camera_source = "usb"                # 信号源: "usb" 或 "fpv"
        self.fpv_channel = 161                    # FPV 信道
        self.fpv_channel_width = 20               # 信道宽度 (20/40/80)
        self.fpv_key = "gs.key"  # WFB 密钥文件路径（相对路径，resolve_path 解析）
        self.fpv_link_id = 7669206                # WFB 链路 ID（防串信号）
        self.fpv_codec = "h265"                   # 视频编码: h264/h265
        self.fpv_width = 1280                     # 视频宽度
        self.fpv_height = 720                     # 视频高度
        self.fpv_fps = 120                        # 帧率

        # ── 协议参数 ──
        self.protocol_max_value = 9999           # 协议数据最大值 (0~9999)

        # ── GUI 布局参数 (五) ──
        self.gui_button_panel_width = 800
        self.gui_grid_button_size = 190
        self.gui_grid_rows = 3
        self.gui_grid_cols = 1
        self.gui_video_max_width = 1600   # 右侧视频显示最大宽度
        self.grid_crop_ratio = 1.0   # 格子截图裁剪比例
        self.gui_mode = "3"          # GUI 模式: "3" 三格大图 / "6" 六格小图

        # 两套 GUI 模式预设（截图格布局 + 飞手路线编号 成对整体切换）
        self.GUI_PRESETS = {
            "3": {"gui_button_panel_width": 800, "gui_grid_rows": 3,
                  "gui_grid_cols": 1, "field_nums": [1, 3, 5, 6, 4, 2]},
            "6": {"gui_button_panel_width": 400, "gui_grid_rows": 6,
                  "gui_grid_cols": 1, "field_nums": [1, 2, 3, 4, 5, 6]},
        }

        # ── 抓取范围圆 (可视化) ──
        # 圆心/半径存为占画面宽高的比例 (0~1)：画圆时按当前帧尺寸现场换算像素
        self.grab_range_x_ratio = 0.5
        self.grab_range_y_ratio = 0.5
        self.grab_range_radius_ratio = 0.0

        # 画面叠加线总开关：范围圆 + 十字准星（标定时可关闭，画面保持干净）
        self.show_overlays = True

        # ── 坐标偏差修正 (mm) ──
        # 叠加到映射后的平面坐标上，用于修正机构/安装的系统性偏差。
        # 正值方向：X 向右为正、Y 向上为正（与画面直角坐标系一致）。
        self.coord_offset_x_mm = 0.0
        self.coord_offset_y_mm = 0.0

        # ── UI 预设列表 (七) ──
        self.resolution_presets = [
            ("640×480", 640, 480),
            ("1280×720", 1280, 720),
            ("1920×1080", 1920, 1080),
        ]
        self.serial_ports_windows = [f"COM{i}" for i in range(1, 11)]
        self.serial_ports_linux = [
            "/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyUSB2",
            "/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyS0",
        ]

        self.homography_file = "calibration_data/homography.npy"
        self.camera_matrix_file = "calibration_data/camera_matrix.npy"
        self.dist_coeffs_file = "calibration_data/dist_coeffs.npy"

        # 将所有文件路径统一规范化为相对路径（跨平台可移植）
        self._normalize_file_paths()

        # 相机内参（如果未提供则使用默认值）
        self.camera_matrix = None
        self.dist_coeffs = None

        # GUI 配置
        self.fps_display = True
        self.timer_interval = 30  # 毫秒

        # 出厂默认值快照（录制于 YAML 加载前，用于差异比对）
        self._defaults = {k: getattr(self, k) for k in self._YAML_PERSIST_KEYS}

        # 加载配置文件（如果提供）
        if config_file and os.path.exists(config_file):
            self._load_from_yaml(config_file)

    def _normalize_file_paths(self):
        """将配置中的文件路径统一规范化为相对 PROJECT_ROOT 的路径

        属性始终保存相对路径（跨平台可移植），需要绝对路径时用 resolve_path() 解析。
        用户自选的项目外本机绝对路径（外部文件）原样保留。
        """
        path_attrs = list(self._DEFAULT_FILE_PATHS)
        for attr in path_attrs:
            path = getattr(self, attr)
            if not path:
                continue
            path = str(path).replace('\\', '/')
            if os.path.isabs(path) or self._WIN_DRIVE_RE.match(path):
                rel = self._to_project_relative(path)
                if rel is not None:
                    if rel != path:
                        print(f"[INFO] 路径 '{path}' 已转换为项目相对路径: {rel}")
                    path = rel
                elif self._WIN_DRIVE_RE.match(path) and not self.is_windows:
                    print(f"[WARNING] 无法在当前系统使用路径 '{path}'，已回退默认路径 {self._DEFAULT_FILE_PATHS[attr]}")
                    path = self._DEFAULT_FILE_PATHS[attr]
                # 本机绝对路径且位于项目外：保留原样（resolve_path 会原样返回）
            setattr(self, attr, path)

    def resolve_path(self, path):
        """将配置文件路径解析为基于 PROJECT_ROOT 的绝对路径（点使用时调用）

        - 相对路径（calibration_data/homography.npy）→ 项目内绝对路径
        - 其他操作系统的绝对路径（如 Windows 的 d:/code/...）→ 自动转换为项目内路径
        - 本机绝对路径 → 原样返回
        """
        if not path:
            return path
        path = str(path).replace('\\', '/')
        if os.path.isabs(path):
            return path
        if self._WIN_DRIVE_RE.match(path):
            rel = self._foreign_to_project_relative(path)
            if rel is None:
                return path  # 无法识别，保持原样（由上层给出明确的文件不存在错误）
            return os.path.join(self.PROJECT_ROOT, rel)
        return os.path.join(self.PROJECT_ROOT, path)

    def _to_project_relative(self, path):
        """将任意绝对路径转换为相对 PROJECT_ROOT 的路径

        - 本机绝对路径：位于 PROJECT_ROOT 内则转为相对，否则返回 None（保留原样）
        - 其他操作系统的绝对路径（如 Windows 的 d:/...）：定位项目目录名后截取相对部分
        """
        path = str(path).replace('\\', '/')
        if self._WIN_DRIVE_RE.match(path) and not self.is_windows:
            return self._foreign_to_project_relative(path)
        root = self.PROJECT_ROOT.replace('\\', '/')
        if path.startswith(root + '/'):
            return path[len(root) + 1:]
        return None

    @classmethod
    def _foreign_to_project_relative(cls, path):
        """将其他操作系统的绝对路径转换为相对 PROJECT_ROOT 的路径

        例：Windows 的 d:/code/souiju12_no_detect/calibration_data/homography.npy
        在当前 Linux 上会转换为 calibration_data/homography.npy。
        无法定位项目目录名时返回 None，由调用方回退默认路径。
        """
        m = cls._WIN_DRIVE_RE.match(path)
        rest = path[m.end():].lstrip('/')
        marker = os.path.basename(PROJECT_ROOT) + '/'
        if marker in rest:
            return rest.split(marker, 1)[1]
        return None

    def _load_from_yaml(self, config_file):
        """从 YAML 文件加载用户配置覆盖（扁平结构，key 直映射属性名）"""
        try:
            import numpy as np
            with open(config_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if data is None:
                return
            # 旧版像素抓取范围 → 按配置分辨率换算为比例（-1 自动居中 → 0.5）
            if "grab_range_x" in data and "grab_range_x_ratio" not in data:
                self.grab_range_x_ratio = self._px_to_ratio(
                    data["grab_range_x"], data.get("camera_width", self.camera_width))
            if "grab_range_y" in data and "grab_range_y_ratio" not in data:
                self.grab_range_y_ratio = self._px_to_ratio(
                    data["grab_range_y"], data.get("camera_height", self.camera_height))
            if "grab_range_radius" in data and "grab_range_radius_ratio" not in data:
                self.grab_range_radius_ratio = self._px_to_ratio(
                    data["grab_range_radius"], data.get("camera_width", self.camera_width))
            for key, value in data.items():
                if isinstance(value, dict):
                    print(f"  [INFO] 跳过旧格式段 '{key}'，下次保存后自动更新")
                    continue
                if key == 'camera_matrix':
                    self.camera_matrix = np.array(value, dtype=np.float32)
                elif key == 'dist_coeffs':
                    self.dist_coeffs = np.array(value, dtype=np.float32).reshape(-1, 1)
                elif key not in self._YAML_PERSIST_KEYS:
                    print(f"  [INFO] 跳过未知配置项 '{key}'")
                    continue
                elif key == 'serial_port':
                    port = str(value)
                    if self.is_windows:
                        if port.startswith('/dev/'):
                            print(f"  [WARNING] 端口 '{port}' 是 Linux 格式，当前为 Windows，已跳过")
                            continue
                    else:
                        if port.upper().startswith('COM'):
                            print(f"  [WARNING] 端口 '{port}' 是 Windows 格式，当前为 Linux，已跳过")
                            continue
                    self.serial_port = port
                else:
                    setattr(self, key, value)
            self._normalize_file_paths()
        except Exception as e:
            print(f"[WARNING] 加载配置文件失败: {e}，使用默认配置")

    @staticmethod
    def _px_to_ratio(px, ref_size) -> float:
        """像素值 → 占画面比例 (0~1)；负值/无参考尺寸时回退 0.5"""
        try:
            px = float(px)
        except (TypeError, ValueError):
            return 0.5
        if px < 0 or not ref_size or ref_size <= 0:
            return 0.5
        return max(0.0, min(1.0, px / float(ref_size)))

    def to_dict(self):
        """导出所有持久化配置项为字典"""
        d = {}
        # 文件路径属性已规范化为相对路径，直接导出即可（跨平台可移植）
        for key in self._YAML_PERSIST_KEYS:
            d[key] = getattr(self, key, None)
        for extra in ['camera_fps', 'camera_scan_max_index', 'camera_fallback_width',
                       'camera_fallback_height', 'camera_fourcc', 'protocol_max_value',
                       'grid_crop_ratio']:
            d[extra] = getattr(self, extra, None)
        return d

    # ─────────────── 事务安全（用于配置修改的回退） ───────────────

    def snapshot(self) -> dict:
        """保存当前全部配置的快照（用于回退）"""
        return copy.deepcopy(self.to_dict())

    def restore(self, snapshot: dict):
        """从快照恢复配置"""
        for key, value in snapshot.items():
            if hasattr(self, key):
                setattr(self, key, value)

    _VALIDATORS = {
        "camera_id": lambda v: isinstance(v, int) and 0 <= v <= 99,
        "camera_width": lambda v: isinstance(v, int) and 160 <= v <= 7680,
        "camera_height": lambda v: isinstance(v, int) and 120 <= v <= 4320,
        "camera_source": lambda v: v in ("usb", "fpv"),
        "fpv_channel": lambda v: isinstance(v, int) and 1 <= v <= 200,
        "camera_fps": lambda v: isinstance(v, int) and 1 <= v <= 120,
        "camera_scan_max_index": lambda v: isinstance(v, int) and 1 <= v <= 99,
        "camera_fallback_width": lambda v: isinstance(v, int) and 160 <= v <= 7680,
        "camera_fallback_height": lambda v: isinstance(v, int) and 120 <= v <= 4320,
        "protocol_max_value": lambda v: isinstance(v, int) and 1 <= v <= 99999,
        "serial_baudrate": lambda v: v in [9600, 19200, 38400, 57600, 115200, 230400],
        "serial_timeout": lambda v: 0.01 <= v <= 10.0,
        "serial_prefix": lambda v: isinstance(v, int) and 0x0000 <= v <= 0xFFFF,
        "timer_interval": lambda v: 10 <= v <= 1000,
        "coordinate_scale": lambda v: 1 <= v <= 100000,
        "coordinate_offset": lambda v: 0 <= v <= 99999,
        "grab_range_x_ratio": lambda v: isinstance(v, (int, float)) and 0.0 <= v <= 1.0,
        "grab_range_y_ratio": lambda v: isinstance(v, (int, float)) and 0.0 <= v <= 1.0,
        "grab_range_radius_ratio": lambda v: isinstance(v, (int, float)) and 0.0 <= v <= 1.0,
        "show_overlays": lambda v: isinstance(v, bool),
        "gui_mode": lambda v: v in ("3", "6"),
        "coord_offset_x_mm": lambda v: isinstance(v, (int, float)) and -10000.0 <= v <= 10000.0,
        "coord_offset_y_mm": lambda v: isinstance(v, (int, float)) and -10000.0 <= v <= 10000.0,
    }

    def validate_param(self, key: str, value) -> bool:
        """校验单个参数的有效性"""
        validator = self._VALIDATORS.get(key)
        if validator is not None:
            return validator(value)
        return True  # 无校验器的参数默认通过

    def update_from_dict_safe(self, data: dict) -> list[str]:
        """安全批量更新配置，返回所有校验失败的参数列表"""
        errors = []
        for key, value in data.items():
            if hasattr(self, key):
                if not self.validate_param(key, value):
                    errors.append(f"{key}={value}")
                    continue
                setattr(self, key, value)
        # 重新规范化路径（新值可能是本机绝对路径或相对路径）
        self._normalize_file_paths()
        return errors

    def save_to_yaml(self, filepath):
        """将用户修改的配置保存到 YAML（扁平结构，仅存与默认值不同的项）

        Args:
            filepath: 保存路径
        """
        data = {}
        current = self.to_dict()
        for key in self._YAML_PERSIST_KEYS:
            if key in current:
                data[key] = current[key]
        # 相机内参（外部工具写入，有值则存）
        if self.camera_matrix is not None:
            data['camera_matrix'] = self.camera_matrix.tolist()
        if self.dist_coeffs is not None:
            data['dist_coeffs'] = self.dist_coeffs.ravel().tolist()
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
            print(f"✅ 配置已保存: {filepath}")
        except Exception as e:
            print(f"[WARNING] 保存配置文件失败: {e}")

    def get_camera_params(self):
        """获取相机参数"""
        if self.camera_matrix is None:
            import numpy as np
            # 默认相机内参
            self.camera_matrix = np.array([
                [1000, 0, self.camera_width / 2],
                [0, 1000, self.camera_height / 2],
                [0, 0, 1]
            ], dtype=np.float32)

        if self.dist_coeffs is None:
            import numpy as np
            self.dist_coeffs = np.zeros((4, 1), dtype=np.float32)

        return self.camera_matrix, self.dist_coeffs

    def validate(self):
        """验证配置有效性"""
        errors = []
        warnings = []

        if not os.path.exists(self.resolve_path(self.homography_file)):
            warnings.append(f"单应性矩阵文件不存在: {self.homography_file}，坐标映射功能不可用")

        if (not os.path.exists(self.resolve_path(self.camera_matrix_file))
                or not os.path.exists(self.resolve_path(self.dist_coeffs_file))):
            warnings.append("畸变参数文件不存在，畸变矫正未启用（不影响坐标映射）")

        if self.camera_id < 0:
            errors.append(f"无效的相机ID: {self.camera_id}")

        # 打印警告
        for w in warnings:
            print(f"[WARNING] {w}")

        return len(errors) == 0, errors


# 全局配置实例（YAML 配置文件路径基于 PROJECT_ROOT 定位）
config = Config(config_file=os.path.join(PROJECT_ROOT, "camera_params.yaml"))

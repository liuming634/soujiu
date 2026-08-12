"""
摄像头管理模块 - 集成采集和去畸变（带断线重连）
"""
import time
import cv2
import os
import numpy as np
from core.config import config
from hardware.undistorter import UndistortMixin
from core.utils import log_error, make_status_frame

# 全局抑制 OpenCV 控制台警告（不影响功能）
os.environ["OPENCV_LOG_LEVEL"] = "ERROR"
try:
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
except Exception:
    pass


def get_camera_backends():
    """按平台返回摄像头后端列表 [(后端标志, 名称), ...]（枚举/初始化共用）"""
    if config.is_windows:
        return [(cv2.CAP_DSHOW, "DSHOW"),
                (cv2.CAP_MSMF, "MSMF")]
    return [(cv2.CAP_V4L2, "V4L2"),
            (cv2.CAP_ANY, "ANY")]


class CameraManager(UndistortMixin):
    """摄像头管理器（集成采集和去畸变）"""

    # 断线重连参数
    _RETRY_INTERVAL_INITIAL = 1.0   # 初始重试间隔（秒）
    _RETRY_INTERVAL_FACTOR = 1.5    # 重试失败后的间隔倍增因子
    _RETRY_INTERVAL_MAX = 5.0       # 重试间隔上限（秒）
    _RETRY_LOG_THROTTLE = 5.0       # 重连日志节流间隔（秒）

    def __init__(self):
        self.camera_id = config.camera_id
        self.width = config.camera_width
        self.height = config.camera_height
        self._cap = None

        # 断线重连状态
        self._connected = False          # 当前是否正常读取帧
        self._last_reconnect_attempt = 0.0   # 上次重试时间戳
        self._reconnect_interval = self._RETRY_INTERVAL_INITIAL  # 重试间隔（秒）
        self._last_log_time = 0.0            # 上次重连日志时间（防刷屏）
        self._last_frame_size = (config.camera_height, config.camera_width)  # 最近一次成功帧尺寸 (h, w)

        # 集成畸变矫正器
        self._init_undistorter(config.resolve_path(config.camera_matrix_file),
                               config.resolve_path(config.dist_coeffs_file))

        self._initialize_camera()
        self._connected = self._cap is not None

    # ─────── 缓存标记：是否有可用摄像头 ───────

    def is_available(self) -> bool:
        """摄像头是否可用"""
        return self._cap is not None

    def is_connected(self) -> bool:
        """摄像头当前是否正常连接（正在采集帧）"""
        return self._connected

    # ─────── 断线重连 ───────

    def _should_retry(self) -> bool:
        """是否到了重试的时间窗口"""
        if time.time() - self._last_reconnect_attempt >= self._reconnect_interval:
            self._last_reconnect_attempt = time.time()
            return True
        return False

    def _handle_disconnect(self):
        """标记断开并释放旧资源"""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._connected = False
        now = time.time()
        if now - self._last_log_time > self._RETRY_LOG_THROTTLE:
            print("[WARNING] ⚠️  摄像头已断开，正在尝试自动重连...")
            self._last_log_time = now

    def _create_status_frame(self, message: str) -> np.ndarray:
        """生成带状态文字的占位帧（无相机时在 GUI 上显示，保持与实拍同分辨率）"""
        return make_status_frame(message, self._last_frame_size,
                                 hint="Check camera connection")

    # ─────── 摄像头初始化 ───────

    def _try_open(self, camera_id, backend):
        """尝试用指定后端和索引打开摄像头并配置参数，返回是否成功"""
        cap = cv2.VideoCapture(camera_id, backend)
        if not cap.isOpened():
            cap.release()
            return None

        mjpg = cv2.VideoWriter_fourcc(*config.camera_fourcc)
        cap.set(cv2.CAP_PROP_FOURCC, mjpg)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, config.camera_fps)

        # 预热重试：采集卡打开后首帧常为空缓冲，需等几帧才有有效数据
        got_frame = False
        for _ in range(10):
            try:
                ret, frame = cap.read()
            except cv2.error:
                ret, frame = False, None
            if ret and frame is not None and frame.size > 0:
                got_frame = True
                break
            time.sleep(0.3)

        if not got_frame:
            cap.release()
            return None

        actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = cap.get(cv2.CAP_PROP_FPS)
        actual_fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        fourcc_str = ''.join(chr(b) if 32 <= b < 127 else f'\\x{b:02X}'
                            for b in [(actual_fourcc >> (8 * i)) & 0xFF for i in range(4)])

        print(f"  实际: {actual_width}x{actual_height}@{actual_fps:.0f} FOURCC=0x{actual_fourcc:08X} ({fourcc_str})")
        return cap

    def _initialize_camera(self):
        """初始化摄像头，失败则标记不可用"""
        try:
            print(f"🎥 摄像头 {self.camera_id} ({self.width}x{self.height}@{config.camera_fps})")

            for backend, name in get_camera_backends():
                self._cap = self._try_open(self.camera_id, backend)
                if self._cap is not None:
                    print(f"✅ 摄像头 {self.camera_id} 初始化成功 ({name})")
                    return

            print(f"  [WARNING] 摄像头 {self.camera_id} 不可用，"
                  f"请在 GUI 中通过「系统设置」选择可用摄像头")

        except Exception as e:
            log_error(e, "摄像头初始化失败")

        # 初始化失败，标记为不可用
        self._cap = None

    # ─────── 帧采集（集成去畸变 + 断线重连） ───────

    def _apply_orientation(self, frame):
        """按配置对原始帧做方向修正（上下/左右翻转，GUI 按钮实时切换）"""
        if frame is None or frame.size == 0:
            return frame
        if config.camera_vflip:
            frame = cv2.flip(frame, 0)
        if config.camera_hflip:
            frame = cv2.flip(frame, 1)
        return frame

    def read_frame(self):
        """
        读取一帧原始图像（内部自动处理断线重连）

        Returns:
            tuple: (success: bool, frame: np.ndarray)
            success=False 时 frame 为带有状态提示的占位图
        """
        # 情况1：_cap 为空（从未初始化 / 断开后正在等待重试）
        if self._cap is None:
            if self._should_retry():
                self._initialize_camera()
                if self._cap is not None:
                    # 重连成功
                    self._connected = True
                    print("✅ 摄像头已重新连接")
                    ret, frame = self._cap.read()
                    if ret and frame is not None:
                        self._last_frame_size = frame.shape[:2]
                        return True, self._apply_orientation(frame)
                    # 重连后读帧仍然失败，重新标记断开
                    self._handle_disconnect()
                else:
                    # 重连失败，增加下次重试间隔（最大 5 秒）
                    self._reconnect_interval = min(
                        self._reconnect_interval * self._RETRY_INTERVAL_FACTOR,
                        self._RETRY_INTERVAL_MAX)
            return False, self._create_status_frame("⏳ 相机重试中...")

        # 情况2：_cap 存在，正常读帧
        try:
            ret, frame = self._cap.read()
            if not ret or frame is None:
                self._handle_disconnect()
                return False, self._create_status_frame("⚠️ 相机已断开，正在重连...")

            # 如果之前是断开状态，现在恢复（比如重连后读帧成功）
            if not self._connected:
                self._connected = True
                self._reconnect_interval = self._RETRY_INTERVAL_INITIAL  # 重置重试间隔
                print("✅ 摄像头已恢复")

            self._last_frame_size = frame.shape[:2]
            return True, self._apply_orientation(frame)
        except Exception as e:
            log_error(e, "读取摄像头帧失败")
            self._handle_disconnect()
            return False, self._create_status_frame("⚠️ 相机异常，正在重连...")

    # ─────── 去畸变（由 UndistortMixin 提供 read_undistorted_frame/undistort/is_calibrated） ───────

    # ─────── 资源管理 ───────

    def release(self):
        """释放摄像头资源"""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            print("✅ 摄像头已释放")

    def __del__(self):
        self.release()

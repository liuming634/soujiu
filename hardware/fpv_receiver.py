import os
import sys
import time

_ext_dir = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', 'extern', 'fpv_rx', 'bin',
    'windows' if sys.platform.startswith('win') else 'linux'))
if _ext_dir not in sys.path:
    sys.path.insert(0, _ext_dir)

try:
    import fpv_rx
    FPV_RX_AVAILABLE = True
except (ImportError, OSError):
    fpv_rx = None
    FPV_RX_AVAILABLE = False
    print("[WARNING] fpv_rx 扩展不可用，FPV 图传功能已禁用（缺少编译产物时可忽略）")

import numpy as np

from core.config import config
from hardware.undistorter import UndistortMixin
from core.utils import make_status_frame


class FpvReceiver(UndistortMixin):
    """FPV 图传接收器（RTL8812AU + WFB-ng 协议），接口与 CameraManager 保持一致"""

    VID_PID = "0bda:8812"      # RTL8812AU 网卡 USB ID
    CH_WIDTH_MAP = {20: 0, 40: 1, 80: 2}

    def __init__(self):
        self._rx = fpv_rx.Receiver() if FPV_RX_AVAILABLE else None
        self._connected = False
        self._conn_params = None
        self._last_valid_time = 0.0
        self._last_frame = None
        self._ever_connected = False
        self._last_frame_size = (config.fpv_height, config.fpv_width)  # 最近一次成功帧尺寸 (h, w)

        # 与 USB 相机同一条链路：集成畸变矫正器
        self._init_undistorter(config.resolve_path(config.camera_matrix_file),
                               config.resolve_path(config.dist_coeffs_file))

    def open(self, vid_pid=VID_PID, channel=149, channel_width=20,
             key_path="gs.key", link_id=7669206,
             codec="h265", video_width=1280, video_height=720, fps=120):
        if self._rx is None:
            print("  [WARNING] fpv_rx 扩展不可用，无法初始化 FPV 接收器")
            return False
        cw = self.CH_WIDTH_MAP.get(channel_width, 0)
        self._conn_params = (vid_pid, channel, cw, key_path, link_id,
                             codec, video_width, video_height, fps)
        self._ever_connected = False
        ok = self._rx.start(vid_pid, channel, cw, key_path, link_id,
                            codec, video_width, video_height, fps)
        self._connected = ok
        if ok:
            self._last_valid_time = time.time()
        return ok

    def read_frame(self, timeout_ms=1):
        if self._rx is None:
            return False, self._status_frame("FPV 扩展不可用")
        fd = self._rx.recv(timeout_ms)

        if fd.valid and fd.width > 0 and fd.height > 0:
            try:
                arr = np.frombuffer(fd.data, dtype=np.uint8).reshape((fd.height, fd.width, 3))
            except Exception:
                return False, self._status_frame("等待 FPV 信号...")
            self._last_frame = arr
            self._last_frame_size = arr.shape[:2]
            self._last_valid_time = time.time()
            self._ever_connected = True
            if not self._connected:
                self._connected = True
                print("✅ FPV 信号已恢复")
            return True, arr

        if (self._last_frame is not None
                and self._last_valid_time > 0
                and time.time() - self._last_valid_time < 2.0):
            return True, self._last_frame
        return False, self._status_frame("等待 FPV 信号...")

    def is_available(self) -> bool:
        return self._rx is not None and self._conn_params is not None and self._connected

    def is_connected(self) -> bool:
        return self._connected

    def release(self):
        if self._rx is not None:
            try:
                self._rx.stop()
            except Exception:
                pass
        if self._conn_params:
            self._connected = False
            self._last_frame = None

    def _status_frame(self, message: str) -> np.ndarray:
        return make_status_frame(message, self._last_frame_size)

    def __del__(self):
        self.release()

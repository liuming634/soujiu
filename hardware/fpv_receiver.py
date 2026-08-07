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

import cv2
import numpy as np

from core.config import config
from hardware.undistorter import Undistorter


class FpvReceiver:
    CH_WIDTH_MAP = {20: 0, 40: 1, 80: 2}

    def __init__(self):
        self._rx = fpv_rx.Receiver() if FPV_RX_AVAILABLE else None
        self._waiting_frame = None
        self._connected = False
        self._conn_params = None
        self._last_valid_time = 0.0
        self._last_frame = None
        self._ever_connected = False

        # 与 USB 相机同一条链路：集成畸变矫正器
        self._undistorter = Undistorter()
        self._undistorter.load(config.resolve_path(config.camera_matrix_file),
                               config.resolve_path(config.dist_coeffs_file))

    def open(self, vid_pid="0bda:8812", channel=149, channel_width=20,
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

    def is_calibrated(self) -> bool:
        return self._undistorter.is_calibrated()

    def undistort(self, frame):
        return self._undistorter.undistort(frame)

    def read_undistorted_frame(self):
        ret, frame = self.read_frame()
        if not ret:
            return False, frame
        return True, self._undistorter.undistort(frame)

    def release(self):
        if self._rx is not None:
            try:
                self._rx.stop()
            except Exception:
                pass
        if self._conn_params:
            self._connected = False
            self._waiting_frame = None
            self._last_frame = None

    def _status_frame(self, message: str) -> np.ndarray:
        self._waiting_frame = None
        h, w = 480, 640
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        font = cv2.FONT_HERSHEY_SIMPLEX
        text_size = cv2.getTextSize(message, font, 0.8, 2)[0]
        tx = (w - text_size[0]) // 2
        ty = h // 2 - 10
        cv2.putText(frame, message, (tx, ty), font, 0.8, (0, 165, 255), 2)
        return frame

    def __del__(self):
        self.release()

"""
畸变矫正模块 - 相机内参标定与帧去畸变
"""
import cv2
import numpy as np
import os
from core.utils import log_error


class Undistorter:
    """畸变矫正器：加载/保存畸变参数，对每一帧做去畸变"""

    def __init__(self):
        self.camera_matrix = None   # 3x3 相机内参矩阵
        self.dist_coeffs = None     # 畸变系数 (k1, k2, p1, p2, ...)
        self._map1 = None           # remap x 映射缓存
        self._map2 = None           # remap y 映射缓存

    def load(self, camera_matrix_file, dist_coeffs_file):
        """从 .npy 文件加载畸变参数，成功返回 True"""
        try:
            if (os.path.exists(camera_matrix_file)
                    and os.path.exists(dist_coeffs_file)):
                self.camera_matrix = np.load(camera_matrix_file)
                self.dist_coeffs = np.load(dist_coeffs_file)
                self._map1 = None  # 缓存失效，等下次 undistort 重建
                print("✅ 畸变参数已加载")
                print(f"   内参矩阵:\n{self.camera_matrix}")
                print(f"   畸变系数: {self.dist_coeffs.ravel()}")
                return True
        except Exception as e:
            log_error(e, "加载畸变参数失败")
        return False

    def save(self, camera_matrix_file, dist_coeffs_file):
        """保存畸变参数到 .npy 文件"""
        try:
            dir_name = os.path.dirname(camera_matrix_file)
            if dir_name and not os.path.exists(dir_name):
                os.makedirs(dir_name)
            np.save(camera_matrix_file, self.camera_matrix)
            np.save(dist_coeffs_file, self.dist_coeffs)
            print("✅ 畸变参数已保存")
            print(f"   内参矩阵: {camera_matrix_file}")
            print(f"   畸变系数: {dist_coeffs_file}")
        except Exception as e:
            log_error(e, "保存畸变参数失败")
            raise

    def is_calibrated(self):
        """是否已加载畸变参数"""
        return self.camera_matrix is not None

    def undistort(self, frame):
        """
        对一帧图像做去畸变

        Args:
            frame: 原始 BGR 帧 (numpy.ndarray)

        Returns:
            去畸变后的帧（未标定时返回原图）
        """
        if not self.is_calibrated():
            return frame

        h, w = frame.shape[:2]
        # remap 缓存按分辨率缓存，分辨率变了就重建
        if (self._map1 is None
                or self._map1.shape[:2] != (h, w)):
            new_mtx, roi = cv2.getOptimalNewCameraMatrix(
                self.camera_matrix, self.dist_coeffs, (w, h), 1, (w, h)
            )
            self._map1, self._map2 = cv2.initUndistortRectifyMap(
                self.camera_matrix, self.dist_coeffs, None,
                new_mtx, (w, h), cv2.CV_32FC1
            )
            self._roi = roi
            self._new_mtx = new_mtx

        undist = cv2.remap(frame, self._map1, self._map2, cv2.INTER_LINEAR)

        # 可选：裁剪掉畸变校正后边缘的黑边
        x, y, w, h = self._roi
        undist = undist[y:y + h, x:x + w]
        undist = cv2.resize(undist, (frame.shape[1], frame.shape[0]),
                            interpolation=cv2.INTER_LINEAR)

        return undist


class UndistortMixin:
    """去畸变集成 mixin：供采集类（CameraManager 等）复用，统一采集路线接口。

    要求子类：
      - 定义 read_frame()，返回 (success, frame)
      - 构造时调用 self._init_undistorter(matrix_file, coeffs_file)
    """

    def _init_undistorter(self, matrix_file, coeffs_file):
        """加载畸变参数（未标定时 is_calibrated() 返回 False，undistort 原样返回）"""
        self._undistorter = Undistorter()
        self._undistorter.load(matrix_file, coeffs_file)

    def is_calibrated(self):
        """畸变参数是否已加载"""
        return self._undistorter.is_calibrated()

    def undistort(self, frame):
        """对任意帧做去畸变（未标定时返回原图）"""
        return self._undistorter.undistort(frame)

    def read_undistorted_frame(self):
        """读取一帧并做去畸变（采集+预处理一步完成）"""
        ret, frame = self.read_frame()
        if not ret:
            return False, frame
        return True, self._undistorter.undistort(frame)



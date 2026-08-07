"""
坐标映射模块 - 像素坐标到平面物理坐标的转换
"""
import cv2
import numpy as np
import os
from core.config import config
from core.utils import log_error


class PixelToPlaneMapper:
    """像素坐标到平面物理坐标的映射器"""

    def __init__(self, homography_file=None, H=None, image_size=None):
        """
        初始化映射器

        Args:
            homography_file: 单应性矩阵文件路径 (.npy)
            H: 直接传入 3x3 单应性矩阵
            image_size: (宽, 高) 图像尺寸，设置后以画面中心为原点 (0,0)
        """
        self.H = None
        self.center_offset = None  # 画面中心在平面坐标系中的偏移量
        self._img_size = image_size  # 保存图像尺寸，用于符号校正和中心偏移

        try:
            if homography_file:
                if not os.path.exists(homography_file):
                    raise FileNotFoundError(f"文件不存在: {homography_file}")

                loaded_H = np.load(homography_file)
                if loaded_H.shape != (3, 3):
                    raise ValueError(f"矩阵形状错误: {loaded_H.shape}, 期望 (3,3)")
                self.H = loaded_H
                print(f"✅ 单应性矩阵加载成功: {homography_file}")

            elif H is not None:
                H_arr = np.array(H, dtype=np.float64)
                if H_arr.shape != (3, 3):
                    raise ValueError(f"矩阵形状错误: {H_arr.shape}, 期望 (3,3)")
                self.H = H_arr
                print("✅ 单应性矩阵设置成功")
            else:
                raise ValueError("需要提供 homography_file 或 H")

            # 初始化时用 image_size 算中心偏移（后续可通过 set_image_size 更新）
            if image_size is not None and self.H is not None:
                self._compute_center_offset(image_size)

        except Exception as e:
            log_error(e, "单应性矩阵初始化失败")
            raise

    # ─────────── 公开方法 ───────────

    def set_image_size(self, w: int, h: int):
        """设置实际帧尺寸，重新计算中心偏移

        在以下情况调用：
          - 启动后知道实际帧尺寸时
          - 标定完新的单应性矩阵后（搭配 calibrate_from_array 的 image_size 使用）
        """
        self._img_size = (w, h)
        if self.H is not None:
            self._compute_center_offset((w, h))

    def ensure_image_size(self, w: int, h: int) -> bool:
        """仅在尺寸变化时更新中心偏移，尺寸未变直接返回 False

        适合每帧调用：两种信号源共用，真实帧一到即自动生效。
        """
        if self._img_size == (w, h):
            return False
        self.set_image_size(w, h)
        return True

    def _compute_center_offset(self, image_size):
        """计算画面中心在平面坐标系中的偏移量

        Args:
            image_size: (宽, 高) 图像尺寸
        """
        try:
            w, h = image_size
            center_u = w / 2.0
            center_v = h / 2.0

            pt = np.array([center_u, center_v, 1.0], dtype=np.float64)
            world_pt = self.H @ pt

            if abs(world_pt[2]) < config.HOMOGRAPHY_DIV_EPS:
                print("[WARNING] 画面中心变换时除数接近零，无法启用中心原点模式")
                return

            world_pt = world_pt / world_pt[2]
            self.center_offset = (float(world_pt[0]), float(world_pt[1]))
            print(f"📐 画面中心原点模式: 中心偏移 X={self.center_offset[0]:.4f}m, Y={self.center_offset[1]:.4f}m")
        except Exception as e:
            log_error(e, "计算画面中心偏移量失败")

    def pixel_to_plane(self, u, v):
        """
        将像素坐标转换为平面物理坐标

        Args:
            u: 像素 x 坐标
            v: 像素 y 坐标

        Returns:
            tuple: (X, Y) 平面物理坐标（米），失败时返回 (None, None)
        """
        if self.H is None:
            print("[ERROR] 单应性矩阵未初始化")
            return None, None

        try:
            pt = np.array([u, v, 1.0], dtype=np.float64)

            # 齐次坐标变换
            world_pt = self.H @ pt

            # 检查除数是否接近零
            if abs(world_pt[2]) < config.HOMOGRAPHY_DIV_EPS:
                print(f"[WARNING] 除数接近零 (u={u}, v={v})")
                return None, None

            # 归一化
            world_pt = world_pt / world_pt[2]
            x, y = float(world_pt[0]), float(world_pt[1])

            # 减去画面中心偏移，使画面中心为原点 (0,0)
            if self.center_offset is not None:
                x -= self.center_offset[0]
                y -= self.center_offset[1]

            # ── 强制符号与画面直角坐标系一致 ──
            # 不管棋盘格怎么摆放，保证：
            #   画面右侧 → X 为正，画面左侧 → X 为负
            #   画面上方 → Y 为正，画面下方 → Y 为负
            if self._img_size is not None:
                w, h = self._img_size
                cx, cy = w / 2.0, h / 2.0

                # X 符号校正
                if abs(u - cx) > config.SIGN_CORRECTION_THRESHOLD:  # 偏离中心至少半像素
                    if (u > cx and x < 0) or (u < cx and x > 0):
                        x = -x

                # Y 符号校正（图像 v 向下为正，我们要 Y 向上为正）
                if abs(v - cy) > config.SIGN_CORRECTION_THRESHOLD:
                    if (v < cy and y < 0) or (v > cy and y > 0):
                        y = -y

            return x, y

        except Exception as e:
            log_error(e, f"像素坐标 ({u}, {v}) 转换失败")
            return None, None

    def save(self, filepath):
        """保存单应性矩阵到文件"""
        try:
            if self.H is None:
                raise ValueError("单应性矩阵为空，无法保存")

            # 确保目录存在
            dir_name = os.path.dirname(filepath)
            if dir_name and not os.path.exists(dir_name):
                os.makedirs(dir_name)

            np.save(filepath, self.H)
            print(f"✅ 单应性矩阵已保存: {filepath}")
        except Exception as e:
            log_error(e, "保存单应性矩阵失败")
            raise

    @classmethod
    def calibrate(cls, image_path, pattern_size=None, square_size=None, image_size=None):
        """
        从棋盘格图像文件标定单应性矩阵

        Args:
            image_path: 棋盘格图像路径
            pattern_size: 棋盘格角点数量 (列, 行)
            square_size: 棋盘格方格边长（米）
            image_size: (宽, 高) 图像尺寸，设置后以画面中心为原点 (0,0)

        Returns:
            PixelToPlaneMapper 实例
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                raise FileNotFoundError(f"无法读取图像: {image_path}")
            return cls.calibrate_from_array(img, pattern_size, square_size, image_size)
        except Exception as e:
            log_error(e, "单应性矩阵标定失败")
            raise

    @classmethod
    def calibrate_from_array(cls, image_array, pattern_size=None, square_size=None, image_size=None):
        """
        直接从图像数组（numpy ndarray）标定单应性矩阵，无需保存文件

        Args:
            image_array: 图像数据 (BGR格式 numpy数组)
            pattern_size: 棋盘格角点数量 (列, 行)
            square_size: 棋盘格方格边长（米）
            image_size: (宽, 高) 图像尺寸，设置后以画面中心为原点 (0,0)

        Returns:
            PixelToPlaneMapper 实例
        """
        try:
            if pattern_size is None:
                pattern_size = config.CHESSBOARD_PATTERN
            if square_size is None:
                square_size = config.CHESSBOARD_SQUARE_SIZE
            # 转灰度
            gray = cv2.cvtColor(image_array, cv2.COLOR_BGR2GRAY)

            # 检测角点
            ret, corners = cv2.findChessboardCorners(gray, pattern_size, None)
            if not ret:
                raise Exception("棋盘格角点检测失败")

            # 亚像素优化
            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
                        config.CALIB_CRITERIA_MAX_ITER, config.CALIB_CRITERIA_EPS)
            corners = cv2.cornerSubPix(gray, corners,
                                       config.CORNER_SUBPIX_WIN_SIZE,
                                       config.CORNER_SUBPIX_ZERO_ZONE,
                                       criteria)

            # 生成世界坐标
            objp = np.zeros((pattern_size[0] * pattern_size[1], 3), np.float32)
            objp[:, :2] = np.mgrid[0:pattern_size[0], 0:pattern_size[1]].T.reshape(-1, 2)
            objp *= square_size
            world_pts = objp[:, :2]

            # 计算单应性矩阵
            H, _ = cv2.findHomography(corners.reshape(-1, 2), world_pts)
            if H is None:
                raise RuntimeError("findHomography 计算返回 None")

            print("✅ 单应性矩阵标定成功")
            return cls(H=H, image_size=image_size)
        except Exception as e:
            log_error(e, "单应性矩阵标定失败")
            raise

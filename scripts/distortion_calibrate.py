"""
畸变标定工具 - 独立脚本，采集棋盘格图像并标定相机内参

无需依赖 core.config，脚本自动定位项目目录。
帧率优化：waitKey(1) 实时显示 + 缩略图检测棋盘格 + 冷却计数代替硬阻塞。

使用方法:
    python scripts/distortion_calibrate.py

操作说明:
    - 将棋盘格在摄像头前移动，展示不同角度和位置
    - 检测到棋盘格时自动采集（每帧检测）
    - 集齐 15 张后自动标定，保存参数到 calibration_data/
"""
import cv2
import numpy as np
import os
import sys

# ── 标定参数（可直接修改） ──────────────────────────────────────
CHESSBOARD_PATTERN = (11, 8)          # 内角点数 (列, 行)
CHESSBOARD_SQUARE_SIZE = 0.03         # 方格边长（米）
TARGET_COUNT = 15                     # 采集目标帧数
CAMERA_ID = 0                         # 摄像头编号
CAMERA_WIDTH = 1920                   # 0 表示使用默认
CAMERA_HEIGHT = 1080                  # 0 表示使用默认

# ➜ 脚本自己定位项目目录，不再依赖 core.config
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
CALIB_DIR = os.path.join(PROJECT_ROOT, "calibration_data")
CAMERA_MATRIX_FILE = os.path.join(CALIB_DIR, "camera_matrix.npy")
DIST_COEFFS_FILE = os.path.join(CALIB_DIR, "dist_coeffs.npy")


def main():
    pattern = CHESSBOARD_PATTERN
    square_size = CHESSBOARD_SQUARE_SIZE

    print("=" * 60)
    print("📷 畸变标定工具")
    print("=" * 60)
    print(f"   棋盘格角点: {pattern[0]} x {pattern[1]}")
    print(f"   方格边长: {square_size} m")
    print(f"   目标帧数: {TARGET_COUNT}")
    print()
    print("   请在摄像头前移动棋盘格，展示不同角度")
    print("   检测到棋盘格时自动采集 (按 Q 退出)")
    print("=" * 60)

    # 打开摄像头（带后端回退）
    def _try_open_cam():
        if sys.platform.startswith("win"):
            backends = [(cv2.CAP_DSHOW, "DSHOW"), (cv2.CAP_MSMF, "MSMF")]
        else:
            backends = [(cv2.CAP_V4L2, "V4L2"), (cv2.CAP_ANY, "ANY")]
        for backend, name in backends:
            cap = cv2.VideoCapture(CAMERA_ID, backend)
            if cap.isOpened():
                return cap
        cap = cv2.VideoCapture(CAMERA_ID)
        return cap

    cap = _try_open_cam()
    if not cap or not cap.isOpened():
        print("[ERROR] 无法打开摄像头")
        return False

    # 设置分辨率（仅在 >0 时尝试）
    if CAMERA_WIDTH > 0:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    if CAMERA_HEIGHT > 0:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)

    objp = np.zeros((pattern[0] * pattern[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:pattern[0], 0:pattern[1]].T.reshape(-1, 2)
    objp *= square_size

    objpoints = []
    imgpoints = []
    image_size = None
    collected = 0

    # 采集冷却计数（代替 waitKey 硬阻塞，避免同一帧重复采集）
    cooldown = 0

    while collected < TARGET_COUNT:
        ret, frame = cap.read()
        if not ret:
            print("[WARNING] 读取摄像头失败")
            continue

        if cooldown > 0:
            cooldown -= 1

        # ── 棋盘格检测（缩小图检测提高帧率） ──
        scale = 0.5
        small = cv2.resize(frame, (0, 0), fx=scale, fy=scale,
                           interpolation=cv2.INTER_LINEAR)
        gray_small = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        ret_cb, corners_small = cv2.findChessboardCorners(
            gray_small, pattern, None
        )

        display = frame.copy()
        if ret_cb:
            # 角点坐标缩回原图尺寸
            corners = corners_small / scale
            cv2.drawChessboardCorners(display, pattern, corners, ret_cb)

        # 状态提示
        status = (f"已采集: {collected}/{TARGET_COUNT}  "
                  f"{'✅ 检测到棋盘格' if ret_cb else '等待棋盘格...'}")
        cv2.putText(display, status, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 255, 0) if ret_cb else (0, 0, 255), 2)
        cv2.imshow("畸变标定 - 按 Q 退出", display)

        # waitKey(1) → 不阻塞帧率，摄像头能跑多快就多快
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == ord('Q'):
            print("\n   ❌ 用户取消")
            break

        # 检测到棋盘格 + 冷却结束 → 采集
        if ret_cb and cooldown == 0:
            # 在原图上做亚像素优化
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
            corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)

            if image_size is None:
                image_size = (frame.shape[1], frame.shape[0])

            objpoints.append(objp)
            imgpoints.append(corners2)
            collected += 1
            print(f"   📸 采集 {collected}/{TARGET_COUNT}")

            # 冷却 30 帧避免重复
            cooldown = 30

    cap.release()
    cv2.destroyAllWindows()

    if collected < 4:
        print(f"\n[ERROR] 有效帧数不足 ({collected}/4)，标定失败")
        return False

    print(f"\n   ⏳ 正在标定 ({collected} 帧)...")
    ret_cal, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(
        objpoints, imgpoints, image_size, None, None
    )

    if not ret_cal:
        print("[ERROR] 标定失败")
        return False

    # 重投影误差
    total_error = 0
    for i in range(len(objpoints)):
        imgpoints2, _ = cv2.projectPoints(objpoints[i], rvecs[i], tvecs[i], mtx, dist)
        error = cv2.norm(imgpoints[i], imgpoints2, cv2.NORM_L2) / len(imgpoints2)
        total_error += error
    avg_error = total_error / len(objpoints)

    # 保存
    os.makedirs(CALIB_DIR, exist_ok=True)
    np.save(CAMERA_MATRIX_FILE, mtx)
    np.save(DIST_COEFFS_FILE, dist)

    print(f"\n{'=' * 60}")
    print(f"✅ 畸变标定完成！")
    print(f"{'=' * 60}")
    print(f"   帧数: {collected}")
    print(f"   重投影误差: {avg_error:.4f} 像素")
    print(f"   内参矩阵:\n{mtx}")
    print(f"   畸变系数: {dist.ravel()}")
    print(f"   已保存: {CAMERA_MATRIX_FILE}")
    print(f"           {DIST_COEFFS_FILE}")
    print(f"{'=' * 60}\n")

    return True


if __name__ == "__main__":
    main()

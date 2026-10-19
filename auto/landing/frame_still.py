"""落地判定源二：前后帧光流对比——画面"几乎没动"判定（§1.5 方案 A）。

【并列备选源】层1 主判据为接收机（2026-10-18 口述定稿），本源与 IMU
同为并列备选，融合启用时按帧喂图；亦可独立为串口异常时的兜底判稳
路线。不用 YOLO：效果一样但性能占用大没有意义。相邻两帧降采样
后算 Farneback 稠密光流，平均幅值落进可调区间（auto/params.py
landing 段）→ 画面静止，佐证机体已落地。备选实现：方案 B 帧差
（相邻帧灰度差分均值/变化像素占比），保留未实现（路径见
docs/扩展功能技术路线.md）。

纯函数：输入两帧、return 判定，调用方（flow 或图像采集侧）按帧
喂图；连续 K 帧/M 组的组合计数是确认窗逻辑，在 flow 做。
"""
import cv2
import numpy as np

from auto import params

# Farneback 算法内部参数（固定不动，调参只调 params.py 的幅值区间）
_FARNEBACK = dict(pyr_scale=0.5, levels=3, winsize=15,
                  iterations=3, poly_n=5, poly_sigma=1.2, flags=0)


def _to_gray_small(frame):
    """转灰度并按 FRAME_STILL_MAX_WIDTH 降采样（保持长宽比）"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    if w > params.FRAME_STILL_MAX_WIDTH:
        scale = params.FRAME_STILL_MAX_WIDTH / w
        gray = cv2.resize(gray, (params.FRAME_STILL_MAX_WIDTH,
                                 max(1, int(h * scale))),
                          interpolation=cv2.INTER_AREA)
    return gray


def frame_flow_magnitude(prev_frame, curr_frame) -> float | None:
    """相邻两帧的平均光流幅值（像素/帧）；无法计算返回 None

    调参/日志用：把测到的幅值拿出来，供阈值标定时对照。
    """
    if prev_frame is None or curr_frame is None:
        return None
    if prev_frame.shape[:2] != curr_frame.shape[:2]:
        return None
    flow = cv2.calcOpticalFlowFarneback(_to_gray_small(prev_frame),
                                        _to_gray_small(curr_frame),
                                        None, **_FARNEBACK)
    mag = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
    return float(mag.mean())


def check_frame_still(prev_frame, curr_frame) -> bool | None:
    """画面静止判定：平均光流幅值落进 params 区间 → True（画面几乎没动）

    三态：True 画面几乎没动 / False 画面在动 / None 无法判定
    （任一帧为空或两帧尺寸不一致）。
    """
    mean_mag = frame_flow_magnitude(prev_frame, curr_frame)
    if mean_mag is None:
        return None
    return params.FRAME_STILL_FLOW_MIN <= mean_mag <= params.FRAME_STILL_FLOW_MAX

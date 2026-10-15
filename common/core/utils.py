"""
工具函数模块 - 提供通用的工具函数
"""
import sys
import os

import cv2
import numpy as np


def log_error(e, context=""):
    """
    统一的错误日志记录

    Args:
        e: 异常对象
        context: 错误上下文描述
    """
    exc_type, exc_obj, exc_tb = sys.exc_info()
    if exc_tb:
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        lineno = exc_tb.tb_lineno
        msg = f"[ERROR] File: {fname}, Line: {lineno} | {type(e).__name__}: {str(e)}"
        if context:
            msg = f"[ERROR] {context} | File: {fname}, Line: {lineno} | {type(e).__name__}: {str(e)}"
        print(msg)
    else:
        msg = f"[ERROR] {type(e).__name__}: {str(e)}"
        if context:
            msg = f"[ERROR] {context} | {type(e).__name__}: {str(e)}"
        print(msg)


def make_status_frame(message: str, size, hint: str | None = None) -> np.ndarray:
    """生成带状态文字的占位帧（无画面时在 GUI 上显示，与实拍同分辨率）

    Args:
        message: 主提示文字（居中橙色显示，字号随分辨率缩放）
        size: 帧尺寸 (h, w)
        hint: 可选的小字灰色提示（位于主文字下方）
    """
    h, w = size
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = max(0.8, min(2.5, w / 1280.0))
    text_size = cv2.getTextSize(message, font, scale, 2)[0]
    tx = (w - text_size[0]) // 2
    ty = h // 2 - 10
    cv2.putText(frame, message, (tx, ty), font, scale, (0, 165, 255), 2)
    if hint:
        hint_size = cv2.getTextSize(hint, font, scale * 0.6, 1)[0]
        cv2.putText(frame, hint, ((w - hint_size[0]) // 2, ty + int(40 * scale)),
                    font, scale * 0.6, (100, 100, 100), 1)
    return frame


def px_to_ratio(px, ref_size) -> float:
    """像素值 → 占画面比例 (0~1)；负值/无参考尺寸时回退 0.5"""
    try:
        px = float(px)
    except (TypeError, ValueError):
        return 0.5
    if px < 0 or not ref_size or ref_size <= 0:
        return 0.5
    return max(0.0, min(1.0, px / float(ref_size)))

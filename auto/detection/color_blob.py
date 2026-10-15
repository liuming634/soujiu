"""通用色块识别工具（OpenCV）：按 BGR 颜色区间在画面里找色块。

只识别六种颜色：黑 / 棕 / 粉 / 蓝 / 黄 / 绿，区间定义在 COLOR_RANGES
（BGR 下限/上限），现场光照下直接改数值即可调色。

通用工具接口（无状态、按需调用）：自动链路里给球做颜色权重分析、
后续球投放对应桶的行为等地方共用；输入帧为 OpenCV BGR 格式。
"""
from dataclasses import dataclass, asdict

import cv2
import numpy as np

# ── BGR 颜色区间 (lower, upper)：初始参考值，现场光照下直接改这里 ──
COLOR_RANGES = {
    '黑': ((0, 0, 0),      (70, 70, 70)),
    '棕': ((0, 30, 80),    (90, 110, 190)),
    '粉': ((110, 90, 180), (230, 200, 255)),
    '蓝': ((150, 0, 0),    (255, 180, 100)),
    '黄': ((0, 150, 150),  (120, 255, 255)),
    '绿': ((0, 120, 0),    (120, 255, 120)),
}
COLOR_NAMES = ('黑', '棕', '粉', '蓝', '黄', '绿')

# 形态学核尺寸（开运算去噪点 / 闭运算补空洞）
_MORPH_KERNEL_SIZE = (5, 5)


@dataclass
class ColorBlob:
    """一个色块（find_color_blobs 指定颜色下识别得到，颜色由调用方知晓不重复存）"""

    bbox: tuple[int, int, int, int]   # 色块外接框 (x1, y1, x2, y2) 像素坐标
    center: tuple[int, int]           # 外接框中心（像素）
    area: float                       # 色块面积（像素²），筛选/权重用

    def as_dict(self) -> dict:
        """转字典（GUI 显示 / 调试用）"""
        return asdict(self)


def find_color_blobs(frame, color: str, min_area: int = 500) -> list[ColorBlob]:
    """在一帧里找指定颜色的色块，按面积从大到小返回（大块更可信）

    frame: OpenCV BGR 帧；color: COLOR_RANGES 里的颜色名；
    min_area: 面积门槛（像素²），小于它的碎块丢弃。
    frame 为 None（帧缺失）时返回空列表。
    """
    if color not in COLOR_RANGES:
        raise ValueError(f"未知颜色 '{color}'，可选：{list(COLOR_RANGES)}")
    if frame is None:
        return []

    lower, upper = (np.array(v, dtype=np.uint8) for v in COLOR_RANGES[color])
    mask = cv2.inRange(frame, lower, upper)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, _MORPH_KERNEL_SIZE)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    blobs: list[ColorBlob] = []
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in contours:
        area = cv2.contourArea(c)
        if area < min_area:
            continue
        x, y, w, h = cv2.boundingRect(c)
        blobs.append(ColorBlob(bbox=(x, y, x + w, y + h),
                               center=(x + w // 2, y + h // 2), area=area))
    blobs.sort(key=lambda b: b.area, reverse=True)
    return blobs

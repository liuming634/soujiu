"""抓取范围判定：按画面上的抓取圈判定物体是否可抓/可投（§2、§6.2）。

判定方法沿用上一版"对比板查色"：把抓取圈覆盖区域做成黑色(0)、其余
做成白色(255)的查找板，ROI 中点直接用 (x, y) 查板取色判定是否在圈
内（numpy 索引，不逐个循环比较）；板的尺寸/配置不变时缓存复用。

抓取圈来自 config 比例（grab_range_x/y/radius_ratio），换算公式与
手动模式画面上画的圆完全一致（看到即可抓）——比例是手动/自动共用
参数，留在 common config（GUI 可调），不进 auto/params.py；盆可投
阈值等 auto 专用参数在 auto/params.py region 段。

纯函数 API：只判定、只 return，不入库；"先按本轮品类筛、再圈内筛"
的次序与连续 M 帧防抖都在 flow 做（§2.3）。
"""
import cv2
import numpy as np

from common.core.config import config

from auto import params
from auto.detection.state import RoiTarget

# 对比板缓存：(w, h, x_ratio, y_ratio, radius_ratio, board)，配置/尺寸变化即重画
_mask_cache: tuple | None = None


def grab_circle(w: int, h: int) -> tuple[int, int, int]:
    """抓取圈像素参数 (cx, cy, r)，换算公式与画面画圆一致"""
    cx = int(round(config.grab_range_x_ratio * (w - 1)))
    cy = int(round(config.grab_range_y_ratio * (h - 1)))
    r = int(round(config.grab_range_radius_ratio * w))
    return cx, cy, r


def _range_mask(w: int, h: int) -> np.ndarray:
    """生成抓取范围对比板：圈内黑色(0)，圈外白色(255)（带缓存复用）"""
    global _mask_cache
    key = (w, h, config.grab_range_x_ratio, config.grab_range_y_ratio,
           config.grab_range_radius_ratio)
    if _mask_cache is not None and _mask_cache[:5] == key:
        return _mask_cache[5]

    cx, cy, r = grab_circle(w, h)
    board = np.full((h, w), 255, dtype=np.uint8)
    cv2.circle(board, (cx, cy), r, 0, -1)
    _mask_cache = (*key, board)
    return board


def point_in_range(x: int, y: int, frame) -> bool | None:
    """判定一个像素点是否在抓取圈内（对比板查色：黑 = 在圈内）

    用于阶段六桶可投判定（桶 ROI 中点在圈内，§6.2）。
    frame 只用尺寸生成对比板；点坐标越界按边界夹取。
    三态：True 在圈内 / False 在圈外 / None 帧缺失无法判定。
    """
    if frame is None:
        return None
    h, w = frame.shape[:2]
    xi = min(max(int(x), 0), w - 1)
    yi = min(max(int(y), 0), h - 1)
    return bool(_range_mask(w, h)[yi, xi] == 0)


def overlap_px(roi: tuple[int, int, int, int], frame) -> int | None:
    """矩形 ROI 与抓取圈的重合像素数（对比板裁剪 ROI 区域统计黑像素）

    用于阶段六盆可投判定（§6.2：重合面积 ≥ 阈值即判可投），阈值判断
    配合 overlap_ok 用。roi: (x1, y1, x2, y2)；越界部分自动裁剪到
    画面内。
    三态：像素数 ≥ 0 / None 帧缺失无法判定（ROI 裁剪后无效算 0）。
    """
    if frame is None:
        return None
    h, w = frame.shape[:2]
    x1 = min(max(int(roi[0]), 0), w)
    y1 = min(max(int(roi[1]), 0), h)
    x2 = min(max(int(roi[2]), 0), w)
    y2 = min(max(int(roi[3]), 0), h)
    if x2 <= x1 or y2 <= y1:
        return 0
    region = _range_mask(w, h)[y1:y2, x1:x2]
    return int((region == 0).sum())


def overlap_ok(roi: tuple[int, int, int, int], frame) -> bool | None:
    """盆可投判定：ROI 与抓取圈重合像素数 ≥ params.PAN_OVERLAP_MIN_PX

    盆大、颜色均匀、首次投放为空，有一定面积在圈内即可判可投。
    三态：True 可投 / False 不可投 / None 帧缺失无法判定。
    """
    px = overlap_px(roi, frame)
    if px is None:
        return None
    return px >= params.PAN_OVERLAP_MIN_PX


def filter_grabbable(objects: list[RoiTarget],
                     frame) -> list[RoiTarget] | None:
    """圈内过滤：只保留 ROI 中点在抓取圈内的对象（阶段二可抓判定用）

    不在圈内的不作为评分候选；返回新列表，不修改原列表。
    三态：过滤后的列表 / None 帧缺失无法判定。
    """
    if frame is None:
        return None
    return [o for o in objects
            if point_in_range(o.center[0], o.center[1], frame)]

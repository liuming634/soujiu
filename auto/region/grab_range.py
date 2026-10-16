"""抓取范围判定：按画面上的抓取圈判定物体是否可抓取（自动链路第二步）。

判定方法（对比板）：把抓取圈覆盖区域做成黑色(0)、其余做成白色(255)的
查找板，ROI 中点直接用 (x, y) 查板取色即可判定是否在范围内
（numpy 索引，不做逐个循环比较）；板的尺寸/配置不变时缓存复用。

抓取圈来自 YAML 配置比例（grab_range_x/y/radius_ratio），换算公式与
手动模式画面上画的圆（ui/display.py）完全一致，看到即可抓。

说明：范围判定本可在 YOLO 阶段直接做（色块识别同理），当前按独立
接口处理，后续流程优化时可前移合并。
"""
import cv2
import numpy as np

from common.core.config import config
from common.core.runtime_data import RuntimeData

# 对比板缓存：(w, h, x_ratio, y_ratio, radius_ratio, board)，配置/尺寸变化即重画
_mask_cache: tuple | None = None


def grab_circle(w: int, h: int) -> tuple[int, int, int]:
    """抓取圈像素参数 (cx, cy, r)，换算公式与画面画圆（ui/display.py）一致"""
    cx = int(round(config.grab_range_x_ratio * (w - 1)))
    cy = int(round(config.grab_range_y_ratio * (h - 1)))
    r = int(round(config.grab_range_radius_ratio * w))
    return cx, cy, r


def _range_mask(w: int, h: int) -> np.ndarray:
    """生成抓取范围对比板：范围内黑色(0)，范围外白色(255)"""
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


def point_in_range(x: int, y: int, frame) -> bool:
    """判定一个像素点是否在抓取范围内（对比板查色：黑=在范围内）

    frame 只用尺寸生成对比板；点坐标越界时按边界夹取。帧缺失返回 False。
    """
    if frame is None:
        return False
    h, w = frame.shape[:2]
    xi = min(max(int(x), 0), w - 1)
    yi = min(max(int(y), 0), h - 1)
    return bool(_range_mask(w, h)[yi, xi] == 0)


def overlap_px(roi: tuple[int, int, int, int], frame) -> int:
    """矩形 ROI 与抓取范围重合的像素数（对比板裁剪 ROI 区域统计黑像素）

    roi: (x1, y1, x2, y2)；越界部分自动裁剪到画面内。
    帧缺失或 ROI 无效返回 0。
    """
    if frame is None:
        return 0
    h, w = frame.shape[:2]
    x1 = min(max(int(roi[0]), 0), w)
    y1 = min(max(int(roi[1]), 0), h)
    x2 = min(max(int(roi[2]), 0), w)
    y2 = min(max(int(roi[3]), 0), h)
    if x2 <= x1 or y2 <= y1:
        return 0
    region = _range_mask(w, h)[y1:y2, x1:x2]
    return int((region == 0).sum())


def filter_grabbable(objects: list, frame) -> list:
    """过滤一个识别列表：只保留 ROI 中点在抓取范围内的对象

    不在范围内的不作为评分的待抓取对象；返回新列表，不修改原列表。
    """
    if frame is None:
        return []
    return [o for o in objects if point_in_range(o.center[0], o.center[1], frame)]


def refresh_grabbable(frame, data: RuntimeData) -> tuple[list, list]:
    """对识别结果做抓取范围过滤，结果存入独立的可抓取列表

    过滤后的魔方/球存入 data.grabbable_cube_list / grabbable_ball_list
    （评分的待抓取对象，整体覆盖并打 grabbable_time 时间戳）；
    cube_list / ball_list 保留全部识别结果不动，detection_time 不变。
    返回过滤后的 (魔方, 球)。
    """
    cubes = filter_grabbable(data.cube_list, frame)
    balls = filter_grabbable(data.ball_list, frame)
    data.set_grabbable(cubes, balls)    # 入库时统一打时间戳
    return cubes, balls

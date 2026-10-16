"""投放判定接口层：判定魔方/球"是否可以投放"。

说明：投放成功本身不需要判定（魔方投放后下一次抓球、球投放后下一次抓魔方，
投放成功与否不影响下一步），所以这里只做"是否可以投放"的判定：

  1. judge_cube_droppable  魔方是否可以投放：
     投放大盆（YOLO 识别，类别占位名 pan）的 ROI 与抓取范围（圆）重合的
     像素数 ≥ config.drop_pan_overlap_min_px。盆大、颜色均匀、首次投放为空，
     盆 ROI 大部分落在抓取范围内才可投放。
  2. judge_ball_droppable  球是否可以投放：
     投放桶（YOLO 识别 bucket）的 ROI 中点是否在抓取范围内，用
     grab_range.point_in_range（对比板查色）。该判定不够可靠（桶位置与投放
     区未必重合），当前为占位实现，后续在此改进。

每个接口返回 True=可投放 / False=不可投放 / None=无法判定（帧或目标缺失）。
阈值全部参数化进 config；接口也接受显式参数覆盖（缺省取 config）。
"""
from common.core.config import config
from common.core.runtime_data import RuntimeData

from auto.region import grab_range


def _as_bbox(obj) -> tuple | None:
    """对象（带 bbox 字段的数据类）或 (x1, y1, x2, y2) 元组统一取 bbox"""
    if obj is None:
        return None
    if isinstance(obj, (tuple, list)):
        return tuple(obj)
    bbox = getattr(obj, 'bbox', None)
    return tuple(bbox) if bbox is not None else None


def judge_cube_droppable(frame,
                         pan=None,
                         data: RuntimeData | None = None,
                         overlap_min_px: int | None = None) -> bool | None:
    """魔方是否可以投放：投放大盆 ROI 与抓取范围重合像素 ≥ 阈值

    pan 传入盆对象（PanObject）或 (x1,y1,x2,y2)；缺省取 data.pan_list 里
    第一个（YOLO 识别结果）。overlap_min_px 缺省取
    config.drop_pan_overlap_min_px。
    """
    if frame is None:
        return None
    if pan is None and data is not None and data.pan_list:
        pan = data.pan_list[0]
    bbox = _as_bbox(pan)
    if bbox is None:
        return None
    if overlap_min_px is None:
        overlap_min_px = config.drop_pan_overlap_min_px
    return grab_range.overlap_px(bbox, frame) >= overlap_min_px


def judge_ball_droppable(frame,
                         bucket=None,
                         data: RuntimeData | None = None) -> bool | None:
    """球是否可以投放：投放桶 ROI 中点是否在抓取范围内

    bucket 传入桶对象（BucketObject）或带 center 的对象；缺省取
    data.bucket_list 里第一个（YOLO 识别结果）。
    占位实现（判定不够可靠），后续在此改进判定标准。
    """
    if frame is None:
        return None
    if bucket is None and data is not None and data.bucket_list:
        bucket = data.bucket_list[0]
    if bucket is None:
        return None
    center = getattr(bucket, 'center', None)
    if center is None:
        return None
    return grab_range.point_in_range(center[0], center[1], frame)

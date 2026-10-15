"""识别模块的函数接口（项目链路）：YOLO 识别 → 编号 → 刷新入库 → 返回。

detect(frame, data) 是自动链路里"每一次抓取行为之前"调一次的识别接口：
调用方把当前帧作为参数传入，识别结果（魔方列表, 球列表）整体刷新存回
RuntimeData（入库时打时间戳），并作为返回值直接给调用方。
detect_buckets(frame, data) 同链路识别投放桶位置（球投放行为用）。
"""
from common.core.runtime_data import RuntimeData

from auto.detection.model import (BALL_CLASS_NAME, BUCKET_CLASS_NAME,
                                  CONF_THRESHOLD, CUBE_CLASS_NAME,
                                  run_inference)
from auto.detection.state import BucketObject, DetectedObject


def assign_numbers(objects: list[DetectedObject]) -> list[DetectedObject]:
    """按 ROI 中点像素坐标编号：先比 x（从左到右），x 相同比 y（从上到下）

    最靠左（上）的编号最小，从 1 开始；就地排序并写回 number 字段，
    同时返回该列表（方便链式使用）。
    """
    objects.sort(key=lambda o: (o.center[0], o.center[1]))
    for i, obj in enumerate(objects, start=1):
        obj.number = i
    return objects


def build_objects(raw: list) -> tuple[list[DetectedObject], list[DetectedObject]]:
    """原始检测 → 置信度过滤（≥80% 才认定对应品类）→ 分魔方/球 → 编号

    返回 (魔方列表, 球列表)；类别只用于分列表，不存进对象。
    """
    cubes: list[DetectedObject] = []
    balls: list[DetectedObject] = []
    for cls_name, bbox, conf in raw:
        if conf < CONF_THRESHOLD:
            continue
        x1, y1, x2, y2 = bbox
        obj = DetectedObject(bbox=tuple(bbox),
                             center=((x1 + x2) // 2, (y1 + y2) // 2))
        if cls_name == CUBE_CLASS_NAME:
            cubes.append(obj)
        elif cls_name == BALL_CLASS_NAME:
            balls.append(obj)
    assign_numbers(cubes)
    assign_numbers(balls)
    return cubes, balls


def detect(frame, data: RuntimeData | None = None,
           ) -> tuple[list[DetectedObject], list[DetectedObject]]:
    """跑一次识别（自动链路第一步，每次抓取行为前调用一次）

    frame 由调用方传入当前画面帧；识别结果整体刷新存入 data（cube_list /
    ball_list / detection_time）并原样返回 (魔方列表, 球列表)；
    data 不传时只返回不存储。frame 为 None（相机未就绪）时按空结果处理。
    """
    if frame is None:
        print("[WARNING] 当前帧缺失，本次识别按空结果处理")
        raw = []
    else:
        raw = run_inference(frame)
    cubes, balls = build_objects(raw)
    if data is not None:
        data.set_detections(cubes, balls)   # 入库时统一打时间戳
    return cubes, balls


def build_buckets(raw: list) -> list[BucketObject]:
    """原始检测 → 置信度过滤（≥80% 才认定）→ 取桶 → 按 ROI 中点 x 优先排序

    桶不编号，只保证列表顺序稳定（与识别编号同规则：先比 x，x 同比 y）。
    """
    buckets: list[BucketObject] = []
    for cls_name, bbox, conf in raw:
        if cls_name != BUCKET_CLASS_NAME or conf < CONF_THRESHOLD:
            continue
        x1, y1, x2, y2 = bbox
        buckets.append(BucketObject(bbox=tuple(bbox),
                                    center=((x1 + x2) // 2, (y1 + y2) // 2)))
    buckets.sort(key=lambda b: b.center)
    return buckets


def detect_buckets(frame, data: RuntimeData | None = None) -> list[BucketObject]:
    """跑一次投放桶识别（球投放行为用，按需调用一次）

    frame 由调用方传入当前画面帧；识别到每个桶返回 ROI 识别框 + 中点。
    结果整体刷新存入 data（bucket_list / bucket_time，入库时打时间戳）
    并原样返回；data 不传时只返回不存储。
    frame 为 None（相机未就绪）时按空结果处理。
    """
    if frame is None:
        print("[WARNING] 当前帧缺失，本次桶识别按空结果处理")
        raw = []
    else:
        raw = run_inference(frame)
    buckets = build_buckets(raw)
    if data is not None:
        data.set_buckets(buckets)   # 入库时统一打时间戳
    return buckets

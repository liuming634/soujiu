"""目标检测 API：一帧 → (魔方列表, 球列表, 盆, 桶)。

一个 YOLO 模型一次推理四类标签（model.py），这里只做整理：
- 魔方、球：场上多个，列表存储，每项只有 ROI 外接框 + ROI 中点
- 盆、桶：单次投放任务里各只有一个，不列表——识别到多处时取
  置信度最高的一处，没识别到为 None

纯函数 API：只返回数据，不入库、不存队列（调用方自行处理）；
模型未加载/权重缺失时 load_model 抛明确异常，兜底方式由调用方定。
"""
from auto.detection.model import (run_inference, CONF_THRESHOLD,
                                  CUBE_CLASS_NAME, BALL_CLASS_NAME,
                                  PAN_CLASS_NAME, BUCKET_CLASS_NAME)
from auto.detection.state import RoiTarget


def _midpoint(bbox: tuple[int, int, int, int]) -> tuple[int, int]:
    """ROI 外接框 → 中点像素坐标"""
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def detect(frame) -> tuple[list[RoiTarget], list[RoiTarget],
                           RoiTarget | None, RoiTarget | None]:
    """对一帧推理，返回 (魔方列表, 球列表, 盆, 桶)

    - 置信度 ≥ CONF_THRESHOLD 才认定对应品类
    - 盆/桶识别到多处时取置信度最高的一处；未识别到为 None
    - frame 为 None（无帧）时返回 ([], [], None, None)
    """
    cubes: list[RoiTarget] = []
    balls: list[RoiTarget] = []
    pan: RoiTarget | None = None
    bucket: RoiTarget | None = None
    if frame is None:
        return cubes, balls, pan, bucket

    pan_conf = bucket_conf = 0.0
    for name, bbox, conf in run_inference(frame):
        if conf < CONF_THRESHOLD:
            continue                      # 低于阈值不认定品类
        if name == CUBE_CLASS_NAME:
            cubes.append(RoiTarget(bbox=bbox, center=_midpoint(bbox)))
        elif name == BALL_CLASS_NAME:
            balls.append(RoiTarget(bbox=bbox, center=_midpoint(bbox)))
        elif name == PAN_CLASS_NAME:
            if conf > pan_conf:           # 多处识别取最高置信度
                pan = RoiTarget(bbox=bbox, center=_midpoint(bbox))
                pan_conf = conf
        elif name == BUCKET_CLASS_NAME:
            if conf > bucket_conf:
                bucket = RoiTarget(bbox=bbox, center=_midpoint(bbox))
                bucket_conf = conf
    return cubes, balls, pan, bucket

"""YOLO 模型加载与推理：一个模型一次推理出四类目标。

职责只有一件事：加载模型 → 对帧推理 → 返回原始检测
[(类别名, (x1,y1,x2,y2), 置信度), ...]。魔方/球/盆/桶同帧全出，
整理成"魔方列表 / 球列表 / 盆 / 桶"由 detector.detect 做。

模型权重尚未训练好：MODEL_FILE 为占位文件名，权重放到该路径即可跑通。
"""
import os

from common.core.config import config

# ── 模型配置（权重就位后按实际文件名与类别名改这里） ──────────
MODEL_FILE = "models/cube_ball.pt"   # 权重路径（相对项目根，占位名）
CUBE_CLASS_NAME = "cube"             # 权重里魔方的类别名
BALL_CLASS_NAME = "ball"             # 权重里球的类别名
BUCKET_CLASS_NAME = "bucket"         # 权重里投放桶的类别名
PAN_CLASS_NAME = "pan"               # 权重里投放大盆的类别名
CONF_THRESHOLD = 0.8                 # 置信度阈值：≥0.8 才认定为对应品类

_model = None  # 进程内缓存的模型实例（懒加载，只加载一次）


def load_model():
    """加载 YOLO 权重并缓存；依赖/权重缺失时给出明确提示"""
    global _model
    if _model is not None:
        return _model
    try:
        from ultralytics import YOLO
    except ImportError:
        raise RuntimeError("未安装 ultralytics：pip install ultralytics")
    path = config.resolve_path(MODEL_FILE)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"YOLO 权重不存在: {path}（训练好的权重放到该路径即可）")
    _model = YOLO(path)
    print(f"   [YOLO] 模型已加载: {path}")
    return _model


def run_inference(frame) -> list:
    """对一帧推理，返回原始检测 [(类别名, (x1,y1,x2,y2), 置信度), ...]"""
    model = load_model()
    raw = []
    for r in model.predict(frame, verbose=False):
        for box in r.boxes:
            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
            raw.append((r.names[int(box.cls[0])],
                        (x1, y1, x2, y2), float(box.conf[0])))
    return raw

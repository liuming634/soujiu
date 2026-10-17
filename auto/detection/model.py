"""YOLO 模型加载与推理：一个模型一次推理出四类目标。

职责只有一件事：加载模型 → 对帧推理 → 返回原始检测
[(类别名, (x1,y1,x2,y2), 置信度), ...]。魔方/球/盆/桶同帧全出，
整理成"魔方列表 / 球列表 / 盆 / 桶"由 detector.detect 做。

模型权重尚未训练好：权重路径为占位文件名，权重放到该路径即可跑通。
模型文件与类别名、置信度阈值等参数都在 auto/params.py detection 段。
"""
import os

from common.core.config import config

from auto import params

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
    path = config.resolve_path(params.DETECT_MODEL_FILE)
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

"""识别模块：YOLO 魔方/球检测 + 编号（自动链路第一步）+ 通用色块识别工具。

- state.py      识别结果数据结构 DetectedObject（ROI框/中点/编号，不含类别与置信度）
- model.py      YOLO 加载与推理（权重未就绪：MODEL_FILE 与类别名为占位，就位即跑通）
- detector.py   函数接口：detect(frame, data) 对传入帧 YOLO 推理 →
                置信度 ≥80% 才认定品类 → 分魔方/球两个列表 → 按 ROI 中点
                x（x 同比 y）编号从 1 开始 → 整体刷新存入 RuntimeData 并返回；
                detect_buckets(frame, data) 识别投放桶（球投放行为用），
                返回桶的 ROI/中点列表并刷新存入 RuntimeData（桶不编号）
- color_blob.py 通用色块识别工具（OpenCV BGR 区间，黑/棕/粉/蓝/黄/绿六色，
                区间可调；球颜色权重分析、球投放对应桶行为等共用）
"""

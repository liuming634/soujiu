"""权重评分系统：对可抓取目标打分，决定抓取哪一个魔方或球（魔方/球分开评）。

- scorer.py 函数接口：score_cubes（距离+密集）、score_balls（距离+颜色+密集，
  颜色用 color_blob.dominant_color 在球 ROI 内判定）。
  评分树/公式见 scorer 模块 docstring；所有权重、距离同分区间(0.8)、
  密集统计半径(像素)、六色球得分全部是 config 参数（YAML 持久化 +
  设置界面"评分权重"页可改），默认等权占位。
"""

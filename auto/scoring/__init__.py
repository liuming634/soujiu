"""评分选靶模块（已实现，scorer.py + state.py）：给可抓目标打分，决定
先抓哪一个（§3）。

评分树（§3.2，框架沿用上一版）：总分 = 各因子加权求和——
  距离因子（魔方/球同）：中点到圈心，plateau 以内同分 1.0，线性递减
  到圆边界 0；
  颜色因子（仅球）：球 ROI 判主色（复用 detection 色块工具）→ 查
  params.BALL_COLOR_SCORES，判不出记 0；
  密集因子（魔方/球同）：以目标中点为圆心数邻居中点个数，1/(1+个数)；
  C1 口径（已定）：密集只算魔方——邻居 = 魔方全部识别目标（含抓取
  圈外），球不参与统计（只有魔方影响抓取），球评分邻域同样传魔方。
  魔方总分 = 权重距离×距离 + 权重密集×密集
  球总分   = 权重距离×距离 + 权重颜色×颜色分值 + 权重密集×密集

权重/plateau/密集半径/六色分值全部在 auto/params.py scoring 段
（等权占位，现场标定）。

函数 API（纯函数：只评分、只 return，不入库、不改输入列表）：
  1. score_cubes(cubes, frame, all_cubes=None) → list[ScoredTarget] | None
     魔方评分（距离 + 密集）
  2. score_balls(balls, frame, all_cubes=None) → list[ScoredTarget] | None
     球评分（距离 + 颜色 + 密集）
   cubes / balls = 圈内候选（filter_grabbable 过滤后的本轮品类目标，
   评分对象）；all_cubes = 魔方
  全部识别目标（密集统计用，含抓取圈外——C1 口径：密集只算魔方）。
  输出按分数从高到低（最高分 = 先抓）；并列按中点 x→y 升序 =
  编号小者优先（§2.4 编号规则）。三态：排序列表 / [] 空列表 /
  None 帧缺失无法判定。

数据格式适配说明：本分支 RoiTarget 只带 bbox/center，评分结果不写
回目标，成对打包成 ScoredTarget（target + score，见 state.py）返回；
输入 = 圈内候选（本轮品类），flow 按品类二选一调用。

已定设计说明：不做"失败目标排除"——评分每轮重算自然反映
新布局；密集邻居 = 魔方全部识别目标含圈外（C1 口径已定，球不参与）。
"""

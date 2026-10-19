"""权重评分选靶：给圈内候选目标打分，决定先抓哪一个（§3）。

评分框架沿用上一版 scoring 模块的标准（§3.2 评分树），总分 = 各因子
加权求和（权重/半径/六色分值都在 auto/params.py scoring 段）：
  ├─ 距离因子（魔方/球同规则）：ROI 中点到抓取圈圆心的距离，
  │   plateau（×半径）以内同分 1.0，以外线性递减到圆边界为 0
  ├─ 颜色因子（仅球）：球 ROI 内色块判主色（复用 detection 的
  │   dominant_color）→ 查 params.BALL_COLOR_SCORES 该颜色分值，
  │   判不出主色记 0
  └─ 密集因子（魔方/球同规则）：以目标中点为圆心、密集统计半径为
      像素圆，数邻居中点个数，取 1/(1+个数)——邻居越多分越低。
      C1 口径（已定）：密集只算魔方——邻居 = 魔方全部识别目标（含
      抓取圈外的），球不参与统计（只有魔方影响抓取）；魔方评分与
      球评分都用魔方邻域（score_balls 传 all_cubes）

抓取圈换算复用 region 的 grab_circle（与手动模式画圆公式一致）。
纯函数 API：只评分、只 return（ScoredTarget 列表），不入库、不改
输入列表——本分支的 RoiTarget 不带分数，评分结果成对打包返回。
排序：分数从高到低（最高分 = 先抓）；并列按 ROI 中点 x → y 升序，
即"编号小者优先"（编号规则 = 中点先比 x 再比 y，§2.4）。

设计说明（§3.3）：不做"失败目标排除"——每次抓取（无论成败）都可能
改变物体位置，评分每轮重算自然反映新布局；球移动后重新评分自然覆盖
"改抓圈内其他颜色的球"，无需特殊处理。
"""
import math

from auto import params
from auto.detection.color_blob import dominant_color
from auto.detection.state import RoiTarget
from auto.region.grab_range import grab_circle
from auto.scoring.state import ScoredTarget


def _distance_factor(center: tuple[int, int],
                     circle: tuple[int, int, int]) -> float:
    """距离因子：plateau（×半径）以内同分 1.0，以外线性递减到圆边界为 0"""
    cx, cy, r = circle
    if r <= 0:
        return 0.0
    t = min(math.hypot(center[0] - cx, center[1] - cy) / r, 1.0)
    plateau = params.SCORE_DISTANCE_PLATEAU
    if plateau >= 1.0 or t <= plateau:
        return 1.0
    return max(0.0, 1.0 - (t - plateau) / (1.0 - plateau))


def _density_factor(target: RoiTarget, neighbors: list[RoiTarget]) -> float:
    """密集因子：以目标中点为圆心数邻居列表内其他目标中点个数，1/(1+个数)

    邻居列表由调用方传（C1 口径 = 魔方全部识别目标含圈外）——圈外
    目标挤在评分对象旁边同样说明位置差。
    """
    n = sum(1 for o in neighbors
            if o is not target
            and math.hypot(o.center[0] - target.center[0],
                           o.center[1] - target.center[1])
            <= params.SCORE_DENSITY_RADIUS_PX)
    return 1.0 / (1.0 + n)


def _sort_key(scored: ScoredTarget) -> tuple:
    """排序键：分数降序 + 并列按中点 x→y 升序（编号小者优先）"""
    return (-scored.score, scored.target.center[0], scored.target.center[1])


def score_cubes(cubes: list[RoiTarget], frame,
                all_cubes: list[RoiTarget] | None = None) -> list[ScoredTarget] | None:
    """魔方评分：距离 + 密集加权（权重 params.SCORE_WEIGHT_CUBE_*）

    cubes = 圈内候选（filter_grabbable 过滤后的目标，评分对象）；
    all_cubes = 本轮品类
    全部识别目标（密集统计用，**含抓取圈外的**，缺省 = 只数 cubes
    自身）。三态：ScoredTarget 列表按分数从高到低 / [] 列表为空
    （没东西可评）/ None 帧缺失无法判定。
    """
    if frame is None:
        return None
    if not cubes:
        return []
    circle = grab_circle(frame.shape[1], frame.shape[0])
    neighbors = cubes if all_cubes is None else all_cubes
    scored = [ScoredTarget(target=o, score=(
        params.SCORE_WEIGHT_CUBE_DISTANCE * _distance_factor(o.center, circle)
        + params.SCORE_WEIGHT_CUBE_DENSITY * _density_factor(o, neighbors)))
        for o in cubes]
    scored.sort(key=_sort_key)
    return scored


def score_balls(balls: list[RoiTarget], frame,
                all_cubes: list[RoiTarget] | None = None) -> list[ScoredTarget] | None:
    """球评分：距离 + 颜色 + 密集加权（权重 params.SCORE_WEIGHT_BALL_*）

    balls = 圈内候选；all_cubes = 全部魔方识别目标（密集统计用，含抓取
    圈外）——C1 口径：密集只算魔方（球不参与，只有魔方影响抓取），
    缺省 = 无邻域（密集记 1）。颜色在球 ROI 内判主色（dominant_color），
    得分查 params.BALL_COLOR_SCORES（判不出主色记 0）。三态同 score_cubes。
    """
    if frame is None:
        return None
    if not balls:
        return []
    circle = grab_circle(frame.shape[1], frame.shape[0])
    neighbors = all_cubes if all_cubes is not None else []
    scored = [ScoredTarget(target=o, score=(
        params.SCORE_WEIGHT_BALL_DISTANCE * _distance_factor(o.center, circle)
        + params.SCORE_WEIGHT_BALL_COLOR * params.BALL_COLOR_SCORES.get(
            dominant_color(frame, o.bbox), 0.0)
        + params.SCORE_WEIGHT_BALL_DENSITY * _density_factor(o, neighbors)))
        for o in balls]
    scored.sort(key=_sort_key)
    return scored

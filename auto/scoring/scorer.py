"""权重评分：魔方/球分开评分，决定先抓哪一个。

评分树（确认定稿）：
  总分 = 各因子加权求和
  ├─ 距离因子（魔方/球同规则）：ROI 中点到抓取圈圆心的距离，
  │   抓取圈半径的 score_distance_plateau 比例以内同分，以外线性递减
  │   到圆边界为 0；上半圈/下半圈对称
  ├─ 颜色因子（仅球）：球 ROI 内色块判主色 → 查 config 里该颜色球的得分
  └─ 密集因子（魔方/球同规则）：以对象 ROI 中点为圆心、
      score_density_radius_px 为半径，数圈内其他魔方 ROI 中点个数，
      1/(1+个数) 越多分越低

所有权重、距离同分区间、密集统计半径、六色球得分全部是 config 参数
（YAML 持久化、设置界面"评分权重"页可改），默认等权占位，比例自行调整。
"""
import math

from common.core.config import config
from common.core.runtime_data import RuntimeData

from auto.detection.color_blob import dominant_color
from auto.detection.state import DetectedObject
from auto.region.grab_range import grab_circle

# 颜色名 → config 里该颜色球得分参数名
_BALL_COLOR_SCORE_KEY = {
    '黑': 'ball_score_black', '棕': 'ball_score_brown', '粉': 'ball_score_pink',
    '蓝': 'ball_score_blue', '黄': 'ball_score_yellow', '绿': 'ball_score_green',
}


def _distance_factor(center: tuple[int, int], circle: tuple[int, int, int]) -> float:
    """距离因子：plateau（×半径）以内同分 1.0，以外线性递减到圆边界为 0"""
    cx, cy, r = circle
    if r <= 0:
        return 0.0
    t = min(math.hypot(center[0] - cx, center[1] - cy) / r, 1.0)
    plateau = config.score_distance_plateau
    if plateau >= 1.0 or t <= plateau:
        return 1.0
    return max(0.0, 1.0 - (t - plateau) / (1.0 - plateau))


def _density_factor(obj: DetectedObject, others: list, radius_px: float) -> float:
    """密集因子：以 obj 的 ROI 中点画圆，数圈内其他对象中点个数，1/(1+个数)"""
    n = sum(1 for o in others
            if o is not obj
            and math.hypot(o.center[0] - obj.center[0],
                           o.center[1] - obj.center[1]) <= radius_px)
    return 1.0 / (1.0 + n)


def score_cubes(cubes: list[DetectedObject], frame,
                data: RuntimeData | None = None) -> list[DetectedObject]:
    """魔方评分：距离 + 密集程度（权重取 config.cube_score_weight_*）

    写回 score，按分数从高到低就地排序返回；data 传入时刷新到
    grabbable_cube_list（球侧不动，入库打时间戳）。
    frame 缺失或列表为空时原样返回不评分。
    """
    if frame is None or not cubes:
        return cubes
    circle = grab_circle(frame.shape[1], frame.shape[0])
    dens_r = config.score_density_radius_px
    for o in cubes:
        o.score = (config.cube_score_weight_distance * _distance_factor(o.center, circle)
                   + config.cube_score_weight_density * _density_factor(o, cubes, dens_r))
    cubes.sort(key=lambda o: o.score, reverse=True)
    if data is not None:
        data.set_grabbable(cubes, data.grabbable_ball_list)
    return cubes


def score_balls(balls: list[DetectedObject], frame,
                cubes: list[DetectedObject] | None = None,
                data: RuntimeData | None = None) -> list[DetectedObject]:
    """球评分：距离 + 颜色 + 密集程度（权重取 config.ball_score_weight_*）

    颜色在球 ROI 内判主色，得分查 config 里该颜色球的得分参数
    （判不出主色记 0）；密集程度数周边魔方 ROI 中点（cubes 传魔方列表，
    缺省视为无邻居）。写回 score，排序返回；data 传入时刷新到
    grabbable_ball_list（魔方侧不动，入库打时间戳）。
    """
    if frame is None or not balls:
        return balls
    circle = grab_circle(frame.shape[1], frame.shape[0])
    dens_r = config.score_density_radius_px
    cubes = cubes if cubes is not None else []
    for o in balls:
        color = dominant_color(frame, o.bbox)
        o.score = (config.ball_score_weight_distance * _distance_factor(o.center, circle)
                   + config.ball_score_weight_color * getattr(
                       config, _BALL_COLOR_SCORE_KEY.get(color, ''), 0.0)
                   + config.ball_score_weight_density * _density_factor(o, cubes, dens_r))
    balls.sort(key=lambda o: o.score, reverse=True)
    if data is not None:
        data.set_grabbable(data.grabbable_cube_list, balls)
    return balls

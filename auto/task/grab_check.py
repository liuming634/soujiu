"""抓取成功判定（任务链路）：依据三个舵机的状态反馈综合判定。

判定规则（阈值/范围全部参数化进 config，占位默认为舵机全行程，
现场标定后调整；魔方与球的判定数据不一样，分开配置）：
  1. 伸缩机构正常：舵机1/2 均在伸缩运动范围内，且两者角度偏差 ≤ 容差
  2. 抓取机构已动作：抓取舵机不在静止状态角度范围内
  3. 抓取到位：抓取舵机落在对应目标（魔方/球）的夹取角度范围内
以上全部满足判成功，任一不满足判失败；无状态返回 None（无法判定）。
"""
from common.core.config import config

from auto.actuator.state import ActuatorState
from auto.detection.state import CLS_BALL, CLS_CUBE


def judge_grab_success(state: ActuatorState | None,
                       target: str = CLS_CUBE) -> bool | None:
    """判定是否抓取成功（魔方/球分开判定，参数取 config.grab_*）

    target: 'cube' 用夹魔方角度范围，'ball' 用夹球角度范围。
    """
    if state is None:
        return None

    # 1. 伸缩机构运动范围（舵机1/2共用一套范围），越界即失败
    s_min = config.grab_stretch_range_min
    s_max = config.grab_stretch_range_max
    if not (s_min <= state.stretch_servo_1 <= s_max
            and s_min <= state.stretch_servo_2 <= s_max):
        return False
    # 2. 伸缩舵机1/2 角度偏差在容差内 = 机构正常（无卡斜）
    if abs(state.stretch_servo_1 - state.stretch_servo_2) > config.grab_stretch_deviation_tol:
        return False
    # 3. 抓取舵机已离开静止状态角度范围 = 执行了夹取动作
    if config.grab_idle_range_min <= state.grab_servo <= config.grab_idle_range_max:
        return False
    # 4. 抓取舵机落在对应目标的夹取角度范围内 = 夹到了对应物体
    if target == CLS_BALL:
        g_min, g_max = config.grab_ball_range_min, config.grab_ball_range_max
    else:
        g_min, g_max = config.grab_cube_range_min, config.grab_cube_range_max
    return g_min <= state.grab_servo <= g_max


def is_grabber_idle(state: ActuatorState | None) -> bool | None:
    """抓取机构是否处于静止状态角度范围（空闲判定，供流程层调度用）"""
    if state is None:
        return None
    return config.grab_idle_range_min <= state.grab_servo <= config.grab_idle_range_max

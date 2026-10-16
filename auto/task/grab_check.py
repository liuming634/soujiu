"""抓取判定接口层：每个判定规则一个独立函数，组合逻辑由上层（流程层）自行决定。

本模块只提供"单项判定"接口，不做任何聚合判断：
  1. check_stretch_in_range     伸缩机构运动范围（伸缩舵机1/2 共用一套范围）
  2. check_stretch_aligned      伸缩舵机1/2 角度偏差 ≤ 容差（机构无卡斜）
  3. check_stretch_in_hold      伸缩机构处于静止保持位置角度范围
                               （抓取成功/未抓取时机构都会停在这个保持位置，
                                是判定抓取成功的依据之一）
  4. check_grab_engaged         抓取舵机已离开静止状态范围（执行了夹取动作）
  5. check_grab_in_target_range 抓取舵机落在对应目标（魔方/球）的夹取角度范围
  6. is_grabber_idle            抓取机构是否处于静止状态范围（调度用）

阈值/范围全部参数化进 config（占位默认为舵机全行程 0~4095，现场标定后
调整；魔方与球的夹取范围分开配置）。

返回值语义统一：True=满足该判断 / False=不满足 / None=状态缺失，无法判定。
"""
from common.core.config import config

from auto.actuator.state import ActuatorState
from auto.detection.state import CLS_BALL, CLS_CUBE


def check_stretch_in_range(state: ActuatorState | None) -> bool | None:
    """伸缩机构运动范围：伸缩舵机1/2 是否均在伸缩运动范围内（两舵机共用一套范围）"""
    if state is None:
        return None
    s_min = config.grab_stretch_range_min
    s_max = config.grab_stretch_range_max
    return (s_min <= state.stretch_servo_1 <= s_max
            and s_min <= state.stretch_servo_2 <= s_max)


def check_stretch_aligned(state: ActuatorState | None) -> bool | None:
    """伸缩舵机1/2 角度偏差是否 ≤ 容差（= 机构正常，无卡斜）"""
    if state is None:
        return None
    return abs(state.stretch_servo_1 - state.stretch_servo_2) <= config.grab_stretch_deviation_tol


def check_stretch_in_hold(state: ActuatorState | None) -> bool | None:
    """伸缩机构是否处于静止保持位置角度范围

    伸缩机构在抓取成功/未抓取时都有一个静止保持位置，本接口判定两个
    伸缩舵机是否都落在该保持位置范围内。
    """
    if state is None:
        return None
    lo = config.grab_stretch_hold_range_min
    hi = config.grab_stretch_hold_range_max
    return (lo <= state.stretch_servo_1 <= hi
            and lo <= state.stretch_servo_2 <= hi)


def check_grab_engaged(state: ActuatorState | None) -> bool | None:
    """抓取机构是否已动作：抓取舵机离开静止状态角度范围"""
    if state is None:
        return None
    return not (config.grab_idle_range_min <= state.grab_servo <= config.grab_idle_range_max)


def check_grab_in_target_range(state: ActuatorState | None,
                               target: str = CLS_CUBE) -> bool | None:
    """抓取舵机是否落在对应目标（魔方/球）的夹取角度范围内

    target: 'cube' 用夹魔方角度范围，'ball' 用夹球角度范围。
    """
    if state is None:
        return None
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

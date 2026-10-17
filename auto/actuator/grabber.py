"""抓取机构实时状况判定：抓取舵机角度 → 当前属于什么状况。

抓取舵机基本就三个状况（参考 auto 分支判定思路），各对应一个角度
范围，用这三个范围判定当前状况并返回：
  'empty' 静止状况（空爪闭合位 = 指令角附近，未夹物品）
  'ball'  抓球状况（角度落在夹球范围）
  'cube'  抓魔方状况（角度落在夹魔方范围）
  None    无法判定（无回传；角度不在任何已知范围 = 运动或执行动作中）

状态监视线程（flow）全程轮询调用，结果写 RuntimeData.auto_grabber_status，
供流程逻辑判"抓着东西飞 / 空着飞 / 飞行中掉落"等状况。掉落判定材料：
上一刻 'cube'/'ball'、这一刻 'empty' = 物品脱落（§6.6 思路 A：爪瓣
失去阻力、舵机落回静止位；组合与场景处理在 flow 的树状逻辑里做，
本模块只出单点判定）。

角度范围参数在 auto/params.py actuator 段（GRAB_SERVO_*，占位示意
区间，现场标定后填）。
"""
from common.core.runtime_data import (GRABBER_HOLDING_CUBE, GRABBER_HOLDING_BALL,
                                      GRABBER_EMPTY)

from auto import params
from auto.actuator.state import ActuatorState


def judge_grabber(state: ActuatorState | None) -> str | None:
    """抓取舵机角度 → 抓取机构状况（'empty' / 'ball' / 'cube' / None）"""
    if state is None:
        return None
    g = state.grab_servo
    if params.GRAB_SERVO_CUBE_MIN <= g <= params.GRAB_SERVO_CUBE_MAX:
        return GRABBER_HOLDING_CUBE
    if params.GRAB_SERVO_BALL_MIN <= g <= params.GRAB_SERVO_BALL_MAX:
        return GRABBER_HOLDING_BALL
    if params.GRAB_SERVO_IDLE_MIN <= g <= params.GRAB_SERVO_IDLE_MAX:
        return GRABBER_EMPTY
    return None      # 不在任何已知范围：运动中 / 执行动作中，无法判定

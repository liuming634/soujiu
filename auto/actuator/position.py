"""抓取装置位置解算：闭环传感器读数 → 抓取装置的真实位置。

下位机回传的横向/旋转电机闭环传感器数据是真实的传动位置来源
（算出来的即真实位置），本模块只做读数到物理量的换算，
增益/偏置为参数，待现场标定后传入。

当前为占位实现：先占住位置，后续扩展（如自优化模式）在此模块上做。
"""
from dataclasses import dataclass, asdict

from auto.actuator.state import ActuatorState


@dataclass
class GrabberPosition:
    """抓取装置真实位置（由闭环传感器读数换算）"""

    x: float          # 横向位置（横向移动电机闭环读数换算）
    angle: float      # 旋转角度（旋转移动电机闭环读数换算）

    def as_dict(self) -> dict:
        """转字典（GUI 显示 / 调试用）"""
        return asdict(self)


def solve_position(state: ActuatorState,
                   horizontal_gain: float = 1.0, horizontal_offset: float = 0.0,
                   rotate_gain: float = 1.0, rotate_offset: float = 0.0) -> GrabberPosition:
    """解算抓取装置真实位置

    x = 横向读数 × horizontal_gain + horizontal_offset
    angle = 旋转读数 × rotate_gain + rotate_offset
    增益/偏置为换算参数，现场标定后传入；占位默认 1.0/0.0 即原始读数。
    """
    return GrabberPosition(
        x=state.horizontal_motor * horizontal_gain + horizontal_offset,
        angle=state.rotate_motor * rotate_gain + rotate_offset)


def solve_position_from_data(data, **kwargs) -> GrabberPosition | None:
    """从 RuntimeData 的最新执行机构状态解算位置；状态缺失返回 None"""
    if data.actuator_state is None:
        return None
    return solve_position(data.actuator_state, **kwargs)

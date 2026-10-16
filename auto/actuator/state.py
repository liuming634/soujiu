"""执行机构状态数据：下位机回传的五项数据组成的一个整体。

实时系统只保留最新一帧：旧值直接被覆盖，不做缓存/历史。
时间戳不在这里打 —— 由 ActuatorLink 存入 RuntimeData 时统一打。
"""

from dataclasses import dataclass, asdict


@dataclass
class ActuatorState:
    """下位机一帧回传的执行机构数据（五项为一个整体，整帧更新）"""

    stretch_servo_1: int = 0    # 伸缩机构 舵机 1 位置
    stretch_servo_2: int = 0    # 伸缩机构 舵机 2 位置
    grab_servo: int = 0         # 抓取机构 舵机 位置
    horizontal_motor: int = 0   # 横向移动电机 闭环传感器读数
    rotate_motor: int = 0       # 旋转移动电机 闭环传感器读数

    def as_dict(self) -> dict:
        """转字典（GUI 显示 / 调试用）"""
        return asdict(self)

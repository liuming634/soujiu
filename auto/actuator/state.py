"""执行机构状态数据：下位机回传的数据组成的一个整体。

实时系统只保留最新数据：队列满丢最旧、最新镜像整体覆盖，不做长期
缓存/历史。每帧数据自带 time 时间戳字段——由接收线程在入队前打
（time.time()），多线程处理时按它对齐时序；解析函数本身不打戳，
保持解析纯净。
"""
import time

from dataclasses import dataclass, asdict


@dataclass
class ActuatorState:
    """下位机一帧回传的执行机构数据（三舵机 + 两电机，整帧更新）"""

    stretch_servo_1: int = 0    # 伸缩机构 舵机 1 位置
    stretch_servo_2: int = 0    # 伸缩机构 舵机 2 位置
    grab_servo: int = 0         # 抓取机构 舵机 位置
    horizontal_motor: int = 0   # 横向移动电机 闭环传感器读数
    rotate_motor: int = 0       # 旋转移动电机 闭环传感器读数
    time: float = 0.0           # 帧时间戳（接收线程入队前打，多线程处理对齐用）

    def stamp(self, ts: float | None = None) -> None:
        """打时间戳（接收线程入队前调用；缺省取当前时间）"""
        self.time = time.time() if ts is None else ts

    def as_dict(self) -> dict:
        """转字典（GUI 显示 / 调试用）"""
        return asdict(self)


@dataclass
class ImuData:
    """下位机一帧转发的 IMU 数据（六轴原始读数，落地判定用）

    IMU 接在下位机 STM32 上、由其随回传帧转发（本侧不做 I2C 直连）；
    这里存原始读数，量程换算（原始值 → g / °/s）由使用方按 IMU 量程
    配置换算，不在传输层做。
    """

    accel_x: int = 0            # 加速度计 X 轴原始读数
    accel_y: int = 0            # 加速度计 Y 轴原始读数
    accel_z: int = 0            # 加速度计 Z 轴原始读数
    gyro_x: int = 0             # 陀螺仪 X 轴原始读数
    gyro_y: int = 0             # 陀螺仪 Y 轴原始读数
    gyro_z: int = 0             # 陀螺仪 Z 轴原始读数
    time: float = 0.0           # 帧时间戳（接收线程入队前打，多线程处理对齐用）

    def stamp(self, ts: float | None = None) -> None:
        """打时间戳（接收线程入队前调用；缺省取当前时间）"""
        self.time = time.time() if ts is None else ts

    def as_dict(self) -> dict:
        """转字典（GUI 显示 / 调试用）"""
        return asdict(self)

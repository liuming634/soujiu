"""落地判定源一：IMU 数据跳变检测（触地冲击触发，§1.4）。

【并列备选源】2026-10-18 口述定稿：层1 飞行/落地主判据 = 接收机
（flow._receiver_flight_loop 直改 auto_flight_state），本源与光流
同为并列备选，融合启用时由各自监视线程直改同一状态量。输入是
actuator 接收线程放进 RuntimeData.imu_queue /
imu_state 的 ImuData（auto/actuator/state.py），本模块只做判定函数：
跳变 = 相邻两帧读数之差的合矢量落进可调区间（区间在 auto/params.py
landing 段，随时可调）。触地冲击必现加速度尖峰，角速度尖峰为伴随
条件——任一命中即触发，交由 flow 的确认窗去排除误触发。

持续判定由 monitor.py 的落地监视线程做（imu_queue 逐帧算跳变、
结果写 RuntimeData.landing_imu_hit），启动权在 flow。
"""
import math

from auto import params
from auto.actuator.state import ImuData


def imu_jump_values(current: ImuData, previous: ImuData) -> tuple[float, float]:
    """相邻两帧 IMU 跳变幅度：(加速度合矢量差, 角速度差)（原始读数）

    调参/日志用：把两帧的原始差值算出来，供阈值标定时对照。
    """
    da = math.sqrt((current.accel_x - previous.accel_x) ** 2
                   + (current.accel_y - previous.accel_y) ** 2
                   + (current.accel_z - previous.accel_z) ** 2)
    dg = math.sqrt((current.gyro_x - previous.gyro_x) ** 2
                   + (current.gyro_y - previous.gyro_y) ** 2
                   + (current.gyro_z - previous.gyro_z) ** 2)
    return da, dg


def check_imu_impact(current: ImuData | None,
                     previous: ImuData | None) -> bool | None:
    """IMU 跳变判定：相邻两帧差值落进 params 区间 → True（疑似落地冲击）

    三态：True 跳变命中 / False 未命中 / None 数据缺失（两帧不齐，
    无法算跳变）。加速度、角速度任一差值命中各自区间即 True。
    """
    if current is None or previous is None:
        return None
    da, dg = imu_jump_values(current, previous)
    accel_hit = params.IMU_ACCEL_JUMP_MIN <= da <= params.IMU_ACCEL_JUMP_MAX
    gyro_hit = params.IMU_GYRO_JUMP_MIN <= dg <= params.IMU_GYRO_JUMP_MAX
    return accel_hit or gyro_hit

"""落地判定源三：接收机失联判定（遥控器侧，层1 主判据的判定函数）。

【主判据】2026-10-18 口述定稿：层1 飞行/落地主判定 = 接收机——
flow._receiver_flight_loop 直改 auto_flight_state（收到信号 = flying、
没收到 = landed）；本模块是同一口径的独立判定函数形态（超时失联），
供融合/备选结构复用；IMU 跳变、光流静止为并列备选源。计算平台
（电脑/树莓派）连接收机：落地后人工基本不再操作遥控器，接收机长
时间收不到遥控器信号 → 佐证已落地。超时时长在 auto/params.py
landing 段。

接收机读数线程待硬件接入后实现（协议待定），它负责刷新
RuntimeData.receiver_last_time（最近一次收到信号的时刻，
RuntimeData.set_receiver_signal）；本模块只做判定函数。

注意：早期口径是"通道值不变"，现按"收不到信号"判，判据以本文件为准。
"""
import time

from auto import params


def check_receiver_lost(last_signal_time: float | None,
                        now: float | None = None) -> bool | None:
    """接收机失联判定：距最近一次收到遥控器信号超过超时时长 → True

    三态：True 已失联（疑似落地佐证）/ False 信号正常 /
    None 接收机从未收到过信号（硬件未接入或还没收到第一帧，
    无法判定）。
    """
    if last_signal_time is None:
        return None
    now = time.time() if now is None else now
    return (now - last_signal_time) > params.RECEIVER_LOST_TIMEOUT

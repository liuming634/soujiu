"""落地判定源三：接收机失联判定（遥控器侧辅助源）。

【备用源】当前主判据是 IMU 跳变（impact），本源接口已留，后续融合
时启用。计算平台（电脑/树莓派）连接收机：落地后人工基本不再操作
遥控器，接收机长时间收不到遥控器信号 → 佐证已落地。超时时长在
auto/params.py landing 段。

接收机读数线程待硬件接入后实现（协议待定），它负责刷新
RuntimeData.receiver_last_time（最近一次收到信号的时刻，
RuntimeData.set_receiver_signal）；本模块只做判定函数。

注意：伪代码 §1.4 旧口径是"通道值不变"，现按最新口径改为
"收不到信号"，判据以本文件为准。
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

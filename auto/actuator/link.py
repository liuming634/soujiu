"""与下位机的串口交互接口：发执行命令 + 读执行机构状态。

按需调用的一次性函数接口，不是常驻服务：要发命令时调一次发送函数，
要看执行机构状况时调一次读取函数。发送完全复用
common/hardware/serial_protocol.py（SerialComm，与手动模式同协议同帧）；
读取为拉模式 —— 现场把串口已有数据全部收掉，解析出五项数据
（三个总线舵机 + 两个电机闭环传感器）组成的整体 ActuatorState，
只返回最新一帧，不做缓存/历史；传入 RuntimeData 时存入并统一打时间戳。

反馈帧格式（下位机 → PC，与发送帧同风格，具体以电控实现为准，改本文件常量即可）:
  [0-1]   0x56 0x78   前缀(硬件校验，与发送帧同源 config.serial_prefix)
  [2-3]   0xAA 0x55   帧头
  [4]     0x13(19)    子帧长（帧头→校验和的字节数，与发送帧口径一致）
  [5]     0x02        命令字（状态反馈）
  [6-7]   伸缩舵机1   uint16 大端
  [8-9]   伸缩舵机2   uint16 大端
  [10-11] 抓取舵机    uint16 大端
  [12-15] 横向电机    int32  大端（闭环传感器读数）
  [16-19] 旋转电机    int32  大端（闭环传感器读数）
  [20]    checksum    校验和 (bytes 2~19 累加和低字节，与发送帧口径一致)
"""
import struct
import time

from common.hardware.serial_protocol import SerialComm
from common.core.config import config
from common.core.runtime_data import RuntimeData

from auto.actuator.state import ActuatorState

# ── 反馈帧常量 ──────────────────────────────────────────────
FEEDBACK_HEADER = b'\xAA\x55'
FEEDBACK_LEN = 19            # 子帧长（帧头→校验和）
FEEDBACK_CMD = 0x02          # 命令字：执行机构状态反馈
FEEDBACK_FRAME_LEN = 21      # 整帧字节数
FEEDBACK_PAYLOAD_LEN = 14    # 五项数据的负载字节数


def _feedback_sync() -> bytes:
    """同步头（前缀与发送侧同源，运行时读取以跟随 GUI 修改）"""
    return config.serial_prefix.to_bytes(2, 'big') + FEEDBACK_HEADER


def _feedback_checksum(frame: bytes) -> int:
    """校验和 = bytes 2~19 累加和低字节（与发送帧口径一致）"""
    return sum(frame[2:-1]) & 0xFF


def parse_feedback_payload(payload: bytes) -> ActuatorState | None:
    """反馈帧负载（14 字节）→ ActuatorState；长度不符返回 None"""
    if len(payload) != FEEDBACK_PAYLOAD_LEN:
        return None
    s1, s2, sg = struct.unpack('>HHH', payload[0:6])
    hm, rm = struct.unpack('>ii', payload[6:14])
    return ActuatorState(
        stretch_servo_1=s1, stretch_servo_2=s2, grab_servo=sg,
        horizontal_motor=hm, rotate_motor=rm)


def drain_feedback_frames(buf: bytearray) -> list[ActuatorState]:
    """从接收缓冲取出所有完整合法的反馈帧（原地消费 buf）

    - 找不到同步头：只保留末尾 3 字节（防止同步头被两次读取截断）
    - 半帧：留在缓冲等下一次数据
    - 校验失败：滑过一个字节重新同步，脏数据不会撑爆缓冲
    """
    sync = _feedback_sync()
    states = []
    while True:
        idx = buf.find(sync)
        if idx < 0:
            if len(buf) > 3:
                del buf[:-3]
            return states
        if idx > 0:
            del buf[:idx]                      # 丢弃同步头前的脏数据
        if len(buf) < FEEDBACK_FRAME_LEN:
            return states                      # 半帧，等下一次
        frame = bytes(buf[:FEEDBACK_FRAME_LEN])
        if (frame[4] == FEEDBACK_LEN and frame[5] == FEEDBACK_CMD
                and _feedback_checksum(frame) == frame[20]):
            state = parse_feedback_payload(frame[6:FEEDBACK_FRAME_LEN - 1])
            if state is not None:
                states.append(state)
            del buf[:FEEDBACK_FRAME_LEN]
        else:
            del buf[:1]                        # 假同步头，滑过重新找


# ── 对外函数接口（按需调用一次，非常驻服务） ──────────────────

def open_comm() -> SerialComm:
    """按当前配置打开下位机串口（调用方持有，用完 close()）"""
    return SerialComm(config.serial_port, config.serial_baudrate,
                      timeout=config.serial_timeout)


def send_command(comm: SerialComm, x: int, y: int, n: int, rx: int = 0) -> bool:
    """发送一条执行命令（协议值 0~9999，与手动模式同一帧格式）"""
    return comm.send_data(x, y, n, rx)


def send_command_repeat(comm: SerialComm, x: int, y: int, n: int, rx: int = 0,
                        duration: float | None = None,
                        interval: float | None = None,
                        cancel_event=None) -> bool:
    """连续发送：duration 秒内每隔 interval 发一次（阻塞调用）

    时长/间隔缺省取配置 serial_send_duration / serial_send_interval；
    需要不阻塞调用方时自行放线程跑（手动模式即此做法），
    cancel_event 可从外部提前停止。
    """
    return comm.send_data_repeat(x, y, n, rx, duration=duration,
                                 interval=interval, cancel_event=cancel_event)


def read_actuator_state(comm: SerialComm, data: RuntimeData | None = None,
                        timeout: float = 0.2) -> ActuatorState | None:
    """读一次执行机构状态（拉模式，按需调用一次）

    把串口现有数据全部收掉并解析，返回最新一帧 ActuatorState；
    timeout 秒内没等到任何完整帧返回 None（0 = 只收当前已有数据，不等）。
    data 传入 RuntimeData 时把结果整体存入并打时间戳
    （data.actuator_state / data.actuator_state_time）。
    """
    buf = bytearray()
    ser = comm.ser
    deadline = time.monotonic() + timeout
    latest = None
    while True:
        try:
            chunk = ser.read(64)
        except Exception as e:
            print(f"读取执行机构状态失败: {e}")
            return None
        if chunk:
            buf += chunk
            for state in drain_feedback_frames(buf):
                latest = state          # 整体覆盖，只留最新一帧
        if time.monotonic() >= deadline:
            break
        if latest is not None and not chunk:
            break                       # 已拿到帧且端口暂时静默，收干净了
    if latest is not None and data is not None:
        data.set_actuator_state(latest)  # 入库时统一打时间戳
    return latest

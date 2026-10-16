"""与下位机的串口交互：接收侧——把 STM32 回传的数据收到、解析、入库。

本模块只做接收；发送不另做封装，直接用
common/hardware/serial_protocol.py 的 SerialComm（与手动模式同协议
同帧，open_comm() 返回的就是它，收发共用同一个串口）。

持续接收：ActuatorReceiver 起一个后台读线程持续收串口、按命令字
分流——机构状态帧入 RuntimeData.actuator_queue，IMU 帧入
RuntimeData.imu_queue（队列满丢最旧、保留最新），同时刷新 *_state
最新一帧镜像。时间戳打在数据对象自己的 time 字段里（入队前打，
多线程处理时序对齐用）。串口是单字节流，物理读取只能由一个线程做
（两个线程同时 read 会把同一帧的字节撕到两个线程里、谁也拼不完整），
分流到两条队列后，各数据通道（机构状态 / IMU）独立取用。

回传数据（下位机 → PC，经同一串口；帧格式与发送帧同风格，具体以
电控实现为准 —— 命令字/负载布局改本文件常量与解析函数即可，接收
主体按"校验和合法 → 按命令字分发"工作，新增数据类型不动接收逻辑）：

  命令字 0x02 执行机构状态帧（三舵机 + 两电机）:
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

  命令字 0x03 IMU 数据帧（IMU 接在 STM32 上由其转发，落地判定用）:
    [0-1]   0x56 0x78   前缀（同上）
    [2-3]   0xAA 0x55   帧头
    [4]     0x11(17)    子帧长
    [5]     0x03        命令字（IMU 转发）
    [6-17]  加速度 xyz + 角速度 xyz   6 × int16 大端（原始读数）
    [18]    checksum    校验和 (bytes 2~17 累加和低字节)

  其他数据（预留）：电控后续要回传新数据（如下位机状态位、舵机
  负载/电流）时，加一个命令字 + 解析函数即可；未知命令字整帧丢弃，
  不影响已支持的帧。
"""
import struct
import time
import threading

from common.hardware.serial_protocol import SerialComm
from common.core.config import config
from common.core.runtime_data import RuntimeData

from auto.actuator.state import ActuatorState, ImuData

# ── 帧公共常量（与发送帧同风格） ────────────────────────────
FRAME_HEADER = b'\xAA\x55'           # 帧头（前缀之后）
MIN_SUB_LEN = 6                      # 子帧长下限（帧头2+长1+命令1+校验1+负载1）
MAX_SUB_LEN = 64                     # 子帧长上限（脏数据防误判）


def _sync() -> bytes:
    """同步头（前缀与发送侧同源，运行时读取以跟随 GUI 修改）"""
    return config.serial_prefix.to_bytes(2, 'big') + FRAME_HEADER


def _checksum(frame: bytes) -> int:
    """校验和 = bytes 2~倒数第二字节 累加和低字节（与发送帧口径一致）"""
    return sum(frame[2:-1]) & 0xFF


# ── 执行机构状态帧（命令字 0x02） ───────────────────────────
CMD_STATUS = 0x02
STATUS_SUB_LEN = 19                  # 子帧长（帧头→校验和）
STATUS_PAYLOAD_LEN = 14              # 五项数据负载字节数


def _parse_status_payload(payload: bytes) -> ActuatorState | None:
    """状态帧负载（14 字节）→ ActuatorState；长度不符返回 None"""
    if len(payload) != STATUS_PAYLOAD_LEN:
        return None
    s1, s2, sg = struct.unpack('>HHH', payload[0:6])
    hm, rm = struct.unpack('>ii', payload[6:14])
    return ActuatorState(
        stretch_servo_1=s1, stretch_servo_2=s2, grab_servo=sg,
        horizontal_motor=hm, rotate_motor=rm)


# ── IMU 数据帧（命令字 0x03） ───────────────────────────────
CMD_IMU = 0x03
IMU_SUB_LEN = 17                     # 子帧长（帧头→校验和）
IMU_PAYLOAD_LEN = 12                 # 六轴原始读数负载字节数


def _parse_imu_payload(payload: bytes) -> ImuData | None:
    """IMU 帧负载（12 字节）→ ImuData；长度不符返回 None"""
    if len(payload) != IMU_PAYLOAD_LEN:
        return None
    ax, ay, az, gx, gy, gz = struct.unpack('>6h', payload)
    return ImuData(accel_x=ax, accel_y=ay, accel_z=az,
                   gyro_x=gx, gyro_y=gy, gyro_z=gz)


# 命令字 → 负载解析函数（新增回传数据类型时在这里加一行即可）
_PARSERS = {
    CMD_STATUS: _parse_status_payload,
    CMD_IMU: _parse_imu_payload,
}


def drain_frames(buf: bytearray) -> list[tuple[int, ActuatorState | ImuData]]:
    """从接收缓冲取出所有完整合法的回传帧（原地消费 buf）

    返回 [(命令字, 解析结果), ...]，保持帧序（同类型多帧时取末尾的
    即最新）。处理规则：
    - 找不到同步头：只保留末尾 len(同步头)-1 字节（防同步头被截断）
    - 半帧：留在缓冲等下一次数据
    - 子帧长不合法 / 校验失败 / 假同步头：滑过一个字节重新同步，
      脏数据不会撑爆缓冲
    - 校验合法但命令字未知：按其声明长度整帧丢弃（为电控新增
      数据类型预留，不影响已支持的帧）
    """
    sync = _sync()
    frames: list[tuple[int, ActuatorState | ImuData]] = []
    while True:
        idx = buf.find(sync)
        if idx < 0:
            if len(buf) > len(sync) - 1:
                del buf[:-(len(sync) - 1)]
            return frames
        if idx > 0:
            del buf[:idx]                      # 丢弃同步头前的脏数据
        if len(buf) < MIN_SUB_LEN + 2:
            return frames                      # 连子帧长都读不全，等下一次
        sub_len = buf[4]                       # 子帧长（帧头→校验和）
        if not (MIN_SUB_LEN <= sub_len <= MAX_SUB_LEN):
            del buf[:1]
            continue                           # 长度不合法，假同步头
        total = sub_len + 2                    # 整帧 = 前缀2 + 子帧
        if len(buf) < total:
            return frames                      # 半帧，等下一次
        frame = bytes(buf[:total])
        if _checksum(frame) == frame[-1] and frame[5] in _PARSERS:
            obj = _PARSERS[frame[5]](frame[6:-1])
            if obj is not None:
                frames.append((frame[5], obj))
            del buf[:total]
        else:
            del buf[:1]                        # 校验失败/未知命令字，滑过重找


# ── 对外接口：打开串口 + 后台接收线程 ─────────────────────────

def open_comm() -> SerialComm:
    """按当前配置打开下位机串口（调用方持有，用完 close()）"""
    return SerialComm(config.serial_port, config.serial_baudrate,
                      timeout=config.serial_timeout)


class ActuatorReceiver:
    """下位机回传接收器：后台读线程持续收串口，按命令字分流入两条队列

    单读线程原因：串口是单字节流，两个线程同时 read 会把同一帧的字节
    撕到两个线程里、谁也拼不完整——物理读取必须单线程；分流由
    drain_frames 按命令字完成，机构状态与 IMU 各进各的队列
    （RuntimeData.actuator_queue / imu_queue，满了丢最旧保最新），
    处理端各取各的队列，时间戳已在数据对象里。
    """

    def __init__(self, comm: SerialComm, data: RuntimeData):
        self._comm = comm
        self._data = data
        self._buf = bytearray()
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """启动接收线程（重复调用无副作用）"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run,
                                        name="actuator-rx", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止接收线程并等待退出"""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _run(self) -> None:
        ser = self._comm.ser
        while self._running:
            try:
                chunk = ser.read(64)   # 阻塞至串口超时（config.serial_timeout）
            except Exception as e:
                print(f"接收线程读串口失败: {e}")
                time.sleep(0.2)        # 异常时缓一拍，避免刷屏死循环
                continue
            if not chunk:
                continue
            self._buf += chunk
            for cmd, obj in drain_frames(self._buf):
                obj.stamp()            # 时间戳打进数据对象（入队前打）
                if cmd == CMD_STATUS:
                    self._data.actuator_queue.append(obj)
                    self._data.set_actuator_state(obj)   # 最新一帧镜像
                elif cmd == CMD_IMU:
                    self._data.imu_queue.append(obj)
                    self._data.set_imu_state(obj)
                # 新增回传数据类型时：在 _PARSERS 加解析函数，这里加分流分支


# ── 模块级函数 API（调用方一行起停） ──────────────────────────

_receiver: ActuatorReceiver | None = None   # 当前接收器（start/stop 管理）


def start_receiving(comm: SerialComm, data: RuntimeData) -> None:
    """启动持续接收：后台线程一直收，数据进 RuntimeData 两条队列

    已在收则不重复启动；要换串口/数据中心先 stop_receiving()。
    """
    global _receiver
    if _receiver is not None:
        return
    _receiver = ActuatorReceiver(comm, data)
    _receiver.start()


def stop_receiving() -> None:
    """停止持续接收线程"""
    global _receiver
    if _receiver is not None:
        _receiver.stop()
        _receiver = None

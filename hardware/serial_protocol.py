"""
串口通信协议模块
"""
import re
import serial
import sys
import os


def _normalize_port(port: str) -> str:
    """规范化串口端口名

    Windows 上 COM10 及以上必须使用 \\\\.\\COM10 格式，
    否则 serial.Serial() 无法打开。
    Linux/macOS 不变。
    """
    if sys.platform.startswith("win"):
        m = re.match(r'^(COM)(\d+)$', port, re.IGNORECASE)
        if m and int(m.group(2)) >= 10:
            return rf'\\.\{port}'
    return port


class SerialDataProtocol:
    """18 字节协议：2字节hex前缀 0x5678 + 16字节STM32数据帧

    帧布局:
      [0-1]  0x56 0x78  前缀(硬件校验)
      [2-3]  0xAA 0x55  帧头标志位
      [4]    0x10       STM32帧长(16)
      [5]    0x01       命令字
      [6-7]  X          数据1 大端 (0~9999)
      [8-9]  Y          数据2 大端 (0~9999)
      [10]   N          数据3 (0~9)
      [11-12] RX        右键X 大端 (0~9999)
      [13-16] 0x00      保留区 (4字节)
      [17]   checksum   校验和 (bytes 2~16 累加和低字节)
    """

    HEADER = b'\xAA\x55'
    FRAME_LEN = 18
    STM32_FRAME_LEN = 16
    CMD_DATA = 0x01
    MAX_DATA = 9999   # 数据1/2/4 取值范围 (0~9999)
    MAX_N = 9         # 数据3 N 取值范围 (0~9)

    @staticmethod
    def pack(data1: int, data2: int, data3: int, data4: int = 0, prefix: bytes = None) -> bytes:
        """打包四个数成 18 字节帧

        prefix: 硬件校验前缀，2字节（由调用方按 config.serial_prefix 传入，必填）
        """
        if not (0 <= data1 <= SerialDataProtocol.MAX_DATA
                and 0 <= data2 <= SerialDataProtocol.MAX_DATA
                and 0 <= data3 <= SerialDataProtocol.MAX_N
                and 0 <= data4 <= SerialDataProtocol.MAX_DATA):
            raise ValueError("data1/data2/data4 必须为 0~9999，data3 必须为 0~9")
        if not prefix or len(prefix) != 2:
            raise ValueError("prefix 必须为 2 字节")

        frame = bytearray(SerialDataProtocol.FRAME_LEN)
        # 前缀 (硬件校验)
        frame[0:2] = prefix
        # STM32 帧头
        frame[2:4] = SerialDataProtocol.HEADER
        # STM32 帧长
        frame[4] = SerialDataProtocol.STM32_FRAME_LEN
        # 命令字
        frame[5] = SerialDataProtocol.CMD_DATA
        # 数据1 X (大端)
        frame[6] = (data1 >> 8) & 0xFF
        frame[7] = data1 & 0xFF
        # 数据2 Y (大端)
        frame[8] = (data2 >> 8) & 0xFF
        frame[9] = data2 & 0xFF
        # 数据3 N
        frame[10] = data3 & 0xFF
        # 数据4 右键X (大端)
        frame[11] = (data4 >> 8) & 0xFF
        frame[12] = data4 & 0xFF
        # 保留区 (13~16) 4 字节已默认为 0
        # 校验和 = STM32 子帧前 15 字节累加和
        checksum = sum(frame[2:17]) & 0xFF
        frame[17] = checksum
        return bytes(frame)

class SerialComm:
    """串口通讯模块，基于上述协议（带连接状态追踪）"""

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 0.1):
        """
        :param port: 串口号，如 'COM3' (Windows) 或 '/dev/ttyUSB0' (Linux)
        :param baudrate: 波特率
        :param timeout: 读取超时（秒）
        """
        # Linux 上先检查设备文件是否存在，避免 serial.Serial() 长时间阻塞
        if not sys.platform.startswith("win") and not os.path.exists(port):
            raise FileNotFoundError(f"串口设备不存在: {port}")

        # 规范化端口名（解决 Windows COM10+ 问题）
        normalized = _normalize_port(port)
        if normalized != port:
            print(f"   [INFO] 端口名规范化: {port} → {normalized}")
        self.ser = serial.Serial(normalized, baudrate, timeout=timeout)
        self.protocol = SerialDataProtocol()
        self._connected = True  # 打开成功即为已连接

    def is_connected(self) -> bool:
        """串口当前是否正常连接"""
        try:
            return self.ser.is_open and self._connected
        except Exception:
            return False

    def send_data(self, data1: int, data2: int, data3: int, data4: int = 0) -> bool:
        """发送四个数，成功返回 True，失败标记断开"""
        try:
            from core.config import config
            prefix = config.serial_prefix.to_bytes(2, 'big')
            frame = self.protocol.pack(data1, data2, data3, data4, prefix=prefix)
            self.ser.write(frame)
            self._connected = True
            return True
        except Exception as e:
            print(f"发送失败: {e}")
            self._connected = False
            return False

    def close(self):
        """关闭串口"""
        if self.ser and self.ser.is_open:
            self.ser.close()

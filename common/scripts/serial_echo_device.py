"""串口接收端（回传确认）模拟脚本

接收端逻辑：循环 收帧 → 校验(前缀/帧头/checksum) → 原样回传相同帧。
发送端配合 send_data_reliable() 使用：收到回传的相同数据帧即确认停止。

PC 上全链路测试：
  socat -d -d pty,raw,echo=0 pty,raw,echo=0   # 创建虚拟串口对 /dev/pts/X 和 /dev/pts/Y
  python common/scripts/serial_echo_device.py /dev/pts/X 9600
  （主程序串口设为 /dev/pts/Y）

STM32 端实现参考：串口中断收满 18 字节 → 校验帧头/校验和 → 原样回发。
"""
import os
import sys
import time

import serial

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from common.hardware.serial_protocol import SerialDataProtocol, SerialComm, _normalize_port


def run(port: str, baudrate: int, prefix: bytes):
    ser = serial.Serial(_normalize_port(port), baudrate, timeout=0.1)
    proto = SerialDataProtocol()
    frame_len = proto.FRAME_LEN
    anchor = prefix + proto.HEADER  # 2字节前缀 + 帧头作为整体锚点
    print(f"接收端已打开: {port} @ {baudrate}，等待数据帧...")

    buf = bytearray()
    ack_count = 0
    try:
        while True:
            chunk = ser.read(frame_len - len(buf))
            if chunk:
                buf.extend(chunk)
            if len(buf) < frame_len:
                continue

            # 对齐：丢弃锚点之前的杂散字节
            idx = buf.find(anchor)
            if idx < 0:
                if len(buf) > len(anchor) - 1:
                    del buf[:len(buf) - (len(anchor) - 1)]
                continue
            elif idx > 0:
                del buf[:idx]

            if len(buf) < frame_len:
                continue
            frame = bytes(buf[:frame_len])
            checksum = sum(frame[2:17]) & 0xFF
            if frame[17] == checksum:
                d1 = int.from_bytes(frame[6:8], 'big')
                d2 = int.from_bytes(frame[8:10], 'big')
                d3, d4 = frame[10], int.from_bytes(frame[11:13], 'big')
                ack_count += 1
                print(f"[收到 #{ack_count}] X={d1}, Y={d2}, N={d3}, 右键X={d4} → 回传确认")
                ser.write(frame)  # 原样回传相同帧
                del buf[:frame_len]
            else:
                del buf[:1]
            time.sleep(0.005)
    except KeyboardInterrupt:
        print("\n接收端退出")
    finally:
        ser.close()


if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/pts/3"
    baudrate = int(sys.argv[2]) if len(sys.argv) > 2 else 9600
    from common.core.config import config
    run(port, baudrate, config.serial_prefix.to_bytes(2, 'big'))

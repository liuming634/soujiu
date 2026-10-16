"""执行机构（下位机）交互：监控抓取机构状况、反馈是否抓取成功。

- state.py    下位机回传的五项数据（3 总线舵机 + 2 电机闭环传感器）组成的整体数据
- link.py     下位机串口交互的函数接口（按需调用一次，非常驻服务）：
              send_command / send_command_repeat 发执行命令
              （复用 common/hardware/serial_protocol.py），
              read_actuator_state 拉模式读一次执行机构状态，
              可选整体存入 RuntimeData（入库时打时间戳）
- position.py 抓取装置位置解算：闭环传感器读数 → 真实位置
              （换算增益/偏置为参数，占位实现待扩展）
"""

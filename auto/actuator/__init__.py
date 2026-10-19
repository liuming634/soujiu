"""执行机构模块：把下位机 STM32 回传的数据收到（接收侧已实现）。

职责口径（已定）：本模块只管把数据收到——三舵机、两电机、IMU、
其他数据都由 STM32 从同一串口发回来，这里收掉、按命令字解析、入库。
发送不另做封装：flow 直接用 common/hardware/serial_protocol.py 的
SerialComm（与手动模式同协议同帧，收发共用一个串口）。

已实现（state.py / link.py / grabber.py）：
  1. ActuatorState（state.py）：执行机构状态——三舵机（伸缩1/2 + 抓取）
     + 两电机闭环读数，五项一帧整体更新（命令字 0x02）
  2. ImuData（state.py）：IMU 六轴原始读数一帧（命令字 0x03）——
     IMU 接在 STM32 上由其转发，落地判定（auto/landing）从
     RuntimeData.imu_queue / imu_state 取，本侧不做 I2C 直连
  3. 持续接收（link.py ActuatorReceiver）：后台读线程持续收串口 →
     按命令字分流 → 机构状态帧入 RuntimeData.actuator_queue、IMU 帧
     入 RuntimeData.imu_queue（队列满丢最旧保最新，长度在
     runtime_data.py 定：机构 16 / IMU 128），同时刷新 *_state 最新
     一帧镜像；时间戳打在数据对象自己的 time 字段里（入队前打，
     多线程处理时序对齐用）。串口是单字节流、物理读取只能一个线程
     （两个线程同时 read 会把帧撕碎），分流到两条队列后各数据通道
     独立消费；模块级函数 API：start_receiving(comm, data) 启动 /
     stop_receiving() 停止
  4. 帧格式：与发送帧同风格（前缀 + 帧头 + 子帧长 + 命令字 + 负载 +
     校验和），格式细节以电控实现为准——改 link.py 常量与解析函数即可；
     接收主体按"校验和合法 → 按命令字分发"工作，未知命令字整帧丢弃，
     后续"其他数据"要回传时加一个命令字 + 解析函数即可，接收逻辑不动
  5. 抓取机构实时状况判定（grabber.py judge_grabber）：抓取舵机角度 →
     'empty' / 'ball' / 'cube' / None（三状况各一个角度范围：静止 /
     抓球 / 抓魔方），状态监视线程全程轮询写 RuntimeData.
     auto_grabber_status；范围参数在 auto/params.py actuator 段
      （占位示意区间，标定后填）。三舵机六要素的组合判定（抓取成败
      完整版）路径见 docs/扩展功能技术路线.md

数据用途对照（谁消费什么）：
  三舵机   → 抓取成败判定（简化版直判已实现，六要素完整版见 docs）
           / 机构健康监视（G2，路径见 docs）/ 掉落检测
  两电机   → 下位机判稳佐证（帧间静止，路径见 docs）/ 位置解算（自优化预留）
  IMU 六轴 → 落地判定（IMU 跳变判定源；融合升级路径见 docs）
  其他数据 → 预留待电控确认：下位机状态位 / 舵机负载电流（掉落思路 B）

后续待实现：舵机角度判定工具完整版（抓取成败/机构健康/掉落三处
共用，路径见 docs/扩展功能技术路线.md）、帧间静止判定工具（判稳
佐证）、位置解算（闭环读数 → 真实位置，占位）。

待电控确认：0x02 机构状态帧的回传频率；0x03 IMU 帧的转发频率与
量程换算系数（原始值 → g / °/s）；"其他数据"要不要加、加什么。
"""

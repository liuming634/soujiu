"""落地判定模块：三个判定源并列实现，接口就绪。

【主判据 = 接收机】（2026-10-18 定稿）：flow._receiver_flight_loop
监视线程持续判定、直改 auto_flight_state（收到遥控器信号 = flying、
超时收不到 = landed）；IMU 跳变 / 光流画面静止为并列备选源——三者
同形态、换主源 = 换线程，大循环与字段零改动。多源融合升级与下位机
判稳佐证的结构化说明见 docs/扩展功能技术路线.md。

三个判定源（都是"输入 → 判定 → return"的函数，三态：True 命中 /
False 未命中 / None 数据缺失无法判定；可调参数全部集中在
auto/params.py 的 landing 段，调参只改那一个文件）：

  1. receiver.check_receiver_lost(last_signal_time) ——【主判据判定函数】
      实时判定在 flow 的接收机线程做；本模块是超时失联的独立函数
      形态，供备选结构与融合复用：超过超时时长收不到遥控器信号 →
      佐证已落地（落地后人工基本不再操作）。接收机读数线程待硬件
      接入后实现（协议待定），接入后负责刷新
      RuntimeData.receiver_last_time（判定口径三选一见
      flow/main.py 的 _receiver_signal_active 注释）。

  2. impact.check_imu_impact(current, previous) ——【并列备选源】
      IMU 数据跳变检测（触地冲击触发）：相邻两帧读数差值的合矢量落
      进可调区间（加速度/角速度任一命中即触发）。输入是 actuator 收
      进 RuntimeData 的 ImuData（imu_queue / imu_state）。
      持续判定由 monitor 的监视线程做：start_landing_monitor(data) /
      stop_landing_monitor()（启动权在 flow，与 start_receiving 同款
      start/stop API）——监视线程只读 imu_queue 最新帧逐帧判定，结果
      写 RuntimeData.landing_imu_hit / landing_imu_hit_time，不消费
      队列（历史帧留给确认窗）。IMU 单独用线程监视的原因：落地信号
      毫秒级，单线程把所有链路顺下来会漏判定。

  3. frame_still.check_frame_still(prev_frame, curr_frame) ——【并列备选源】
      前后帧光流对比（Farneback 稠密光流，降采样提性能）：平均光流
      幅值落进区间 → 画面几乎没动。不用 YOLO——效果一样但性能占用
      大没有意义。纯函数按帧喂图，结果由调用方回写
      landing_frame_still；方案 B 帧差备选见 docs/扩展功能技术路线.md。

落地信号融合确认（如"冲击触发 + 多源短确认窗"）是 flow 侧组合逻辑，
本模块只给单源判定函数；数值待实测标定（IMU 量程换算系数——阈值现为
原始读数占位值、各区区间、接收机读数接入方式）。
"""

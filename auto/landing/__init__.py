"""落地判定模块：阶段一的三个落地判定源（§1.4、§1.5），判定接口已实现，
多源组合与确认窗逻辑在 flow。

【当前主判据 = IMU 跳变】暂时只用 IMU 检测判定落地（监视线程持续
判定、不会漏帧），光流画面静止 / 接收机失联为备用源（接口已留），
后面考虑和其他方法做融合。实时性优先：不等"稳定持续很久"，直接
检测落地冲击事件作触发，触发后由 flow 开很短的确认窗做多源并联
确认——本模块只给单源判定函数，组合方式由 flow 按现场情况决定。

三个判定源（都是"输入 → 判定 → return"的函数，三态：True 命中 /
False 未命中 / None 数据缺失无法判定；可调参数全部集中在
auto/params.py 的 landing 段，调参只改那一个文件）：

  1. impact.check_imu_impact(current, previous) ——【主判据】
     IMU 数据跳变检测（触地冲击触发）：相邻两帧读数差值的合矢量落
     进可调区间（加速度/角速度任一命中即触发）。输入是 actuator 收
     进 RuntimeData 的 ImuData（imu_queue / imu_state）。
     持续判定由 monitor 的监视线程做：start_landing_monitor(data) /
     stop_landing_monitor()（启动权在 flow，与 start_receiving 同款
     start/stop API）——监视线程只读 imu_queue 最新帧逐帧判定，结果
     写 RuntimeData.landing_imu_hit / landing_imu_hit_time，不消费
     队列（历史帧留给确认窗）。IMU 单独用线程监视的原因：落地信号
     毫秒级，单线程把所有链路顺下来会漏判定。

  2. frame_still.check_frame_still(prev_frame, curr_frame) ——【备用源】
     前后帧光流对比（Farneback 稠密光流，降采样提性能）：平均光流
     幅值落进区间 → 画面几乎没动。不用 YOLO——效果一样但性能占用
     大没有意义。纯函数按帧喂图，结果由调用方回写
     landing_frame_still；连续 K 帧/M 组的组合计数在 flow。

  3. receiver.check_receiver_lost(last_signal_time) ——【备用源】
     接收机失联判定：计算平台连接收机，超过超时时长收不到遥控器
     信号 → 佐证已落地（落地后人工基本不再操作）。接收机读数线程
     待硬件接入后实现（协议待定），接入后负责刷新
     RuntimeData.receiver_last_time。（口径更新：伪代码旧稿是
     "通道值不变"，现按"收不到信号"判。）

状态位接线（接口已备，逻辑后面写）：检测到落地信号后把
RuntimeData.auto_state 切到 landed（RuntimeData.set_auto_state），
状态切了下游链路才启动——切换时机与条件由 flow 的逻辑代码做。

待定（电控/实测）：IMU 量程换算系数（阈值现为原始读数占位值）、
各区间的实测标定、接收机读数接入方式。
"""

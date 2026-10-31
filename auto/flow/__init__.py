"""流程主干模块：自动链路的总调度（已实现，main.py）。

实现形态（2026-10-18 口述定稿）：FreeRTOS 式轮询调度——监视线程持续
监控、直接修改 RuntimeData 状态量；while 大循环只读状态量、三层 if
分发；接口处理只改状态与记账，动作在下一轮轮询里由新状态驱动。
入口：start_flow(data, with_camera) / stop_flow()。

  监视线程（生产者，直改状态量）：
    STM32 接收（actuator.start_receiving）→ actuator_state / imu_state
    接收机判飞行线程   → 层1 auto_flight_state（flying/landed；
                         主源 = 接收机，IMU/光流并列备选，同形态换源）
    机构监视线程       → 层2 auto_mech_state（idle/hold/process；
                         低频采样入长队列，收样当场判脱落）
    YOLO 任务判定线程  → yolo_task（抓魔方/抓球/投放魔方/投放球）
    相机取帧线程       → current_frame
  大循环三层 if：层1 飞行状况 → 层2 机构状况 → 层3 任务记账/yolo_task
    两层状态组合 2×3 = 六情况，覆盖任务全程；抓取链路：N 定奇偶品类
    → region 圈内过滤 → scoring 评分选靶 → common 坐标映射 → 发指令
    → 验证（超时计数，3 次失败提示人工重飞）；掉落 = N+1 且奇偶映射
    翻转 → 重抓同品类；投放完成 = 落地松开（动作或掉落都算）→ N+1
    计消耗、提示飞回；完赛：cube_done ≥ 15（G1）。

判定工具与各判定源（detection / region / scoring / actuator / landing
提供；每个判定都留了并列可换的实现路径，详见 docs/扩展功能技术路线.md）：
  - 层1 判定源三选一：接收机（主）/ IMU 跳变 / 光流静止——同形态
    换监视线程，大循环不动
  - 掉落检测：思路 A 角度越界（现用，机构监视线程长队列）/ 思路 B
    负载/电流回读（备选，看总线舵机型号）
  - 发送 API 两档：SerialComm.send_data 单发 / send_data_repeat 连发
    （单发还是连发待电控定口径）
  - 画面静止备选实现：方案 A 光流（现用）/ 方案 B 帧差（保留未实现）
  - 调度形态备选：行为树（py_trees，纯 Python、树莓派可用）等价实现
    ——状态量做黑板、六情况做动作叶子节点、Selector/Sequence 表达
    分发与顺序；留作单独分支的实现路径，主循环骨架可原样复用
"""

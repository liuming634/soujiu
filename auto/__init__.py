"""自动链路包：抓取机构自动化（总调度在 flow/main.py，可调参数在 params.py）。

角色分工（重要）：无人机由人工飞行，本包只做抓取机构的自动化——
识别、判定、给下位机发指令、推进状态；"是否重新飞"由人工决定。
总调度形态：FreeRTOS 式轮询——监视线程直改 RuntimeData 状态量 +
while 大循环三层 if 分发（层1 飞行状况 → 层2 机构状况 → 层3 任务
记账/YOLO 任务判定），两层状态组合 = 六情况覆盖任务全程；
模块架构约定见 docs/开发约束.md，方法与路径见 docs/自动抓取技术实现.md，
备选与未实现路径见 docs/扩展功能技术路线.md。

模块划分（6 个子包）：
  flow/       流程主干（已实现）：start_flow/stop_flow 装 5 个监视线程
              （STM32 接收 / 接收机判飞行 / 机构监视 / YOLO 任务判定 /
              相机取帧）+ while 大循环三层 if 分发
  landing/    落地判定：三判定源并列已实现——接收机（【主判据】，flow
              监视线程直改）/ IMU 跳变（监视线程 start_landing_monitor）/
              光流画面静止；换主源 = 换线程，大循环不动；融合升级路径
              见 docs/扩展功能技术路线.md
  params.py   auto 模块专用参数文件：全链路可调参数集中处（按模块分段，
              调参只改这一个文件）
  detection/  识别（已实现）：YOLO 四类检测 API + 六色色块工具
  region/     抓取圈几何（已实现）：对比板查色——圈换算 / 点在圈内
              （桶可投）/ 重合面积 + 阈值判定（盆可投）/ 圈内过滤
  scoring/    评分选靶（已实现）：距离+颜色(球)+密集 三因子加权，
              ScoredTarget 排序列表（最高分先抓，并列编号序）；
              复用 detection 色块工具与 region 圈换算
  actuator/   执行机构（已实现）：串口收发 + 回传解析 ActuatorState +
              舵机角度判定工具（judge_grabber 单点判定；三舵机六要素
              完整版路径见 docs/扩展功能技术路线.md）

协作关系：flow 是唯一编排者——通过各模块的函数 API 把能力串起来
（detection 识别 → region 圈内过滤 → scoring 评分选靶 → common 坐标
映射 → actuator 收发；landing 提供判定源）；scoring 复用 detection
色块工具与 region 圈换算，除此之外平级模块间不互相调用。
与手动链路共用 common/ 下的通用工具。

开发约定（全包通用，详见 docs/开发约束.md）：
  - 判定输出三态：True / False / None（None = 数据缺失无法判定）
  - 参数不写死：阈值/范围/权重/时间周期统一放 auto/params.py
  - 串口 18 字节协议不变（无线改有线链路），复用 common 串口模块
  - 推理时机：仅落地后投帧推理（落地之后才需要识别，飞行中跑推理
    没有意义；树莓派部署约定，比赛说明 §6）
"""

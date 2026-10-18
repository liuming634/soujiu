"""auto 模块专用参数文件：自动链路所有可调参数集中在这一个文件。

调参只改这里，不动逻辑代码（模块代码只 import 本文件取值）。手动
链路的参数仍在 common 的 config（camera_params.yaml / GUI 设置），
两边不混。标注"占位"的数值待实测标定；按模块分段，新模块的参数
随实现往这里加段。
"""

# ══════════════════════ landing 落地判定 ══════════════════════
# 主判据 = 接收机（2026-10-18 口述定稿，flow._receiver_flight_loop
# 直改层1状态）；IMU 跳变 / 光流画面静止为并列备选源（接口已留，
# 融合启用时再标定）。三个源同形态换用，大循环骨架不动。

# ── IMU 跳变判定（check_imu_impact，相邻两帧差值，原始读数单位） ──
# 参考量级（待电控确认量程后重标）：若 ±16g/16bit，1g ≈ 2048；
# 若 ±2000dps/16bit，1°/s ≈ 16.4。判定 = 差值合矢量落在本区间内；
# 想单独关闭某一条件，把对应区间的下限调到永远达不到即可。
IMU_ACCEL_JUMP_MIN = 2048.0    # 加速度跳变下限（≈1g 突变才认）
IMU_ACCEL_JUMP_MAX = 32767.0   # 加速度跳变上限（防野值，调大 = 不设限）
IMU_GYRO_JUMP_MIN = 819.0      # 角速度跳变下限（≈50°/s 突变才认）
IMU_GYRO_JUMP_MAX = 32767.0    # 角速度跳变上限

# ── 光流画面静止判定（check_frame_still，平均幅值单位 = 像素/帧） ──
FRAME_STILL_FLOW_MIN = 0.0     # 平均光流幅值下限
FRAME_STILL_FLOW_MAX = 0.5     # 平均光流幅值上限（低于此 ≈ 画面几乎没动）
FRAME_STILL_MAX_WIDTH = 320    # 光流计算前降采样的最大宽度（提性能，树莓派友好）

# ── 接收机失联判定（check_receiver_lost，秒） ──────────────────────
RECEIVER_LOST_TIMEOUT = 1.0    # 超过该时长没收到遥控器信号 → 判失联

# ── IMU 落地监视线程（monitor） ────────────────────────────────────
IMU_MONITOR_POLL_INTERVAL = 0.005   # 轮询 imu_queue 的间隔（秒），≈200Hz 跟随回传

# ══════════════════════ detection 识别 ══════════════════════

# ── YOLO 模型（权重就位后按实际文件名与类别名改这里） ──────────────
DETECT_MODEL_FILE = "models/cube_ball.pt"   # 权重路径（相对项目根，占位名）
DETECT_CUBE_CLASS = "cube"                  # 权重里魔方的类别名
DETECT_BALL_CLASS = "ball"                  # 权重里球的类别名
DETECT_BUCKET_CLASS = "bucket"              # 权重里投放桶的类别名
DETECT_PAN_CLASS = "pan"                    # 权重里投放大盆的类别名
DETECT_CONF_THRESHOLD = 0.8                 # 置信度阈值：≥0.8 才认定为对应品类

# ── 六色色块（BGR 区间 (lower, upper)：初始参考值，现场光照下改这里） ──
COLOR_RANGES = {
    '黑': ((0, 0, 0),      (70, 70, 70)),
    '棕': ((0, 30, 80),    (90, 110, 190)),
    '粉': ((110, 90, 180), (230, 200, 255)),
    '蓝': ((150, 0, 0),    (255, 180, 100)),
    '黄': ((0, 150, 150),  (120, 255, 255)),
    '绿': ((0, 120, 0),    (120, 255, 120)),
}
COLOR_NAMES = ('黑', '棕', '粉', '蓝', '黄', '绿')

# ══════════════════════ region 范围判定 ══════════════════════
# 抓取圈比例（grab_range_x/y/radius_ratio）与手动模式画圆同源，在
# common 的 config（GUI 可调），不进本文件。
PAN_OVERLAP_MIN_PX = 2000     # 盆可投判定：盆 ROI 与抓取圈重合像素数下限（占位，待实测标定）

# ══════════════════════ scoring 评分选靶 ══════════════════════
# 权重默认等权占位，现场按"距离/颜色/密集"的相对重要性调；距离/密集
# 因子分值范围 0~1，颜色因子分值 = 该颜色分值（也按 0~1 配）。
SCORE_WEIGHT_CUBE_DISTANCE = 1.0    # 魔方·距离权重
SCORE_WEIGHT_CUBE_DENSITY = 1.0     # 魔方·密集权重
SCORE_WEIGHT_BALL_DISTANCE = 1.0    # 球·距离权重
SCORE_WEIGHT_BALL_COLOR = 1.0       # 球·颜色权重
SCORE_WEIGHT_BALL_DENSITY = 1.0     # 球·密集权重
SCORE_DISTANCE_PLATEAU = 0.3        # 距离同分 plateau（×抓取圈半径的比例，占位）
SCORE_DENSITY_RADIUS_PX = 150       # 密集统计半径（像素，占位）
BALL_COLOR_SCORES = {               # 六色球分值初值 = GUI 得分说明分值÷70 归一化（比例同分值，随时可调）
    '黑': 1.0,   '棕': 0.571, '粉': 0.857,   # 黑70 棕40 粉60
    '蓝': 0.714, '黄': 0.286, '绿': 0.429,   # 蓝50 黄20 绿30
}

# ══════════════════════ actuator 舵机抓取状况 ══════════════════════
# 抓取舵机三个状况各一个角度范围（参考 auto 分支判定思路）：抓球 / 抓魔方
# / 静止（空爪闭合位 = 指令角附近）。夹住物品时爪瓣被挡、停在指令角上方
# （魔方大 → 角度更大）；脱落 → 失去阻力、落回静止位（§6.6 思路 A）。
# 占位为示意区间（互不重叠、方向按机构机制定），现场标定后填。
GRAB_SERVO_IDLE_MIN = 200      # 静止状况角度下限（空爪闭合位）
GRAB_SERVO_IDLE_MAX = 600      # 静止状况角度上限
GRAB_SERVO_BALL_MIN = 800      # 抓球状况角度范围
GRAB_SERVO_BALL_MAX = 1400
GRAB_SERVO_CUBE_MIN = 1600     # 抓魔方状况角度范围（魔方大、角度更大）
GRAB_SERVO_CUBE_MAX = 2400

# ══════════════════════ flow 流程编排 ══════════════════════
FLOW_LOOP_INTERVAL = 0.05      # 大循环轮询/相机取帧线程间隔（秒）
RECEIVER_POLL_INTERVAL = 0.05  # 接收机判飞行线程轮询间隔（秒，占位）
MECH_QUEUE_LEN = 20            # 机构监视历史队列长 = 过程态窗长（占位）
MECH_SAMPLE_INTERVAL = 0.05    # 机构监视采样间隔（秒，0.05~0.1 及时响应，占位）
YOLO_TASK_INTERVAL = 0.5       # YOLO 任务判定推理间隔（秒，树莓派上控制占用，占位）
GRAB_VERIFY_TIMEOUT = 5.0      # 抓取指令发出→等机构夹住的验证窗（秒，占位）
GRAB_FAIL_MAX = 3              # 同一轮连续抓取失败上限（超过提示人工重飞）
CUBE_DONE_MAX = 15             # 魔方投完 15 个 → 任务完成
BALL_DONE_MAX = 6              # 球投完 6 个 → 后续轮次全抓魔方
FLOW_IMU_HIT_FRESH = 3.0       # 落地触发新鲜度窗口（秒）：IMU 备选源启用时用，
                               # 起飞等旧冲击超窗自然过滤（下一次落地必有新冲击）

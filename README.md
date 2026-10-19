# soujiu —— CADC 模拟搜救无人机抓取机构自动化

中国大学生无人机竞赛（CADC）模拟搜救任务的抓取机构自动化项目：
**无人机由人工飞行，本代码自动化"抓/投"这一段**——目标识别、评分选靶、
给下位机发指令、状态推进与异常处理。比赛已结束，项目用于开源与技术沉淀。

## 功能概览

- **手动链路**（`main.py`，PyQt5 GUI）：相机画面、手动控制抓取机构、
  坐标映射与串口发送（VisionFramework 生命周期管理）。
- **自动链路**（`auto/flow`）：FreeRTOS 式轮询调度——监视线程直改
  状态量，while 大循环三层 if 分发，自动完成"识别 → 抓取 → 转场 →
  投放 → 计数 → 下一轮"全流程，含飞行中掉落、抓取失败重试等分支。

## 目录结构

```
auto/                  自动链路
  flow/                总调度：监视线程 + while 大循环（main.py）
  detection/           YOLO 识别（一次推理四类）+ 六色色块
  region/              抓取圈判定（圈内过滤 / 盆桶可投）
  scoring/             评分选靶（距离 + 颜色 + 密集加权）
  actuator/            下位机串口收发 + 抓取舵机角度分档
  landing/             落地判定三源（接收机主 / IMU 跳变 / 光流静止）
  params.py            自动链路全部可调参数（调参只改这一个文件）
common/                手动/自动共用：相机、串口协议、坐标映射、RuntimeData、config
calibration_data/      单应性等标定文件
docs/                  文档（见下）
main.py                程序入口（GUI，VisionFramework）
比赛说明.md            竞赛任务说明与项目现状
```

## 文档

| 文档 | 内容 |
|------|------|
| [docs/自动抓取技术实现.md](docs/自动抓取技术实现.md) | 主链路的方法与路径：方案选型、总体架构、六情况覆盖表、掉落翻转计数机制、复用接口清单 |
| [docs/扩展功能技术路线.md](docs/扩展功能技术路线.md) | 备选与未实现功能的实现路径：落地多源融合、掉落检测完整版、三舵机六要素、颜色↔桶映射、行为树等价、电控待接入项与**接线清单** |
| [docs/开发约束.md](docs/开发约束.md) | 框架架构契约：模块 = 函数 API、线程归属、参数集中、RuntimeData 数据约定——**在框架上加功能照此办** |

**给参考本项目的人**：主流程已实现，每个判定都留了并列可换的实现路径
（代码注释与上述文档对应）；想在自己的框架上实现同类功能，按
"技术实现.md 看方法 → 扩展功能技术路线.md 看路径 → 开发约束.md 看写法"
的顺序即可。

## 环境与安装

```bash
pip install -r requirements.txt
```

自动链路的 YOLO 识别另需 `ultralytics`（权重就位后 `pip install
ultralytics`），权重文件放到 `auto/params.py` 的 `DETECT_MODEL_FILE`
路径即可跑通识别（当前为占位名，权重待训练）。

## 运行

```bash
python main.py        # 启动 GUI（手动链路）
```

自动链路由 GUI 集成调用，也可在代码中直接启动：

```python
from common.core.runtime_data import RuntimeData
from auto.flow.main import start_flow, stop_flow

data = RuntimeData()
start_flow(data, with_camera=True)   # 树莓派部署开相机；纯调试可不开
...
stop_flow()
```

下位机串口未接时自动链路照常运行（提示并跳过接收），接上后重启流程即可。

## 自动链路架构速览

```
监视线程（直改 RuntimeData 状态量）
  接收机判飞行 → auto_flight_state（flying/landed，主源=接收机，
                 IMU/光流并列备选）
  机构监视     → auto_mech_state（idle/hold/process，低频采样入长队列，
                 收样当场判，抓/放角度差大可直接判脱落）
  YOLO 任务判定 → yolo_task（识别到什么 ≈ 做什么任务，四类别）
while 大循环（只读状态量，三层 if 分发）
  层1 飞行状况 → 层2 机构状况 → 层3 任务记账 / YOLO 任务判定
  接口处理只改状态与记账，动作在下一轮轮询里由新状态驱动
```

详细的方法与路径（选型理由、六情况覆盖表、掉落翻转计数机制、复用
接口清单、待办）见 **[docs/自动抓取技术实现.md](docs/自动抓取技术实现.md)**。

## 当前状态与待办

框架已完成并通过编译/导入/起停冒烟；以下为待接入项（代码内均有 TODO 标注）：

- 接收机数据源（层1 飞行判定主判据，待电控接入）
- 抓取/投放指令的协议语义（X/Y/N/RX，待电控定义后填发送函数）
- YOLO 权重训练与放置
- 三舵机角度范围、验证窗等参数实测标定（`auto/params.py`）
- IMU / 光流备选源的启用与融合

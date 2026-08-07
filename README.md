# 视觉检测系统

基于单应性矩阵坐标映射的视觉定位系统。支持 **USB 摄像头** 与 **FPV 图传（Wifilink 2 + RTL8812AU）** 两种信号源，将画面上的像素坐标映射为平面物理坐标，并通过串口发送给下位机（如 STM32）。集成 CADC 模拟搜救操作手辅助面板。

支持 **Windows / Linux** 双平台运行。

---

## 快速启动

```bash
# Windows（建议使用项目自带 venv）
.venv\Scripts\python.exe main.py

# Linux
python3 main.py
```

启动后默认按 `camera_params.yaml` 中的 `camera_source` 选择信号源（`usb` 或 `fpv`）。

---

## 信号源

| 信号源 | 硬件 | 说明 |
|--------|------|------|
| `usb` | 普通 USB 摄像头 | 通过 OpenCV（DSHOW/V4L2）采集，支持断线自动重连 |
| `fpv` | RTL8812AU 网卡 + Wifilink 2 | 通过 C++ 扩展 `fpv_rx` 接收，解密 WFB-ng 图传 |

两种信号源共用同一条处理链路（去畸变 → 坐标映射 → 显示），切换后画面分辨率变化会自动适配中心原点（详见「坐标映射」）。

---

## 操作流程

```
1. 插上摄像头（USB）或 RTL8812AU 网卡 + Wifilink 2（FPV），插上串口设备
2. 运行主程序
3. （可选）点击「系统设置」调整信号源、相机索引、串口端口等
4. 把棋盘格放在画面中，点击「标定映射」标定单应性矩阵
5. 标定成功后，左键点击目标位置映射平面坐标
6. 按数字键 0-9 打包数据 → 按空格键确认发送
```

> FPV 图传的首次配置（密钥、信道、驱动）见 [FPV_SETUP.md](FPV_SETUP.md)。

---

## 操作说明

### 顶部状态栏布局

```
┌──────┬──────┬──────┬────────────────────────────────┬──────┐
│ 状态  │ ROI  │ 路线  │ 抓取规则 + 分值                │ 系统  │
│ 文本  │ 预览  │ 图①~⑥│ 魔方🔄台球  │ 魔→a │ b区:分值 │ 按钮  │
│      │      │      │ 若抓错→重来  │ :10  │          │      │
└──────┴──────┴──────┴────────────────────────────────┴──────┘
```

- **状态文本**：相机/串口状态（✓/✗ 彩色）、坐标数值、待发/已发协议值（刷新内容红色高亮）
- **ROI 预览**：鼠标点击位置的画面局部放大
- **路线图**：倒U型飞行路径（①→⑥），预设飞行轨迹参照
- **抓取规则 + 分值**：CADC 模拟搜救物资运送顺序速查 | 魔方→a区:10 | b区各球分值
- **断开提示**：相机或串口断开时，画面中心弹出红色警告（0.75s 自动消失）

### 鼠标 & 键盘

| 操作 | 功能 |
|------|------|
| **左键** | 映射平面坐标 + 设参考点 |
| **右键** | 查看世界坐标 |
| **数字键 0-9** | 打包数据（计算协议值，缓存不发送） |
| **空格键** | 确认发送打包好的数据 |
| **格子 1-6** | 截取当前画面中心区域放入格子 |

### GUI 按钮（视频上方状态栏右侧）

| 按钮 | 功能 |
|------|------|
| 重置状态 | 重置所有运行时数据 |
| 系统信息 | 显示当前相机和坐标信息 |
| 标定映射 | 拍摄一帧棋盘格图像标定单应性矩阵（当场生效） |
| 系统设置 | 修改串口、相机等配置（确认后自动重启生效并持久化到 camera_params.yaml） |
| 刷新重启 | 按当前内存配置重启系统 |
| 退出程序 | 安全释放资源并退出 |

> **配置持久化**：所有通过「系统设置」修改的配置项都会在重启成功后自动写回 `camera_params.yaml`，下次启动直接加载。文件路径类配置以相对路径存储，跨平台可移植。

---

## 核心架构

### 生命周期管理模式

```
VisionFramework
  ├── start()   初始化全部硬件 + 启动处理循环
  ├── stop()    停止循环 + 释放全部硬件
  └── restart() stop → 改配置 → start（事务回退）
```

### 运行时数据流

```
摄像头 / FPV → CameraManager / FpvReceiver
              ├── 采集原始帧
              └── 去畸变（如果已标定）
                      │
                      ▼
              RuntimeData.set_frame(frame)
                      │
                      ▼
              InteractionManager  ← 鼠标/键盘事件
                      │
              ├── 左键: 坐标映射 → 设参考点
              ├── 右键: 存储右键坐标
              ├── 数字键: rotated_plane_coords → 打包数据（不立即发送）
              ├── 空格键: 确认发送打包好的数据
              │
              └── get_state()
                  └── 从 RuntimeData 读取所有状态
                          │
                          ▼
                  Display.update_all(state)
                  Display.update_frame(frame)
```

---

## 目录结构

```
souiju12_no_detect/
│
├── main.py                          ← 程序入口，VisionFramework
├── requirements.txt
├── camera_params.yaml               ← 用户配置（GUI 设置持久化落点）
├── gs.key                           ← Wifilink 2 图传解密密钥
├── user.ini                         ← Wifilink 2 发射端配置参考（须与接收端一致）
├── FPV_SETUP.md                     ← FPV 图传完整设置指南
├── calibration_data/                ← 标定数据文件
│   ├── camera_matrix.npy
│   ├── dist_coeffs.npy
│   └── homography.npy
│
├── core/                            ← 核心框架
│   ├── config.py                    ← 配置管理（默认值/加载/校验/事务回退）
│   ├── runtime_data.py              ← 运行时数据中心（统一管理所有内存态数据）
│   └── utils.py                     ← 工具函数（日志）
│
├── hardware/                        ← 硬件抽象层
│   ├── camera.py                    ← USB 摄像头管理（去畸变、断线重连）
│   ├── fpv_receiver.py              ← FPV 图传接收（RTL8812AU + fpv_rx 扩展）
│   ├── undistorter.py               ← 畸变矫正（加载/去畸变）
│   └── serial_protocol.py           ← 串口通信协议（18字节帧发送）
│
├── logic/                           ← 业务逻辑层
│   ├── interaction_manager.py       ← 交互管理器（事件/映射/串口发送）
│   └── coordinate_mapper.py         ← 像素→平面坐标映射（单应性矩阵）
│
├── ui/                              ← GUI 界面层
│   ├── display.py                   ← 视频显示窗口（状态栏/路线图/规则/ROI预览）
│   └── settings_dialog.py           ← 系统设置对话框
│
├── scripts/                         ← 独立工具脚本
│   ├── calibrate.py                 ← 单应性矩阵标定工具（命令行）
│   ├── distortion_calibrate.py      ← 畸变标定工具（独立运行，自动采集标定）
│   └── list_cameras.py              ← 摄像头列举工具
│
└── extern/                          ← 第三方依赖
    └── fpv_rx/                      ← WFB-ng 接收 C++ 扩展
        ├── setup.py                 ← 扩展构建脚本（含 MSVC/FFmpeg 配置）
        ├── src/                     ← C++ 源码
        ├── ffmpeg_dev/              ← Windows 构建用 FFmpeg 开发包（按需从 gyan.dev 下载，不随仓库携带）
        └── bin/
            ├── windows/             ← Windows 预编译扩展 + 运行 DLL
            │   ├── fpv_rx.pyd
            │   ├── avcodec-62.dll / avformat-62.dll / avutil-60.dll
            │   ├── swscale-9.dll / swresample-6.dll
            │   ├── libusb-1.0.dll
            │   └── libsodium.dll
            └── linux/
                └── fpv_rx.cpython-310-x86_64-linux-gnu.so
```

---

## 坐标映射

### 工作原理

- **单应性矩阵 H**：从 `calibration_data/homography.npy` 加载，启动时读入一次。
- **画面中心原点**：每帧按**真实画面尺寸**实时计算 `H × 画面中心`，因此切换 USB/FPV、或分辨率变化后中心原点自动跟随，无需硬编码。
- **符号校正**：按真实画面中心强制统一坐标系（画面右侧 → X 正，画面上方 → Y 正）。
- **GUI 点击映射**：按比例把窗口点击坐标换算回原始帧像素坐标，窗口缩放不影响精度。

### ⚠️ 重要：标定分辨率规则

> **H 的映射隐含标定时的画面分辨率。实时画面分辨率必须与标定 H 时一致，坐标才是准的。**
> **换相机 / 改变安装高度 / 切换信号源分辨率 → 必须重新标定一次 H。**

```
1. 保持画面分辨率不变（USB 或 FPV 出流分辨率）
2. 把棋盘格放在目标平面上，点击「标定映射」
3. 标定结果当场生效并写回 homography.npy，下次启动自动加载
```

相同比例（如都是 16:9）但分辨率不同，坐标会整体缩放出错——不要只凭画面比例判断，按分辨率重标定。

### 去畸变与坐标

畸变标定（`scripts/distortion_calibrate.py`）与单应性标定互相独立：去畸变改变画面像素位置，因此**建议先去畸变、再标单应性**（主程序标定会自动在去畸变画面上进行）。

---

## 串口协议

### 协议格式（18 字节）

| 偏移 | 字节 | 内容 | 说明 |
|------|------|------|------|
| 0-1 | 2 | `0x56 0x78` (默认) | 硬件校验前缀（可在设置中修改） |
| 2-3 | 2 | `0xAA 0x55` | 帧头 |
| 4 | 1 | `0x10` | STM32 帧长 (16) |
| 5 | 1 | `0x01` | 命令字 |
| 6-7 | 2 | X (大端) | 0~9999 |
| 8-9 | 2 | Y (大端) | 0~9999 |
| 10 | 1 | N | 0~9 |
| 11-12 | 2 | 右键X (大端) | 0~9999，与 X 同编码 |
| 13-16 | 4 | 保留 | 0x00 |
| 17 | 1 | checksum | 帧内字节 2~16 累加和低字节 |

协议前缀 `serial_prefix` 可在「系统设置 → 串口」中修改（十六进制），默认 `0x5678`。Windows 下 COM10 及以上端口号会自动规范化为 `\\.\COM10` 格式。

### 坐标转换

```
协议值 = 坐标(米) × coordinate_scale + coordinate_offset
真实值 = (协议值 - coordinate_offset) / coordinate_scale
```

默认 `coordinate_scale = 1000`、`coordinate_offset = 5000`（负坐标映射到协议正数范围），均可在「系统设置 → 通用」修改。

---

## 配置文件（camera_params.yaml）

扁平结构，GUI 修改后自动写回，启动时加载。文件路径以相对路径存储，跨平台可移植。

```yaml
# 当前项目实际使用的配置示例
camera_source: fpv            # usb / fpv
camera_id: 0                  # USB 相机索引
camera_width: 1920            # USB 请求分辨率
camera_height: 1080
fpv_channel: 161              # FPV 信道（与 Wifilink 2 一致）
fpv_channel_width: 20         # 20 / 40 / 80
fpv_codec: h265               # h264 / h265
fpv_width: 1920               # FPV 分辨率（须与发射端 user.ini 一致）
fpv_height: 1080
fpv_fps: 60
serial_port: COM10
serial_baudrate: 9600
coordinate_scale: 1000
coordinate_offset: 5000
grid_crop_ratio: 0.5          # 格子截图裁剪比例
```

> 串口端口名按平台自动校验：Windows 读到 `/dev/` 格式、Linux 读到 `COM` 格式时自动跳过。

---

## FPV 图传

FPV 链路使用 RTL8812AU 网卡 + Wifilink 2 摄像头（WFB-ng 协议），通过 C++ 扩展 `fpv_rx` 接收解密。**完整设置（密钥获取、驱动、编译、信道匹配、user.ini 发射端配置）见 [FPV_SETUP.md](FPV_SETUP.md)。**

---

## 双平台支持

| 功能 | Linux | Windows |
|------|-------|---------|
| USB 摄像头 | V4L2 / ANY 后端 | DSHOW / MSMF 后端 |
| FPV 扩展 | `fpv_rx.cpython-310-x86_64-linux-gnu.so` | `fpv_rx.pyd`（Python 3.11, MSVC 构建） |
| 串口 | /dev/ttyUSB* / /dev/ttyACM* | COM1~COM10（COM10+ 自动规范化） |
| 串口打开 | 先检查设备文件存在 | 无文件检查 |
| 平台端口校验 | 加载 YAML 时读到 COM 格式→自动跳过 | 加载 YAML 时读到 /dev/ 格式→自动跳过 |

---

## 常见问题

**Q: 串口打不开？**
- Linux: 检查 `ls /dev/ttyUSB*`、权限 `sudo usermod -a -G dialout $USER`
- Windows: 检查设备管理器，确认端口号；COM10+ 已自动处理规范化

**Q: USB 摄像头打不开？**
- 运行 `python scripts/list_cameras.py` 确认系统能枚举到摄像头
- Windows 下若设备被 libwdi/WinUSB 驱动顶掉（Zadig 误操作），需在设备管理器恢复为「USB Video Device」驱动
- 在「系统设置」中修改相机索引，确认后自动重启

**Q: FPV 收不到信号？**
- 见 [FPV_SETUP.md](FPV_SETUP.md)，检查 RTL8812AU 驱动、信道号、Wifilink 2 上电、gs.key

**Q: 标定失败？**
- 确保棋盘格完整、平整、清晰出现在画面中

**Q: 畸变标定怎么做？**
- 运行独立脚本：`python scripts/distortion_calibrate.py`
- 在摄像头前移动棋盘格展示不同角度，自动采集 15 帧后标定
- 标定结果自动保存到 `calibration_data/`，主程序启动时自动加载

**Q: 改分辨率/换相机后坐标不准？**
- 重新标定单应性矩阵（见「坐标映射」章节）

# FPV 图传接收设置

使用 RTL8812AU 网卡 + Wifilink 2 摄像头（WFB-ng 协议）接收无人机图传。接收端为 C++ 扩展 `fpv_rx`，本指南覆盖 **密钥获取、驱动、扩展构建/预编译、信道匹配、发射端 user.ini 配置** 全流程。

---

## 运行条件

| 项目 | 说明 |
|------|------|
| USB 网卡 | RTL8812AU 插入电脑（VID:PID = 0bda:8812） |
| 密钥文件 | `gs.key` 放在项目根目录（见下） |
| Wifilink 2 | 上电开机，自动发射 WiFi 图传 |
| 信道 | 发射端和接收端必须一致（本项目使用 **161**，见 camera_params.yaml `fpv_channel`） |

---

## 获取 gs.key 密钥

gs.key 是 Wifilink 2（发射端）生成的解密密钥文件，接收端需要它才能解密视频。

### 方法一：插空 SD 卡（推荐，先试这个）

```
1. 准备一张空的 microSD 卡（FAT32 格式）
2. Wifilink 2 断电，拆开外壳
3. 找到 SD 卡槽（底面，风扇朝上时在底部，可能在板子内侧）
4. 卡触点朝向电路板插入
5. 上电开机，等待蓝色指示灯亮起（启动完成）
6. 断电，取出 SD 卡
7. 插到电脑上，SD 卡里应该有两个文件：
   ├── gs.key    ← 密钥文件（64 字节二进制）
   └── user      ← 摄像头配置文件（对应本项目的 user.ini）
8. 复制 gs.key 到项目根目录
```

如果没有生成 gs.key → 改用方法二。

### 方法二：刷 OpenIPC 固件

```
1. 下载固件：https://www.runcam.com/download/runcamwifilink2
   下载 WiFiLink2_OpenIPC_V3.1（或最新版）

2. 解压，得到两个文件：
   ├── WiFiLink-part0.bin
   └── WiFiLink-part1.bin

3. 把这两个文件复制到空 SD 卡根目录

4. 插 SD 卡到 Wifilink 2 → 上电 → 自动刷机（约 1 分钟）
   绿灯熄灭 → 刷机完成

5. 断电，换一张空 SD 卡（不要放 bin 文件）

6. 上电 → 自动生成 gs.key → 取出复制到电脑
```

---

## 发射端配置（user.ini）

`user.ini`（项目根目录）是 Wifilink 2 发射端配置文件的本地参考副本，改动后需放回 SD 卡 `user` 文件（或按厂家方式写入）才能生效。

**⚠️ 发射端与接收端必须匹配：**

| 项 | 当前值 | 对应接收端配置 |
|----|--------|----------------|
| `channel` | 161 | `camera_params.yaml` → `fpv_channel: 161` |
| `codec` | h265 | `fpv_codec: h265` |
| `Size` | 1920x1080 | `fpv_width: 1920` / `fpv_height: 1080` |
| `fps` | 60 | `fpv_fps: 60` |
| `bitrate` | 5120 | 越高画质越好，码率需留裕量 |

```
[video]
codec=h265
Size=1920x1080
fps=60
bitrate=5120
```

> 有效分辨率/帧率组合：720p60/720p90/720p120/1080p60/1080p90。改分辨率或帧率后，请同步修改接收端 `camera_params.yaml` 中的 `fpv_width/fpv_height/fpv_fps`，并**重新标定单应性矩阵**（换分辨率后旧 H 不再适用）。

---

## C++ 扩展（fpv_rx）

### 使用预编译扩展（推荐）

Windows 与 Linux 均已内置预编译扩展，**正常使用无需编译**：

```
Windows: extern/fpv_rx/bin/windows/fpv_rx.pyd     （Python 3.11, MSVC 构建，自带运行 DLL）
Linux:   extern/fpv_rx/bin/linux/fpv_rx.cpython-310-x86_64-linux-gnu.so
```

主程序启动时会自动把对应目录加入 `sys.path` 并加载。

### 重新编译

**Linux：**
```bash
pip install --no-build-isolation ./extern/fpv_rx/
# 需安装 libusb-1.0、libsodium、libavcodec/libavformat/libswscale/libavutil 开发包
```

**Windows（MSVC）：**
前置条件：
- Visual Studio 2022 Build Tools（勾选「使用 C++ 的桌面开发」）
- vcpkg（如 `<项目目录>\..\vcpkg`）已安装 `libusb:x64-windows` 与 `libsodium:x64-windows`
- FFmpeg 8.1.2 dev 包（`ffmpeg-dev` / `ffmpeg.zip` 等）**不再随仓库携带**，需从 [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) 下载 *ffmpeg-release-full-shared* 版 dev 包，解压到 `extern/fpv_rx/ffmpeg_dev/ffmpeg-dev/ffmpeg-8.1.2-full_build-shared`（setup.py 自动查找）
- venv 为 Python 3.11

```bat
cd extern\fpv_rx
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" x64
set "VCPKG_ROOT=..\..\..\vcpkg"
..\..\.venv\Scripts\python.exe setup.py build_ext --inplace
```

编译产物在 `build\lib.win-amd64-cpython-311\` 下，复制到 `extern\fpv_rx\bin\windows\fpv_rx.pyd` 即可。

---

## 启动程序

```bash
# 默认使用 USB 摄像头（camera_source = usb）
python3 main.py

# 使用 FPV 模式：camera_params.yaml 中 camera_source: fpv
```

### 配置

编辑 `camera_params.yaml` 或在程序「系统设置 → 相机」中切换：

```yaml
camera_source: fpv          # 信号源: usb / fpv
fpv_channel: 161            # 信道（与 Wifilink 2 一致）
fpv_channel_width: 20       # 信道宽度: 20 / 40 / 80
fpv_codec: h265             # 编码: h264 / h265
fpv_key: gs.key             # 密钥文件路径
fpv_width: 1920             # 与发射端 user.ini Size 一致
fpv_height: 1080
fpv_fps: 60                 # 与发射端 user.ini fps 一致
```

### 测试接收（无 GUI 快速验证）

```python
import fpv_rx

rx = fpv_rx.Receiver()
# 第三个参数是信道宽度索引: 0=20MHz / 1=40MHz / 2=80MHz
rx.start("0bda:8812", 161, 0, "gs.key", 7669206, "h265", 1920, 1080, 60)

import cv2
import numpy as np

while True:
    fd = rx.recv(3000)
    if not fd.valid:
        print("超时")
        continue
    print(f"收到 {fd.codec} 帧: {len(fd.data)} bytes")
    frame = cv2.imdecode(np.frombuffer(fd.data, np.uint8), cv2.IMREAD_COLOR)
    if frame is not None:
        cv2.imshow("FPV", frame)
        if cv2.waitKey(1) == ord('q'):
            break

rx.stop()
```

> 注意：主程序中的实际调用走 `hardware/fpv_receiver.py`，会自动集成去畸变并返回 BGR 帧，无需手动 imdecode。

---

## USB 权限 / 驱动

Linux 下使用 libusb 操作 RTL8812AU 需要 root 权限或 udev 规则；Windows 下需要安装 libusb WinUSB 驱动替代系统自带驱动。

### Windows：使用 Zadig 安装 libusb WinUSB 驱动

1. 下载并运行 [Zadig](https://zadig.akeo.ie/)
2. Options → List All Devices
3. 找到 RTL8812AU 设备（802.11n NIC / Realtek 8812AU，VID:PID = 0bda:8812）
4. 选择驱动为 `WinUSB (libusb)`
5. 点击 "Replace Driver"

> ⚠️ **重要：不要用 Zadig 对摄像头设备操作。** Zadig 会把摄像头的 UVC 驱动替换成 WinUSB/libusb，导致摄像头在系统中不可用（设备管理器显示驱动被阻止）。若误操作，需在设备管理器把摄像头恢复为「USB Video Device」驱动。只对 RTL8812AU 网卡用 Zadig。

### Linux：免 sudo 运行（配置 udev 规则）

```bash
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="0bda", ATTR{idProduct}=="8812", MODE="0666"' \
  | sudo tee /etc/udev/rules.d/88-rtl8812au.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

---

## 常见问题

**Q: 没有 gs.key，启动报错怎么办？**
A: 先用本指南「获取 gs.key 密钥」获取。

**Q: 程序卡在 FPV 初始化？**
A: 检查 RTL8812AU 是否插好且已装 WinUSB 驱动（`lsusb`/设备管理器），确认 Wifilink 2 已上电。

**Q: 画面花屏/卡顿？**
A: 检查信道号是否与 Wifilink 2 一致（都应为 161）。尝试减小信道宽度到 20MHz，或降低发射端 bitrate/fps。

**Q: FPV 收得到画面但坐标不准？**
A: FPV 出流分辨率必须与标定 H 时的分辨率一致。确认 `user.ini` 的 Size 与 `camera_params.yaml` 的 `fpv_width/fpv_height` 一致后，**重新标定单应性矩阵**。

**Q: Windows 上摄像头突然打不开了？**
A: 多半是 Zadig 误把摄像头驱动换成了 WinUSB。设备管理器 → 摄像头设备 → 更新驱动 → 浏览 → 从列表选 → Microsoft →「USB Video Device」。

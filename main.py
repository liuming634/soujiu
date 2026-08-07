"""
主程序 - 视觉检测系统入口（生命周期管理模式）

架构：
  Config → VisionFramework（生命周期管理器）
    ├── start()    初始化全部硬件 + 启动处理循环
    ├── stop()     停止循环 + 释放全部硬件
    └── restart()  stop → 改配置 → start（事务回退）

  RuntimeData（统一运行时数据中心）
    └── 所有内存态数据集中于此，刷新覆盖，防泄漏

  功能模块（由框架调用）：
    ├── CameraManager     采集 + 去畸变
    ├── InteractionManager 交互 + 坐标映射 + 串口发送
    ├── VideoDisplay       GUI 显示
    └── SerialComm         串口通信
"""
import sys
import os

if sys.platform.startswith("win"):
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

# 强制先加载 fpv_rx 扩展，避免 DLL 加载顺序冲突（扩展缺失时优雅跳过）
_fpv_rx_dir = os.path.abspath(os.path.join(
    os.path.dirname(__file__), 'extern', 'fpv_rx', 'bin',
    'windows' if sys.platform.startswith('win') else 'linux'))
if _fpv_rx_dir not in sys.path:
    sys.path.insert(0, _fpv_rx_dir)
try:
    import fpv_rx
except (ImportError, OSError):
    fpv_rx = None

import cv2
import numpy as np
from PyQt5.QtWidgets import QApplication, QDialog
from PyQt5.QtCore import QTimer, Qt

from core.config import config
from core.utils import log_error
from hardware.camera import CameraManager
from hardware.fpv_receiver import FpvReceiver
from logic.coordinate_mapper import PixelToPlaneMapper
from hardware.serial_protocol import SerialComm
from core.runtime_data import RuntimeData
from logic.interaction_manager import InteractionManager
from ui.display import VideoDisplay
from ui.settings_dialog import SettingsDialog


class VisionFramework:
    """视觉检测系统 - 生命周期框架管理"""

    def __init__(self):
        """仅初始化 GUI、配置、数据中心，不碰硬件"""
        print("=" * 60)
        print("🚀 视觉检测系统启动中...")
        print("=" * 60)

        # 验证配置
        valid, errors = config.validate()
        if not valid:
            print("[ERROR] 配置验证失败:")
            for error in errors:
                print(f"   - {error}")
            sys.exit(1)

        # 统一运行时数据中心
        self.data = RuntimeData()

        # 初始化图形界面
        self.app = QApplication(sys.argv)
        self.display = VideoDisplay(title="视觉检测系统", show_fps=config.fps_display)

        # 设置鼠标/键盘回调（绑定到框架方法）
        self.display.set_keyboard_callback(self._on_keyboard_event)
        self.display.set_grid_click_callback(self._on_grid_click)

        # 设置按钮
        self._setup_buttons()

        # 定时器（处理循环）
        self.timer = QTimer()
        self.timer.timeout.connect(self._process_one_frame)

        # 运行时组件（由 start() 创建，stop() 销毁）
        self.camera = None
        self.interaction = None
        self._running = False

        print("=" * 60)
        print("✅ GUI 初始化完成")
        print("   (硬件将在首次 start() 时初始化)")
        print("=" * 60)

    # ─────────── 生命周期 ───────────

    def start(self):
        """初始化全部硬件并启动处理循环"""
        print("\n🔧 初始化硬件...")
        try:
            # 1. 根据信号源设置创建摄像头
            if config.camera_source == "fpv":
                self.camera = FpvReceiver()
                ok = self.camera.open(
                    vid_pid="0bda:8812",
                    channel=config.fpv_channel,
                    channel_width=config.fpv_channel_width,
                    key_path=config.resolve_path(config.fpv_key),
                    link_id=config.fpv_link_id,
                    codec=config.fpv_codec,
                    video_width=config.fpv_width,
                    video_height=config.fpv_height,
                    fps=config.fpv_fps,
                )
                if ok:
                    print(f"✅ FPV 接收器初始化成功 (信道 {config.fpv_channel})")
                else:
                    print("  [WARNING] FPV 接收器初始化失败，可在「系统设置」中配置")
            else:
                self.camera = CameraManager()
                if self.camera.is_available():
                    print(f"✅ 摄像头初始化成功")
                else:
                    print("  [WARNING] 摄像头不可用，可在「系统设置」中配置")

            # 2. 创建坐标映射器
            mapper = None
            try:
                # 中心原点 + 符号校正在 _process_one_frame 里随真实帧尺寸动态同步
                mapper = PixelToPlaneMapper(
                    homography_file=config.resolve_path(config.homography_file),
                )
            except Exception as e:
                log_error(e, "坐标映射器初始化失败")
                print("[WARNING] 台球平面坐标映射功能可能不可用")

            # 3. 打开串口
            comm = None
            try:
                comm = SerialComm(
                    port=config.serial_port,
                    baudrate=config.serial_baudrate,
                    timeout=config.serial_timeout
                )
                print(f"✅ 串口 {config.serial_port} 已打开")
            except Exception as e:
                print(f"[WARNING] 串口 {config.serial_port} 打开失败: {e}")

            # 4. 创建交互管理器（注入 data + mapper + comm）
            self.interaction = InteractionManager(self.data, mapper, comm)

            # 设置鼠标回调
            self.display.set_mouse_callback('left',
                lambda x, y: self.interaction.handle_click('left', x, y))
            self.display.set_mouse_callback('right',
                lambda x, y: self.interaction.handle_click('right', x, y))

            # 5. 启动循环
            self._running = True
            self.timer.start(config.timer_interval)

            print("✅ 系统启动完成\n")
            return True

        except Exception as e:
            log_error(e, "硬件初始化失败")
            self._cleanup()
            raise

    def stop(self):
        """停止循环并释放全部硬件资源"""
        print("\n🔒 正在停止系统...")
        self._running = False

        try:
            self.timer.stop()
        except Exception:
            pass

        # 释放摄像头
        if self.camera is not None:
            try:
                self.camera.release()
            except Exception as e:
                log_error(e, "释放摄像头时出错")
            self.camera = None

        # 释放串口
        if self.interaction is not None and self.interaction.comm is not None:
            try:
                self.interaction.comm.close()
            except Exception as e:
                log_error(e, "关闭串口时出错")
            self.interaction = None

        # 重置运行时数据
        self.data.reset_all()

        print("✅ 系统已停止\n")

    def _cleanup(self):
        """内部清理（start 失败时释放已初始化的部分）"""
        if self.camera is not None:
            try:
                self.camera.release()
            except Exception:
                pass
            self.camera = None
        if self.interaction is not None:
            if self.interaction.comm is not None:
                try:
                    self.interaction.comm.close()
                except Exception:
                    pass
            self.interaction = None

    def restart(self, new_config: dict):
        """停止 → 改配置 → 启动（带事务回退）

        这是修改配置的唯一入口。替代了原有的热替换方式。

        Args:
            new_config: 设置对话框收集的完整配置字典
        """
        old_snapshot = config.snapshot()

        # 1. 停止全部
        self.stop()

        try:
            # 2. 校验并更新配置
            errors = config.update_from_dict_safe(new_config)
            if errors:
                print(f"[WARNING] 以下参数校验失败，已跳过: {errors}")

            # 3. 重新初始化全部硬件
            self.start()

            # 4. 应用到 UI
            self.display.show_fps = config.fps_display

            # 5. 持久化
            config.save_to_yaml(config.resolve_path("camera_params.yaml"))

            self.display.flash_message("配置修改成功")
            print("✅ 配置修改成功\n")

        except Exception as e:
            log_error(e, "配置变更失败，开始回退")

            self._cleanup()
            config.restore(old_snapshot)

            try:
                self.start()
                self.display.flash_message("配置已回退")
                print("✅ 已回退到旧配置\n")
            except Exception as rollback_err:
                log_error(rollback_err, "回退启动也失败")
                print("[CRITICAL] 系统无法启动，请检查配置后重启程序")

    # ─────────── 处理循环 ───────────

    def _process_one_frame(self):
        """封装一帧的完整处理链（读帧→去畸变→状态更新→显示），带断线重连"""
        try:
            if self.camera is None:
                # 无摄像头对象（start 未调用）
                bw = getattr(self.display, 'original_width', 0) or config.camera_width
                bh = getattr(self.display, 'original_height', 0) or config.camera_height
                blank = np.zeros((bh, bw, 3), dtype=np.uint8)
                cv2.putText(blank, "No Camera", (160, 200),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.5, (100, 100, 100), 3)
                self.data.camera_connected = False
                self.display.update_frame(blank)
                if self.interaction:
                    self.display.update_all(self.interaction.get_state())
                return

            # 读帧（CameraManager 内部自动处理重试，失败也返回占位帧）
            ret, frame = self.camera.read_undistorted_frame()

            # 真实帧到达时同步坐标映射图像尺寸（USB / FPV 共用同一链路）
            if ret and self.interaction is not None and self.interaction.mapper is not None:
                try:
                    self.interaction.mapper.ensure_image_size(frame.shape[1], frame.shape[0])
                except Exception:
                    pass

            # 同步相机连接状态到数据中心
            self.data.set_camera_connected(self.camera.is_connected())

            # 实时帧 → 交互处理
            if ret and self.interaction is not None:
                self.interaction.update_frame(frame)
                state = self.interaction.get_state()
                self.display.update_all(state)
            elif self.interaction is not None:
                # 断线时也刷新状态面板（显示 📷 相机: ✗）
                self.display.update_all(self.interaction.get_state())

            # 无论成功失败都显示帧（失败时返回带提示文字的占位帧）
            self.display.update_frame(frame)

        except Exception as e:
            log_error(e, "帧处理失败")


    def _calibrate_homography(self):
        """从摄像头拍摄一帧棋盘格图像，标定单应性矩阵"""
        print("\n" + "=" * 60)
        print("📸 开始标定 - 从摄像头拍摄棋盘格图像")
        print("=" * 60)

        try:
            if self.camera is None or not self.camera.is_available():
                print("[ERROR] 摄像头未初始化或不可用")
                return

            ret, frame = self.camera.read_frame()
            if not ret or frame is None:
                print("[ERROR] 摄像头读取失败")
                return

            if self.camera.is_calibrated():
                frame = self.camera.undistort(frame)
                print("   🔧 已在去畸变画面上标定")

            mapper = PixelToPlaneMapper.calibrate_from_array(
                image_array=frame,
                pattern_size=config.CHESSBOARD_PATTERN,
                square_size=config.CHESSBOARD_SQUARE_SIZE,
                image_size=(frame.shape[1], frame.shape[0])
            )

            mapper.save(config.resolve_path(config.homography_file))

            if self.interaction is not None:
                self.interaction.mapper = mapper
            print("✅ 标定成功，单应性矩阵已加载，坐标映射功能已就绪")

        except Exception as e:
            log_error(e, "标定过程出错")
            print("[ERROR] 标定失败，请确保棋盘格完整可见")

        print("=" * 60 + "\n")

    # ─────────── 按钮设置 ───────────

    def _setup_buttons(self):
        """设置 GUI 按钮"""

        def on_button_reset():
            self.data.reset_all()
            print("🔄 系统状态已重置")

        def on_button_info():
            print("\n" + "=" * 60)
            print("📊 系统信息")
            print("=" * 60)
            print(f"相机 ID: {config.camera_id}")
            # 显示实际帧尺寸（有实际值就用，否则回退到配置值）
            actual_w = getattr(self.display, 'original_width', 0)
            actual_h = getattr(self.display, 'original_height', 0)
            if actual_w > 0 and actual_h > 0:
                print(f"相机分辨率: {actual_w}x{actual_h} (实际)")
            else:
                print(f"相机分辨率: {config.camera_width}x{config.camera_height} (配置)")
            x, y = self.data.last_plane_coords
            print(f"\n当前状态:")
            print(f"  最后位置: X={x:.3f}, Y={y:.3f}, Z={0.0}")
            print("=" * 60 + "\n")

        def on_button_calibrate():
            self._calibrate_homography()

        def on_button_quit():
            print("👋 正在退出系统...")
            self.stop()
            self.app.quit()

        def on_button_settings():
            self._open_settings()

        self.display.add_sys_button("重置状态", on_button_reset, "重置所有状态")
        self.display.add_sys_button("系统信息", on_button_info, "显示系统信息")
        self.display.add_sys_button("标定映射", on_button_calibrate, "拍摄棋盘格照片并标定单应性矩阵")
        self.display.add_sys_button("系统设置", on_button_settings, "修改串口、相机等配置")
        self.display.add_sys_button("刷新重启", self._on_button_reload, "保存配置并重启系统")
        self.display.add_sys_button("退出程序", on_button_quit, "安全退出系统")

    def _open_settings(self):
        """打开系统设置对话框

        对话框只负责 UI 展示和值收集。点击确认后由框架处理重启。
        """
        dialog = SettingsDialog(parent=self.display)
        result = dialog.exec_()

        if result == QDialog.Accepted and dialog.is_modified:
            new_values = dialog.collected_values
            print("\n⚙️  配置已修改，正在重启系统...")
            self.restart(new_values)

    def _on_button_reload(self):
        """保存配置并重启系统"""
        old_snapshot = config.snapshot()
        self.stop()
        try:
            self.start()
            self.display.show_fps = config.fps_display
            self.display.flash_message("系统已重启")
        except Exception as e:
            log_error(e, "重启失败")
            self._cleanup()
            config.restore(old_snapshot)
            try:
                self.start()
                self.display.flash_message("重启失败，已回退")
            except Exception:
                print("[CRITICAL] 系统无法启动，请重启程序")

    # ─────────── 交互回调 ───────────

    def _on_grid_click(self, row, col):
        """格子按钮被点击 → 截取当前画面中心区域放入格子"""
        frame = self.data.current_frame
        if frame is None:
            print("[INFO] 无画面可截取")
            return
        self.display.set_grid_image(row, col, frame)
        print(f"✅ 格子 ({row},{col}) 已截图")

    def _on_keyboard_event(self, event_type, key, _text, _modifiers):
        """数字键打包，空格确认发送"""
        if event_type != 'press' or self.interaction is None:
            return

        # 数字键 0-9：打包数据（不立即发送）
        if Qt.Key_0 <= key <= Qt.Key_9:
            n = key - Qt.Key_0
            self.data.set_key(n)
            self.interaction.handle_key(n)

            # ROI 预览
            if (self.data.last_click_pos is not None
                    and self.data.current_frame is not None):
                cx, cy = self.data.last_click_pos
                self.display.update_roi_preview(
                    self.data.current_frame, int(cx), int(cy))

        # 空格键：确认发送打包好的数据
        elif key == Qt.Key_Space:
            self.interaction.confirm_send()

    # ─────────── 运行入口 ───────────

    def run(self):
        """启动系统"""
        self.display.show()
        from PyQt5.QtCore import QCoreApplication
        QCoreApplication.processEvents()
        try:
            self.start()

            print("\n💡 提示:")
            print("   - 左键设参考点（世界坐标）  右键查看坐标")
            print("   - 数字键 0-9 打包数据  空格键确认发送\n")

            sys.exit(self.app.exec_())

        except Exception as e:
            log_error(e, "系统运行失败")
            self.stop()
            sys.exit(1)

def main():
    """主函数"""
    framework = VisionFramework()
    framework.run()


if __name__ == '__main__':
    main()

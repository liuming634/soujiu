"""
独立秒表显示控件 - 自包含 GUI 组件

内部持有自己的 Stopwatch 实例，同时自带「开始/停止」「清零」按钮，
计时数字与操作按钮完全封装在同一个控件内，与主界面解耦。

主界面只需：
  1. 创建 StopwatchWidget 并放入布局
  2. 每帧调用 tick() 刷新显示

不依赖 config、RuntimeData、InteractionManager。
"""
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from logic.stopwatch import Stopwatch


class StopwatchWidget(QWidget):
    """秒表显示控件 — 大号 'MM:SS' 计时数字 + 开始/停止、清零按钮"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(150, 200)

        self._stopwatch = Stopwatch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel("计时")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #888; font-size: 12px;")
        title.setFont(QFont("Monospace", 11))
        layout.addWidget(title)

        self._time_label = QLabel("00:00")
        self._time_label.setAlignment(Qt.AlignCenter)
        self._time_label.setStyleSheet("color: #66ff66; font-weight: bold;")
        self._time_label.setFont(QFont("Monospace", 30))
        layout.addWidget(self._time_label)

        state = QLabel("未开始")
        state.setAlignment(Qt.AlignCenter)
        state.setStyleSheet("color: #aaa; font-size: 11px;")
        state.setFont(QFont("Monospace", 10))
        layout.addWidget(state)
        self._state_label = state

        # ── 操作按钮（开始/停止 + 清零） ──
        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(4)

        self._toggle_btn = QPushButton("开始")
        self._toggle_btn.setFixedSize(64, 26)
        self._toggle_btn.setStyleSheet(
            "font-size: 12px; background-color: #2a6a2a; color: #fff;"
            " border: 1px solid #3a8a3a; border-radius: 3px;"
        )
        self._toggle_btn.clicked.connect(self._on_toggle)
        btn_layout.addWidget(self._toggle_btn)

        self._reset_btn = QPushButton("清零")
        self._reset_btn.setFixedSize(64, 26)
        self._reset_btn.setStyleSheet(
            "font-size: 12px; background-color: #5a3a2a; color: #fff;"
            " border: 1px solid #8a5a3a; border-radius: 3px;"
        )
        self._reset_btn.clicked.connect(self.reset)
        btn_layout.addWidget(self._reset_btn)

        layout.addWidget(btn_row)

        self._refresh()

    # ─────── 控制 ───────

    def _on_toggle(self):
        if self._stopwatch.is_running:
            self.stop()
        else:
            self.start()

    def start(self):
        self._stopwatch.start()
        self._refresh()

    def stop(self):
        self._stopwatch.stop()
        self._refresh()

    def reset(self):
        self._stopwatch.reset()
        self._refresh()

    # ─────── 每帧刷新 ───────

    def tick(self):
        """每帧调用，实时刷新计时数字（仅在运行中需要更新）"""
        if self._stopwatch.is_running:
            self._time_label.setText(self._stopwatch.fmt_min_sec())

    def _refresh(self):
        """立即同步显示当前状态（用于开始/停止/清零后）"""
        self._time_label.setText(self._stopwatch.fmt_min_sec())
        if not self._stopwatch.has_started:
            self._state_label.setText("未开始")
            self._toggle_btn.setText("开始")
        elif self._stopwatch.is_running:
            self._state_label.setText("计时中")
            self._toggle_btn.setText("停止")
        else:
            self._state_label.setText("已停止")
            self._toggle_btn.setText("开始")
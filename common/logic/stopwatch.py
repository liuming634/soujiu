"""
独立秒表计时模块 - 纯业务逻辑，零依赖（不依赖 config / runtime_data / UI）

设计：
  用「绝对时间戳」计算耗时，而非逐帧累加增量，因此长时间运行也不会累积
  舍入误差或漂移。每次读取 elapsed() 都是从起点时间戳重新计算一遍。

  状态机：
    未开始(idle)  --start()-->  运行中(running)
    运行中(running) --stop()-->  已停止(stopped, 冻结)
    (任意状态)  --reset()-->  未开始(idle)
"""
import time


class Stopwatch:
    """秒表 - 记录开始/停止的绝对时间戳，按需计算耗时"""

    def __init__(self):
        self._start_ts: float | None = None
        self._stop_ts: float | None = None
        self._running: bool = False

    # ─────── 控制 ───────

    def start(self):
        """开始计时（从当前时刻重新起算）"""
        self._start_ts = time.time()
        self._stop_ts = None
        self._running = True

    def stop(self):
        """停止计时（冻结当前耗时；未运行时无效果）"""
        if not self._running:
            return
        self._stop_ts = time.time()
        self._running = False

    def reset(self):
        """清零归位（回到未开始状态）"""
        self._start_ts = None
        self._stop_ts = None
        self._running = False

    # ─────── 查询 ───────

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def has_started(self) -> bool:
        """是否已经启动过（区别于是否正在运行）"""
        return self._start_ts is not None

    def elapsed(self) -> float:
        """当前耗时（秒）。

        运行中 → now - start；已停止 → stop - start；未开始 → 0。
        每次调用都从起点重新计算，不累积误差。
        """
        if self._start_ts is None:
            return 0.0
        end = time.time() if self._running else self._stop_ts
        if end is None:
            return 0.0
        return max(0.0, end - self._start_ts)

    def elapsed_min_sec(self) -> tuple[int, int]:
        """返回 (分钟, 秒)，供显示用（只到秒，不显示小时）"""
        total = int(self.elapsed())
        return total // 60, total % 60

    def fmt_min_sec(self) -> str:
        """格式化为 'MM:SS'（分钟满100也照常累加，不折叠进小时）"""
        m, s = self.elapsed_min_sec()
        return f"{m:02d}:{s:02d}"

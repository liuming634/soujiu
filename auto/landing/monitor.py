"""IMU 落地监视线程：持续对 RuntimeData.imu_queue 的新帧算跳变，结果写回。

与 actuator 接收线程同模式的 start/stop 函数 API（启动权在 flow）：
监视线程只读 imu_queue 的最新帧做判定（不消费队列——确认窗还要用
队列里的历史帧），相邻两帧喂给 check_imu_impact，判定结果刷新
RuntimeData.landing_imu_hit / landing_imu_hit_time。

落地信号 → 状态位切换的接线（RuntimeData.set_auto_state(landed)，
切完下游链路才启动）属流程逻辑，后面在 flow 里写；本线程只负责
不停判定不漏帧，IMU 数据全部从 RuntimeData 取。

光流判定与接收机判定不在此线程：光流要按帧喂图、接收机读数线程
待硬件接入，都是纯函数由调用方编排（flow 串起来）。
"""
import threading
import time

from common.core.runtime_data import RuntimeData

from auto import params
from auto.landing.impact import check_imu_impact


class ImuLandingMonitor:
    """IMU 落地监视线程（daemon）：imu_queue 新帧 → 跳变判定 → 写 RuntimeData"""

    def __init__(self, data: RuntimeData):
        self._data = data
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_seen = None          # 上一次判定的帧（跳变的"上一帧"）

    def start(self) -> None:
        """启动监视线程（重复调用无副作用）"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run,
                                        name="landing-imu", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止监视线程并等待退出"""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _run(self) -> None:
        while self._running:
            queue = self._data.imu_queue
            if len(queue) == 0:
                time.sleep(params.IMU_MONITOR_POLL_INTERVAL)
                continue
            cur = queue[-1]             # 只看最新帧，不消费（历史留给确认窗）
            if cur is self._last_seen:
                time.sleep(params.IMU_MONITOR_POLL_INTERVAL)
                continue
            prev = self._last_seen
            self._last_seen = cur
            hit = check_imu_impact(cur, prev)
            if hit is not None:
                self._data.set_landing_imu(hit, cur.time or time.time())


# ── 模块级函数 API（调用方一行起停，与 start_receiving 同款） ──────

_monitor: ImuLandingMonitor | None = None   # 当前监视器（start/stop 管理）


def start_landing_monitor(data: RuntimeData) -> None:
    """启动 IMU 落地监视线程（已在跑则不重复启动）

    要换数据中心先 stop_landing_monitor()。
    """
    global _monitor
    if _monitor is not None:
        return
    _monitor = ImuLandingMonitor(data)
    _monitor.start()


def stop_landing_monitor() -> None:
    """停止 IMU 落地监视线程"""
    global _monitor
    if _monitor is not None:
        _monitor.stop()
        _monitor = None

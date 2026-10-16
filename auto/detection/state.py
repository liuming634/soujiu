"""识别结果数据结构：目标只带 ROI 信息，纯数据不带行为。

魔方/球/盆/桶通用一个结构：调用方拿到哪个列表/单例就知道品类，
结构本身不重复存类别。
"""

from dataclasses import dataclass, asdict


@dataclass
class RoiTarget:
    """一个识别目标：ROI 外接框 + ROI 中点（像素坐标）"""

    bbox: tuple[int, int, int, int]   # 外接框 (x1, y1, x2, y2)
    center: tuple[int, int]           # ROI 中点

    def as_dict(self) -> dict:
        """转字典（GUI 显示 / 调试用）"""
        return asdict(self)

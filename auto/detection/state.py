"""识别结果数据结构 + 编号规则。

编号规则：按 ROI 识别框中点的像素坐标排序 —— 先比 x（从左到右，最靠左的
编号最小），x 相同再比 y（从上到下）；从 1 开始，魔方与球分别独立编号。
类别在入库前已按品类分好列表（魔方/球各一份），对象里不存类别与置信度。
评分（score）由 scoring 模块写回；投放桶见 BucketObject（球投放行为用，
只有位置信息，不编号）。
"""

from dataclasses import dataclass, asdict

CLS_CUBE = 'cube'   # 品类：魔方（链路各处引用的品类词汇）
CLS_BALL = 'ball'   # 品类：球


@dataclass
class DetectedObject:
    """单个识别目标（魔方或球，存哪个列表由类别决定）"""

    bbox: tuple[int, int, int, int]     # ROI 识别框 (x1, y1, x2, y2) 像素坐标
    center: tuple[int, int]             # ROI 中点（像素），编号依据
    number: int = 0                     # 编号：最靠左 1 号，x 同则 y 从上到下
    score: float = 0.0                  # 评分（scoring 写回，分数最高为先抓目标）

    def as_dict(self) -> dict:
        """转字典（GUI 显示 / 调试用）"""
        return asdict(self)


@dataclass
class BucketObject:
    """投放桶（球投放行为用）：YOLO 识别到的桶位置"""

    bbox: tuple[int, int, int, int]     # 桶的 ROI 识别框 (x1, y1, x2, y2) 像素坐标
    center: tuple[int, int]             # ROI 中点（像素）

    def as_dict(self) -> dict:
        """转字典（GUI 显示 / 调试用）"""
        return asdict(self)


@dataclass
class PanObject:
    """投放大盆（魔方投放行为用）：YOLO 识别到的盆位置

    盆大、颜色均匀、首次投放为空，按投放判定只需要其 ROI 区域与抓取范围
    的重合像素，故只存位置信息，不编号。
    """

    bbox: tuple[int, int, int, int]     # 盆的 ROI 识别框 (x1, y1, x2, y2) 像素坐标
    center: tuple[int, int]             # ROI 中点（像素）

    def as_dict(self) -> dict:
        """转字典（GUI 显示 / 调试用）"""
        return asdict(self)

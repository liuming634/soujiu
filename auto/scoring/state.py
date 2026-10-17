"""评分结果数据结构：目标 + 总分成对返回。

本分支的 RoiTarget 只存几何信息（bbox/center，纯识别结果不带分数、
不带可写字段），评分结果不写回目标对象——score 与 target 成对打包
成 ScoredTarget 返回，由调用方（flow）取用/显示；输入列表保持不动。
"""
from dataclasses import dataclass, asdict

from auto.detection.state import RoiTarget


@dataclass
class ScoredTarget:
    """一个目标的评分结果（target 指回原 RoiTarget，不复制）"""

    target: RoiTarget              # 原识别目标（bbox/center）
    score: float = 0.0             # 加权总分（各因子加权求和）

    def as_dict(self) -> dict:
        """转字典（GUI 显示 / 调试用）"""
        d = asdict(self.target)
        d["score"] = self.score
        return d

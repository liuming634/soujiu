"""抓取圈几何模块（已实现，grab_range.py）：判定目标/容器是否处于
机构可达范围。

判定方法沿用上一版"对比板查色"：抓取圈做成黑/白对比板（尺寸/配置
不变时缓存复用），查板取色判定，免逐点循环。抓取圈比例
（grab_range_x/y/radius_ratio）与手动模式画圆同源，在 common config
（GUI 可调）；盆可投阈值在 auto/params.py region 段。

函数 API（纯函数：只判定、只 return，不入库；三态 None = 帧缺失）：
  1. grab_circle(w, h) → (cx, cy, r)
     抓取圈像素换算（与手动模式画圆公式一致）
  2. point_in_range(x, y, frame) → True/False/None
     点是否在圈内——阶段六桶可投判定（桶 ROI 中点在圈内，§6.2）
  3. overlap_px(roi, frame) → 重合像素数/None
     矩形 ROI 与抓取圈的重合面积
  4. overlap_ok(roi, frame) → True/False/None
     盆可投判定（重合像素数 ≥ params.PAN_OVERLAP_MIN_PX，§6.2）
  5. filter_grabbable(objects, frame) → 列表/None
     圈内过滤：只保留 ROI 中点在圈内的对象（阶段二可抓候选；
     先按本轮品类筛、再圈内筛，连续 M 帧防抖在 flow 做）

输入：帧（只用尺寸生成对比板）+ 像素点 / 矩形 ROI / 识别列表
（RoiTarget）；输出布尔判定 / 重合像素数 / 过滤后的列表。
"""

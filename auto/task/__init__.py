"""任务流程：抓取判定的接口层（魔方/球任务链路的任务层）。

- grab_check.py 抓取判定接口：每个判定规则一个独立函数，不做聚合判断、
  不做组合逻辑，由上层（流程层）自行组合：
  check_stretch_in_range（伸缩运动范围）/ check_stretch_aligned（伸缩舵机
  1/2 偏差容差）/ check_stretch_in_hold（伸缩机构静止保持位置）/
  check_grab_engaged（抓取舵机离开静止范围）/ check_grab_in_target_range
  （抓取舵机落在对应目标夹取范围）/ is_grabber_idle（抓取机构静止判定）。
  阈值/范围为 config 参数（设置界面"抓取判定"页可改），
  占位默认为舵机全行程 0~4095，现场标定后调整。

- drop_check.py 投放判定接口：只判定"是否可以投放"（投放成功与否不影响
  下一步，无需判定）：
  judge_cube_droppable（魔方：投放大盆 ROI 与抓取范围重合像素 ≥
  config.drop_pan_overlap_min_px，占位默认 5000）；
  judge_ball_droppable（球：投放桶 ROI 中点是否在抓取范围内，占位实现，
  判定不够可靠，后续改进）。阈值参数化进 config（设置界面"投放判定"页
  可改），接口也接受显式参数覆盖。
"""

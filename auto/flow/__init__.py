"""流程层（合并原 task + flow）：任务编排与流程判定接口。

原 task（抓取/投放判定）与 flow（流程树调度）功能重合，合并为一层：
  - 编排：流程树（树状结构调度任务，按节点组织自动流程，增强鲁棒性与
    功能；骨架待开发）
  - grab_check.py 抓取判定接口：每项判定一个独立函数（伸缩运动范围 /
    伸缩舵机偏差容差 / 伸缩静止保持位 / 抓取动作 / 目标夹取范围 / 静止
    判定），组合逻辑由上层决定
  - drop_check.py 投放判定接口：judge_cube_droppable（盆与抓取圈重合
    像素）、judge_ball_droppable（桶中点判据，占位待改进）

其余模块（detection/region/scoring/actuator）保持原状。
"""
"""区域判定：基于画面上绘制的抓取圈范围（grab_range），判定目标是否可以抓取到。

- grab_range.py 函数接口：抓取圈按 YAML 比例做成黑/白对比板（缓存复用），
  ROI 中点查板判定是否可抓取。point_in_range 判定单点，
  filter_grabbable 过滤一个列表，refresh_grabbable 过滤后存入独立的
  可抓取列表 grabbable_cube_list/grabbable_ball_list（评分待抓取对象），
  识别列表本身保留全部结果。
"""

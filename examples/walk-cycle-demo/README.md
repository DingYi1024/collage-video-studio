# 9:16 全身纸偶步态基准

这个技术案例验证全身纸偶不是整张人物贴纸横向滑动。角色由躯干根节点、双臂、
左右大腿、左右小腿和左右脚组成。两条腿分别形成关节链，根节点连续前进时，左右脚
交替锁定在地面。

![五个步态采样点](result/walk-strip.jpg)

- [30 FPS 竖屏视频](result/walk-cycle.mp4)
- [运动审计](result/audit.json)
- [可编辑图层清单](generated/layers/layers.json)

一条命令重建：

```bash
python examples/walk-cycle-demo/build_demo.py
```

构建脚本使用双关节逆运动学计算大腿和小腿角度。每个落脚区间同时锁定脚部的 `x`
和 `y`，逐帧审计会拒绝滑步、连续使用同一只脚、过长双脚同时着地以及根节点没有
有效前进的伪步态。

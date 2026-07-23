# 关键帧生成记录

这些提示词对应本案例固定在 `source-media/` 的公开演示素材。实际生产时，Skill 会从
`project.json` 的主题六字段、beat 和 shot 自动拼成 `jobs/*.jsonl`；这里额外保留案例
创作时的人工导演版提示，方便比较“结构化项目描述”和“最终模型指令”。

所有图像共用负面约束：

> No words, no letters, no numbers, no logos, no watermark.

所有最终关键帧共用风格锁：

> Vertical 9:16 keyframe. Clean paper science-lab diorama; warm off-white card stock,
> cobalt blue and vermilion red accents; precise layered cut-paper architecture; real
> tactile paper fibers; soft directional studio shadows; subtle halftone texture; calm
> explanatory editorial composition.

## 三方向比较板

让模型在一个横向画布内制作三个等宽竖屏面板，并让三个面板使用完全相同的“树荫与
曝晒沥青对半分城市街道”场景：

1. 地图版画：奶油纸、珊瑚红和钴蓝、地图碎片、套印偏移；
2. 街头复印：黑白 Xerox 颗粒、酸性橙、胶带和撕裂瓦楞纸；
3. 纸艺实验室：米白卡纸、钴蓝与朱红、精确纸建筑和柔和投影。

要求构图等价、边界清楚，确保评审比较的是视觉系统而不是场景差异。

## b01-s01 · 钩子

> A single city street seen from a slightly elevated cinematic perspective, visually
> split down the middle. Left: dense cobalt paper tree canopy, blue shade pool and relaxed
> paper pedestrians. Right: charcoal asphalt under a vermilion paper sun, rising heat-wave
> ribbons and uncomfortable pedestrians. Same city, two thermal worlds. Strong depth and
> generous safe area near the bottom.

## b02-s01 · 对照证据

> A macro tabletop experiment comparing two ground samples under the same vermilion paper
> sun. Left: cobalt tree canopy, pale pavement, low blue thermometer and droplets from
> leaves. Right: charcoal asphalt, stacked vermilion heat bands, high thermometer and
> intense curling heat waves. Strong left-versus-right symmetry.

## b03-s01 · 机制剖面

> A three-quarter paper cutaway of one city block. Dark road and roof trap descending red
> sun rays inside stacked layers and release heat arrows after sunset. Cobalt trees
> intercept sunlight, roots connect to blue water layers, and cool vapor rises from leaves.
> Explain heat storage versus shade and evapotranspiration without labels.

## b04-s01 · 解决方案

> A hopeful three-quarter aerial paper planning model. Connected cobalt tree canopy, pale
> reflective roofs, a slim blue bus lane and a small water plaza cool the neighborhood.
> Red heat ribbons shrink and peel away while residents use the street. Practical,
> uplifting and with a safe lower caption area.

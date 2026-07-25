# 关键帧生成记录

三方向比较板使用了下面的提示设计。旧的扁平关键帧提示保留为构图研究记录，但当前
最终视频不再使用单张生成图做整图推拉。最终镜头由 `create_layer_assets.py` 生成
透明 PNG 图层，再由 `layers.json` 驱动独立动画。

所有图像共用负面约束：

> No words, no letters, no numbers, no logos, no watermark.

当前横屏环境底图的风格锁：

> Native 16:9 landscape background plate. Authentic physical cut-paper city cooling
> diorama; warm ivory stock, muted teal, cobalt and restrained brick red; torn edges,
> real paper fibers and consistent soft cast shadows; clear foreground, middle ground and
> background; camera parallel to the paper stage; open travel space for separately
> overlaid character and butterfly layers. No people, animals, text, logos or watermark.

## 三方向比较板

让模型在一个横向画布内制作三个等宽横屏面板，并让三个面板使用完全相同的“树荫与
曝晒沥青对半分城市街道”场景：

1. 地图版画：奶油纸、珊瑚红和钴蓝、地图碎片、套印偏移；
2. 街头复印：黑白 Xerox 颗粒、酸性橙、胶带和撕裂瓦楞纸；
3. 纸艺实验室：米白卡纸、钴蓝与朱红、精确纸建筑和柔和投影。

要求构图等价、边界清楚，确保评审比较的是视觉系统而不是场景差异。

## 以下为早期构图研究，不是当前动画输入

### b01-s01 · 钩子

> A single city street seen from a slightly elevated cinematic perspective, visually
> split down the middle. Left: dense cobalt paper tree canopy, blue shade pool and relaxed
> paper pedestrians. Right: charcoal asphalt under a vermilion paper sun, rising heat-wave
> ribbons and uncomfortable pedestrians. Same city, two thermal worlds. Strong depth and
> generous safe area near the bottom.

### b02-s01 · 对照证据

> A macro tabletop experiment comparing two ground samples under the same vermilion paper
> sun. Left: cobalt tree canopy, pale pavement, low blue thermometer and droplets from
> leaves. Right: charcoal asphalt, stacked vermilion heat bands, high thermometer and
> intense curling heat waves. Strong left-versus-right symmetry.

### b03-s01 · 机制剖面

> A three-quarter paper cutaway of one city block. Dark road and roof trap descending red
> sun rays inside stacked layers and release heat arrows after sunset. Cobalt trees
> intercept sunlight, roots connect to blue water layers, and cool vapor rises from leaves.
> Explain heat storage versus shade and evapotranspiration without labels.

### b04-s01 · 解决方案

> A hopeful three-quarter aerial paper planning model. Connected cobalt tree canopy, pale
> reflective roofs, a slim blue bus lane and a small water plaza cool the neighborhood.
> Red heat ribbons shrink and peel away while residents use the street. Practical,
> uplifting and with a safe lower caption area.

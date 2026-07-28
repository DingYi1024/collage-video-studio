# 完整案例：马斯克成为首富的路径 · V6

这个案例验证作品集模式的完整链路：原创生产素材、8 镜多图层导演、连续旁白实测
定帧、逐镜头构图证明、同运行时动作证明、readiness seal、单一 Remotion 正式成片
和编码后 QA。它不是平面图推拉，也不依赖关节模拟。

## 成片与证据

- 成片：[final.mp4](final.mp4)
- 12 帧总览：[result/contact-sheet.jpg](result/contact-sheet.jpg)
- 动作样片：[proofs/action/preview.mp4](proofs/action/preview.mp4)
- 动作六连帧：[proofs/action/contact-sheet.jpg](proofs/action/contact-sheet.jpg)
- 8 镜构图证明：[proofs/composition/proof.json](proofs/composition/proof.json)
- 创意多样性报告：[qa/creative-quality.json](qa/creative-quality.json)
- 技术 QA：[qa/report.md](qa/report.md)

## 生产素材

案例保存了 3 张由内置图像生成工具制作的原始 source sheet：

1. 4 个职业阶段的一致人物状态；
2. 4 套独立历史环境；
3. 8 个可分离业务/科技道具。

构建脚本将它们确定性拆为 4 套环境、4 个身份阶段和 8 个道具，并登记
`provider-generated` 来源、provider、model、调用尝试和内容哈希。每个镜头引用完整
来源链；测试占位图不能进入 readiness seal。

## 8 镜导演

| Beat | Shot A | Shot B | 环境 |
|---|---|---|---|
| 1995 | 代码换股权 | 办公室就是起点 | 编程办公室 |
| 1999 | 第一笔退出 | 现金继续变成筹码 | 收购会议室 |
| 2002–2008 | 再次退出 | 同时逼近现金断裂 | 工厂/发射场 |
| 2021 | 现金不是终点 | 股权放大结果 | 汽车工厂/火箭基地 |

全片使用 4 个景别、8 个构图模式和 rear/subject/front 纵深。人物同一状态最多出现
两镜；环境随故事阶段变化。每镜都包含独立关键帧、camera-coupled parallax、统一
`setup`/`payoff` edit points、数据时间线或图表和最终可读证明。

## 声音与时长

旁白是单一 `zh-CN-YunxiNeural` 连续资产。母带先移除首尾填充，再将 TTS 句内异常
长静音压到约 0.18 秒，并叠加导演定义的语义停顿。`main.timing.json` 的实测结果
生成 913 个精确帧（约 30.43 秒）；`timing_compiler.py --apply` 同时缩放项目镜头
帧数和所有注册图层包的关键帧、证明时刻与设计停顿。

配乐是本地可复现的低频纸张脉冲；Remotion 在旁白发声区间自动降低配乐。

## 重建

前置条件：Python 3.10+、Pillow、FFmpeg/FFprobe、Node.js 和 Remotion 依赖。
生成 source sheet 已随案例保存，重建图层不需要再次调用图像模型。

```bash
python examples/musk-wealth-demo/create_v6_demo.py
python scripts/voice_director.py examples/musk-wealth-demo
python scripts/proof_system.py --register examples/musk-wealth-demo \
  composition --all --force
python scripts/action_proof.py create examples/musk-wealth-demo \
  media/layers-v6/b01-s01/layers.json
python scripts/action_proof.py approve examples/musk-wealth-demo \
  --note "reviewed"
python scripts/readiness_seal.py seal examples/musk-wealth-demo \
  --subtitles examples/musk-wealth-demo/media/audio/main.timing.json \
  --note "reviewed"
python scripts/render.py examples/musk-wealth-demo --output final.mp4
python scripts/qa.py examples/musk-wealth-demo
```

正式视觉由项目内 `remotion-workspace` 的一个 `ProductionFilm` composition 直接消费
全部 `layers:*` 包。Python 合成器只用于派生素材和证明，不是作品集成片渲染器。

## 如何改成自己的主题

1. 重写 4–6 个叙事 beat，每 beat 设计 context + detail 两镜；
2. 先生成并登记环境、人物状态和道具 source sheet；
3. 为每镜声明 shot scale、composition pattern、environment、source ids 和
   rear/subject/front；
4. 为 16:9、9:16、1:1 分别导演 node layout，不裁切横屏成竖屏；
5. 先通过 action proof，再批量完成所有镜头；
6. 只有整片 creative quality、project-wide composition proof、readiness seal、
   Remotion render report 和最终 QA 全部通过时才交付。

完整标准见
[production-standard-v6.md](../../references/production-standard-v6.md)。

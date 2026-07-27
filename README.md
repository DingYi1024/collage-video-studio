# Collage Video Studio

[![Validate Skill](https://github.com/DingYi1024/collage-video-studio/actions/workflows/validate.yml/badge.svg)](https://github.com/DingYi1024/collage-video-studio/actions/workflows/validate.yml)
[![Latest Release](https://img.shields.io/github/v/release/DingYi1024/collage-video-studio)](https://github.com/DingYi1024/collage-video-studio/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

一个可恢复、可审计、可扩展的纸张拼贴视频制作 Skill。

它将创意意图、媒体任务、生成状态、技术 QA 和最终交付分开保存，可以从主题、人物/
产品照片或已有视频开始制作，并支持暂停、继续、局部重跑、检查点恢复和后端替换。

## v3 可视化编辑与执行证明

仓库现在包含真实的 Remotion/React 可视化工作区，而不是只靠文档描述编辑协议：

```bash
cd workspace
npm ci
npm run dev
```

工作区支持 Remotion Player 播放/拖动时间线、递归图层选择、属性检查器、JSON
打开/保存、统一 edit point 跳转，以及同一故事在 16:9、9:16、1:1 间切换导演方案。
`npm run render` 会通过 Remotion CLI 生成真实 MP4。

同一个递归多层构图现在可以分别导演横屏、竖屏和方屏，而不是裁切一张平面图：

| 16:9 | 9:16 | 1:1 |
|---|---|---|
| ![横屏编辑协议](examples/editorial-proof-demo/result/poster-16x9.png) | ![竖屏编辑协议](examples/editorial-proof-demo/result/poster-9x16.png) | ![方屏编辑协议](examples/editorial-proof-demo/result/poster-1x1.png) |

- [观看 16:9 成片](examples/editorial-proof-demo/result/proof-16x9.mp4)
- [观看 9:16 成片](examples/editorial-proof-demo/result/proof-9x16.mp4)
- [观看 1:1 成片](examples/editorial-proof-demo/result/proof-1x1.mp4)
- [查看三画幅构图与运动门报告](examples/editorial-proof-demo/result/proof-report.json)

三份视频均由同一份源构图编译，包含递归父子图层、相机耦合景深、可编辑文字、
data-SVG、图表、时间线、路线和自动避让标注；每份都是 11 层、11 个活动层、恒定
30 FPS。运行：

```bash
python examples/editorial-proof-demo/build_demo.py
```

## 完整案例演示

仓库内置了一个可一键重建的 24 秒横屏案例：
**“马斯克成为首富的路径”**

![马斯克首富路径案例效果](examples/musk-wealth-demo/result/preview.gif)

- [查看完整实现流程与事实来源](examples/musk-wealth-demo/README.md)
- [观看 1920×1080 成品 MP4](examples/musk-wealth-demo/final.mp4)
- [观看 30 FPS 轻量预览 MP4](examples/musk-wealth-demo/result/preview.mp4)
- [查看 12 帧效果总览](examples/musk-wealth-demo/result/contact-sheet.jpg)
- [查看人物肩—肘关节五连帧](examples/musk-wealth-demo/result/rig-strip.jpg)
- [查看 0 错误、0 警告的 QA 报告](examples/musk-wealth-demo/qa/report.md)

案例覆盖事实核对、六镜故事、三风格比较、风格审批、JSONL 任务、62 个透明纸艺
图层、38 个有意义的活动层、注册姿态序列、持续显隐、循环环境条带、种子母题场、
六个定向主动作、五个父子跟随层（含两个层级关节）、
双轴落脚接触锁、逐帧连续性审计、预备/执行/回稳三段节奏、设计停顿、分段缓动、
30 FPS、2× 子像素合成、一条连续普通话表演、逐句时间证据、原创底乐、字幕、水印、
最终渲染、动态密度 QA、定向动态 QA 和创意审批。
无需 API 密钥即可重建：

```bash
python examples/musk-wealth-demo/build_demo.py
```

## 9:16 全身步态基准

新增一个可重建的竖屏技术案例，使用双关节逆运动学驱动左右大腿、小腿和脚：

![全身纸偶交替落脚](examples/walk-cycle-demo/result/walk-strip.jpg)

- [观看 30 FPS 步态视频](examples/walk-cycle-demo/result/walk-cycle.mp4)
- [查看完整实现与运动审计](examples/walk-cycle-demo/README.md)

该案例包含 13 个图层、10 个活动层、8 个层级关节和 4 个交替落脚区间。根节点持续
前进时，落地脚同时锁定 x/y；滑步、重复同一只脚、双脚长时间同时着地或无有效位移
都会被验证器拒绝。

## 主要能力

- 递归父子构图、显式编辑点和相机耦合的前/中/后景视差
- Remotion/React 可视化编辑工作区、Player 时间线和 CLI MP4 渲染
- 本地可编辑文字、形状、data-SVG、柱状图、时间线、路线与避让标注
- 同一构图分别导演 16:9、9:16、1:1，并验证安全区与文字适配
- 身份、拓扑、机制、信息图语义契约及其自动检查
- style、composition、moment 三类 proof 与证据指纹失效
- 基于实测人声的 beat/shot 整数帧重排，以及实际执行的语义转场路由
- 注册纵深栈及镜头耦合视差
- 观察实际边框颜色的色键清理、去溢色和透明/半透明边缘残留 QA
- 追加式供应商生命周期：预留、完成、失败、拒绝、恢复、替换、复用
- 可安装 Codex Plugin 与传统 `.skill` 双分发
- 丝滑优先的关键帧人物运动；默认不要求骨骼或真实步态
- 所有生产项目默认恒定 30 FPS，低帧率素材自动运动插帧，禁止用重复帧伪装流畅
- 全管线卡顿、片尾冻结、素材时长覆盖和声明式阅读停顿检查
- 默认整片连续生成旁白，并独立检测人声内部、首尾和跨片段静音
- 多语言自动选声、四种节奏档案、缩写/小数保护及无标点长句安全分句
- 标点驱动四级气口，并拦截停顿位置错误、语义停顿不足和超过5.5秒的一口气朗读
- 逐短语时间清单驱动 QA 与同步字幕；旧项目自动回退为整段字幕
- 第三方 TTS 可返回标准时间清单；缺失时会显式降级而非假装同步
- 分别检测纯人声与最终混音的 LUFS 和真峰值，过响、过轻、削波都阻断交付
- 主题、照片、已有视频三种输入模式
- 故事与视觉方向双审批门
- 图片生成、图片编辑、图生视频、视频重绘、配音、音乐六类媒体任务
- 可编辑 `layers.json`、透明 PNG 图层和确定性多层合成
- 注册画布素材族、离散姿态序列、持续显隐、无缝环境条带和固定种子母题场
- 草稿/均衡/全景深制作档位与精确的生成尝试预算
- 任务、素材和 QA 输入内容指纹；参数或素材变化会自动判定旧证据过期
- 独立动态密度审计，拦截“没有重复帧但仍然像静态图”的成片
- 主动作、物理原因、运动密度、三段节奏和设计停顿的导演协议
- 父子图层跟随、从属动作说明、落地接触锁和逐帧运动突变检测
- 连续关键帧停顿审计、小状态精灵、可选层级关节与真实步态、铰链支点、曲线路径和
  大姿态闪现拦截
- 自动横竖画幅决策，并保存可审计的选择原因
- 分段缓动、连续速度曲线、子像素抗抖和多镜头动态转场
- 按时间线导演、前置密度检查并响度归一的多语言神经旁白
- JSONL 任务清单和可插拔后端
- 断点恢复、防重复付费提交和不确定提交保护
- FFmpeg 渲染、FFprobe 技术 QA、人工创意验收
- 检查点、状态报告和项目归档
- 使用视频内容哈希保存可跨复制、安装和解压保持有效的创意 QA 审批
- 离线端到端自测及可安装 `.skill` 打包
- 种子化纸纹与确定性图层生成，减少维护更新中的无意义二进制变化

## 安装

推荐使用开放的 Skills CLI 从 GitHub 安装：

```bash
npx skills add DingYi1024/collage-video-studio
```

全局安装到 Codex：

```bash
npx skills add DingYi1024/collage-video-studio \
  --skill collage-video-studio \
  --global \
  --agent codex
```

检查仓库中可安装的 Skill：

```bash
npx skills add DingYi1024/collage-video-studio --list
```

更新已安装版本：

```bash
npx skills update collage-video-studio -g -y
```

也可以从
[GitHub Releases](https://github.com/DingYi1024/collage-video-studio/releases/latest)
下载最新的 `collage-video-studio.skill`，通过支持 `.skill` 文件的客户端安装。

如果直接使用源码，请确保系统中已有：

- Python 3.11 或更高版本
- Node.js 22 或更高版本（可视化工作区）
- FFmpeg
- FFprobe

真实媒体生成还需要安装后端 SDK：

```bash
python -m pip install -r requirements.txt
```

API 密钥只通过环境变量提供，不要写入项目文件。

## 快速开始

```bash
python scripts/studio.py doctor
python scripts/studio.py init ./my-project \
  --mode topic \
  --topic "为什么城市会越来越热" \
  --duration 30 \
  --aspect auto \
  --language zh
```

然后按照 [SKILL.md](SKILL.md) 中的审批门和制作流程执行。

真实媒体接入见
[references/replicate-backend.md](references/replicate-backend.md)。首次付费运行建议：

```bash
python scripts/replicate_backend.py doctor ./my-project
python scripts/job_runner.py ./my-project --stage images \
  --adapter scripts/replicate_backend.py --limit 1 --retries 0
```

## 开发与验证

修改 Skill、任务协议或后端后运行：

```bash
python scripts/selftest.py
cd workspace
npm ci
npm run build
npm run render
cd ..
python scripts/sync_plugin.py --check
python scripts/package_skill.py --output dist/collage-video-studio.skill --force
```

自测不会调用付费媒体服务。它会验证六类生产路由、重复提交保护、分层清单、独立图层
合成、30 FPS 运动插帧、全局冻结检测、旁白时间清单、最终响度、完整项目流程、
渲染、QA、审批、恢复、报告和打包。

## 版本与发布

- 版本号保存在 [VERSION](VERSION)。
- 每次可见变更写入 [CHANGELOG.md](CHANGELOG.md)。
- 使用语义化版本：`主版本.次版本.修订版本`。
- 推送 `v*` Tag 后，GitHub Actions 会重新自测、打包并创建 Release。

## 目录

```text
agents/       Agent 客户端入口配置
assets/       后端模板
examples/     可重建的完整案例、真实素材和最终效果
references/   按需读取的规范和操作文档
scripts/      项目控制、执行、渲染、QA、测试和打包工具
workspace/    Remotion/React 可视化编辑与 CLI 渲染工作区
SKILL.md      Skill 主入口
```

## 安全

- 不提交 API 密钥、用户原始素材或生产项目目录；仓库只保留明确用于公开演示的案例媒体。
- 不在服务端状态未知时直接重新提交付费任务。
- 处理人脸、客户素材或未发布产品前，确认所选模型的数据政策。

安全问题与凭据泄漏处理见 [SECURITY.md](SECURITY.md)。

## 许可

本项目使用 [MIT License](LICENSE)。

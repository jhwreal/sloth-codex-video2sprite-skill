# sloth-codex-video2sprite-skill

一个对最终游戏资产直接负责、且不依赖其他精灵 Skill 的 2D 流水线：先确定角色母图，再用用户选择的视频模型生成单动作、带声音的短视频，最后完全在本地完成原帧率切帧、深色哑光去背、固定锚点、图集、音效、质检、结果选择和 Godot 打包。

Seedream 属于图像生成方向；本项目的默认母图引擎是 GPT Image 2。Seedance 用于视频，但不硬编码为唯一选择。仓库内置 Seedance 2.0、2.0 Fast、1.5 Pro 和 1.0 Pro 别名，也允许直接传入账号实际可用的完整模型 ID。

## 核心目标

- 高质量透明精灵动画，并保留动作原生音效。
- 默认按像素 ACT 指导全身动作：强化蓄力、命中、收势的轮廓差异和快慢反差，待机仍保持克制；固定镜头不再等于锁死双脚。
- 图片、视频、音频和 Base64 永远不进入 Codex 对话上下文。
- 有效动作窗口可按原生 24fps 完整保留，不再把高速动作稀疏抽成几帧。
- 默认不用绿幕；只删除与画面边缘连通的深色哑光，并清理半透明边缘串色。
- 视频只解码一次；所有帧使用同一个固定画布变换和明确脚底锚点。
- localhost 工作台左侧铺满逐帧图，右侧上方循环播放动作视频、下方放大显示当前点击的单帧；页面不放评分、备注或审核按钮，用户直接在对话里决定采用或重做。
- 用小型指标比较多个模型，再由用户决定默认模型。
- 整个 run 一次并发轮询和处理，避免每个动作来回操作。
- 首个付费远程样片未确认前默认禁止跨动作批量提交，防止跑错项目后继续烧预算。
- 输入未变化时直接命中处理缓存，不重复切帧、不让审核失效。
- 同一 Image 2 母图请求会按指纹复用，不会因重复命令再次计费。
- 固定画布在 FFmpeg 解帧时直接缩到目标尺寸，避免先写整套大分辨率 PNG。
- 草稿/成品双档、默认两个远端候选上限，避免无边界重试。

## 快速检查

```bash
python scripts/video2sprite.py doctor
python scripts/video2sprite.py models
```

完整流程见 [`SKILL.md`](SKILL.md)。本 Skill 唯一默认的持久凭据位置是 `~/.config/sloth-codex-video2sprite/credentials.env`；它位于源码仓库、Codex 安装目录和输出目录之外，不能被 Git 跟踪。环境变量仍然优先。

没有配置 Key 时，用隐藏输入保存：

```bash
python scripts/video2sprite.py configure-key --name ark
```

如果 Key 已在本地环境变量中，可安全迁移且不会把值放进命令参数：

```bash
python scripts/video2sprite.py configure-key \
  --name ark \
  --from-env SEEDANCE_API_KEY
```

`--name openai` 用于 GPT Image。命令自动创建 `700` 目录和 `600` 文件，原子写入、保留另一个供应商的 Key，并且绝不打印 Key。仓库中的 [`.env.example`](.env.example) 仅是空模板；真实值不得写入它。详见 [`references/configuration.md`](references/configuration.md)。

火山任务可直接使用 run 内的规范母图：

```bash
python scripts/video2sprite.py submit \
  --run-dir /absolute/path/to/run \
  --action-id attack \
  --reference-file /absolute/path/to/run/master/source.png \
  --model seedance-2.0
```

本地图片只会在 provider worker 内临时编码；候选记录和终端输出仅保留路径、哈希与尺寸。

## 像素 ACT 动作张力

`add-action` 默认使用 `--motion-style pixel-act --root-motion in-place`：
攻击强调膝、髋、躯干、肩臂共同发力，轻击保持短促，重击强调蓄力与收势，
受击/死亡强调明确的身体姿势变化。它指导动作表现，不改变参考图的绘制风格。
需要安静动作时可选 `restrained`，需要自然幅度时可选 `natural`。

位移与结束姿势独立选择：

- `in-place` 允许下蹲、重心移动、抬脚和短前冲，固定的是画布锚点。
- `planted` 仅固定提示词指定的承重接触点，身体仍可充分运动。
- `travel` 将指定的位移烘焙进精灵，需与引擎位移协调，避免重复移动。
- 非循环默认 `--end-state recover`；死亡、变身和连招中间段用
  `--end-state hold` 保留终态/衔接姿势。循环用 `--loop`，不另传结束状态。

提示词会带上有效动作窗口，避免把短挥击均匀拉长到供应商要求的整段时长。
母图先定角色在游戏里的像素高度，再为极端姿势和完整武器轨迹预留画布。
验收按实际游戏尺寸和速度判断身体姿势及节奏，不能只看放大图或刀光大小。
详见 [`references/prompting.md`](references/prompting.md)。

设置会保存到动作和提交记录，并参与指纹校验；修改设置后旧审核不再有效。
旧动作没有这些字段时仍可复用已有缓存，升级 Skill 不会自动重跑视频或产生费用。
提示词的实际改善仍须以真实模型样片为准，离线测试不证明画面效果。

## 模型选择

默认值可通过环境变量设置：

```bash
export VIDEO2SPRITE_VIDEO_MODEL=seedance-2.0-fast
```

某次任务可用 `--model` 覆盖。只有在确实需要比较模型时，才为同一动作创建多个候选并运行：

```bash
python scripts/video2sprite.py compare --run-dir /absolute/path/to/run
```

`compare` 只读取模型、耗时、QC、采用/重做决定和可选的历史评分元数据，不读取媒体。它不会自动修改环境变量；少于四类代表动作时，推荐结果会明确标记为暂定。

## 高效批量推进

显式提交完需要的付费任务后，用一个命令推进整个 run：

```bash
python scripts/video2sprite.py advance \
  --run-dir /absolute/path/to/run \
  --process-ready \
  --profile draft \
  --wait-seconds 50
```

它在最多 55 秒的窗口内并发轮询已存在的任务、下载已完成视频并处理就绪候选，只输出一次有界摘要，绝不会自动提交或产生新计费任务。相同输入再次执行 `process` 会返回 `cached: true`。查看整批候选只需一个本地工作台：

```bash
python scripts/video2sprite.py review --run-dir /absolute/path/to/run
```

草稿只用于模型和动作选择。最终候选需要用 `--profile production` 重建并再次确认，打包器会拒绝草稿产物。详细策略见 [`references/efficiency.md`](references/efficiency.md)。

## 本地输出

每个候选会生成透明逐帧 PNG、`atlas.png`、`sfx.ogg`、带声 `preview.mp4`、`manifest.json`、`qc.json` 和哈希绑定的 `approval.json`。可导出通用包或 Godot `SpriteFrames` 资源。

LibTV 来源必须先通过内置包装器下载。包装器固定同时传递
`--without-ai-watermark --vip`，并生成绑定下载文件哈希的 receipt；随后
`attach-video --source-origin libtv --source-receipt ...` 才允许进入处理链。
普通本地视频则显式使用 `--source-origin local`。如果 LibTV 节点使用了来自
LibTV 的上游参考资产，还必须用其原始 artifact + receipt 声明并验证祖先链；
不得从无 receipt 或已见水印的候选抽帧后再次上传。receipt 只证明命令参数与
文件身份，不代替最终机器检查和视觉水印审查。完整命令见
[`SKILL.md`](SKILL.md)。

## 开发验证

```bash
python -m unittest discover -s tests -v
```

测试媒体在运行时程序化生成，不在仓库中保存二进制素材。真实 API 调用需要用户提供环境变量并明确授权；默认测试不产生 API 费用。

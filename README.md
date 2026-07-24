# sloth-codex-video2sprite-skill

一个面向 Codex 的高效率 2D 游戏资产流水线：先用 GPT Image 2 生成一致的角色母图，再用用户选择的视频模型生成单动作、带声音的短视频，最后完全在本地完成切帧、抠色、统一对齐、图集、音效、质检、审核和打包。

Seedream 属于图像生成方向；本项目的默认母图引擎是 GPT Image 2。Seedance 用于视频，但不硬编码为唯一选择。仓库内置 Seedance 2.0、2.0 Fast、1.5 Pro 和 1.0 Pro 别名，也允许直接传入账号实际可用的完整模型 ID。

## 核心目标

- 高质量透明精灵动画，并保留动作原生音效。
- 图片、视频、音频和 Base64 永远不进入 Codex 对话上下文。
- 视频只解码一次；所有帧使用同一个裁切和缩放变换。
- 自动 QC 后通过 localhost 页面人工看画面、听声音并评分。
- 用小型指标比较多个模型，再由用户决定默认模型。
- 整个 run 一次并发轮询和处理，避免每个动作来回操作。
- 输入未变化时直接命中处理缓存，不重复切帧、不让审核失效。
- 草稿/成品双档、默认两个远端候选上限，避免无边界重试。

## 快速检查

```bash
python scripts/video2sprite.py doctor
python scripts/video2sprite.py models
```

完整流程见 [`SKILL.md`](SKILL.md)。环境变量示例见 [`.env.example`](.env.example)，但程序不会自动读取 `.env`；请通过 shell 或密钥管理器加载，避免凭据进入日志和任务文件。

## 模型选择

默认值可通过环境变量设置：

```bash
export VIDEO2SPRITE_VIDEO_MODEL=seedance-2.0-fast
```

某次任务可用 `--model` 覆盖。为同一动作创建多个候选、在审核页评分后运行：

```bash
python scripts/video2sprite.py compare --run-dir /absolute/path/to/run
```

`compare` 只读取模型、耗时、QC 和人工评分，不读取媒体。它不会自动修改环境变量；少于四类代表动作时，推荐结果会明确标记为暂定。

## 高效批量推进

显式提交完需要的付费任务后，用一个命令推进整个 run：

```bash
python scripts/video2sprite.py advance \
  --run-dir /absolute/path/to/run \
  --process-ready \
  --profile draft
```

它只并发轮询已存在的任务、下载已完成视频并处理就绪候选，绝不会自动提交或产生新计费任务。相同输入再次执行 `process` 会返回 `cached: true`。审核整批候选只需一个本地页面：

```bash
python scripts/video2sprite.py review --run-dir /absolute/path/to/run
```

草稿只用于模型和动作选择。最终候选需要用 `--profile production` 重建并重新审核，打包器会拒绝草稿产物。详细策略见 [`references/efficiency.md`](references/efficiency.md)。

## 本地输出

每个候选会生成透明逐帧 PNG、`atlas.png`、`sfx.ogg`、带声 `preview.mp4`、`manifest.json`、`qc.json` 和哈希绑定的 `approval.json`。可导出通用包或 Godot `SpriteFrames` 资源。

## 开发验证

```bash
python -m unittest discover -s tests -v
```

测试媒体在运行时程序化生成，不在仓库中保存二进制素材。真实 API 调用需要用户提供环境变量并明确授权；默认测试不产生 API 费用。

# sloth-codex-video2sprite-skill

以尽量少的总成本交付尽量多的**合格游戏动作**：复用角色母图，通过 LibTV 等外部工具生成或接入本地视频，再本地切帧、去背、对齐、提取同步音效、审核和导出 Godot/通用图集。

## 默认策略

- 视频从 **768** 开始，主体尽量大，完整容纳动作，只留必要边距。更低档位须在代表样片上满足游戏尺寸下的细节要求；**2K 必须先说明理由并获得用户同意**。
- 先复用已有母图、视频和兼容动作。新母图默认 `medium`；不为每个动作重画，也不为了换质量档位重做已可用的图。
- 一段简短的动作描述，加一份自动追加的通用约束。只描述当前动作，不把所有动作和失败清单都塞进提示词。
- 选最短够用时长，先验证一个代表样片，再扩展动作集。默认一个候选加一次针对性重试；反复失败先诊断。
- 普通候选直接按 `production` 处理并审核一次；只有比较较大/多个候选时才考虑 `draft`。草稿只影响本地编码，不降低远端生成费用。
- 先修窗口、去背、摆放和导出配置，再考虑重新生成。自然连续的连招可共享视频，但必须验证切分、衔接和声音，不拼接无关动作凑数量。

完整执行流程见 [SKILL.md](SKILL.md)，成本与复用策略见 [efficiency.md](references/efficiency.md)，提示词写法见 [prompting.md](references/prompting.md)。

## 使用

需要 Python 3.9+、Pillow、NumPy、FFmpeg 和 FFprobe：

```bash
python scripts/video2sprite.py doctor
python scripts/video2sprite.py models
```

母图使用 GPT Image 2，只有缺少合适母图时才生成；视频在外部工具中生成。Skill 没有 Ark 提交、轮询或视频模型配置入口。

```bash
python scripts/video2sprite.py export-prompt \
  --run-dir /absolute/path/to/run --action-id attack \
  --output /absolute/path/to/action-video-prompt.txt
python scripts/video2sprite.py advance \
  --run-dir /absolute/path/to/run --process-ready --profile production
python scripts/video2sprite.py review --run-dir /absolute/path/to/run
```

LibTV 视频先通过 `libtv-download`，固定带上 `--without-ai-watermark --vip`，再以 `--source-origin libtv --source-receipt ...` 接入。参考资产的 LibTV 上游也必须有凭据链。普通本地素材显式声明 `--source-origin local`。下载凭据不能替代画面水印审查。

媒体和 Base64 不进入 Codex 对话。使用本地工作台查看，用户明确决定采用/重做。已批准成品才可打包；保留原片、帧率、动作窗口、统一尺度、音效和来源哈希。修改既有精灵时默认采用“工作中 → 已确认 → 游戏绑定”流程。

## 凭据与验证

只管理 `OPENAI_API_KEY`，环境变量优先，其次是工作区外的 `~/.config/sloth-codex-video2sprite/credentials.env`。使用隐藏输入或环境变量安全配置，详见 [configuration.md](references/configuration.md)。不提交凭据、媒体或运行输出。

```bash
python scripts/video2sprite.py configure-key --name openai
python -m unittest discover -s tests -v
```

离线测试使用程序生成素材，不调用付费 API。提示词变短不等于画面已经变好；实际效果、低档位适用性和每个合格动作的成本，须以真实样片和游戏内验收为准。

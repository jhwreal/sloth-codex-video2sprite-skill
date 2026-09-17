# sloth-codex-video2sprite-skill

统一的**游戏精灵制作入口**：连续动作默认通过视频生成/切帧；角色母图和局部图片编辑使用内置 imagegen；直接生成或处理精灵表时，按需调用 `my-codex-sprite-skill`。复用已有资产，保留各自的处理、审核和导出格式。

## 按需路径

- 视频动作：[video-workflow.md](references/video-workflow.md)。
- 母图、图片编辑、精灵表：[image-workflow.md](references/image-workflow.md)。
- 视频路径可独立使用。精灵表路径需要单独安装 `my-codex-sprite-skill`；该技能可独立使用，本机检测到统一入口时会设为按需后端。
- 不迁移旧工程、不复制脚本或批准记录；现有命令和技能名称保持兼容。

## 视频路径默认策略

- 视频从 **768** 开始，主体尽量大，完整容纳动作，只留必要边距。更低档位须在代表样片上满足游戏尺寸下的细节要求；**2K 必须先说明理由并获得用户同意**。
- 先复用已有母图、视频和兼容动作。显式选择的 API 母图生成默认 `medium`；不为每个动作重画，也不为了换质量档位重做已可用的图。
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

母图优先复用，缺少时默认使用内置 imagegen；已有 `generate-master` API 工具仅用于用户明确选择的脚本路径。视频在外部工具中生成；没有 Ark 提交、轮询或视频模型配置入口。

```bash
python scripts/video2sprite.py export-prompt \
  --run-dir /absolute/path/to/run --action-id attack \
  --output /absolute/path/to/action-video-prompt.txt
python scripts/video2sprite.py advance \
  --run-dir /absolute/path/to/run --process-ready --profile production
python scripts/video2sprite.py review --run-dir /absolute/path/to/run
```

LibTV 视频先通过 `libtv-download`，固定带上 `--without-ai-watermark --vip`，再以 `--source-origin libtv --source-receipt ...` 接入。参考资产的 LibTV 上游也必须有凭据链。普通本地素材显式声明 `--source-origin local`。下载凭据不能替代画面水印审查。

视频和成批抽帧保留在本地工作台，用户明确决定采用/重做；图片路径允许必要的图片输入和查看。任何路径都不把 Base64、完整供应商响应或凭据写入对话/日志。已批准成品才可打包；保留原片、帧率、动作窗口、统一尺度、音效和来源哈希。修改既有精灵时默认采用“工作中 → 已确认 → 游戏绑定”流程。

## 凭据与验证

内置 imagegen 不需要此 CLI 的 API key；仅显式选择 `generate-master` API 路径时需要。CLI 只管理 `OPENAI_API_KEY`，环境变量优先，其次是工作区外的 `~/.config/sloth-codex-video2sprite/credentials.env`。使用隐藏输入或环境变量安全配置，详见 [configuration.md](references/configuration.md)。不提交凭据、媒体或运行输出。

```bash
python scripts/video2sprite.py configure-key --name openai
python -m unittest discover -s tests -v
```

离线测试使用程序生成素材，不调用付费 API。提示词变短不等于画面已经变好；实际效果、低档位适用性和每个合格动作的成本，须以真实样片和游戏内验收为准。

## 通用 Sprite 修改工作台

Boss、小怪、玩家及其他角色修改都使用同一套[即时工作台模板](references/sprite-edit-workbench.md)，视频和图片精灵表路径共用。新版本追加到末尾；未手选时默认最新，手选后按动作记忆。每帧左上 ✓ 保留、右上 × 排除，立即更新动画与时间轴；独立音效可从保留后的指定帧触发，不再为剪辑预览生成或加载视频。

模板位于 `assets/sprite-edit-workbench/instant/`。先在工程输出目录准备 `production-plan.json`，再执行 `python scripts/create_sprite_workbench.py --output-dir /path/to/workbench` 并通过 localhost 提供给用户。已有实例按模板合并更新，不覆盖项目数据。剪辑可持久化并导出 JSON；确认与游戏绑定继续使用各后端的真实记录及适配器。旧顶层 `.template` 仅保留为项目绑定参考。

前端逻辑回归：`node --test tests/test_editor_model.mjs`。

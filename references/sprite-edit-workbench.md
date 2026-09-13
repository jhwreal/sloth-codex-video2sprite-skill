# Default sprite modification workbench

When modifying existing sprites, default to this three-stage workbench. Reuse an existing project instance when available; otherwise adapt the source templates in `assets/sprite-edit-workbench/`. These are adaptation templates, not a standalone generic server. Keep the standard CLI observation-only reviewer available for generation-only tasks.

## User flow

- 工作中: action list, named versions, original video, transparent animation, complete numbered filmstrip, large selected-frame view, play/pause, previous/next frame, range, FPS and loop controls. Make edits into NEW unconfirmed versions and preserve originals.
- 已确认: only explicit human approvals of the exact candidate and selected range/timing. Accept confirmation in the conversation or a deliberate UI click. Approval is not game binding. Show legacy approved material with an explicit source label; never imply it is an approved generated candidate.
- 游戏绑定: show the actual runtime selection. Bind only after explicit user intent and valid approval; provide per-action rollback. Use the host game's existing adapter, not a second persistence system.

## Editing behavior

Interpret ordinary user frame numbers as one-based and inclusive. If a code template exposes zero-based indices, label or convert them clearly. Retain the original order and pixels of unchanged frames, canvas, root and consistent scale. Do not normalize each frame to its own bounds.

For compact timing, identify redundant holds and near-duplicates using bounded motion measurements. Preserve anticipation, main movement and recovery or terminal pose appropriate to the action. Match requested duration with both selection and timing, not arbitrary sparse frame removal. There is no default 0.5-second action or 80-second generation budget: follow each user's request.

Regenerate atlas, frame hashes, manifest, preview, synchronized audio and review metadata for a derived candidate. Verify decoded preview frame count and duration; short audio must not truncate the video. Keep source video, receipts and derivation mapping. New media/range/timing invalidates approval. Image redraws or paid regeneration require user intent; editing existing frames does not imply permission to generate.

## Template adaptation

The supplied `.template` files preserve the approved Boss workbench layout and interaction code. Before running, adapt ROOT/RUN/HERE, skill scripts path, action IDs/names, legacy atlas path, title, API namespace/port, character identity, scale and game adapter to the target project. The sample character constants are examples, never defaults for other sprites. Do not copy approval files, bound assets, user media or generation budgets.

The example server's `select` note must describe the user's actual decision, without attributing unasked audiovisual claims. Its `bind` receipt handling must branch on source origin: validate LibTV receipts only for LibTV sources and preserve legitimate local/image provenance. Configure scale per asset; never inherit the sample 768/552 correction universally. Any binding logic and timing/events need target-engine verification before use.

Use the sample filmstrip and preview behavior as the visual standard. Provide new-version trim/deletion either through UI controls or agent processing, but always return the result to 工作中. Preserve localhost token/origin checks, path bounds and media hash approval checks when adapting writes. Do not open generated media in the agent context; human review remains the visual authority.

## Verification

Check that the requested candidate appears in 工作中 unconfirmed; retained frames match source; preview count/duration agree with manifest; confirming does not bind; binding rejects unconfirmed or modified candidates; rollback preserves other actions. No paid test is needed to adapt this template.

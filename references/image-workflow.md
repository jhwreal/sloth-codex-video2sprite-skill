# Image and image-sheet workflow

Read this only for image creation/editing, image sheets, or existing image-sheet
runs. Video timing/processing/export fixes remain on the video workflow.

## One master or image edit

1. Reuse a suitable approved master. Otherwise load the installed `imagegen`
   skill and use its built-in default for the requested creation or edit.
2. For edits, inspect the exact target and preserve identity, clothing, grip,
   pose and unaffected pixels as appropriate. Use the current image tool's
   reference mechanism, not a hardcoded schema. Permit necessary image viewing.
3. For standalone cutouts/image sheets request true transparency and validate
   alpha. For a video reference follow the selected generator/project matte
   contract. Preserve the original alpha master; any matte-backed reference is
   a separate derived asset. Do not assume video matte defaults apply to sheets.
4. Save the selected output inside the user's workspace. Record source path,
   hash and relevant user acceptance; do not overwrite an approved master.
5. If this was only an image request, deliver it. If it is a video master,
   return the file path to the video workflow; do not create an image-sheet run.

Normal built-in imagegen does not require the video's `OPENAI_API_KEY`. Do not
prompt for that key or call the headless worker unless that API path was selected.
If generation is unavailable, complete independent local processing and report
the exact missing capability; do not silently switch provider or spend.

## Image-sheet backend, loaded only when needed

Use `my-codex-sprite-skill` for direct imagegen action sheets, supplied sheets,
and processing/repair/export of existing image-sheet runs. It remains a separate
maintained backend with its own scripts and formats, not a copied second manual.

Resolve the backend from the available skill location or as a sibling of the
installed unified Skill; for standard Codex installs use
`${CODEX_HOME:-$HOME/.codex}/skills/my-codex-sprite-skill`.
In the source workspace it is the sibling source repository. Check for
`SKILL.md` and `scripts/prepare_sprite_run.py`, then read its Skill and only
the references needed. A missing backend blocks this branch only; report the
dependency without silently installing or falling back to billed video work.

Pass a compact handoff:

- task and authorized action list; create vs repair vs inspect;
- project/output/run paths, master or sheet path and provenance;
- engine, frame size, pivot, facing, FPS and loop/ending where known;
- fixed identity/equipment constraints, exact defect and accepted decisions;
- sound requirements and remaining authorized budget.

Use the backend's `prepare_sprite_run.py`, `process_action_sheet.py`,
`qc_action.py`, `render_action_preview.py`, `select_candidate.py` and
`pack_atlas.py` according to its documented workflow. Do not point these at
a video run or substitute `video2sprite.py package` for image-sheet export.
Supplied good sheets go straight to processing, QC and review; generation is
not a compulsory step. The backend must not route this handoff back to the
unified Skill or ask the user to invoke it again.

## Existing frames and crossing between paths

For an explicit visual redraw of a video-derived frame, use imagegen on only
the target and necessary references. Save the result as an unconfirmed derivative.
Preserve the original video, source receipt, frame identity, dimensions, pivot,
timing and required audio. Rebuild through the project's existing derived-edit
adapter and workbench, not by overwriting cached frames or copying approval.

If no supported adapter can accept that derivative, deliver the edited image
as unintegrated/pending and identify the needed integration. Do not claim the
video candidate was rebuilt or approved. Raw loose frames without a known
run/atlas layout similarly need verified frame order, geometry and an existing
import path; do not invent a universal frames importer.

Image-sheet QC cannot approve a video candidate; video QC cannot validate an
image-sheet run. Share the chosen source image and task constraints, not mutable
run files, acceptance hashes, caches or provider receipts with altered identity.

For modifications to existing action sprites, use the shared
[instant editing workbench](sprite-edit-workbench.md) for user interaction on
this path, preserving its native run format and acceptance.

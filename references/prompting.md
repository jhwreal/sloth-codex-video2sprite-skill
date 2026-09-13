# Action prompts

## Keep one source of instructions

The brief owns **what this character does**. The exporter owns shared identity,
framing, camera, matte, selected motion/ending and audio constraints. Use the
exported text once in LibTV or another external tool. Do not feed an already
exported prompt back into `add-action`; do not append this reference document.

Aim for a few action-specific sentences. Name facing, required props/grip,
visible key poses, timing contrast and the final pose. Avoid synonym chains,
cinematic/quality superlatives and a growing list of every possible failure.
Put provider resolution/duration options in its controls; put engine movement,
pivot coordinates, approval rules and cost notes in the run, outside the prompt.
The exporter preserves the brief verbatim, so resolve conflicts before export.

## Master and framing

Reuse a suitable approved master. When making one, describe identity, style,
view and equipment only; do not request multiple poses, a grid or video motion.
Keep required props joined to the correct hands. Start with image quality
`medium`; use `high` only for a demonstrated unresolved detail need.
Choose an unlit solid matte absent from the character; dark aubergine often
separates better from navy clothing than blue-black. Review the actual result.

Maximize usable character pixels at the selected video tier: use the largest
constant scale that fits the complete body, weapon path and intended travel
with small safety margins. Keep scale consistent across actions for one actor.
Do not prescribe a universal occupancy percentage, crop extremities, weaken
motion, zoom mid-clip or normalize each pose's bounds.

An exact first frame fixes composition. Reframe and review a tiny reference
before generating. With identity-only referencing, the tool may compose a new
frame; select matching reference mode in the external tool as well as
`export-prompt --reference-role reference_image`. Check the extracted sprite at
actual gameplay size. Upscaling an already soft crop cannot recover lost detail.

## Select only the required motion and ending

No keyword classifier chooses motion from the action name. The agent chooses
flags to match the user's move, and writes its visible action in the brief.

| Setting | Visible instruction / use |
| --- | --- |
| `pixel-act` (default) | Distinct whole-body silhouettes and timing contrast appropriate to the move. Exaggerate articulation, not anatomy. |
| `restrained` | Economical movement; useful for quiet idle without adding flourish. |
| `natural` | Natural weight transfer at the described amplitude. |
| `in-place` (default) | Remain near the starting area while allowing foot lifts, crouches, short steps and full articulation. |
| `planted` | Keep only the named supporting foot/hand fixed while it bears weight. |
| `travel` | Cross the specified distance and finish at the destination. |
| `recover` (default) | Finish in the ready pose at the starting spot, or at the destination after travel. |
| `hold` | Keep the specified death, transformed or combo bridge pose; no idle reset. |
| `--loop` | Join final pose, position and velocity to the opening without pausing. Incompatible with accumulating travel. |

One short brief should describe only its action. Examples (adapt timing/anatomy):

- **Heavy slash:** “Facing right, make one forward sword slash. Sink through the
  knees and wind hips and shoulders back, release quickly with full arm extension,
  then follow through and recover. Keep both hands on the single sword.”
- **Run loop:** “Run facing right in the same area. Alternate full strides with
  bent-knee passing poses, opposite arm swing and clear hip rise and fall.”
- **Death:** “Recoil, lose balance and collapse forward. Remain fallen.”
- **Idle:** “Breathe quietly in a ready stance with a slight weight shift.”

Use body pose and fast/slow contrast to communicate force. Don't turn every
light attack into a heavy windup, or add attacks and hops to idle. Preserve the
complete fast movement inside the effective source-time window; padding belongs
outside it. Gameplay hit-stop normally belongs in the engine.

## Conditional details

Add only details needed for the current move or a demonstrated failure:

- For a planted support, name which foot or hand bears weight.
- For a jump/lunge, specify visible takeoff, reach and landing position; keep
  engine displacement decisions separate from the provider prompt.
- For a linked combo, specify exact hit count and bridge poses, with no idle
  reset until the final recovery. See `sprite-production.md` before splitting.
- For near/far-plane sword motion, define those planes explicitly. Screen-right
  is forward for a right-facing character; near/far is not left/right. Keep
  contact in the forward attack zone while allowing useful torso rotation and
  a brief-specified windup above or behind the body.

Keep character/prop motion clean: no added VFX, trails, particles, glow or motion
blur. Required audio is synchronized dry SFX without BGM, speech or ambience.
The exporter handles these once; don't duplicate the ban in every example.

A retry should correct a concrete failure in one sentence, e.g. “Keep the sword
contact in front of the character” or “Use a deeper knee bend before release.”
Remove superseded/conflicting directions instead of appending another checklist.
If the same failure persists, diagnose the reference, framing, model or local
processing before another paid attempt. Offline tests check these contracts;
only a reviewed real pilot establishes generation quality.

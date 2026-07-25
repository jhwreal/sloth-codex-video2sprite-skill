# Result-owned sprite production

Use this reference for production actions. The Skill owns the complete path from
one approved character still to a runnable game asset; another sprite Skill is
never a runtime or instruction dependency.

## 1. Establish the target contract

Before a paid video call, inspect the current game asset that the new action must
match and record:

- view and facing direction;
- logical frame size, foot-root pivot, character height, and safe margins;
- runtime FPS and any per-frame holds;
- anticipation, contact, follow-through, recovery, and event frame;
- whether the effect is composite or must remain a separate engine layer;
- target-engine import mode, filtering, atlas-size limit, and animation name.

Treat an existing action as a motion benchmark, not a template that overrides the
new brief. Preserve its gameplay semantics while improving the source frame rate
and visual quality when requested.

## 2. Lock one canonical opening frame

Use one approved, fully visible, right-facing game pose with every identity-critical
feature and required held prop already present. Author it on the same flat matte
and aspect ratio requested from the video provider. Put the foot root at a known
image coordinate and leave enough reach for the complete weapon arc.

Do not use an unrelated character, generic robot, placeholder costume, or a
weaponless master for a sword action.

Treat grip continuity and equipment scope as hard gates. A required held prop
must visibly meet the correct hand or joined hands at its handle; reject any gap,
floating weapon, detached grip, or pose where the hand/handle relationship is
ambiguous. Include only equipment required by the brief. Remove unrelated guns,
holsters, scabbards, sheaths, pouches, backpacks, and secondary props before the
master is approved.

## 3. Direct one game action, not a scene

Write the provider prompt in temporal order:

1. a very short readable starting hold;
2. anticipation with weight transfer;
3. acceleration driven by hips, torso, shoulders, hands, and prop;
4. one unambiguous contact direction;
5. follow-through with secondary hair and cloth lag;
6. recovery to the original foot root and matching ready pose;
7. a still end hold for local trimming.

State the side-view direction, exact prop count, hand relationship, root behavior,
and forbidden alternatives. For a sword slash, allow one blade and one trailing
arc that originates from the moving blade. Reject mirrored arcs, simultaneous
upper/lower arcs, a detached effect leading the weapon, extra blades, camera
motion, scene cuts, or a second attack.

Do not confuse canvas direction with depth direction. For a right-facing
side-view character, screen-right is forward toward the enemy and screen-left is
behind the character. An inward/outward slash may alternate between the far and
near picture planes, but every contact must remain in the forward attack zone.
Reject any middle-stage turn that reverses facing or sends the blade and trail
behind the spine.

## 4. Preserve motion frames

Keep the provider source video unchanged. Inside the effective action window,
process at the intended runtime rate—normally the native 24fps for a smooth
video-derived action. Do not reduce a fast strike to a handful of evenly spaced
poses. It is valid to omit only deliberate static padding before or after the
action.

If the target game later needs a lower-rate pixel animation, derive it from the
full-rate master with explicit motion-aware timing and retain the 24fps master.
Never delete the only high-rate sequence.

## 5. Split a linked combo without resetting its momentum

When several player inputs form one continuous combo, use one uninterrupted
provider source for the whole sequence, then derive one gameplay action per
input. Four inputs and four strikes therefore become four action assets even
when they share one paid source video.

Do not return to the opening idle pose between middle stages. Choose a readable
bridge pose after each impact: the final frame of stage N must be the exact
opening frame of stage N+1, with matching root, body momentum, sword position,
hair, cloth, and effect state. The first stage may begin from combat idle; only
the final stage should include the full recovery to that idle.

If the player stops after a middle stage, leave the core attack clip unchanged.
Use a short stage-specific recovery branch or an engine blend after the input
window expires. Never bake that recovery into the linked core clip in a way
that forces a visible idle reset before the next buffered input.

Record one impact event and one chain/cancel window per stage. Four player
inputs always remain four gameplay actions; a stage may contain more than one
impact only when one input intentionally owns a multi-hit move.

## 6. Use a dark connected matte

Do not default to green. Choose a flat, unlit, dark hue that is absent from the
character and VFX. For navy or black clothing, prefer a distinct dark aubergine
or oxblood hue instead of a nearly identical blue-black.

Use border-connected keying: remove only pixels close to the matte color that are
connected to the canvas edge, then decontaminate partial-alpha edge pixels. This
preserves enclosed clothing pixels even when they resemble the matte and avoids
colored fringes.

## 7. Keep one spatial transform

For an authored provider canvas, use `placement=fixed`: resize the complete source
canvas once into every logical frame. Never recenter or rescale each frame.
Package the configured pivot in every frame record. Let root drift remain visible
so QC and the user can reject it instead of hiding it.

Use `fit-union` only for legacy footage that lacks target-canvas framing. It still
uses one union crop and one scale for the whole sequence.

## 8. Verify the deliverable

Machine checks must cover empty frames, matte mismatch, edge clipping, scale
pumping, root drift, first/end pose difference, audio presence and headroom,
atlas geometry, hashes, and event timing.

The localhost workbench shows all extracted frames on the left, the action video
at the upper right, and an enlarged selected frame at the lower right. Click a
thumbnail or use the left and right arrow keys to step through adjacent frames.
Keyboard selection remains focused and scrolls into view. The header shows the
current Sprite number, total Sprite count, action name, and candidate name so
captured review evidence remains attributable. It is an observation surface,
not a rating form. The user communicates “use this” or “redo” in the
conversation; numeric scoring is not part of the normal path.

Package only a chosen production-profile candidate. Import it with nearest
filtering when appropriate, play it at the manifest FPS in the target engine,
verify the pivot and contact event, and keep gameplay collision geometry out of
pixel-derived inference.

## 9. Spend deliberately

Run prompt, geometry, matte, extraction, atlas, and engine-package checks offline
first. Submit one paid pilot for the hardest representative action. Inspect and
process that result before paying for the remaining action set. Never submit an
automatic retry after an ambiguous provider response or an aesthetic failure.

# Action-video prompting

## Canonical master

Request:

- one complete character;
- approved view and proportions;
- centered full body with generous margin;
- flat solid extraction matte;
- no scenery, floor, shadow, text, guides, frame, or UI;
- stable palette, costume, props, handedness, and silhouette.
- every required held prop visibly seated in the correct hand or joined hands,
  with no gap or floating grip;
- only brief-required equipment, with no unrelated gun, holster, scabbard,
  sheath, pouch, backpack, or secondary prop.

Default to a dark non-green matte absent from the character and intended visual
effects. For a navy character, prefer a distinct dark aubergine or oxblood hue
instead of blue-black.

For pixel games, establish the standing character's **final pixel height** first,
then reserve canvas space for the largest pose, lunge, and full weapon arc. Match
the master and video aspect ratios. Excessive empty margins reduce the character
and its motion after downscaling. Enlarge the planned canvas when necessary;
do not solve an extreme pose by shrinking the character during the action.

## Action video

Use one action per clip. State:

- fixed orthographic-like camera;
- no pan, zoom, shake, crop change, cut, transition, or depth-of-field shift;
- complete character visible for the entire clip;
- flat unchanging dark matte with no floor, green screen, shadow, gradient, rim
  light, or texture;
- preserve reference identity, camera view, anatomical proportions, outfit,
  palette, props, and handedness, except an explicitly requested form change;
  keep apparent scale stable while allowing silhouette bounds to change;
- identify the footage as a 2D game-sprite source, not a cinematic scene;
- describe anticipation, acceleration, impact, follow-through, recovery, and the
  still end pose in temporal order;
- separate fixed camera/canvas registration from the moving body; choose the
  root behavior and ending described below instead of fixing both feet;
- request only diegetic action sound: no music, dialogue, narration, ambience, or reverb tail.

For a loop, require the last pose, root, and velocity to connect to the first
without a still end hold. For a one-shot action, retain its complete motion and
intended ending inside the effective window. Place redundant padding outside it.
The CLI appends the configured window in source seconds to the provider prompt;
it is a direction, not proof the provider obeyed. Confirm timing on the pilot.

## Pixel ACT motion direction

`add-action` defaults to `--motion-style pixel-act --root-motion in-place` and
`--end-state recover` for non-loops. These are motion instructions, not a filter
that converts rendered footage to pixel art. Choose `restrained` for deliberately
quiet motion or `natural` for unexaggerated physical movement. No action ID or
language-specific keyword classifier selects these settings.

The `pixel-act` direction adapts to the action in the brief: forceful actions use
large, distinct body poses; idle remains controlled. It does not make every move
a heavy attack. Define the move's weight and player-input semantics first.

| Action | Pose and timing direction | Root / ending |
| --- | --- | --- |
| Idle | Small readable breathing and compact weight shifts; no unsolicited hopping or attack | `planted` or `in-place`, `--loop` |
| Walk/run | Distinct contact and passing poses, leg separation, coordinated arm swing | `in-place`, `--loop`; engine owns locomotion |
| Light attack | Compact but distinct anticipation, sharp release, clear extension and short recovery | `in-place`, `recover` |
| Heavy attack | Deep weight transfer, strong hip/shoulder drive, large reach and committed follow-through | `in-place`, `recover` |
| Hit reaction | Directional whole-body recoil and readable compression, then recovery | `in-place`, `recover` |
| Dodge/jump | Clear takeoff, compressed/extended body shape, readable landing | Usually `in-place`, `recover`; specify what the engine moves |
| Death/transformation | Committed collapse or form-change silhouette, persistent terminal state | Usually `in-place`, `hold` |
| Middle combo stage | Distinct strike, momentum flowing into the next stage's exact bridge pose | Usually `in-place`, `hold` |

Root settings are independent of canvas placement:

- `in-place`: allow bounded weight shifts, crouches, lifted feet, and short
  lunges around the stage anchor. `recover` returns to the opening root;
  `hold` keeps the described terminal/bridge pose. A fixed exported pivot
  does not lock an anatomical foot to the same pixel throughout the sequence.
- `planted`: the brief names the support contact to keep planted while bearing
  weight; knees, hips, torso, and free limbs remain articulated. Use only when
  the action actually needs planted support.
- `travel`: deliberately bake the brief's displacement into the sprite. Specify
  direction, range, destination, and how engine movement avoids double travel.
  `recover` returns to the ready **pose at the destination**, not the original
  coordinate. Seamless `--loop` with `travel` is rejected.

`--end-state hold` means the action keeps its described terminal state, including
a fallen body, changed form, airborne state, or combo bridge. It does not insert
a freeze into a continuous combo. Use `--loop` alone for a loop ending; combining
it with an explicit non-loop `--end-state` is rejected. Reconcile flags with the
brief before submission instead of appending conflicting prose to override them.

Write observable pose differences rather than repeating "more powerful":

1. Describe the start, anticipation, contact/extreme, and follow-through/terminal
   silhouettes in terms of knees, pelvis, torso, limbs, and weapon reach. For
   attacks, make at least anticipation, contact, and follow-through easy to tell
   apart at gameplay size. Do not demand three phases from a quiet idle.
2. Give amplitude relative to the approved body and the move's existing reach,
   such as a deeper knee bend and full arm extension. Numeric pose targets are
   optional creative directions, not measured output or a reason to change
   hitboxes. Avoid arbitrary global multipliers, limb stretching, or forced
   squash/stretch on a rigid character.
3. Contrast readable anticipation with a faster release and committed
   follow-through. Fit those phases in the actual gameplay action window;
   a provider's multi-second minimum is mostly padding for a short strike.
   Keep source motion complete at its native rate. Apply gameplay hit-stop in
   the engine unless explicitly authored into the asset and audio timing.
4. Make the body readable without VFX. Do not compensate for static hips and
   shoulders with a larger slash trail, blur, extra hits, or camera shake.

Example brief for a right-facing heavy slash (adapt its timing and anatomy):

> One heavy forward slash. Sink visibly through the knees and shift weight back,
> with torso and shoulders winding up. Drive hips and shoulders into a fast
> release; extend the joined arms and blade toward the forward contact zone.
> Let the torso lean and the free foot step briefly, then show substantial
> follow-through with delayed hair and cloth. Anticipation, contact, and
> follow-through must have clearly different silhouettes at gameplay size.
> Recover to the opening combat pose at the original root within the action
> window. Keep one blade and one trailing arc; preserve limb lengths and facing.

Use the hardest representative action as the pilot. If its motion is still too
small, name the missing pose change in a regeneration note. If clearer textual
direction remains ineffective, consider an approved pose or motion reference
only through a provider that supports it, within the existing budget and media
firewall. Do not invent multi-reference support or silently pay for retries.

For a linked multi-input combo, describe all impacts in one continuous temporal
sequence and explicitly forbid an idle reset between them. Require a short,
readable bridge pose after each middle impact so the continuous source can be
split into one gameplay action per input. Only the final stage returns to combat
idle. Ask for exactly the requested hit count and one synchronized sound
transient per hit.

For a side-view attack that alternates into and out of the picture plane,
declare the axes before describing motion. For a right-facing character,
screen-right is the forward/enemy side and screen-left is the rear side.
"Far plane" means deeper into the picture while remaining in the forward attack
zone; "near plane" means toward the viewer while remaining in that same forward
zone. Never substitute screen-left/screen-right for far-plane/near-plane motion.
Require the character to keep facing the enemy and forbid the blade, contact,
and trail from reversing the attack toward the rear. Contact and attack VFX
remain in the forward zone; the brief may allow a weapon windup above or behind
the body. Do not turn a forward-contact rule into a ban on torso rotation or
useful anticipation.

For sword actions, specify one blade, joined hands when appropriate, one contact
direction, and one arc that trails the blade path. Explicitly forbid a mirrored
upper/lower pair of arcs, detached effects, extra blades, a second attack, or an
effect that arrives before the weapon.

## Effects

Bake short visual-only effects such as sparks, slash arcs, dust, or a break flash when they belong in the sprite silhouette. Keep gameplay projectiles, persistent hazards, hitboxes, and large scene effects separate in engine code.

## Regeneration notes

When a candidate fails, feed the provider a short failure-specific note:

- camera moved;
- background was not flat;
- character identity drifted;
- action timing was unclear;
- hips/shoulders stayed static or key silhouettes were too similar at game size;
- release was too slow relative to anticipation, or recovery reset a combo;
- body or effect was clipped;
- unwanted speech, music, or ambience appeared.

Do not ask an image model to repair individual extracted frames. Regenerate the short video from the approved master.

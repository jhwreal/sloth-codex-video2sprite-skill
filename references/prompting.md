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

## Action video

Use one action per clip. State:

- fixed orthographic-like camera;
- no pan, zoom, shake, crop change, cut, transition, or depth-of-field shift;
- complete character visible for the entire clip;
- flat unchanging dark matte with no floor, green screen, shadow, gradient, rim
  light, or texture;
- preserve the exact reference identity, view, scale, outfit, palette, props, and handedness;
- identify the footage as a 2D game-sprite source, not a cinematic scene;
- describe anticipation, acceleration, impact, follow-through, recovery, and the
  still end pose in temporal order;
- keep the foot root at one image coordinate and return a one-shot action to the
  opening ready pose;
- request only diegetic action sound: no music, dialogue, narration, ambience, or reverb tail.

For a loop, require the last pose and velocity to connect to the first. For a
one-shot action, hold the start and end poses briefly so the local processor can
retain the full-rate motion window while omitting only redundant padding.

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
and trail from crossing behind the spine.

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
- body or effect was clipped;
- unwanted speech, music, or ambience appeared.

Do not ask an image model to repair individual extracted frames. Regenerate the short video from the approved master.

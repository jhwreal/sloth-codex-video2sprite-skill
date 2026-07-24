# Action-video prompting

## Canonical master

Request:

- one complete character;
- approved view and proportions;
- centered full body with generous margin;
- flat solid chroma background;
- no scenery, floor, shadow, text, guides, frame, or UI;
- stable palette, costume, props, handedness, and silhouette.

Choose a chroma color absent from the character and intended visual effects.

## Action video

Use one action per clip. State:

- fixed orthographic-like camera;
- no pan, zoom, shake, crop change, cut, transition, or depth-of-field shift;
- complete character visible for the entire clip;
- flat unchanging chroma background with no floor or shadow;
- preserve the exact reference identity, view, scale, outfit, palette, props, and handedness;
- describe anticipation, action, impact, recovery, and end pose in temporal order;
- request only diegetic action sound: no music, dialogue, narration, ambience, or reverb tail.

For a loop, require the last pose and velocity to connect to the first. For a one-shot action, hold the start and end poses briefly so the local processor can detect the active interval.

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

---
name: so101-pour-v2
description: Operate the simulated SO-ARM101 to transfer loose beads between two cups using four RGB views, joint encoders and the pouring controls.
---

# Pour beads with the SO-ARM101

**Pick and align.** In the initial overhead image, locate the centers of both colored top rims. Use the midpoint between opposite inner rim edges. The handle, base, shadows and yellow bead cluster can sit off-center. Use full-frame pixels for `approach(u,v)` at the blue rim. Close with `grasp`, then `lift`. Check the side view for a gap under the blue cup and the wrist view for a cup held in the jaws. A missed grasp can be reset with `return`, `release`, then a fresh approach.

Use `align(u,v)` at the orange rim center from the clearest overhead frame. Choose the geometric center for the first alignment. The controller compensates for discharge direction as it lowers and rolls the lip. The blue cup's body should be beside the opening; look for the edge that will feed beads into the receiver. An acknowledged movement confirms joint motion. The images show whether the cup actually followed.

**Control the flow.** `tip(angle)` takes an absolute angle from 1° to 120°. Establish a moderate tilt (around 60°), inspect where the beads collect, then move toward the flow threshold (around 90–100°). Once flow starts, inspect the overhead sequence from the last tip. The panels run from earlier to later and zoom around your last aim point. Use the full overhead frame for subsequent pixel commands. Use the wrist view to judge what remains in the source.

If the beads are landing inside and still moving, repeating the same angle holds the lip in place and lets the stream drain. If beads remain after the flow slows, increase the angle to empty the cup. If the stream consistently passes one edge and beads remain in the source, use `upright`, adjust `align` slightly opposite the observed miss, then resume tilting. The first overhead view remains a reference if the orange rim is obscured.

**Set down.** When the blue cup looks empty, use `upright`, `return`, `release`, then `park`. Check that both cups are upright and the gripper is clear before `finish`. In each decision, describe the visible evidence for your next move. Use zero in unused action fields.

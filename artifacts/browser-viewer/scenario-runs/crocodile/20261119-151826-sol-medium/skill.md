Place the entire green toy crocodile inside the blue rectangular outline on the
table. Its snout, feet, and tail tip all need to fit. Leave the toy resting and released.
Use the current overhead RGB to choose (u,v) in its 640 × 480 image; right increases u and
down increases v. Pick(u,v,angle) approaches the torso, closes the jaws and lifts. Choose
a pinch point on the torso clear of the legs. The jaw-closing axis is measured clockwise
from image right in degrees (0 horizontal, 90 vertical). The jaws should close across the
torso. Place(u,v,angle) brings the held pinch point over that table pixel, lowers the toy,
opens, and withdraws. The angle is an absolute jaw-closing axis in the overhead image.
Use the pick angle to keep the orientation, or rotate the toy to fit. Account for the
snout and tail relative to the pinch point. Park opens the gripper and moves it clear
for inspection. Robot motion acknowledgements describe only the arm. Inspect the
images to verify grasp and placement. Retry after a miss if needed. Finish submits.
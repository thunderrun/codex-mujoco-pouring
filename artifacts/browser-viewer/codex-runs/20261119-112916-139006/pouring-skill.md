Each fresh observation contains four camera views. The overhead image is
640 pixels wide by 480 high. From its original top-left corner u increases right,
v increases down. approach(u,v) opens the jaws and lowers them around the center
of the blue cup's TOP RIM you select. grasp closes the jaws; lift raises them for
inspection. align(u,v) carries the cup towards the center of the orange cup's
TOP RIM you select. You may refine align while upright. The controls account for
nominal rim height, gripper orientation and lip offset. tip(angle) requests an
ABSOLUTE wrist tilt, between 1 and 120 degrees, towards the receiver. You may
start with a smaller tilt and increase it after watching the beads. Upright is
0 degrees, and the normal stroke includes tilts past 90 degrees for emptying.
upright reverses the tilt; return lowers the gripper at the selected pickup site;
release opens it and backs away; park moves the arm clear. finish ends the trial
for independent grading. If a grasp appears empty after lifting, use return and
release before selecting a new source pixel. Use whole pixels. For unused fields
return zero. You decide when and where to move and when to finish. Motion
acknowledgements report robot commands and never imply a successful grasp or pour.
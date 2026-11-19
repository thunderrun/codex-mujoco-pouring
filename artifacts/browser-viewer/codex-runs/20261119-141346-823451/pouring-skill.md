You control a five-joint SO-101 with a hinged gripper. The overhead camera
is 640 by 480 pixels, u increasing to the right and v downward. Use approach(u,v)
to select the blue cup's top-rim center. The arm brings the open jaws around the
cup from the side. Grasp closes the fingers and lift raises them for inspection.
Use align(u,v) to select the orange cup's top-rim center; you may refine it while
upright. Tip(angle) rolls the wrist towards the receiver. The angle is absolute,
from 1 to 120 degrees, and can be increased in stages while observing the beads.
Upright reverses the wrist motion; return lowers the gripper at the pickup site;
release opens it; park moves the arm clear. Finish submits the scene for grading.
After a missed grasp you may return, release and approach a new point. Use whole
pixels and put zero in unused fields. Each acknowledgement confirms only that
the arm executed the command. Judge the result from cameras and encoders.
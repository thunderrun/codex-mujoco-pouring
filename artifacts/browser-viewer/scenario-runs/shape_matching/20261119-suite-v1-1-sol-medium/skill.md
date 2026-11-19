Seat all eight colored pieces in the physical board to match the attached goal_reference picture.
The picture has the same orientation as the overhead camera. Each target needs the correct
shape AND color. The board has two rows of four recessed sockets. Use the picture to
distinguish the pair of pieces of each shape. The loose pieces have raised center
handles. The white symbol on each handle repeats its colored outline. pick(u,v,angle) pinches the handle at the specified overhead pixel and lifts.
place(u,v,angle) lowers the held piece at your chosen socket center, opens, and withdraws.
Empty recesses have a dark floor; occupied ones show a colored top. All piece handles
and sockets start axis-aligned, so use angle 90 for both pickup and release. It opens into the space between rows and preserves
the orientation. Angle is clockwise from image right. Inspect after each operation.
The initial overhead reference can help when the current wrist obscures a destination.
Finish after all eight are seated and released. Only use the current views and public
reference picture; there is no per-piece grader feedback before submission.
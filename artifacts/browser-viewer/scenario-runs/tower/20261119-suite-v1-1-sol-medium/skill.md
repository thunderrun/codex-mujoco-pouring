Build the tallest freestanding tower using all four foam blocks. Each block
is 20 mm tall and the blocks have different square footprints. Use a large base and
center each successively smaller block on the one below. Keep their marked faces up,
release the gripper, and inspect the final stack. A hand-supported tower fails.
Pick selects a block on the tabletop by its top-center overhead pixel (u,v).
Use place_level2 on a one-block base, place_level3 on a two-block stack, and
place_level4 on a three-block stack. Aim at the overhead center of the current
TOP face. These commands calibrate the gripper height for that tier; you select
the stack and aim. place_table sets a held block on bare table.
The angle in pick/place is the jaw-closing axis clockwise from overhead-image right.
Align the jaws with flat sides. Keeping the same angle on pick and release keeps
the orientation. Park clears the view if the jaws hide the stack. Use the initial
overhead view for loose blocks that the arm temporarily hides. Submit finish.
"""Public task names, goal descriptions, and camera choices for the robotics dashboard."""

# Keep the physical benchmark's task order. Pouring has its own runner and history.
WORKSPACES = {
    "button": ("Press the red button", "Red button",
               "Press with the gripper until the button flashes.", "wrist"),
    "crocodile": ("Place the crocodile in the rectangle", "Crocodile placement",
                  "Set the whole toy inside the marked rectangle.", "left"),
    "pouring": ("Pour into the cup", "Pouring",
                "Transfer 21 beads from the blue cup into the orange cup.", "front"),
    "tidying": ("Tidy the blocks into the box", "Block tidying",
                "Put all four blocks in the box and close the lid flush.", "front"),
    "shape_matching": ("Complete the shape matching challenge", "Shape matching",
                       "Seat the pieces in the board so they match the reference picture.", "overhead"),
    "writing": ("Write hello world", "Writing",
                "Write a legible “hello world” entirely inside the black box.", "overhead"),
    "tower": ("Build the tallest tower", "Tower building",
              "Stack the blocks into a freestanding tower at the maximum achievable height.", "front"),
    "measurement": ("Measure the box", "Box measurement",
                    "Measure the length, width, and height within 2 mm of each dimension.", "front"),
}

TASKS = {task: labels[0] for task, labels in WORKSPACES.items() if task != "pouring"}


def public_catalog():
    return [
        {"id": task, "name": name, "short": short, "description": description, "camera": camera,
         "href": "/pouring" if task == "pouring" else "/scenarios#" + task}
        for task, (name, short, description, camera) in WORKSPACES.items()
    ]

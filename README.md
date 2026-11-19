# Codex MuJoCo Robotics

Watch Codex operate a simulated SO-ARM101 across eight tabletop tasks inspired by AA-Robotics. The local dashboard shows live camera views, model decisions, recorded replays, and grades from MuJoCo. The pouring workspace also includes I2RT YAM trials. [Set up the viewer](#run-the-local-viewer) · [Open the local dashboard](http://127.0.0.1:37656/)

![Robotics dashboard showing all eight tabletop tasks, their latest results and the run history](docs/images/robotics-dashboard.png)

## Results

<a name="five-additional-so-arm101-scenarios"></a>
<a name="so-arm101-button-and-crocodile-trials"></a>

### Seven SO-ARM101 scenarios passed on the first attempt

GPT-6.2 Sol passed all seven tasks on its first attempt with Medium reasoning, Standard speed, and seed 101. Each scored **100/100**. The model received four RGB camera views, joint readings, and command feedback. Independent MuJoCo replays reproduced all seven grades from the saved decisions. Each video follows the original wall-clock timing and holds the verified outcome on screen for four seconds.

| Scenario and recording | Pass criterion | Verified outcome | Decisions | Wall time | Camera evidence |
| --- | --- | --- | ---: | ---: | --- |
| **Press the red button**<br>[Replay](artifacts/browser-viewer/scenario-runs/button/20261119-151826-sol-medium/replay.mp4) · [Grade](artifacts/browser-viewer/scenario-runs/button/20261119-151826-sol-medium/result.json) | Press the button with the gripper until it flashes. | The button traveled 11.60 mm and flashed at 3.202 s of simulated time. | 2 | 28.0 s | [<img src="artifacts/browser-viewer/scenario-runs/button/20261119-151826-sol-medium/frames/00010/wrist.jpg" alt="Wrist view of the gripper pressing the button as it flashes yellow" width="150">](artifacts/browser-viewer/scenario-runs/button/20261119-151826-sol-medium/frames/00010/wrist.jpg) |
| **Place the crocodile in the rectangle**<br>[Replay](artifacts/browser-viewer/scenario-runs/crocodile/20261119-151826-sol-medium/replay.mp4) · [Grade](artifacts/browser-viewer/scenario-runs/crocodile/20261119-151826-sol-medium/result.json) | Release the toy with its entire body inside the rectangle. | All 27 parts settled inside. The closest edge had 4.947 mm of clearance. | 3 | 52.4 s | [<img src="artifacts/browser-viewer/scenario-runs/crocodile/20261119-151826-sol-medium/frames/00030/left.jpg" alt="Left view of the open gripper above the crocodile with its feet and tail inside the blue rectangle" width="150">](artifacts/browser-viewer/scenario-runs/crocodile/20261119-151826-sol-medium/frames/00030/left.jpg) |
| **Tidy the blocks**<br>[Replay](artifacts/browser-viewer/scenario-runs/tidying/20261119-suite-v1-1-sol-medium/replay.mp4) · [Grade](artifacts/browser-viewer/scenario-runs/tidying/20261119-suite-v1-1-sol-medium/result.json) | Place all four blocks below the rim and release the lid flush on all four corners. | All four blocks settled inside and the lid sat flush. | 11 | 3m 29.6s | [<img src="artifacts/browser-viewer/scenario-runs/tidying/20261119-suite-v1-1-sol-medium/frames/00055/front.jpg" alt="Front view of all four blocks in the open box" width="150">](artifacts/browser-viewer/scenario-runs/tidying/20261119-suite-v1-1-sol-medium/frames/00055/front.jpg)<br>[Lid closed](artifacts/browser-viewer/scenario-runs/tidying/20261119-suite-v1-1-sol-medium/frames/00068/front.jpg) |
| **Match the shapes**<br>[Replay](artifacts/browser-viewer/scenario-runs/shape_matching/20261119-suite-v1-1-sol-medium/replay.mp4) · [Grade](artifacts/browser-viewer/scenario-runs/shape_matching/20261119-suite-v1-1-sol-medium/result.json) | Seat all eight pieces flat in the sockets shown in the target picture, matching both shape and color. The pieces have raised handles. | All eight pieces settled in the correct sockets. | 17 | 4m 02.4s | [<img src="artifacts/browser-viewer/scenario-runs/shape_matching/20261119-suite-v1-1-sol-medium/frames/00108/overhead.jpg" alt="Overhead view of all eight pieces seated on the board" width="150">](artifacts/browser-viewer/scenario-runs/shape_matching/20261119-suite-v1-1-sol-medium/frames/00108/overhead.jpg)<br>[Target picture](artifacts/browser-viewer/scenario-runs/shape_matching/20261119-suite-v1-1-sol-medium/reference.png) |
| **Write “hello world”**<br>[Replay](artifacts/browser-viewer/scenario-runs/writing/20261119-suite-v1-1-sol-medium/replay.mp4) · [Grade](artifacts/browser-viewer/scenario-runs/writing/20261119-suite-v1-1-sol-medium/result.json) | Use the premounted marker to write the phrase inside the black rectangle. Tesseract checks the words, ignoring case. | Tesseract read “HELLO WORLD” from the model’s strokes. Every mark was inside the rectangle. | 2 | 55.3 s | [<img src="artifacts/browser-viewer/scenario-runs/writing/20261119-suite-v1-1-sol-medium/frames/00061/overhead.jpg" alt="Overhead view of HELLO WORLD written inside the black rectangle" width="150">](artifacts/browser-viewer/scenario-runs/writing/20261119-suite-v1-1-sol-medium/frames/00061/overhead.jpg) |
| **Build the tower**<br>[Replay](artifacts/browser-viewer/scenario-runs/tower/20261119-suite-v1-1-sol-medium/replay.mp4) · [Grade](artifacts/browser-viewer/scenario-runs/tower/20261119-suite-v1-1-sol-medium/result.json) | Stack all four 20 mm blocks in a freestanding tower with at least 80% of each upper block’s footprint supported. | All four blocks remained stacked after release, reaching 79.6 mm of the nominal 80 mm. | 8 | 1m 42.0s | [<img src="artifacts/browser-viewer/scenario-runs/tower/20261119-suite-v1-1-sol-medium/frames/00045/left.jpg" alt="Left view of the freestanding four-block tower with the gripper withdrawn" width="150">](artifacts/browser-viewer/scenario-runs/tower/20261119-suite-v1-1-sol-medium/frames/00045/left.jpg)<br>[Front view](artifacts/browser-viewer/scenario-runs/tower/20261119-suite-v1-1-sol-medium/frames/00045/front.jpg) |
| **Measure the box**<br>[Replay](artifacts/browser-viewer/scenario-runs/measurement/20261119-suite-v1-1-sol-medium/replay.mp4) · [Grade](artifacts/browser-viewer/scenario-runs/measurement/20261119-suite-v1-1-sol-medium/result.json) | Report length, width, and height, each within 2 mm. The overhead and front views provide scales of 2.4 and 3 pixels/mm, respectively. | Length, width, and height errors were 0.05, 0.46, and 0.27 mm, respectively. | 1 | 13.9 s | [<img src="artifacts/browser-viewer/scenario-runs/measurement/20261119-suite-v1-1-sol-medium/frames/00003/overhead.jpg" alt="Overhead view of the box footprint against the calibrated grid" width="150">](artifacts/browser-viewer/scenario-runs/measurement/20261119-suite-v1-1-sol-medium/frames/00003/overhead.jpg)<br>[<img src="artifacts/browser-viewer/scenario-runs/measurement/20261119-suite-v1-1-sol-medium/frames/00003/front.jpg" alt="Front view of the box height against the calibrated grid" width="150">](artifacts/browser-viewer/scenario-runs/measurement/20261119-suite-v1-1-sol-medium/frames/00003/front.jpg) |

The button log records a verifier error caused by comparing a Python tuple with a JSON array. After the comparison was corrected, replaying the same two decisions confirmed the press. The 28.0 s shown above is the original trial time.

The five trials with archived controller revisions used v1. Their test protocol stops at the first verified pass. If Sol Medium fails, it tries Sol Max, Astra Medium, and Astra Max in order. If all four fail, the sequence repeats after a controller or prompt improvement.

### Pouring

The arm transfers 21 yellow beads from the blue cup to the orange cup, then sets the cups down upright and releases the gripper.

![SO-ARM101 pouring dashboard after the GPT-6.2 Astra Medium v2 trial, showing four cameras, model output, pouring skill versions and twelve timed results](docs/images/pouring-viewer.png)

All twelve trials used Standard inference speed and the same starting layout. The four initial camera views matched across trials for each arm. The table reports final-capture scores from independent physics replays using `final-capture-v3`. Wall time includes model calls, arm motion, grading, verification and video export.

| Arm | Model | Effort | Pouring skills | Beads in target | Outside at finish | Counted as spilled | Score / 100 | Wall time | Replay |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| SO-ARM101 | GPT-6.2 Sol | Medium | v2 | 21 / 21 | 0 | 0 | 100.0 | 2:49 | [Watch](artifacts/browser-viewer/codex-runs/20261119-144751-586310/replay.mp4) |
| SO-ARM101 | GPT-6.2 Sol | Max | v2 | 21 / 21 | 0 | 0 | 100.0 | 4:36 | [Watch](artifacts/browser-viewer/codex-runs/20261119-143835-613508/replay.mp4) |
| SO-ARM101 | GPT-6.2 Astra | Medium | v2 | 19 / 21 | 2 | 2 | 90.5 | 3:50 | [Watch](artifacts/browser-viewer/codex-runs/20261119-145041-728970/replay.mp4) |
| SO-ARM101 | GPT-6.2 Astra | Max | v2 | 21 / 21 | 0 | 0 | 100.0 | 4:33 | [Watch](artifacts/browser-viewer/codex-runs/20261119-144315-759105/replay.mp4) |
| SO-ARM101 | GPT-6.2 Sol | Medium | v1 | 10 / 21 | 11 | 11 | 47.6 | 3:13 | [Watch](artifacts/browser-viewer/codex-runs/20261119-135814-152629/replay.mp4) |
| SO-ARM101 | GPT-6.2 Sol | Max | v1 | 12 / 21 | 9 | 9 | 57.1 | 5:38 | [Watch](artifacts/browser-viewer/codex-runs/20261119-140806-676657/replay.mp4) |
| SO-ARM101 | GPT-6.2 Astra | Medium | v1 | 8 / 21 | 13 | 13 | 38.1 | 3:02 | [Watch](artifacts/browser-viewer/codex-runs/20261119-141346-823451/replay.mp4) |
| SO-ARM101 | GPT-6.2 Astra | Max | v1 | 15 / 21 | 6 | 6 | 71.4 | 4:46 | [Watch](artifacts/browser-viewer/codex-runs/20261119-141651-967847/replay.mp4) |
| I2RT YAM | GPT-6.2 Sol | Medium | v1 | 8 / 21 | 13 | 13 | 38.1 | 3:11 | [Watch](artifacts/browser-viewer/codex-runs/20261119-112142-227580/replay.mp4) |
| I2RT YAM | GPT-6.2 Sol | Max | v1 | 8 / 21 | 13 | 13 | 38.1 | 6:03 | [Watch](artifacts/browser-viewer/codex-runs/20261119-132720-862589/replay.mp4) |
| I2RT YAM | GPT-6.2 Astra | Medium | v1 | 5 / 21 | 16 | 16 | 23.8 | 3:22 | [Watch](artifacts/browser-viewer/codex-runs/20261119-112916-139006/replay.mp4) |
| I2RT YAM | GPT-6.2 Astra | Max | v1 | 9 / 21 | 12 | 12 | 42.9 | 4:31 | [Watch](artifacts/browser-viewer/codex-runs/20261119-133326-326651/replay.mp4) |

On the repeated SO-ARM101 layout, Sol Medium went from 10 to 21 captured beads, Sol Max from 12 to 21, Astra Medium from 8 to 19, and Astra Max from 15 to 21. The three trials that captured all 21 beads each earned 100.0/100 with zero spills. Astra Medium earned 90.5/100 with two spilled beads.

#### What changed in the second SO-ARM101 pouring experiment

All four first-version runs emptied the blue cup. Offline replay showed why many beads missed the receiver. On the shared layout, missed beads crossed the height of the orange rim roughly 47–48 mm beyond its center in the direction of discharge. The inner rim radius is 41 mm.

The second controller estimates the lowest point of the source rim from arm geometry. As the cup tilts, it lowers the outlet from 90 to 53 mm above the receiving rim and moves it upstream by up to one source-cup radius. It follows a smooth wrist arc with a maximum commanded tilt rate of 28° per second. The model still selects the target from the RGB images.

The revised operator skill asks the model to inspect the stream, hold its tilt if beads are draining and adjust its aim if it sees a persistent miss while beads remain. After each tilt, the next decision also receives four chronological crops of the overhead camera, centered on the model’s chosen aim. Both models used the same skill and controller. Each model and reasoning-effort combination was tested once per revision on this layout, so these results compare the combined changes on that layout. [Pouring skill](artifacts/browser-viewer/skills/so101-pour-v2/SKILL.md) · [Motion controller](artifacts/browser-viewer/so101_controls_v2.py)

Six separate scripted checks isolate the motion change by giving both controllers the same image-derived points and tilt angles for each layout. The revised controller caught 21 beads in five layouts. On seed 166, the blue cup knocked the receiver aside and captured zero, down from six. The mean score across all six rose from 37.3 to 83.3. These checks use scripted decisions and are listed separately from the model runs. Run `MUJOCO_GL=egl python artifacts/browser-viewer/check_so101_skills.py` to reproduce them. [Scripted comparisons](artifacts/browser-viewer/check_so101_skills.py)

#### How pouring is scored

For a valid finished pour, the score is **100 × beads in the orange cup ÷ 21**. Capturing all 21 beads earns 100.0, and capturing 19 earns 90.5. Both cups must be upright, settled, separate and released. Beads still in play must also settle. An unsafe finish or an invalid final state earns zero.

The spill count tracks individual beads that touch the bare tabletop, fall below the table, or finish outside both cups. A bead striking the inside base of the orange cup registers as cup contact. A bead that spills and later lands in the receiver counts once in each measure. The grader also records a separate task-success flag, which requires at least 90% captured, at most one spill, and a stable terminal window. [Full results and run history](artifacts/browser-viewer/codex-runs/run-history.json)

## How Codex controls the arm

For each decision, Codex receives front, left, overhead and wrist RGB images, robot joint readings, and previous command feedback. It chooses an action and its parameters. For a button press, the model chooses an overhead pixel. For crocodile placement, it also chooses the angle at which the jaws close across the toy. For pouring, it chooses a cup rim, aligns the gripper, and controls the tilt. A controller converts each command into joint motion. The simulator grades physical contact or final placement and can replay the recorded commands from the same seed.

These are local, camera-guided simulations inspired by Artificial Analysis’s physical AA-Robotics benchmark. The SO-ARM101 uses task-specific motions and calibrated cameras. The button and granular-pouring physics, tower support check, and box measurement grader build on the independently developed `robo_mj_bench` project. The physical benchmark uses different hardware and scoring conditions. [Upstream benchmark revision](https://github.com/lizimo061/robo_mj_bench/tree/a886b54f3cff4e0994f9d3150e032003935b59c6)

The SO-ARM101 uses five arm joints and a hinged gripper. Its controller approaches the blue cup from the side and lifts it by finger contact. During pouring, it rolls the wrist and adjusts the arm pitch to keep the estimated cup lip over the selected target. The controller uses the calibrated overhead camera and nominal cup dimensions. The SO-ARM101 base is mounted 14 cm closer to the cups along the table’s x-axis to accommodate its shorter reach. The table, cups, 21 beads, three external cameras, and revised evaluator are shared with the YAM. [SO-101 model provenance](artifacts/browser-viewer/models/robotstudio_so101/PROVENANCE.json)

## Physical pouring task in AA-Robotics

Artificial Analysis asks the arm to pour a drink from a bottle into a cup without spilling or breaking anything. In this frame from Artificial Analysis’s video of GPT-6.2 Astra’s physical trial, liquid is visible in the cup and on the table. [Task description](https://artificialanalysis.ai/articles/aa-robotics?aa-robotics-run-task=pour-drink-into-cup) · [Original video by Artificial Analysis](https://x.com/ArtificialAnlys/status/2122757022710104131)

![Artificial Analysis’s physical pouring trial with GPT-6.2 Astra, showing the bottle, cup, and spilled liquid](docs/images/aa-robotics-astra-pouring.png)

## Run the local viewer

Use Linux with Python 3.12. The commands below clone the project with its pinned benchmark and install the MuJoCo, NumPy, and Pillow versions used for the recorded trials.

```bash
git clone --recurse-submodules https://github.com/thunderrun/codex-mujoco-robotics.git
cd codex-mujoco-robotics
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ./benchmark 'mujoco==3.17.0' 'numpy==2.3.4' 'Pillow==12.0.0'
MUJOCO_GL=egl python artifacts/browser-viewer/serve.py
```

Open the dashboard and choose a task. In the seven SO-ARM101 scenario workspaces, select a trial to see its four camera feeds and Codex event log. Scrub through recorded frames, play the timeline, or open the exported video. Expand **Task instructions and decision prompts** to read the archived skill and select any decision’s exact prompt. Shape matching also shows the goal picture that the model received. The pouring workspace lets you choose a robot arm, pouring skill, model, inference speed, and reasoning effort for a new run. SO-ARM101 offers v1 or v2 and defaults to v2. I2RT YAM uses its v1 skill. [Dashboard](http://127.0.0.1:37656/) · [Button](http://127.0.0.1:37656/scenarios#button) · [Crocodile](http://127.0.0.1:37656/scenarios#crocodile) · [Pouring](http://127.0.0.1:37656/pouring)

New model trials require a working Linux EGL graphics driver and an authenticated Codex CLI with access to the selected model and speed. The pouring dashboard launcher also requires a systemd user session. The recorded trials used Codex CLI 0.170.0. The video exporters use FFmpeg, ffprobe, and DejaVu Sans. The writing grader uses Tesseract with English language data. Install the Ubuntu packages `ffmpeg`, `fonts-dejavu-core`, `tesseract-ocr`, and `tesseract-ocr-eng` for these features.

To run another camera-guided SO-ARM101 trial on the published layout, choose `button`, `crocodile`, `tidying`, `shape_matching`, `writing`, `tower`, or `measurement`. Each run writes a new directory under `artifacts/browser-viewer/scenario-runs/` and appears in the dashboard.

```bash
MUJOCO_GL=egl python artifacts/browser-viewer/run_scenario.py --task button --seed 101 --model gpt-6.2-sol --effort medium
```

## Reproduce the archived scores

Replay any archived SO-ARM101 scenario from its saved model decisions. The commands below use button and crocodile as examples. Each rebuilds the scene with the recorded seed and compares the grade and controller responses with the original run.

```bash
python artifacts/browser-viewer/run_scenario.py --verify artifacts/browser-viewer/scenario-runs/button/20261119-151826-sol-medium
python artifacts/browser-viewer/run_scenario.py --verify artifacts/browser-viewer/scenario-runs/crocodile/20261119-151826-sol-medium
```

For each pouring trial, the following command checks the recorded physics and computes the final-capture grade from a fresh replay. It saves the verified grade alongside the recording. For trials recorded with `final-capture-v3`, it checks the recorded grade directly.

```bash
(
  set -e
  for run in artifacts/browser-viewer/codex-runs/20*/; do
    python artifacts/browser-viewer/verify_codex_pour.py --rescore "$run"
  done
)
```

Each pouring trial directory contains the public event stream, individual model decisions, final status, grader output, physics verification, rendered video, and the first and last four-camera snapshots. The new SO-ARM101 runs include the overhead crops shown after each tilt. Every v1 history row opens the original pouring instructions used with that arm. [SO-ARM101 v1 skill](artifacts/browser-viewer/codex-runs/20261119-141651-967847/pouring-skill.md) · [I2RT YAM v1 skill](artifacts/browser-viewer/codex-runs/20261119-133326-326651/pouring-skill.md)

Each v2 trial archives the exact UTF-8 text sent at every decision. The [viewer’s prompt and skill panel](http://127.0.0.1:37656/pouring#runInstructions) lets you select a run and decision to inspect. Decision receipts list the image views and a SHA-256 digest of the prompt text. The verifier selects each run’s recorded controller revision. Later runs include the model and per-decision settings receipts. The earliest Sol run predates those receipts. Its viewer recorded the original fixed Medium effort under the display label `Standard`.

New pouring runs save their full camera sequences locally and update `artifacts/browser-viewer/codex-runs/run-history.json`. The web viewer serves that history at [the local JSON endpoint](http://127.0.0.1:37656/api/history). The `benchmark` submodule points to the upstream project and retains its own source and asset notices.

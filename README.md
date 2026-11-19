# Pouring with Codex and MuJoCo

Watch Codex operate a simulated SO-ARM101 or I2RT YAM arm in MuJoCo. The goal is to pour 21 yellow beads from a blue cup into an orange cup, then set the cups down upright and release the gripper. The local browser viewer lets you select the arm, shows four camera feeds, streams each model's observations and commands, and keeps a JSON history of runs.

![SO-ARM101 pouring dashboard after the GPT-6.2 Astra Medium v2 trial, showing four cameras, model output, pouring skill versions and twelve timed results](docs/images/pouring-viewer.png)

## Results

All twelve trials used Standard inference speed, the same starting layout and the local `tabletop-v2` evaluator. The four initial camera views matched across trials for each arm. An independent physics replay verified each result. Wall time includes model calls, arm motion, grading, verification and video export.

| Arm | Model | Effort | Pouring skills | Beads in target | Outside at finish | Counted as spilled | Score / 100 | Wall time | Replay |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| SO-ARM101 | GPT-6.2 Sol | Medium | v2 | 21 / 21 | 0 | 3 | 99.0 | 2:49 | [Watch](artifacts/browser-viewer/codex-runs/20261119-144751-586310/replay.mp4) |
| SO-ARM101 | GPT-6.2 Sol | Max | v2 | 21 / 21 | 0 | 3 | 99.0 | 4:36 | [Watch](artifacts/browser-viewer/codex-runs/20261119-143835-613508/replay.mp4) |
| SO-ARM101 | GPT-6.2 Astra | Medium | v2 | 19 / 21 | 2 | 4 | 90.5 | 3:50 | [Watch](artifacts/browser-viewer/codex-runs/20261119-145041-728970/replay.mp4) |
| SO-ARM101 | GPT-6.2 Astra | Max | v2 | 21 / 21 | 0 | 3 | 99.0 | 4:33 | [Watch](artifacts/browser-viewer/codex-runs/20261119-144315-759105/replay.mp4) |
| SO-ARM101 | GPT-6.2 Sol | Medium | v1 | 10 / 21 | 11 | 12 | 47.6 | 3:13 | [Watch](artifacts/browser-viewer/codex-runs/20261119-135814-152629/replay.mp4) |
| SO-ARM101 | GPT-6.2 Sol | Max | v1 | 12 / 21 | 9 | 10 | 57.1 | 5:38 | [Watch](artifacts/browser-viewer/codex-runs/20261119-140806-676657/replay.mp4) |
| SO-ARM101 | GPT-6.2 Astra | Medium | v1 | 8 / 21 | 13 | 15 | 38.1 | 3:02 | [Watch](artifacts/browser-viewer/codex-runs/20261119-141346-823451/replay.mp4) |
| SO-ARM101 | GPT-6.2 Astra | Max | v1 | 15 / 21 | 6 | 10 | 71.4 | 4:46 | [Watch](artifacts/browser-viewer/codex-runs/20261119-141651-967847/replay.mp4) |
| I2RT YAM | GPT-6.2 Sol | Medium | v1 | 8 / 21 | 13 | 15 | 38.1 | 3:11 | [Watch](artifacts/browser-viewer/codex-runs/20261119-112142-227580/replay.mp4) |
| I2RT YAM | GPT-6.2 Sol | Max | v1 | 8 / 21 | 13 | 16 | 38.1 | 6:03 | [Watch](artifacts/browser-viewer/codex-runs/20261119-132720-862589/replay.mp4) |
| I2RT YAM | GPT-6.2 Astra | Medium | v1 | 5 / 21 | 16 | 18 | 23.8 | 3:22 | [Watch](artifacts/browser-viewer/codex-runs/20261119-112916-139006/replay.mp4) |
| I2RT YAM | GPT-6.2 Astra | Max | v1 | 9 / 21 | 12 | 17 | 42.9 | 4:31 | [Watch](artifacts/browser-viewer/codex-runs/20261119-133326-326651/replay.mp4) |

On the repeated SO-ARM101 layout, Sol Medium went from 10 to 21 captured beads, Sol Max from 12 to 21, Astra Medium from 8 to 19, and Astra Max from 15 to 21. The three 21-bead trials scored 99.0 because three beads registered as spilled during the pour and later landed in the receiver.

### What changed in the second SO-ARM101 experiment

All four first-version runs emptied the blue cup. Offline replay showed why many beads missed the receiver. On the shared layout, missed beads crossed the height of the orange rim roughly 47–48 mm beyond its center in the direction of discharge. The inner rim radius is 41 mm.

The second controller estimates the lowest point of the source rim from arm geometry. As the cup tilts, it lowers the outlet from 90 to 53 mm above the receiving rim and moves it upstream by up to one source-cup radius. It follows a smooth wrist arc with a maximum commanded tilt rate of 28° per second. The model still selects the target from the RGB images.

The revised operator skill asks the model to inspect the stream, hold its tilt if beads are draining and adjust its aim if it sees a persistent miss while beads remain. After each tilt, the next decision also receives four chronological crops of the overhead camera, centered on the model’s chosen aim. Both models used the same skill and controller. Each model and reasoning-effort combination was tested once per revision on this layout, so these results compare the combined changes on that layout. [Pouring skill](artifacts/browser-viewer/skills/so101-pour-v2/SKILL.md) · [Motion controller](artifacts/browser-viewer/so101_controls_v2.py)

Six separate scripted checks isolate the motion change by giving both controllers the same image-derived points and tilt angles for each layout. The revised controller caught 21 beads in five layouts. On seed 166, the blue cup knocked the receiver aside and captured zero, down from six. The mean score across all six rose from 37.3 to 83.0. These checks use scripted decisions and are listed separately from the model runs. Run `MUJOCO_GL=egl python artifacts/browser-viewer/check_so101_skills.py` to reproduce them. [Scripted comparisons](artifacts/browser-viewer/check_so101_skills.py)

### How scoring works

A settled, valid partial pour earns 100 × the fraction of all 21 beads in the orange cup, capped at 99. Full credit requires at least 90% in the target, at most one spilled bead, and a successful stability check over the terminal window. For partial credit, both cups must be upright, at rest, released and separate, and all beads still in play must have settled. The spill count records beads seen spilling during the run, including ones that later land in a cup.

The scene has no floor below the table. The revised scorer treats a spilled bead that has fallen completely below the tabletop and is moving downward as lost. That bead earns no transfer credit and counts as spilled. Other beads still have to settle, including beads rolling across the table.

For SO-ARM101 Sol Medium, the revised scorer awards **47.6/100** for 10 captured beads. Replaying all 14 decisions reproduced the original final positions. [Verified grading comparison](artifacts/browser-viewer/codex-runs/20261119-135814-152629/verification-v2.json) · [Full run history](artifacts/browser-viewer/codex-runs/run-history.json)

## How the trial works

Each Codex decision receives front, left, overhead and wrist RGB images, robot joint encoders, and previous command feedback. The model selects actions such as approaching a cup rim at a chosen overhead pixel, aligning, or tilting to a chosen angle. Each arm has its own controller to translate pixel coordinates and requested tilt into joint motion. The simulator grades the final state separately and stores the seed and final state for replay. This is a local granular-pouring trial based on the independently developed [robo_mj_bench](https://github.com/lizimo061/robo_mj_bench/tree/a886b54f3cff4e0994f9d3150e032003935b59c6). Artificial Analysis runs its separate AA-Robotics benchmark on physical hardware.

The SO-ARM101 uses five arm joints and a hinged gripper. Its controller approaches the blue cup from the side and lifts it by finger contact. During pouring, it rolls the wrist and adjusts the arm pitch to keep the estimated cup lip over the selected target. The controller uses the calibrated overhead camera and nominal cup dimensions. The SO-ARM101 base is mounted 14 cm closer to the cups along the table’s x-axis to accommodate its shorter reach. The table, cups, 21 beads, three external cameras, and revised evaluator are shared with the YAM. [SO-101 model provenance](artifacts/browser-viewer/models/robotstudio_so101/PROVENANCE.json)

## Physical pouring task in AA-Robotics

Artificial Analysis asks the arm to pour a drink from a bottle into a cup without spilling or breaking anything. In this frame from Artificial Analysis’s video of GPT-6.2 Astra’s physical trial, liquid is visible in the cup and on the table. [Task description](https://artificialanalysis.ai/articles/aa-robotics?aa-robotics-run-task=pour-drink-into-cup) · [Original video by Artificial Analysis](https://x.com/ArtificialAnlys/status/2122757022710104131)

![Artificial Analysis’s physical pouring trial with GPT-6.2 Astra, showing the bottle, cup, and spilled liquid](docs/images/aa-robotics-astra-pouring.png)

## Run the local viewer

Use Linux with Python 3.12. The recorded environment used MuJoCo 3.17.0, NumPy 2.3.4 and Pillow 12.0.0. From the root of this checkout, install the pinned benchmark and Python dependencies, then start the viewer.

```bash
git submodule update --init --recursive
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ./benchmark 'mujoco==3.17.0' 'numpy==2.3.4' 'Pillow==12.0.0'
MUJOCO_GL=egl python artifacts/browser-viewer/serve.py
```

Open the [local viewer](http://127.0.0.1:37656/). The viewer opens the latest archived run and links each trial to its video. Choose a robot arm, pouring skill, model, inference speed, and reasoning effort. SO-ARM101 offers v1 or v2 and defaults to v2. I2RT YAM uses its v1 skill. Select **Start run** to begin another trial on the preceding layout.

Launching new trials requires a working Linux EGL graphics driver, a systemd user session, and an authenticated Codex CLI with access to the selected model and speed. The recorded trials used Codex CLI 0.170.0. The video exporter uses FFmpeg, ffprobe, and the DejaVu Sans fonts. On Ubuntu the relevant packages include `ffmpeg` and `fonts-dejavu-core`.

## Reproduce the archived scores

In the activated environment, replay the decisions from the archived runs in fresh, unrendered physics. The command uses the recorded actions and initial layout. For trials recorded with the upstream evaluator, it checks both rules and saves the revised grade and verification alongside the originals. For new trials, it verifies the recorded `tabletop-v2` grade.

```bash
(
  set -e
  for run in artifacts/browser-viewer/codex-runs/20*/; do
    python artifacts/browser-viewer/verify_codex_pour.py --rescore "$run"
  done
)
```

Each trial directory contains the public event stream, individual model decisions, final status, grader output, physics verification, rendered video, and the first and last four-camera snapshots. The new SO-ARM101 runs include the overhead crops shown after each tilt. Every v1 history row opens the original pouring instructions used with that arm. [SO-ARM101 v1 skill](artifacts/browser-viewer/codex-runs/20261119-141651-967847/pouring-skill.md) · [I2RT YAM v1 skill](artifacts/browser-viewer/codex-runs/20261119-133326-326651/pouring-skill.md)

Each v2 trial archives the exact UTF-8 text sent at every decision. The [viewer’s prompt and skill panel](http://127.0.0.1:37656/#runInstructions) lets you select a run and decision to inspect. Decision receipts list the image views and a SHA-256 digest of the prompt text. The verifier selects each run’s recorded controller revision. Later runs include the model and per-decision settings receipts. The earliest Sol run predates those receipts. Its viewer recorded the original fixed Medium effort under the display label `Standard`.

New runs save their full camera sequences locally and update `artifacts/browser-viewer/codex-runs/run-history.json`. The web viewer serves that history at [the local JSON endpoint](http://127.0.0.1:37656/api/history). The `benchmark` submodule points to the upstream project and retains its own source and asset notices.

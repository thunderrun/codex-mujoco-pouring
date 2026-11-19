# Pouring with Codex and MuJoCo

Watch Codex operate a simulated SO-ARM101 or I2RT YAM arm in MuJoCo. The goal is to pour 21 yellow beads from a blue cup into an orange cup, then set the cups down upright and release the gripper. The local browser viewer lets you select the arm, shows four camera feeds, streams each model's observations and commands, and keeps a JSON history of runs.

![MuJoCo viewer showing the I2RT YAM, its four cameras, Codex output, and the original YAM results](docs/images/pouring-viewer.png)

## Results

All trials used Standard inference speed and the same seed for the initial cups and beads. The four YAM trials began with identical images and each took 12 decisions. The SO-ARM101 has different arm geometry and a different wrist camera.

| Arm | Model | Reasoning effort | Beads in target | Outside cups at finish | Counted as spilled during run | Score / 100 | Replay |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| SO-ARM101 | GPT-6.2 Sol | Medium | 10 / 21 | 11 | 12 | 0.0 | [Watch](artifacts/browser-viewer/codex-runs/20261119-135814-152629/replay.mp4) |
| I2RT YAM | GPT-6.2 Sol | Medium | 8 / 21 | 13 | 15 | 38.1 | [Watch](artifacts/browser-viewer/codex-runs/20261119-112142-227580/replay.mp4) |
| I2RT YAM | GPT-6.2 Sol | Max | 8 / 21 | 13 | 16 | 38.1 | [Watch](artifacts/browser-viewer/codex-runs/20261119-132720-862589/replay.mp4) |
| I2RT YAM | GPT-6.2 Astra | Medium | 5 / 21 | 16 | 18 | 23.8 | [Watch](artifacts/browser-viewer/codex-runs/20261119-112916-139006/replay.mp4) |
| I2RT YAM | GPT-6.2 Astra | Max | 9 / 21 | 12 | 17 | 42.9 | [Watch](artifacts/browser-viewer/codex-runs/20261119-133326-326651/replay.mp4) |

The SO-ARM101 transferred 10 beads in 14 decisions. Both cups were upright and released. One bead fell off the table and was still falling when the one-second settling period ended. The other 20 beads met the stability threshold. The evaluator requires all 21 beads to settle before it awards points. Sol at Medium transferred eight beads with the YAM and earned 38.1 points because all beads had settled. [SO-ARM101 grading record](artifacts/browser-viewer/codex-runs/20261119-135814-152629/private/grading.json)

Independent physics replays reproduced the final positions, metrics, and scores for all five trials. The spill count tracks individual beads observed spilling during a run. A bead can later land in a cup. [Full-precision results and run history](artifacts/browser-viewer/codex-runs/run-history.json)

## How the trial works

Each Codex decision receives front, left, overhead and wrist RGB images, robot joint encoders, and previous command feedback. The model selects actions such as approaching a cup rim at a chosen overhead pixel, aligning, or tilting to a chosen angle. Each arm has its own controller to translate pixel coordinates and requested tilt into joint motion. The simulator grades the final state separately and stores the seed and final state for replay. This is a local granular-pouring trial based on the independently developed [robo_mj_bench](https://github.com/lizimo061/robo_mj_bench/tree/a886b54f3cff4e0994f9d3150e032003935b59c6). Artificial Analysis runs its separate AA-Robotics benchmark on physical hardware.

The SO-ARM101 uses five arm joints and a hinged gripper. Its controller approaches the blue cup from the side and lifts it by finger contact. During pouring, it rolls the wrist and adjusts the arm pitch to keep the estimated cup lip over the selected target. The controller uses the calibrated overhead camera and nominal cup dimensions. The SO-ARM101 base is mounted 14 cm closer to the cups along the table’s x-axis to accommodate its shorter reach. The table, cups, 21 beads, three external cameras, and evaluator are shared with the YAM. [SO-101 model provenance](artifacts/browser-viewer/models/robotstudio_so101/PROVENANCE.json)

## Physical pouring task in AA-Robotics

Artificial Analysis asks the arm to pour a drink from a bottle into a cup without spilling or breaking anything. In this frame from GPT-6.2 Astra’s physical trial, liquid is visible in the cup and on the table. [Task description](https://artificialanalysis.ai/articles/aa-robotics?aa-robotics-run-task=pour-drink-into-cup) · [Original video by Artificial Analysis](https://x.com/ArtificialAnlys/status/2122757022710104131)

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

Open the [local viewer](http://127.0.0.1:37656/). The viewer opens the latest archived run and links each trial to its video. Choose a robot arm, model, inference speed, and reasoning effort, then select **Start run** to begin another trial on the preceding layout.

Launching new trials requires a working Linux EGL graphics driver, a systemd user session, and an authenticated Codex CLI with access to the selected model and speed. The recorded trials used Codex CLI 0.170.0. The video exporter uses FFmpeg, ffprobe, and the DejaVu Sans fonts. On Ubuntu the relevant packages include `ffmpeg` and `fonts-dejavu-core`.

## Reproduce the archived scores

In the activated environment, replay the decisions from the archived runs in fresh, unrendered physics. This command uses the recorded actions and the original initial layout. It writes each comparison to that run's `verification.json`.

```bash
(
  set -e
  for run in artifacts/browser-viewer/codex-runs/20*/; do
    python artifacts/browser-viewer/verify_codex_pour.py "$run"
  done
)
```

Each trial directory contains the public event stream, individual model decisions, final status, grader output, physics verification, rendered video, and the first and last four-camera snapshots. Later runs also include the model and per-decision settings receipts. The earliest Sol run predates those receipts. Its viewer recorded the original fixed Medium effort under the display label `Standard`.

New runs save their full camera sequences locally and update `artifacts/browser-viewer/codex-runs/run-history.json`. The web viewer serves that history at [the local JSON endpoint](http://127.0.0.1:37656/api/history). The `benchmark` submodule points to the upstream project and retains its own source and asset notices.

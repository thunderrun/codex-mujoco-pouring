# Pouring with Codex and MuJoCo

Watch GPT-6.2 Sol and Astra operate a simulated I2RT YAM arm. The goal is to pour 21 yellow beads from a blue cup into an orange cup, then set the cups down upright and release the gripper. The local browser viewer shows four camera feeds, streams each model's observations and commands, and keeps a JSON history of runs.

![MuJoCo pouring viewer showing the four camera views, Codex output, and trial results](docs/images/pouring-viewer.png)

## Results

Each model ran once at Medium and once at Max reasoning on November 19, 2026. All four trials used Standard inference speed, the same initial layout, and byte-identical first images from all four cameras. Each model made 12 decisions.

| Model | Reasoning effort | Beads in target | Outside cups at finish | Counted as spilled during run | Score / 100 | Replay |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| GPT-6.2 Sol | Medium | 8 / 21 | 13 | 15 | 38.1 | [Watch](artifacts/browser-viewer/codex-runs/20261119-112142-227580/replay.mp4) |
| GPT-6.2 Sol | Max | 8 / 21 | 13 | 16 | 38.1 | [Watch](artifacts/browser-viewer/codex-runs/20261119-132720-862589/replay.mp4) |
| GPT-6.2 Astra | Medium | 5 / 21 | 16 | 18 | 23.8 | [Watch](artifacts/browser-viewer/codex-runs/20261119-112916-139006/replay.mp4) |
| GPT-6.2 Astra | Max | 9 / 21 | 12 | 17 | 42.9 | [Watch](artifacts/browser-viewer/codex-runs/20261119-133326-326651/replay.mp4) |

All four trials earned partial credit. Independent physics replays reproduced the recorded final joint and object coordinates, metrics, and scores exactly. The spill count tracks individual beads observed spilling during a run. A bead can later land in a cup. [Full-precision results and run history](artifacts/browser-viewer/codex-runs/run-history.json)

## How the trial works

Each Codex decision receives front, left, overhead and wrist RGB images, robot joint encoders, and previous command feedback. The model selects actions such as approaching a cup rim at a chosen overhead pixel, aligning, or tilting to a chosen angle. A shared controller translates those actions into robot motion. The simulator grades the final state separately and stores the seed and final state for replay. This is a local granular-pouring trial based on the independently developed [robo_mj_bench](https://github.com/lizimo061/robo_mj_bench/tree/a886b54f3cff4e0994f9d3150e032003935b59c6). Artificial Analysis runs its separate AA-Robotics benchmark on physical hardware.

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

Open the [local viewer](http://127.0.0.1:37656/). The included relative `current` symlink selects the completed Astra Max run on a fresh clone. The history table links to all four videos. Choose a model, inference speed, and reasoning effort, then select **Start run** to begin another trial on the preceding layout.

Launching new trials requires a working Linux EGL graphics driver, a systemd user session, and an authenticated Codex CLI with access to the selected model and speed. The recorded trials used Codex CLI 0.170.0. The video exporter uses FFmpeg, ffprobe, and the DejaVu Sans fonts. On Ubuntu the relevant packages include `ffmpeg` and `fonts-dejavu-core`.

## Reproduce the archived scores

In the activated environment, replay the decisions from all four archived runs in fresh, unrendered physics. This command uses the recorded actions and the original initial layout. It writes each comparison to that run's `verification.json`.

```bash
(
  set -e
  for run in artifacts/browser-viewer/codex-runs/20*/; do
    python artifacts/browser-viewer/verify_codex_pour.py "$run"
  done
)
```

Each trial directory contains the public event stream, individual model decisions, final status, grader output, physics verification, rendered video, and the first and last four-camera snapshots. The three later runs also include the model and per-decision settings receipts. The earliest Sol run predates those receipts. Its viewer recorded the original fixed Medium effort under the display label `Standard`.

New runs save their full camera sequences locally and update `artifacts/browser-viewer/codex-runs/run-history.json`. The web viewer serves that history at [the local JSON endpoint](http://127.0.0.1:37656/api/history). The `benchmark` submodule points to the upstream project and retains its own source and asset notices.

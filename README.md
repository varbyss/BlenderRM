<p align="center">
  <img src="512x512logo.png" width="128" alt="BRM logo">
</p>

<h1 align="center">Blender Render Manager (BRM)</h1>

<p align="center">
  Queue <code>.blend</code> files, press START, walk away.<br>
  Renders happen in the background — you get a message when it's done.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-2.0.0-blue" alt="version 2.0.0">
  <img src="https://img.shields.io/badge/python-3.10%2B-green" alt="python 3.10+">
  <img src="https://img.shields.io/badge/platform-Windows-lightgrey" alt="Windows">
  <img src="https://img.shields.io/badge/blender-3.x%E2%80%935.x-orange" alt="Blender 3.x-5.x">
</p>

## Contents

- [What it does](#what-it-does)
- [Install](#install)
- [First setup](#first-setup)
- [Daily use](#daily-use)
- [Features in detail](#features-in-detail)
- [Settings tour](#settings-tour)
- [Discord messages](#discord-messages)
- [Files it creates](#files-it-creates)
- [Tests](#tests)
- [Troubleshooting](#troubleshooting)

## What it does

BRM renders many Blender files one after another **without you watching**.
Add files to the queue, press START, and each file opens in Blender behind
the scenes, renders its frames, and moves on. Finished jobs become MP4s in
one click. No Blender knowledge needed to run it.

## Install

**You need:**

| Thing | Why | Where |
|---|---|---|
| Python 3.10+ (check *Add to PATH*) | runs the app | https://www.python.org/downloads/ |
| Blender 3.x–5.x | does the rendering | https://www.blender.org/download/ |
| ffmpeg | only for MP4 convert | https://ffmpeg.org/download/ |

**Then:**

```bat
cd path\to\BlenderRM
pip install -r requirements.txt
python BRM_opencode.pyw
```

| Package | Used for | Required? |
|---|---|---|
| `customtkinter` | modern widgets | yes |
| `pillow` | image display | yes |
| `psutil` | pause/resume | no — feature turns itself off |
| `requests` | Discord messages | no — feature turns itself off |
| `zstandard` | fast reading of compressed `.blend` files | no — falls back to Blender |

> Keep `512x512logo.png` next to the script (window/taskbar icon).

## First setup

1. Open **Settings** (gear icon) → **General** → set your **Blender
   executable** with Browse. The app tries to find it alone (Steam and
   Program Files are checked), but confirm it.
2. Set **ffmpeg.exe path** (only needed for Convert to MP4).
3. **Auto GUI mode for sim files** — keep ON if you render physics/sim
   files (safe choice), OFF for pure background speed. Details below.
4. **Auto full file info** — ON means cameras/resolution appear by
   themselves (big files take a while once, then cached); OFF means instant
   adding, details load on Refresh/render.
5. **Discord tab** → paste your webhook URL for start/progress/done/crash
   messages. Every message text is editable; the `{words}` it understands
   are listed right in the tab.
6. Press **ADD FILES**, click jobs to check settings, press **START**.

Settings, queue, layout and history live in
`C:\Users\<you>\blender_monitor_config.json` — back it up if the queue
matters to you.

## Daily use

| Do this | How |
|---|---|
| Add files | ADD FILES, Ctrl+O, or the `+` button |
| Select | click; Ctrl+click toggles; Shift+click takes a range |
| Reorder | drag rows up/down |
| Remove | Delete key, `x` button, or right-click → Remove |
| Row menu | right-click: move, duplicate, enable/disable, requeue, refresh info, **test frame**, convert, open folder |
| Hide a panel | double-click its tab, right-click → Hide, or drag it out of the window |
| Split a slot side-by-side | drop a tab at the slot's left/right edge (it lights up blue) |
| Layout presets | queue menu (≡) → Layout; Panels checklist shows/hides anything |
| Convert | footer **Convert MP4** (selection, else all finished without MP4) |
| After render | history lists finished projects; Open Folder jumps to files |

## Features in detail

<details>
<summary><b>Render queue</b> — batch rendering that survives real life</summary>

- Jobs render in order; jobs added mid-render join the same run.
- Structural edits (remove/move/duplicate/clear) are blocked mid-render so
  the running loop can't corrupt; appending is always safe.
- Crashes restart the job where it left off (already-rendered frames are
  reused). Set tries next to the checkbox; after that the job is marked
  Failed and the queue moves on. Stopped jobs resume on next START.
- Missing files are skipped as Failed, disabled jobs as OFF.
- Double START is refused; quitting the app kills Blender/ffmpeg instead of
  orphaning them; corrupt config boots to defaults.
</details>

<details>
<summary><b>Per-job settings</b> — scene, camera, resolution, format…</summary>

Click a job: scene, camera, view layer, frames, resolution + percent,
engine, samples, film transparent, output folder (with `{scene_name}` /
`{camera_name}` variables), FPS, format, color, Python args. Empty = use
what's saved in the file. **MATCH SOURCE** copies everything from the file
in one click. Rows always show the real values plus progress % and MP4 state.
</details>

<details>
<summary><b>Viewport</b> — the newest picture, full resolution</summary>

- Follows the job that is **rendering** (clicking other jobs can't hijack it).
- Picture comes from the output folder: newest frame file, loaded as-is,
  never downscaled. Works even when Blender prints nothing (skipped/resumed
  frames).
- Hidden viewport holds no image memory; showing it reloads. Tiles +
  scanline frame show only when there is no picture yet.
</details>

<details>
<summary><b>Progress + log</b></summary>

- Bottom tabs: PROGRESS (bar, frame counter, times) and LOG.
- Log lines are color-coded: 🟩 done · 🟥 crashed/failed · 🟨 warnings/stops
  · 🟦 info. Long sessions auto-trim so the app never slows down.
- Status bar: success rate plus last finished job.
</details>

<details>
<summary><b>MP4 convert</b></summary>

- Converts the selection (or all finished jobs without an MP4), **max 2
  ffmpeg at once** so they don't choke each other, then reports `n/n ok`.
- Finished rows earn an **MP4 READY** badge. MP4-from-folder works on any
  PNG folder. Same FFmpeg flags you already use (`-crf 12`, `yuv444p`,
  bt709).
</details>

<details>
<summary><b>Sim files</b> — read this if objects vanish</summary>

Physics/sim objects render **invisible** in background Blender — a Blender
limitation, proven here (sim data reads back empty headless). Fix: keep
**Auto GUI mode for sim files** ON (or per-job GUI checkbox). Those jobs
then render in a visible Blender window that closes itself with an exit
code, so success/failure still routes correctly and the queue advances.
</details>

<details>
<summary><b>Layout</b> — Premiere-style, everything persists</summary>

- 5 panels (queue, viewport, progress, properties, log) in 4 tabbed slots.
- Drag tabs between slots; drop at an edge for a side-by-side split;
  empty slots collapse to a slim strip; `+` and the Panels menu bring
  anything back.
- Window size/position, column widths, bottom height, tabs, splits,
  selection and scroll are all remembered. Drop guides light up while
  dragging; the landed tab flashes.
</details>

<details>
<summary><b>Fast file reading</b></summary>

- Scene/camera/resolution/sim flags are parsed straight from `.blend`
  files (Blender 5.x headers, zstd, DNA) — no Blender startup needed.
- Results cache on disk; duplicate queue entries parse once and share.
- Automatic background reads never launch Blender and pause while rendering.
  Toggleable per above.
</details>

<details>
<summary><b>Sounds + finish actions</b></summary>

Soft ding when the queue finishes (toggleable), double-ding on crashes.
On completion: nothing, PC shutdown in 60 s, or sleep — fires once after
**all** files (never mid-queue, never after manual stop).
</details>

## Settings tour

| Tab | What lives there |
|---|---|
| General | Blender + ffmpeg paths, quiet/console/GUI toggles, preview + auto-probe toggles, batch limit, retry delay, **finish sound**, auto-restart + **tries**, on-completion action |
| Discord | on/off, webhook URL, update interval, editable title/description + **start / done / crash / stop** messages |
| FFmpeg | path, default FPS/CRF, convert-folder button |
| History | finished projects only, refresh / open folder / clear |

## Discord messages

Placeholders you can use in any template:

```
{filename} {scene} {camera} {start} {end} {frame} {attempt}
{avg} {est} {bar} {pct} {elapsed} {duration} {date}
```

Broken templates fall back to built-ins instead of breaking the render.

## Files it creates

| File | What |
|---|---|
| `blender_monitor_config.json` (home folder) | settings + queue + layout |
| `blender_monitor_history.json` (home folder) | finished renders |
| `.blender_monitor_probecache/` (home folder) | parsed file info |
| `crashlog.txt` (app folder) | crash records |

## Tests

```bat
python -m unittest discover -s tests
```

Needs a display (opens the real app off-screen). ~100 checks: docking,
tabs, splits, probes, settings, queue ops, viewport, converts, render-loop
guards.

## Troubleshooting

| Problem | Fix |
|---|---|
| Sim objects missing in renders | Turn on Auto GUI mode (global or per-job) |
| Viewport shows old/no picture | Check the log: it says why (e.g. `.exr` can't display); PNG/JPG/TIF always work |
| Job skipped | Row says MISSING FILE (bad path) or OFF (disabled) |
| Second job never starts | Log tail: per-job `STARTING` lines + `[BRM gui] render finished ok=` show where it stopped |
| Frozen while adding big files | First probe pass is working through them (`Probing i/N` lines); cached after. Turn off auto full-probe for instant adds |
| Still stuck | Read the log tail — process lifecycle (stops, kills, stalls, gui markers) is narrated there; paste it with a bug report |

---
Made by **var** · v2.0.0

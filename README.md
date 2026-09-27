# Blender Render Manager (BRM)

A desktop app by **var** that renders many Blender files one after another,
in the background, while you do something else. You add `.blend` files to a
queue, press START, and the app opens Blender for each file behind the scenes,
renders the frames, and moves on to the next file by itself.

No Blender knowledge is needed to use it. If you can press ADD FILES and
START, you can use it.

## What it can do (and how)

**Render queue.** Add `.blend` files with ADD FILES (or Ctrl+O, or drag the
 +.blend button in the top bar). Press START and every file renders in turn.
 Add more files any time, even while it renders — new files join the same run.
 Select several jobs with Ctrl+click (one more / one less) or Shift+click
 (a whole range). Drag rows up and down to change the render order. Delete
 removes the selected jobs. Right-click a row for move, duplicate,
 enable/disable, requeue, refresh info, test frame, convert, open folder.

**Per-job settings.** Click a job and the right panel shows its settings:
 scene, camera, view layer, frames, resolution + percent, engine, samples,
 film transparent, output folder, FPS, file format, color mode, Python args.
 Empty means "use what is saved in the file". MATCH SOURCE copies everything
 from the file into the job with one click. The queue rows always show the
 real values (scene, camera, resolution, engine, progress %, MP4 badge).

**Live viewport.** Shows the newest rendered picture of the job that is
 rendering right now (read straight from its output folder). Clicking other
 jobs does not steal it mid-render. Hide the viewport panel and it frees its
 memory; showing it again reloads the picture.

**Progress + log.** The bottom panel has PROGRESS (bar, frame counter, times)
 and LOG tabs. The log color-codes lines: green = done, red = crashed/failed,
 amber = warnings/stops, blue = info. The status bar shows success rate.

**History.** Only finished blend projects land here (everything else stays in
 the log). Double-click magic: none — use Open Folder to jump to the renders.

**MP4 convert.** Select finished jobs (or press Convert MP4 with nothing
 selected to take all finished jobs without an MP4 yet) and the app runs
 ffmpeg on them, at most 2 at once so they don't choke each other. Finished
 rows get an MP4 READY badge. MP4 from folder works on any folder of PNGs.

**Crash restarts.** If Blender crashes, the app waits a few seconds and
 restarts that job where it left off (already-rendered frames are reused).
 Set the number of tries next to the checkbox; after that it marks the job
 Failed and moves on. Stopped jobs keep their state and resume on next START.

**Sim files (Hurricane etc.).** Physics/sim objects render invisible in
 background Blender — this is a Blender limitation, not a bug. Turn on
 "Auto GUI mode for sim files" and those jobs render with a visible Blender
 window so sims bake and show correctly. You can also force it per job.

**Test frame.** Right-click a job > Render test frame: renders one frame
 through the real pipeline. Fast way to check cameras, layers, and sims.

**Discord messages.** Start / progress / done / crash / stop messages, all
 editable in Settings > Discord with simple `{placeholders}` listed there.
 Bad templates fall back to built-ins instead of breaking.

**Sounds + finish actions.** Soft ding when the queue finishes (toggleable),
 double-ding on crashes. On completion: do nothing, shut the PC down in
 60 seconds, or sleep. Shutdown/sleep only fire when the whole queue is done
 (never mid-queue, never after a manual stop, never with jobs left over).

**Layout.** Every panel (queue, viewport, progress, properties, log) lives in
 a tabbed slot you can rearrange: drag tabs between slots, drop at a slot
 edge to split it side-by-side (the edge lights up blue), double-click a tab
 or drag it out of the window to hide it. Empty slots collapse to a slim
 strip. Window size, position, column widths, bottom height, tabs, splits,
 selection and scroll are all remembered between restarts. Layout presets
 live in the queue menu, plus a Panels checklist to show/hide anything.

**Fast file reading.** The app reads scene/camera/resolution info straight
 from `.blend` files without starting Blender (with a disk cache), so adding
 files is instant and cameras appear by themselves. Big files parse in the
 background with progress in the log.

## Install guide

1. Install **Python 3.10 or newer** (https://www.python.org/downloads/).
   During install, check "Add python.exe to PATH".
2. Install **Blender** (3.x–5.x) and **ffmpeg** (https://ffmpeg.org/download/).
   ffmpeg is only needed for MP4 convert.
3. Open a terminal in this folder and install the needed packages:

```bat
pip install -r requirements.txt
```

That installs: `customtkinter` = the modern widgets, `pillow` = image
 display, `psutil` = pause/resume support, `requests` = Discord messages,
 `zstandard` = fast reading of compressed `.blend` files. All optional
 except `customtkinter` + `pillow` — without the rest, those features
 quietly turn themselves off. Keep `512x512logo.png` next to the script
 (used for the window/taskbar icon).

4. Start the app:

```bat
python BRM_opencode.pyw
```

## Setup guide (first run)

1. Open **Settings** (gear icon) > General and set your **Blender executable
   path** (use Browse). The app tries to find it by itself first (Steam and
   Program Files are checked), but confirm it.
2. Same place: set **ffmpeg.exe path** if auto-detect missed it (only needed
   for Convert to MP4).
3. Decide: **Auto GUI mode for sim files** ON if you render physics/sim
   files (safe choice), OFF for pure background speed.
4. Decide: **Auto-load full file info** ON (cameras appear by themselves;
   big files take a while once, then cached) or OFF (instant adding,
   details load on Refresh/render).
5. In **Discord** tab, paste your webhook URL to get phone/PC messages.
   Edit any message text; the `{words}` it understands are listed there.
6. Press **ADD FILES**, pick `.blend` files, click jobs to check their
   settings, press **START**.
7. When frames are done, select jobs and **Convert MP4** (footer button does
   the selection, or everything finished).

Your settings, queue, layout and history live in
`C:\Users\<you>\blender_monitor_config.json` — back it up if the queue
matters to you.

## Tests

```bat
python -m unittest discover -s tests
```

Needs a display (it opens the real app off-screen). ~100 checks cover
docking, tabs, splits, probes, settings, queue ops, viewport and converts.

## If something looks wrong

- **Sim objects missing in renders** → turn on Auto GUI mode (or per-job
  GUI checkbox). Background Blender cannot bake sims.
- **Viewport shows old/no picture** → check the log: it now says why
  (format it can't display, e.g. EXR, or previews waiting on first frame).
- **A job is skipped** → file path broken (row says MISSING FILE) or job
  disabled (row says OFF).
- **Queue looks frozen while adding big files** → first probe pass is
  working through them; watch the `Probing i/N` log lines. It caches after.
- **Second job never starts** → check the log tail: per-job `STARTING`
  lines plus `[BRM gui] render finished ok=` markers show exactly where it
  stopped.

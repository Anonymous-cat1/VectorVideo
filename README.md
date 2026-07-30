# Vector Video Compiler

A powerful, highly optimized Python toolkit for compiling videos into a format playable in Scratch. This compiler turns videos into a series of compact, mathematically aligned JPEG atlases and gapless WAV audio chunks, minimizing file size and rendering cost so it can run flawlessly within Scratch's strict limits.

Developed by Anonymous_cat1 and Google Antigravity.

---

## Features

- **Dynamic Resolution Scaling:** Analyzes frames for detail and motion, lowering resolution dynamically to save space during high motion or low-detail scenes, while preserving extreme crispness during static scenes and cuts.
- **Smart Deduplication:** Groups identical or similar frames together, eliminating redundant images and dramatically reducing file sizes.
- **Flawless Gapless Audio:** Exports audio using uncompressed PCM WAV in 15-second chunks, circumventing MP3 compression padding gaps to guarantee zero audio clicking or "CD glitching" in Scratch.
- **Mathematical Zero-Jitter Packing:** Mathematically calculates exactly how much padding every frame needs to align perfectly with Scratch's sub-pixel 480x360 grid to prevent integer-rounding shakes and wobbles.
- **SB3 Auto-Compiler:** Can completely inject and compile the finished output directly into a playable `.sb3` Scratch Project file automatically.

---

## Installation

### Prerequisites
1. **Python 3.x**
2. **FFmpeg** installed and added to your system PATH (used for video and audio extraction).

### Setup
Clone the repository and install the Python dependencies:

```bash
pip install -r requirements.txt
```

---

## Basic Usage

To compile a standard video (15 FPS, 240px width):
```bash
python3 main.py input_video.mp4
```

To compile a video and **automatically generate a playable `.sb3` Scratch project** (requires a base player `.sb3` in the script directory):
```bash
python3 main.py input_video.mp4 -c
```

To compile an entire folder of videos in a batch:
```bash
python3 main.py ./my_videos/ -c
```

---

## Advanced Usage & Options

The compiler supports a wide variety of flags to optimize and customize your output.

### Resolution & Framing
- `-w, --width <width>`: Set the target frame width (default: 240). 
  - **The `*` Optimizer Feature:** If you append an asterisk to the width (e.g. `-w 240*`), the compiler will intelligently scan a range +/- 25% around your requested width. It will calculate the mathematically perfect resolution that completely maximizes the atlas packing space while wasting the absolute minimum amount of alignment padding. (Highly recommended!)
- `-s, --stretch`: Stretch the video to force a 4:3 aspect ratio (fits the Scratch stage exactly without letterboxing).

### Quality & Performance
- `-f, --fps <fps>`: Target Framerate (default: 15). Lowering FPS is the easiest way to save disk size!
- `-q, --jpeg-quality <1-100>`: JPEG compression quality of the atlases (default: 80).
- `-S, --sensitivity <float>`: Detail sensitivity for dynamic sizing (default: 1.0). Lower values will aggressively shrink the resolution to save space, higher values preserve more detail.
- `-d, --dedup <float>`: Deduplication tolerance (default: 2.0). Higher values merge more similar frames (saving space but lowering framerate slightly during slow motion), lower values keep more unique frames.

### Audio Settings
- `-b, --audio-bitrate <string>`: Expected audio bitrate (default: 64k).
- `-k, --audio-khz <string>`: Audio sample rate in Hz (default: 22050).
- `-m, --mono`: Downmix the extracted audio to Mono (halves audio file size!).
- `-l, --loudness <float>`: Volume multiplier for the audio (default: 1.0).
- `-M, --maximize-volume`: Automatically peak-normalize the audio to 0dB to make it as loud as possible without clipping.

### Utilities
- `-e, --estimator`: Do not actually convert the video. Just scan it and estimate the final disk size, RAM usage, and project specs. Very useful for testing if your settings will fit under the 1000MB limit.
- `-o, --meta-only`: Only generate the `meta.txt` and `Frames.txt` data files. Skips heavy image and audio processing (useful if you only tweaked geometry logic).
- `-t, --threads <int>`: Number of threads for parallel image/video processing.
- `-n, --no-open`: Do not automatically open the Export folder when finished.
- `-v, --verbose`: Enable verbose debugging logs.

---

## Best Practices & Tips for Scratch

- **Stay under the limits:** Aim for a final disk size of `<200MB`. A project over `1000MB` (1GB) is likely going to fail or be unplayable.
- **Save RAM:** Keep RAM usage under ~2000 MB to prevent the Scratch player from crashing on low-end devices or mobile.
- **The Sweet Spot:** `240` and `360` for widths are generally the sweet spots. They look fantastic without causing file sizes to explode. 
- **Framerate:** `12 - 15 FPS` is excellent for most animations and cartoons.

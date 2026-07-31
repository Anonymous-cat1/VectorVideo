# Vector Video Compiler + Client
> NOTE: For Turbowarp/Turbowarp mod users, there is already a video extension that exists in their extension library which does this way better.
 
Vector video is a high quality, performant long form video player built for vanilla Scratch3 VMs. It utilizes the costume renderer along with some clever tricks to get video as high as 360p@30 for minutes (or hours) on end!

<img width="196" height="210" alt="SYTEM-Blank-2x" src="https://github.com/user-attachments/assets/a9c07d4d-eedd-4e20-a516-eaabdd5f1d10" />

https://github.com/user-attachments/assets/f48afc15-c654-4840-8d5d-1e94ec6d465c

**Anonymous_cat1 is not responsible for any action taken by the Scratch website, or the Scratch Team that could result by uploading copyrighted/illegal content. Nor any damage caused by the compiler or client if it breaks.**
## Client
> NOTE: Some versions of the client included a RAM crash script to thwart false reports. This script has been removed from the public release of the client.

> COMPATIBILITY NOTE: Turbowarp does not play nice with the weird timing tricks the client uses. For better performance, you must disable `Warp Timer`, and enable `Disable Compiler`.

The Vector Video client `_VVPlayer_base` is a nearly fully featured high performance video player that supports:
- Arbitrary seeking via a timeline.
- Pausing.
- Preloading (to preload frames into RAM, allowing for smoother playback),
- A skeuomorphic feel inspired by the Android Holo design language.

Developed by Anonymous_cat1.
## Compiler
A powerful Python toolkit for compiling videos into a format playable by Vector Video clients. This compiler turns videos into a series of compact JPEG atlases and audio chunks to allow vanilla Scratch3 VMs to play high resolution video with little CPU cost.

Developed by Anonymous_cat1 and Google Antigravity.

---
The compiler supports:
-  **Dynamic Resolution Scaling:** Analyzes frames for detail and motion, lowering resolution dynamically to save space during high motion or low-detail scenes, while preserving extreme crispness during static scenes and cuts.
-  **Smart Deduplication:** Groups identical or similar frames together, eliminating redundant images and dramatically reducing file sizes.
-  **Seekable Audio:** Exports audio using .MP3s in 15-second chunks, allowing Vector Video clients to arbitrarily seek.
-  **Bin Packing:** Packs frames smartly into costumes to save space, along with calculating exactly how much padding every frame needs to align perfectly with Scratch's sub-pixel 480x360 (or 1024x1024 when using the auto compiler) grid along with 
- **1024x1024 Bitmap Injection** (Only when using the auto compiler): Makes use of a bug in the Scratch3 VM
-  **Auto Compiler:** Can completely inject and compile the finished output directly into a playable `.sb3` Scratch Project file automatically.
## Installation
### Prerequisites
> NOTE: If you're on Linux, you can usually get these from your package manager (E.g., apt, dnf, aur, etc).
1.  **[Python 3.x](https://www.python.org/downloads/)** installed and added to your system PATH.
2.  **[FFmpeg](https://ffmpeg.org/download.html)** installed and added to your system PATH (used for video and audio extraction).
### Setup
> NOTE: Vector Video was developed for, and on Fedora 44 (Linux). But, it should still work on other systems.
1. Clone the repository.
```bash
git clone https://github.com/Anonymous-cat1/VectorVideo/
```
2. Install dependencies.
```bash
pip install -r requirements.txt	
```
## Basic Usage
First, run the `-h`/`--help` command to get acquainted with the compiler's args. **This is really important if you want to customize video settings!**
```bash
python main.py --help
```
---
To compile a standard video (15 FPS, 240px width):
```bash
python main.py input_video.mp4
```
To compile a video using the auto compiler:
```bash
python3 main.py input_video.mp4  -c
```
To compile an entire folder of videos in a batch, just pass a folder.
```bash
python3 main.py ./my_videos/
```
### Example Commands
A command example for films:
```bash
python main.py 'path/to/movie.mp4' -f 12 -w 220* -m -c -e
# 12 FPS
# Width is set to the most efficient resolution around 220p (note the *)
# Mono audio
# Use the auto compiler
# Use with esitmator (does not convert entrie video)
```
A command example for short animated content:
```bash
python main.py 'path/to/animation.mp4' -f 10 -n -w 360* -e -s -q 98
# 10 FPS
# Do not open export folder after conversion
# Width is set to the most efficient resolution around 360p (note the *)
# Use with esitmator (does not convert entrie video)
# Stretch video to 4:3
# 98% Jpeg quality (very high)
```
A command example estimate for live action content:
```bash
python3 main.py 'path/to/liveaction.mp4' -f 12 -w 220* -c -e
# 12 FPS
# Width is set to the most efficient resolution around 220p (note the *)
# Use the auto compiler
# Use with estimator (does not convert entire video)
```
## Using the estimator (and how to interpret it)
> NOTE: The estimator function is really important to getting longer videos to load correctly.

**Always use the estimator!** it will save you from wasting time as it is quick.
To use the (resource) estimator, append `-e`/`--estimator`.
```bash
python main.py input_video.mp4 -e
```
You should see something like this (with added notes):
> NOTE: The estimator cannot be 100% accurate, but it should give you a good reference on how your video looks.
```bash
=============
Specs:
- Name: Test Video
- Resolution (Original): 240x180
- Resolution (Scaled): ~240x180 (Avg scale: 1.00x)
- Framerate: 15 FPS
- Quality: 90% JPEG
- Audio: 64k @ 22050 Hz
- Frames: 3520 <--- Keep this under 15,000.
- Costumes ~392 <-- Keep this under 1,500.
- Audio splits: 4
Estimated disk space
- Best case: 29.33 MB
- Average: 78.83 MB <-- Aim for 200 MB or less.
- Worst case: 194.33 MB
Estimated RAM usage
- 1568 MB (During playback) <-- Keep this under 6000 MB (6GB). The less, the better.
=============
```
### Estimator tips:
To use the estimator to it's advantage:
- Aim for a final disk size of <200 MB. 1,000 MB (1 GB) should be your absolute maximum.
> NOTE: Most devices can hold up to +6,000 MB (6 GB).
- Keep RAM usage under ~2,000 MB to prevent crashes on low-end devices. 
- 240 and 360 for widths often look good and aren't too big.
- 10 - 20 FPS are good for most animations.
- 12 FPS is good for films.
- Lowering the FPS will save you the most space in general.
## Advanced Usage & Options
The compiler supports a wide variety of flags to optimize and customize your output.

---
### Resolution & Framing
-  `-w, --width <width>`: Set the target frame width (default: 240).
> **The `*` Optimizer Feature:** If you append an asterisk to the width (e.g. `-w 240*`), the compiler will intelligently scan a range +/- 25% around your requested width. It will calculate the mathematically perfect resolution that completely maximizes the atlas packing space while wasting the absolute minimum amount of alignment padding (highly recommended!)
-  `-s, --stretch`: Stretch the video to force a 4:3 aspect ratio (fits the Scratch stage exactly without letterboxing).
### Quality & Performance
-  `-f`/`--fps <fps>`: Target Framerate (default: 15). Lowering FPS is the easiest way to save disk size!
-  `-q`/`--jpeg-quality <1-100>`: JPEG compression quality of the atlases (default: 90).
-  `-S`/`--sensitivity <float>`: Detail sensitivity for dynamic sizing (default: 1.0). Lower values will aggressively shrink the resolution to save space, higher values preserve more detail.
-  `-d`/`--dedup <float>`: Deduplication tolerance (default: 2.0). Higher values merge more similar frames (saving space but lowering framerate slightly during slow motion), lower values keep more unique frames.
### Audio Settings
-  `-b, --audio-bitrate <string>`: Expected audio bitrate (default: 64k).
-  `-k, --audio-khz <string>`: Audio sample rate in Hz (default: 22050).
-  `-m, --mono`: Downmix the extracted audio to Mono (halves audio file size!).
-  `-l, --loudness <float>`: Volume multiplier for the audio (default: 1.0).
-  `-M, --maximize-volume`: Automatically peak-normalize the audio to 0dB to make it as loud as possible without clipping.
### Utilities
-  `-e, --estimator`: Do not actually convert the video. Just scan it and estimate the final disk size, RAM usage, and project specs. Very useful for testing your settings.
-  `-o, --meta-only`: Only generate the `meta.txt` and `Frames.txt` data files. Skips heavy image and audio processing (useful if you only tweaked geometry logic).
-  `-t, --threads <int>`: Number of threads for parallel image/video processing.
-  `-n, --no-open`: Do not automatically open the Export folder when finished.
-  `-v, --verbose`: Enable verbose debugging logs.
## Uploading
> NOTE: Uploading works best on Chromium based browsers (E.g., Brave, Edge, Chrome, etc).
 
> PERFORMANCE ADVISORY: On systems with low RAM, uploading more than 1,000 costumes can crash your browser!
You can upload Vector Video projects in two ways:
### Manual Uploading
This requires you to upload a blank `_VVPlayer_base` project to scratch and do the following:
1. Upload a blank `_VVPlayer_base` project via the `Load project from computer` option under `file`.
2. Drag and drop `meta.txt` and `frames.txt` into the lists shown after uploading the project.
3. Upload audio to the player sprite and save. **It is not required to upload them into any order.** 
> NOTE: For faster uploading, you may want to skip the frame blocks and upload all frames at once.
> 
> To do this,  search `.jpg` in your video's export directory, and upload all frames. While uploading, use an autoclicker to click `Save Now` to save in small chucks in order to avoid `Project cannot be saved!` errors.
4. Upload frames to the player sprite. Open a frame block folder, then upload its contents, then save before moving to the next frame block folder. **It is not required to upload them into any order.** 
5. Test the project by pressing the green flag.
6. **Before sharing,** make sure the `_VVPlayer Preloaded Frames?` var is set to `0`. Otherwise preloading will not work.
### Uploading a compiled project
> NOTE: Scratch's backend can sometimes create a "phantom project" which **you cannot delete** if you file is abnormally large (+1gb). 

> COMPATIBILITY NOTE: The compiler does not check if the project is uploadable. There may be times where the compiler creates a project that cannot be uploaded to Scratch. See `Limitations` for more information.

1. Upload your compiled project via the `Load project from computer` option under `file`.
> NOTE: Your browser might freeze here. That is normal. It should unfreeze within a minute. If not, close your browser and try again with a smaller file.
2. Wait for the project to load.
> NOTE: This can take a while, and sometimes your project may fail to save. Don't panic! just try saving a few more times, and it *should* go through.
4. Save the project by clicking `Save Now`
5. Test the project by pressing the green flag.
6. **Before sharing,** make sure the `_VVPlayer Preloaded Frames?` var is set to `0`. Otherwise preloading will not work.
## System Requirements
The compiler requires:
- A system with a multi-core CPU (basically anything past the late 2000's). The faster your CPU is, the faster the compiler goes.
- At least 4 GB of RAM
- At least 1 GB of free space (to hold exports).
## Limitations
Of course with anything, it has limitations:
- ~30,000 Frames is the maximum due to a text file size limit (~1.5mb) on Scratch's backend.
- While you can go higher than 480p@30, there is no gain in doing this as the player cannot show detail higher than that.
- The player used to use .SVG files (hence the name" Vector video) however, it now uses .JPG files due to RAM usage.
- Due to using .JPG files instead of a custom renderer like most long form videos players on Scratch do, RAM usage is a major concern.
- **Again, RAM is your biggest enemy so pay attention to it! you may crash your, or someone elses' system!**
- Scratch cannot seek audio files, so we have to work around it using audio chunks.
- Vector Video is intended for videos ranging from a few minutes to 2 hours. Anything longer, you may run into issues.
## Help Me!
You can always make an issue on this repo, or find me on Discord in the [Scratch Community Discord server](https://discord.gg/y4UnjXHAjV)!

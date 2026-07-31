import argparse
import os
import shutil
import platform
import subprocess
import logging
import concurrent.futures
import math
import time
from libs.audio import extract_audio, get_video_duration
from libs.video import extract_frames, get_video_dimensions
from libs.image import compile_packed_frames
from libs.analysis import analyze_frames
from libs.packer import pack_frames
from libs.autopacker import compile_sb3

logger = logging.getLogger(__name__)

def get_dir_size(path):
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total += os.path.getsize(fp)
    return total

def clean_dir(d):
    if os.path.exists(d):
        shutil.rmtree(d)

def get_optimal_width(base_width_str, video_path, stretch, atlas_w=960, atlas_h=720):
    """
    Calculates the mathematically optimal video width to maximize the use of the 
    image atlas space and minimize wasted alignment padding. 
    
    Triggered when the user appends an asterisk to the width (e.g. `240*`). 
    It iterates over a range (+/- 25%) around the requested width, predicting 
    the sub-pixel padding for each possible width, and returns the one that 
    fits the most "real" video pixels on the atlas.
    """
    base_width_str = str(base_width_str)
    optimize = base_width_str.endswith('*')
    base_w = int(base_width_str.replace('*', ''))
    base_w = min(base_w, 1280)
    
    if not optimize:
        return base_w
        
    orig_w, orig_h = get_video_dimensions(video_path)
    if not orig_w:
        return base_w
        
    def get_grid(w):
        if stretch:
            h = max(1, int(w * 0.75))
        else:
            h = max(1, int((w / float(orig_w)) * orig_h))
            
        aspect = w / float(h)
        if aspect >= (480.0 / 360.0):
            S = 960.0 / w
        else:
            S = 720.0 / h
            
        scratch_size = int(round(S * 10)) * 10
        if scratch_size == 0:
            return 0, 0, 0, 0
            
        S_actual_10 = scratch_size // 10
        D_w = 20 // math.gcd(20, S_actual_10)
        
        rem_w = (w + 2) % D_w
        P_w = 2 + (D_w - rem_w if rem_w != 0 else 0)
        
        rem_h = (h + 2) % D_w
        P_h = 2 + (D_w - rem_h if rem_h != 0 else 0)
        
        space_w = w + P_w
        space_h = h + P_h
        
        return atlas_w // space_w, atlas_h // space_h, w, h

    best_w = base_w
    best_efficiency = 0
    
    # Search a range around base_w (+/- 25%) to find the highest packing efficiency.
    min_search = max(10, int(base_w * 0.75))
    max_search = min(atlas_w, int(base_w * 1.25))
    
    for w in range(min_search, max_search + 1):
        r, c, real_w, real_h = get_grid(w)
        if r == 0 or c == 0:
            continue
            
        # Calculate how many pixels of the atlas are actually used by REAL video pixels (excluding padding)
        efficiency = (r * real_w) * (c * real_h)
        
        # We prefer smaller widths (which are encountered first in the loop), 
        # so we only upgrade to a larger width if it is strictly better by >1%
        if efficiency > best_efficiency * 1.01:
            best_efficiency = efficiency
            best_w = w
            
    return best_w

def process_video(video_path, args):
    """
    The main compiler pipeline for processing a single video.
    
    Workflow:
    1. Extracts audio chunks and raw video frames in parallel.
    2. Analyzes frames for detail scaling and performs deduplication.
    3. Packs the frames into atlas coordinates using a zero-jitter alignment.
    4. Compiles and exports the final JPEG atlases and generates metadata.
    5. Optionally injects everything directly into an .sb3 Scratch project file.
    """
    start_time = time.time()
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    
    working_dir = os.path.abspath(".Working")
    
    export_dir = os.path.abspath(os.path.join("Export", video_name))
    export_audio_dir = os.path.join(export_dir, "Audio")
    export_compiled_dir = os.path.join(export_dir, "Compiled Frames")
    
    logger.info(f"Preparing environment for '{video_name}'...")
    clean_dir(working_dir)
    if not args.meta_only:
        clean_dir(export_dir)
    os.makedirs(working_dir, exist_ok=True)
    os.makedirs(export_audio_dir, exist_ok=True)
    os.makedirs(export_compiled_dir, exist_ok=True)
    
    logger.info("--- Step 1 & 2: Audio and Video Frame Extraction ---")
    
    volume_arg = args.loudness
    if args.maximize_volume:
        from libs.audio import get_max_volume
        logger.info("Detecting maximum volume to maximize and double loudness...")
        max_vol = get_max_volume(video_path)
        
        # Maximize to 0dB, then add an extra 6.02dB to double the amplitude loudness
        total_gain_db = (-max_vol if max_vol < 0 else 0) + 6.02
        volume_arg = f"{total_gain_db}dB"
        logger.info(f"Applying {total_gain_db:.2f}dB gain with an audio limiter to prevent peaking.")
            
    atlas_w = 1024 if args.compile else 960
    atlas_h = 1024 if args.compile else 720
    
    actual_width = get_optimal_width(args.width, video_path, args.stretch, atlas_w, atlas_h)
    if str(args.width).endswith('*') and actual_width != int(str(args.width)[:-1]):
        logger.info(f"Optimized frame width to {actual_width} to maximize atlas space.")
            
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        if args.meta_only:
            audio_future = executor.submit(lambda: math.ceil(get_video_duration(video_path) / 15.0))
        else:
            audio_future = executor.submit(extract_audio, video_path, export_audio_dir, bitrate=args.audio_bitrate, khz=args.audio_khz, threads=args.threads, volume=volume_arg, use_limiter=args.maximize_volume, mono=args.mono)
            
        frames_future = executor.submit(extract_frames, video_path, fps=args.fps, width=actual_width, stretch=args.stretch, threads=args.threads)
        
        audio_splits = audio_future.result()
        frame_list = frames_future.result()
    
    logger.info("--- Step 3: Analysis & Packing ---")
    
    if args.stretch:
        frame_h = int(actual_width * 0.75)
    else:
        orig_w, orig_h = get_video_dimensions(video_path)
        frame_h = int((actual_width / orig_w) * orig_h) if orig_w else int(actual_width * 0.75)
        
    analysis_results = analyze_frames(frame_list, base_w=actual_width, base_h=frame_h, max_w=atlas_w-2, max_h=atlas_h-2, detail_sensitivity=args.sensitivity, dedup_tolerance=args.dedup, threads=args.threads)
    packed_results, num_bins = pack_frames(analysis_results, max_atlas_w=atlas_w, max_atlas_h=atlas_h)
    
    if args.meta_only:
        logger.info("--- Step 4: Skipping Image Packaging (--meta-only) ---")
        img_meta = {
            "compiled_frames": num_bins,
            "virtual_frames": len(frame_list)
        }
    else:
        logger.info("--- Step 4: JPEG Image Packaging ---")
        img_meta = compile_packed_frames(frame_list, packed_results, export_compiled_dir, jpeg_quality=args.jpeg_quality, max_atlas_w=atlas_w, max_atlas_h=atlas_h, threads=args.threads, working_dir=working_dir)
    
    if img_meta:
        logger.info("--- Step 4.5: Metadata Generation ---")
        meta_path = os.path.join(export_dir, "meta.txt")
        with open(meta_path, "w", encoding="utf-8") as meta_f:
            meta_f.write(f"{img_meta['compiled_frames']}\n")
            meta_f.write(f"{img_meta['virtual_frames']}\n")
            meta_f.write(f"{args.fps}\n")
            meta_f.write(f"{actual_width}\n")
            meta_f.write(f"{frame_h}\n")
            meta_f.write(f"{audio_splits}\n")
            meta_f.write(f"{video_name}")
            
        frames_path = os.path.join(export_dir, "Frames.txt")
        with open(frames_path, "w", encoding="utf-8") as f:
            lines = []
            for r in packed_results:
                pack_w = r['pack_w']
                pack_h = r['pack_h']
                x = r['x']
                y = r['y']
                
                # S is the scale factor required to make the frame fit inside the 480x360 Scratch stage.
                aspect = pack_w / float(pack_h)
                if aspect >= (480.0 / 360.0):
                    # Constrained by width
                    S = 960.0 / pack_w
                else:
                    # Constrained by height
                    S = 720.0 / pack_h
                
                # Quantize scratch_size to multiples of 10 to limit required padding
                scratch_size = int(round(S * 10)) * 10
                S_actual = scratch_size / 100.0
                
                # Center of the frame relative to the center of the costume (atlas)
                # Since the Scratch costume's rotation center is exactly the middle of the atlas (e.g. 512,512), 
                # we calculate how far off-center the packed frame's center is.
                cx_rel = (x + pack_w / 2.0) / 2.0 - (atlas_w / 4.0)
                cy_rel = (atlas_h / 4.0) - (y + pack_h / 2.0) / 2.0
                
                # To bring the frame's center to the stage origin (0,0), we must command Scratch 
                # to move the sprite in the exact opposite direction of its off-center offset, 
                # scaled up by the stage size multiplier.
                scratch_x = round(-cx_rel * S_actual)
                scratch_y = round(-cy_rel * S_actual)
                
                lines.append(f"{scratch_x}:{scratch_y}:{scratch_size}:{r['costume_id']}")
                
            f.write("\n".join(lines))
        logger.info(f"Metadata exported to {meta_path} and {frames_path}")
        
    logger.info("--- Step 5: Cleanup ---")
    clean_dir(working_dir)
    logger.info("Cleanup complete.")
    
    if args.compile:
        logger.info("--- Step 6: Autopacking SB3 ---")
        script_dir = os.path.dirname(os.path.abspath(__file__))
        sb3_files = [f for f in os.listdir(script_dir) if f.endswith('.sb3')]
        if not sb3_files:
            logger.error(f"No base .sb3 file found in '{script_dir}' for compilation. Skipping.")
        else:
            base_sb3 = os.path.join(script_dir, sb3_files[0])
            logger.info(f"Found base SB3: {base_sb3}")
            compile_sb3(base_sb3, export_dir, video_name, export_compiled_dir, export_audio_dir)
            
    elapsed = time.time() - start_time
    size_mb = get_dir_size(export_dir) / (1024 * 1024)
    v_frames = img_meta["virtual_frames"] if img_meta else len(frame_list)
    c_frames = img_meta["compiled_frames"] if img_meta else num_bins
    print(f"\n============= Conversion Stats =============")
    print(f"Time Taken: {elapsed:.2f} seconds")
    print(f"Resolution: {actual_width}x{frame_h} @ {args.fps} FPS")
    print(f"Audio Splits: {audio_splits}")
    print(f"Total Frames (Virtual): {v_frames}")
    print(f"Compiled Costumes: {c_frames}")
    print(f"Export Size: {size_mb:.2f} MB")
    print(f"============================================\n")
            
    return True

def estimate_video(video_path, args):
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    logger.info(f"--- Estimating values for '{video_name}' ---")
    
    try:
        duration = get_video_duration(video_path)
    except Exception:
        duration = 100
        logger.warning("Could not get duration, assuming 100s for estimation.")
        
    atlas_w = 1024 if args.compile else 960
    atlas_h = 1024 if args.compile else 720
        
    orig_w, orig_h = get_video_dimensions(video_path)
    actual_width = get_optimal_width(args.width, video_path, args.stretch, atlas_w, atlas_h)
    
    if args.stretch:
        frame_w = actual_width
        frame_h = int(actual_width * 0.75)
    else:
        frame_w = actual_width
        frame_h = int((actual_width / orig_w) * orig_h) if orig_w else int(actual_width * 0.75)
        
    # Take a few samples to estimate average scale
    import tempfile
    import cv2
    from libs.video import extract_sample_frames
    from libs.analysis import determine_scale
    
    avg_scale = 1.0
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            extract_sample_frames(video_path, temp_dir, duration, actual_width, args.stretch, count=5)
            scales = []
            for f in os.listdir(temp_dir):
                if f.endswith('.jpg'):
                    img = cv2.imread(os.path.join(temp_dir, f))
                    if img is not None:
                        scales.append(determine_scale(img, args.sensitivity))
            if scales:
                avg_scale = sum(scales) / len(scales)
    except Exception as e:
        logger.warning(f"Could not sample frames for detail scaling estimation: {e}")
        
    est_w = max(1, int(actual_width * avg_scale))
    est_h = max(1, int(frame_h * avg_scale))
    
    space_w = est_w + 2
    space_h = est_h + 2
    frames_per_row = atlas_w // space_w
    frames_per_col = atlas_h // space_h
    frames_per_image = frames_per_row * frames_per_col
    
    frames = int(duration * args.fps)
    worst_case_costumes = math.ceil(frames / frames_per_image) if frames_per_image > 0 else 0
    audio_splits = math.ceil(duration / 60.0)
    
    # Scale frame sizes based on quality (default 50) and estimated resolution area
    q_scale = (max(1, args.jpeg_quality) / 50.0) * (avg_scale ** 2)
    
    # Calculate audio size based on bitrate (e.g. "64k" -> 64 kbps)
    try:
        kbps = int(''.join(filter(str.isdigit, args.audio_bitrate)))
    except ValueError:
        kbps = 64
    audio_kb_per_split = (kbps * 1000 * 60) / (8 * 1024) # ~468 KB for 64k
    
    best_mb = (5 * q_scale * frames + audio_kb_per_split * audio_splits) / 1024
    avg_mb = (14 * q_scale * frames + audio_kb_per_split * audio_splits) / 1024
    worst_mb = (35 * q_scale * frames + audio_kb_per_split * audio_splits) / 1024
    stretch_text = " (Stretched)" if args.stretch else ""
    ram_mb = worst_case_costumes * 4
    
    print(f"""=============
Specs:
- Name: {video_name}
- Resolution (Original): {actual_width}x{frame_h}{stretch_text}
- Resolution (Scaled): ~{est_w}x{est_h} (Avg scale: {avg_scale:.2f}x)
- Framerate: {args.fps} FPS
- Quality: {args.jpeg_quality}% JPEG
- Audio: {args.audio_bitrate} @ {args.audio_khz} Hz
- Frames: {frames}
- Costumes ~{worst_case_costumes}
- Audio splits: {audio_splits}
Estimated disk space
- Best case: {best_mb:.2f} MB
- Average: {avg_mb:.2f} MB
- Worst case: {worst_mb:.2f} MB
Estimated RAM usage
- {ram_mb} MB (During playback)
=============
Tips:
- Aim for a final disk size of <200MB. 1000MB (1GB) should be your absolute maximum.
- Keep RAM usage under ~2000 MB to prevent crashes on low-end devices.
- 240 and 360 for widths often look good and aren't too big.
- 10 - 20 FPS are good for most animations.
- Lowering the FPS will save you the most space in general.
=============""")
    return True

def main():
    parser = argparse.ArgumentParser(
        description="Vector Video (VV) Compiler (Does not come with Squat Fitzgerald Bonobo the III).",
        epilog="""
Examples:
  Standard compile (15 FPS, width 240, 64k audio):
    python3 main.py video.mp4

  Compile with optimized atlas space and max volume:
    python3 main.py video.mp4 -w 240* -m

  Compile and automatically pack into .sb3 (requires base .sb3 in root folder):
    python3 main.py video.mp4 -c

  Update only the metadata/coordinates without re-encoding media:
    python3 main.py video.mp4 -o
    
  Compile an already exported directory into an .sb3:
    python3 main.py Export/video -c

Developed by Anonymous_cat1 and Google Antigravity.
""",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("video", help="Path to input video file or folder containing videos. Supported formats: .mp4, .avi, .mkv, .mov, .wmv, .flv, .webm, .m4v")
    parser.add_argument("-f", "--fps", type=int, default=15, metavar="", help="Target FPS (default: 15)")
    parser.add_argument("-w", "--width", type=str, default="240", metavar="", help="Target frame width. Append '*' to the closest resolution that utilizes most of the available atlas space. (default: 240)")
    parser.add_argument("-s", "--stretch", action="store_true", help="Stretch video to 4:3 aspect ratio")
    parser.add_argument("-q", "--jpeg-quality", type=int, default=90, metavar="", help="JPEG compression quality %% 1-100 (default: 90)")
    parser.add_argument("-b", "--audio-bitrate", type=str, default="64k", metavar="", help="Audio Bitrate (default: 64k)")
    parser.add_argument("-k", "--audio-khz", type=str, default="22050", metavar="", help="Audio sample rate in Hz (default: 22050)")
    parser.add_argument("-t", "--threads", type=int, default=max(1, int((os.cpu_count() or 4) * 0.75)), metavar="", help="Number of threads for parallel processing. (default: 75%% of CPU cores)")
    parser.add_argument("-l", "--loudness", type=float, default=1.0, metavar="", help="Volume multiplier for audio extraction (default: 1.0)")
    parser.add_argument("-M", "--maximize-volume", action="store_true", help="Maximize audio volume to 0dB without clipping (peak normalization)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("-e", "--estimator", action="store_true", help="Estimate disk space, RAM usage, and project specs without converting")
    parser.add_argument("-n", "--no-open", action="store_true", help="Do not automatically open the export folder when finished")
    parser.add_argument("-S", "--sensitivity", type=float, default=1.0, metavar="", help="Detail sensitivity for dynamic sizing. Lower values shrink more aggressively, higher values preserve more detail (default: 1.0)")
    parser.add_argument("-d", "--dedup", type=float, default=2.0, metavar="", help="Deduplication tolerance. Higher values merge more similar frames (saves space), lower values keep more unique frames (smoother motion) (default: 2.0)")
    parser.add_argument("-m", "--mono", action="store_true", help="Downmix audio to mono")
    parser.add_argument("-o", "--meta-only", action="store_true", help="Only generate metadata files (skip image and audio export) for speed")
    parser.add_argument("-c", "--compile", action="store_true", help="Automatically compile output into a Scratch project using the first .sb3 file found in the script directory.")
    
    args = parser.parse_args()
    
    log_level = logging.INFO if args.verbose else logging.WARNING
    logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    
    input_path = os.path.abspath(args.video)
    if not os.path.exists(input_path):
        logger.error(f"Input path '{input_path}' not found.")
        return

    if os.path.isdir(input_path):
        if args.compile and os.path.exists(os.path.join(input_path, "meta.txt")) and os.path.exists(os.path.join(input_path, "Frames.txt")):
            logger.info(f"Detected existing export directory: '{input_path}'. Running compiler only...")
            script_dir = os.path.dirname(os.path.abspath(__file__))
            sb3_files = [f for f in os.listdir(script_dir) if f.endswith('.sb3')]
            if not sb3_files:
                logger.error(f"No base .sb3 file found in '{script_dir}' for compilation.")
                return
            base_sb3 = os.path.join(script_dir, sb3_files[0])
            logger.info(f"Found base SB3: {base_sb3}")
            
            video_name = os.path.basename(input_path)
            export_compiled_dir = os.path.join(input_path, "Compiled Frames")
            export_audio_dir = os.path.join(input_path, "Audio")
            
            compile_sb3(base_sb3, input_path, video_name, export_compiled_dir, export_audio_dir)
            
            if not args.no_open and platform.system() == "Windows":
                os.startfile(input_path)
            elif not args.no_open and platform.system() == "Darwin":
                subprocess.Popen(["open", input_path])
            elif not args.no_open:
                subprocess.Popen(["xdg-open", input_path])
            return

        supported_exts = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
        video_files = sorted([
            os.path.join(input_path, f) for f in os.listdir(input_path) 
            if os.path.isfile(os.path.join(input_path, f)) and os.path.splitext(f)[1].lower() in supported_exts
        ])
        
        if not video_files:
            logger.error(f"No supported video files found in directory '{input_path}'.")
            return
            
        logger.info(f"Found {len(video_files)} video files for batch processing.")
        
        for idx, v_path in enumerate(video_files, 1):
            logger.info(f"\n========================================================")
            logger.info(f"--- Processing Video {idx}/{len(video_files)}: {os.path.basename(v_path)} ---")
            logger.info(f"========================================================")
            if args.estimator:
                estimate_video(v_path, args)
            else:
                process_video(v_path, args)
            
        export_root = os.path.abspath("Export")
        try:
            if not args.estimator and not args.no_open:
                if platform.system() == "Windows":
                    os.startfile(export_root)
                elif platform.system() == "Darwin":
                    subprocess.run(["open", export_root], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    subprocess.run(["xdg-open", export_root], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            logger.warning(f"Could not automatically open export directory: {e}")
            
        if args.estimator:
            logger.info("Batch estimation finished successfully.")
        else:
            logger.info("Batch compilation finished successfully.")
    else:
        if args.estimator:
            success = estimate_video(input_path, args)
        else:
            success = process_video(input_path, args)
        if success and not args.estimator:
            video_name = os.path.splitext(os.path.basename(input_path))[0]
            export_dir = os.path.abspath(os.path.join("Export", video_name))
            try:
                # Open directory using OS functionality
                if not args.no_open:
                    if platform.system() == "Windows":
                        os.startfile(export_dir)
                    elif platform.system() == "Darwin":
                        subprocess.run(["open", export_dir], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        subprocess.run(["xdg-open", export_dir], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                logger.warning(f"Could not automatically open export directory: {e}")

            logger.info(f"Target '{video_name}' compilation finished successfully. Exports stored at: {export_dir}")

if __name__ == "__main__":
    main()

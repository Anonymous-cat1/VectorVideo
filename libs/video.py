import os
import subprocess
import logging
import re
import shutil
import math
import concurrent.futures
from tqdm import tqdm
from libs.audio import get_video_duration

logger = logging.getLogger(__name__)

def get_video_dimensions(video_path):
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-show_entries',
            'stream=width,height', '-of',
            'csv=p=0:s=x', video_path
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        output = result.stdout.decode('utf-8').strip().split('\n')[0]
        w, h = map(int, output.split('x'))
        return w, h
    except Exception as e:
        logger.warning(f"Could not get video dimensions: {e}. Defaulting to 1920x1080.")
        return 1920, 1080

def extract_sample_frames(video_path, out_dir, duration, width, stretch, count=3):
    os.makedirs(out_dir, exist_ok=True)
    
    actual_width = min(int(width), 1280)
    if stretch:
        scale_param = f"scale={actual_width}:{int(actual_width * 0.75)}"
    else:
        scale_param = f"scale={actual_width}:-1"
        
    from tqdm import tqdm
    for i in tqdm(range(count), desc="Extracting Samples"):
        percent = 0.1 + (0.8 * (i / max(1, count - 1))) if count > 1 else 0.5
        t = duration * percent
        out_file = os.path.join(out_dir, f"sample_{i+1}.jpg")
        
        subprocess.run([
            'ffmpeg', '-y', '-v', 'error',
            '-ss', str(t),
            '-i', video_path,
            '-frames:v', '1',
            '-vf', scale_param,
            '-q:v', '2',
            out_file
        ], stdin=subprocess.DEVNULL)

def extract_frames(video_path, fps=15, width=240, stretch=False, threads=4):
    actual_width = min(int(width), 1280)
    
    if actual_width != int(width):
        logger.warning(f"Requested width {width} exceeds 720p maximums. Capping at {actual_width}.")
        
    logger.info(f"Extracting frames directly to memory at {fps} FPS, width {actual_width}...")
    
    if stretch:
        scale_param = f"scale={actual_width}:{int(actual_width * 0.75)}"
    else:
        scale_param = f"scale={actual_width}:-1"
        
    try:
        duration = get_video_duration(video_path)
    except Exception:
        duration = 100
        
    expected_frames = int(duration * fps)
    
    command = [
        'ffmpeg', '-y', '-v', 'error',
        '-i', video_path,
        '-vf', f'{scale_param},fps={fps}',
        '-q:v', '2',
        '-f', 'image2pipe',
        '-vcodec', 'mjpeg',
        '-'
    ]
    
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    
    frames = []
    buffer = bytearray()
    
    with tqdm(total=expected_frames, desc="Extracting Frames (Memory)") as pbar:
        while True:
            chunk = process.stdout.read(65536)
            if not chunk:
                break
            buffer.extend(chunk)
            
            while True:
                next_start = buffer.find(b'\xff\xd8', 2)
                if next_start != -1:
                    frames.append(bytes(buffer[:next_start]))
                    del buffer[:next_start]
                    pbar.update(1)
                else:
                    break
                    
        if len(buffer) > 0 and buffer.startswith(b'\xff\xd8'):
            frames.append(bytes(buffer))
            pbar.update(1)
            
    process.wait()
    logger.info(f"Video frame extraction complete. ({len(frames)} frames in memory)")
    return frames

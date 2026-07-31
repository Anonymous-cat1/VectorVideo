import os
import subprocess
import math
import logging
from tqdm import tqdm
import concurrent.futures

logger = logging.getLogger(__name__)

def get_video_duration(video_path):
    """
    Uses ffprobe to quickly extract the total duration of the video in seconds.
    This avoids having to decode the entire video just to find out how long it is.
    """
    result = subprocess.run([
        'ffprobe', '-v', 'error', '-show_entries',
        'format=duration', '-of',
        'default=noprint_wrappers=1:nokey=1', video_path
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    return float(result.stdout)

def get_max_volume(video_path):
    import re
    result = subprocess.run([
        'ffmpeg', '-i', video_path, '-af', 'volumedetect',
        '-vn', '-sn', '-dn', '-f', 'null', '/dev/null'
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    output = result.stdout.decode('utf-8', errors='ignore')
    match = re.search(r'max_volume:\s+([\-\d\.]+)\s+dB', output)
    if match:
        return float(match.group(1))
    return 0.0

def extract_sample_audio(video_path, out_dir, duration, bitrate, khz, volume, use_limiter=False, mono=False, length=5):
    os.makedirs(out_dir, exist_ok=True)
    t = max(0, (duration - length) / 2)
    out_file = os.path.join(out_dir, "sample_audio.mp3")
    
    cmd = [
        'ffmpeg', '-y', '-v', 'error',
        '-ss', str(t),
        '-t', str(length),
        '-i', video_path,
        '-b:a', str(bitrate),
        '-ar', str(khz),
        '-map', '0:a?'
    ]
    filters = []
    if volume != 1.0 and volume != '1.0' and volume != '1.0dB':
        filters.append(f'volume={volume}')
    if use_limiter:
        filters.append('alimiter=limit=-0.1dB')
        
    if filters:
        cmd.extend(['-filter:a', ','.join(filters)])
        
    if mono:
        cmd.extend(['-ac', '1'])
        
    cmd.append(out_file)
    subprocess.run(cmd, stdin=subprocess.DEVNULL)

def extract_audio_chunk(video_path, start_time, out_file, bitrate, khz, volume, use_limiter=False, mono=False):
    logger.debug(f"Extracting {out_file} (Start: {start_time}s)")
    cmd = [
        'ffmpeg', '-y', '-v', 'error',
        '-ss', str(start_time),
        '-t', '15',
        '-i', video_path,
        '-b:a', str(bitrate),
        '-ar', str(khz),
        '-map', '0:a?'
    ]
    filters = []
    if volume != 1.0 and volume != '1.0' and volume != '1.0dB':
        filters.append(f'volume={volume}')
    if use_limiter:
        filters.append('alimiter=limit=-0.1dB')
        
    if filters:
        cmd.extend(['-filter:a', ','.join(filters)])
        
    if mono:
        cmd.extend(['-ac', '1'])
        
    cmd.append(out_file)
    subprocess.run(cmd, stdin=subprocess.DEVNULL)

def extract_audio(video_path, export_audio_dir, bitrate="64k", khz="22050", threads=4, volume=1.0, use_limiter=False, mono=False):
    """
    Extracts the entire audio track from the video and chunks it into 15-second MP3 files.
    
    Why 15 seconds? Scratch has a hard limit of 10MB per asset. Long audio files 
    can exceed this limit or cause the Scratch VM to run out of memory. 
    By chunking the audio into small pieces, the Vector Video client can 
    dynamically load and unload them on the fly.
    """
    duration = get_video_duration(video_path)
    splits_needed = math.ceil(duration / 15.0)
    
    logger.info(f"Video duration is {duration:.2f}s. Extracting {splits_needed} audio clip(s)...")

    cmd = [
        'ffmpeg', '-y',
        '-i', video_path,
        '-b:a', str(bitrate),
        '-ar', str(khz),
        '-map', '0:a?'
    ]
    filters = []
    if volume != 1.0 and volume != '1.0' and volume != '1.0dB':
        filters.append(f'volume={volume}')
    if use_limiter:
        filters.append('alimiter=limit=-0.1dB')
        
    if filters:
        cmd.extend(['-filter:a', ','.join(filters)])
        
    if mono:
        cmd.extend(['-ac', '1'])
        
    out_pattern = os.path.join(export_audio_dir, "audio%d.mp3")
    cmd.extend([
        '-f', 'segment',
        '-segment_time', '15',
        '-segment_start_number', '1',
        out_pattern
    ])
    
    import re
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, universal_newlines=True)
    
    with tqdm(total=duration, desc="Extracting Audio chunks", leave=True) as pbar:
        last_time = 0
        for line in process.stderr:
            match = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", line)
            if match:
                h, m, s = match.groups()
                current_time = int(h) * 3600 + int(m) * 60 + float(s)
                if current_time > last_time:
                    pbar.update(current_time - last_time)
                    last_time = current_time
                    
    process.wait()
    
    logger.info("Audio extraction complete.")
    return splits_needed

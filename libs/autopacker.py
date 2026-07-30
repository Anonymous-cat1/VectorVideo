import os
import json
import zipfile
import shutil
import hashlib
import logging
from tqdm import tqdm

logger = logging.getLogger(__name__)

def md5_file(filepath):
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def compile_sb3(base_sb3, export_dir, video_name, compiled_frames_dir, audio_dir):
    logger.info(f"Autopacking into {video_name}.sb3 using base {base_sb3}...")
    
    temp_dir = os.path.join(export_dir, ".temp_sb3")
    os.makedirs(temp_dir, exist_ok=True)
    
    # 1. Extract base sb3
    with zipfile.ZipFile(base_sb3, 'r') as zip_ref:
        zip_ref.extractall(temp_dir)
        
    project_json_path = os.path.join(temp_dir, "project.json")
    with open(project_json_path, 'r', encoding='utf-8') as f:
        project = json.load(f)
        
    # Find targets
    stage = next((t for t in project["targets"] if t["isStage"]), None)
    player = next((t for t in project["targets"] if t["name"] == "VVPlayer"), None)
    
    if not stage or not player:
        logger.error("Could not find Stage or VVPlayer in base SB3.")
        return False
        
    # 2. Inject Data
    meta_path = os.path.join(export_dir, "meta.txt")
    if os.path.exists(meta_path):
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta_data = f.read().splitlines()
        # Find _metafile list in player
        for lst_id, lst_data in player.get("lists", {}).items():
            if lst_data[0] == "_metafile":
                lst_data[1] = meta_data
                break
                
    frames_path = os.path.join(export_dir, "Frames.txt")
    if os.path.exists(frames_path):
        with open(frames_path, 'r', encoding='utf-8') as f:
            frame_data = f.read().splitlines()
        # Find _framedata list in stage
        for lst_id, lst_data in stage.get("lists", {}).items():
            if lst_data[0] == "_framedata":
                lst_data[1] = frame_data
                break
                
    # Set preloaded var to 0
    for var_id, var_data in stage.get("variables", {}).items():
        if var_data[0] == "_VVPlayer Preloaded Frames?":
            var_data[1] = 0
            
    # 3. Import Frames
    # Get all frames across all frame blocks
    all_frames = []
    if os.path.exists(compiled_frames_dir):
        for root, dirs, files in os.walk(compiled_frames_dir):
            for file in files:
                if file.endswith('.jpg'):
                    all_frames.append(os.path.join(root, file))
                    
    # Sort frames numerically by costume ID
    import re
    all_frames.sort(key=lambda f: int(re.search(r'\d+', os.path.basename(f)).group()))
    
    for frame_path in tqdm(all_frames, desc="Importing Frames"):
        md5 = md5_file(frame_path)
        ext = ".jpg"
        new_filename = f"{md5}{ext}"
        shutil.copy2(frame_path, os.path.join(temp_dir, new_filename))
        
        # Determine name (e.g., compiledframe1)
        name = os.path.splitext(os.path.basename(frame_path))[0]
        
        costume = {
            "name": name,
            "bitmapResolution": 2,
            "dataFormat": "jpg",
            "assetId": md5,
            "md5ext": new_filename,
            "rotationCenterX": 512,
            "rotationCenterY": 512
        }
        player.setdefault("costumes", []).append(costume)
        
    # 4. Import Audio
    if os.path.exists(audio_dir):
        audio_files = sorted([f for f in os.listdir(audio_dir) if f.endswith('.wav')])
        # Sort numerically
        audio_files.sort(key=lambda f: int(re.search(r'\d+', f).group()) if re.search(r'\d+', f) else 0)
        
        for audio_file in tqdm(audio_files, desc="Importing Audio"):
            audio_path = os.path.join(audio_dir, audio_file)
            md5 = md5_file(audio_path)
            ext = ".wav"
            new_filename = f"{md5}{ext}"
            shutil.copy2(audio_path, os.path.join(temp_dir, new_filename))
            
            name = os.path.splitext(audio_file)[0]
            
            sound = {
                "name": name,
                "assetId": md5,
                "dataFormat": "wav",
                "format": "",
                "rate": 22050,
                "sampleCount": 0,
                "md5ext": new_filename
            }
            player.setdefault("sounds", []).append(sound)
            
    # 5. Save and Zip
    with open(project_json_path, 'w', encoding='utf-8') as f:
        json.dump(project, f, separators=(',', ':'))
        
    final_sb3_path = os.path.join(export_dir, f"{video_name}.sb3")
    
    # Create zip file manually to avoid top-level folder
    all_files_to_zip = []
    for root, _, files in os.walk(temp_dir):
        for file in files:
            all_files_to_zip.append(os.path.join(root, file))
            
    with zipfile.ZipFile(final_sb3_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in tqdm(all_files_to_zip, desc="Zipping SB3"):
            arcname = os.path.relpath(file_path, temp_dir)
            zipf.write(file_path, arcname)
                
    shutil.rmtree(temp_dir)
    logger.info(f"SB3 successfully compiled to {final_sb3_path}!")
    return True


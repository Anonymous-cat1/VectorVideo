import cv2
import numpy as np
import logging
import concurrent.futures
from tqdm import tqdm

logger = logging.getLogger(__name__)

def dhash(image, hash_size=16):
    """
    Computes a Difference Hash (dHash) for an image.
    dHash works by resizing the image to a small grid and comparing adjacent pixels.
    This generates a tiny 64-bit integer signature that is extremely fast to compare 
    and robust against minor compression artifacts.
    """
    resized = cv2.resize(image, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    if len(resized.shape) == 3:
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    else:
        gray = resized
        
    diff = gray[:, 1:] > gray[:, :-1]
    
    h = 0
    for i, b in enumerate(diff.flatten()):
        if b:
            h |= (1 << i)
    return h

def determine_scale(img, img_prev, detail_sensitivity):
    """
    Dynamically determines the ideal resolution scaling factor for a specific frame.
    
    It analyzes the frame for extreme sharpness (focal points) and motion.
    High-motion scenes are naturally blurry, so scaling them down saves massive amounts 
    of atlas space without the user noticing. Static, highly detailed scenes are 
    preserved at near 100% resolution to maintain crisp visuals.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 1. Focal Point Detail
    # Using the 98th percentile of Laplacian magnitude entirely ignores flat backgrounds 
    # (like large solid-color skies) and strictly measures the sharpest objects/focal points.
    lap_abs = np.abs(cv2.Laplacian(gray, cv2.CV_64F))
    focal_sharpness = np.percentile(lap_abs, 98)
    
    # 2. Motion Dependency
    motion = 0
    if img_prev is not None:
        gray_prev = cv2.cvtColor(img_prev, cv2.COLOR_BGR2GRAY)
        motion = np.mean(cv2.absdiff(gray, gray_prev))
        
    # Heuristic: 
    # High focal_sharpness -> higher scale (preserve detailed focal points)
    # High motion -> lower scale (fast motion is naturally blurry, saves space)
    # If little detail (flat colors), focal_sharpness is near 0 -> heavily scales down.
    
    # We use a tapered curve to detect scene cuts:
    # Mean pixel differences > 30 are typically scene changes, not just fast motion.
    # We rapidly taper off the motion penalty for these so new scenes are crisp.
    if motion > 30:
        motion_penalty = max(0, 30 - (motion - 30) * 1.5) * 0.75
    else:
        motion_penalty = motion * 0.75
        
    score = (focal_sharpness * 2.5) - motion_penalty
    
    # Base buffer ensures flat scenes without motion don't drop to absolute zero instantly.
    target_scale = ((max(0, score) + 15) * detail_sensitivity) / 100.0
    
    # Quantize to increments of 0.05 to eliminate micro-jitter and stabilize aspect ratios
    target_scale = round(target_scale * 20) / 20.0
    
    return max(0.15, min(1.0, target_scale))

def process_frame_for_analysis(args):
    idx, frame_data, prev_frame_data, base_w, base_h, max_w, max_h, detail_sensitivity = args
    nparr = np.frombuffer(frame_data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return idx, None, base_w, base_h
        
    img_prev = None
    if prev_frame_data != frame_data:
        nparr_prev = np.frombuffer(prev_frame_data, np.uint8)
        img_prev = cv2.imdecode(nparr_prev, cv2.IMREAD_COLOR)
        
    scale = determine_scale(img, img_prev, detail_sensitivity)
    target_w = max(1, int(base_w * scale))
    target_h = max(1, int(base_h * scale))
    
    if target_w > max_w or target_h > max_h:
        scale_w = max_w / target_w
        scale_h = max_h / target_h
        min_scale = min(scale_w, scale_h)
        target_w = max(1, int(target_w * min_scale))
        target_h = max(1, int(target_h * min_scale))
    
    # Create dHash for fast global dedup
    h = dhash(img)
    
    return idx, h, target_w, target_h

def analyze_frames(frame_list, base_w, base_h, max_w, max_h, detail_sensitivity=1.0, dedup_tolerance=2.0, threads=4):
    """
    Iterates over all extracted video frames in parallel to:
    1. Determine the optimal downscaled resolution (detail scaling).
    2. Generate perceptual hashes (dHash) for every frame.
    3. Identify consecutive duplicate frames and flag them to be skipped during packing.
       (Skipping duplicates dramatically reduces atlas size and RAM usage during static scenes).
    """
    logger.info("Analyzing frames for detail scaling and deduplication...")
    
    results = [None] * len(frame_list)
    hashes = [None] * len(frame_list)
    
    tasks = []
    for i, data in enumerate(frame_list):
        prev_data = frame_list[i - 1] if i > 0 else data
        tasks.append((i, data, prev_data, base_w, base_h, max_w, max_h, detail_sensitivity))
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, threads)) as executor:
        for res in tqdm(executor.map(process_frame_for_analysis, tasks), total=len(tasks), desc="Analyzing Frames"):
            idx, h, tw, th = res
            hashes[idx] = h
            results[idx] = {
                "w": tw,
                "h": th,
                "duplicate_of": None,
                "is_duplicate": False,
                "index": idx
            }
    
    unique_hashes = [] # list of (hash_int, frame_idx)
    duplicates_found = 0
    
    for i in tqdm(range(len(frame_list)), desc="Global Deduplication"):
        if results[i] is None:
            continue
            
        h = hashes[i]
        if h is None:
            continue
            
        is_dup = False
        duplicate_ref = -1
        
        # Local deduplication: check against the LAST unique frame only to prevent false positives
        for uh, uidx in unique_hashes[-1:]:
            dist = (h ^ uh).bit_count()
            if dist <= int(dedup_tolerance):
                is_dup = True
                duplicate_ref = uidx
                break
                
        if is_dup:
            results[i]["is_duplicate"] = True
            results[i]["duplicate_of"] = duplicate_ref
            results[i]["w"] = results[duplicate_ref]["w"]
            results[i]["h"] = results[duplicate_ref]["h"]
            duplicates_found += 1
        else:
            unique_hashes.append((h, i))
            
    logger.info(f"Analysis complete. Found {duplicates_found} duplicate frames out of {len(frame_list)}.")
    # Filter out None results
    return [r for r in results if r is not None]

from rectpack import newPacker, guillotine
import logging
import math

logger = logging.getLogger(__name__)

def pack_frames(analysis_results, max_atlas_w=960, max_atlas_h=720):
    logger.info("Packing frames into Image atlas(es)...")
    
    unique_frames = [r for r in analysis_results if not r["is_duplicate"]]
    
    chunk_size = 1000
    packed_results = {}
    global_bin_offset = 0
    
    analysis_dict = {f["index"]: f for f in analysis_results}
    
    for i in range(0, len(unique_frames), chunk_size):
        chunk = unique_frames[i:i+chunk_size]
        packer = newPacker(pack_algo=guillotine.GuillotineBssfMaxas, rotation=False)
        
        for frame in chunk:
            target_w = frame["w"]
            target_h = frame["h"]
            
            aspect = target_w / float(target_h)
            if aspect >= (480.0 / 360.0):
                S = 960.0 / target_w
            else:
                S = 720.0 / target_h
                
            scratch_size = int(round(S * 10)) * 10
            S_actual_10 = scratch_size // 10
            
            D_w = 20 // math.gcd(20, S_actual_10)
            
            rem_w = (target_w + 2) % D_w
            P_w = 2 + (D_w - rem_w if rem_w != 0 else 0)
            
            rem_h = (target_h + 2) % D_w
            P_h = 2 + (D_w - rem_h if rem_h != 0 else 0)
            
            w = min(target_w + P_w, max_atlas_w)
            h = min(target_h + P_h, max_atlas_h)
            
            packer.add_rect(w, h, rid=frame["index"])
            
        for _ in range(len(chunk)):
            packer.add_bin(max_atlas_w, max_atlas_h)
            
        logger.info(f"Packing chunk {i//chunk_size + 1}/{(len(unique_frames)-1)//chunk_size + 1}...")
        packer.pack()
        
        for rect in packer.rect_list():
            b, x, y, w, h, rid = rect
            img_y = max_atlas_h - (y + h)
            
            target_w = analysis_dict[rid]["w"]
            target_h = analysis_dict[rid]["h"]
            
            packed_results[rid] = {
                "costume_id": b + 1 + global_bin_offset,
                "x": x,
                "y": img_y,
                "pack_w": target_w,
                "pack_h": target_h
            }
            
        global_bin_offset += len(packer.bin_list())
        
    # Assign packed data to all frames
    for frame in analysis_results:
        idx = frame["index"]
        if frame["is_duplicate"]:
            ref_idx = frame["duplicate_of"]
            if ref_idx in packed_results:
                packed_results[idx] = packed_results[ref_idx].copy()
            else:
                logger.error(f"Duplicate frame {idx} refers to {ref_idx} which was not packed!")
                
    missing = [f["index"] for f in analysis_results if f["index"] not in packed_results]
    if missing:
        logger.error(f"Failed to pack {len(missing)} frames! This usually means frames are too large for the {max_atlas_w}x{max_atlas_h} atlas.")
        
    final_output = []
    for frame in analysis_results:
        idx = frame["index"]
        if idx in packed_results:
            frame.update(packed_results[idx])
            final_output.append(frame)
            
    num_bins = global_bin_offset
    logger.info(f"Packing complete. Used {num_bins} bins for {len(unique_frames)} unique frames.")
    
    return final_output, num_bins

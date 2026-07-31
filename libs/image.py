import os
import io
import logging
import shutil
import concurrent.futures
from PIL import Image
from tqdm import tqdm

logger = logging.getLogger(__name__)

MAX_FOLDER_SIZE = int(9.75 * 1024 * 1024) # 9.75MB limit

def get_folder_size(folder):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(folder):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    return total_size

def process_packed_image_bin(args):
    """
    Worker function to compile a single bin of frames into a JPEG and save to a temporary location.
    It takes the raw JPEG bytes from memory, resizes them if necessary (due to detail scaling), 
    and pastes them onto the black atlas background at the coordinates determined by the packer.
    """
    (costume_id, rects, frame_list, max_atlas_w, max_atlas_h, jpeg_quality, temp_dir) = args
    
    framebuffer = Image.new("RGB", (max_atlas_w, max_atlas_h), (0, 0, 0))
    for rect in rects:
        idx = rect["index"]
        frame_data = frame_list[idx]
        w = rect["pack_w"]
        h = rect["pack_h"]
        x = rect["x"]
        y = rect["y"]
        
        with Image.open(io.BytesIO(frame_data)) as f_img:
            if f_img.mode != "RGB":
                f_img = f_img.convert("RGB")
            if f_img.size != (w, h):
                f_img = f_img.resize((w, h), Image.Resampling.LANCZOS)
            framebuffer.paste(f_img, (x, y))
            
    temp_img_path = os.path.join(temp_dir, f"packedframe_{costume_id}.jpg")
    framebuffer.save(temp_img_path, format="JPEG", quality=jpeg_quality)
        
    return costume_id, temp_img_path

def compile_packed_frames(frame_list, packed_results, export_compiled_dir, jpeg_quality=80, max_atlas_w=960, max_atlas_h=720, threads=4, working_dir=".Working"):
    """
    Takes the theoretical bin packing coordinates and physically renders the final 
    JPEG atlas images using the PIL (Pillow) library.
    
    After rendering, it sorts the atlases into "Frame Block" folders. 
    Scratch has a hard limit of 10MB per asset upload. To make manual importing easier, 
    the compiler groups the atlases into folders that are strictly under 9.75MB each.
    """
    if not frame_list:
        logger.warning("No frames found to compile.")
        return None

    logger.info(f"Packing into {max_atlas_w}x{max_atlas_h} image bins.")

    temp_img_dir = os.path.join(working_dir, "Unsorted_Images")
    os.makedirs(temp_img_dir, exist_ok=True)

    # Group by costume_id
    bins = {}
    for res in packed_results:
        if res["is_duplicate"]:
            continue
        cid = res["costume_id"]
        if cid not in bins:
            bins[cid] = []
        bins[cid].append(res)
        
    tasks = []
    for cid, rects in bins.items():
        tasks.append((cid, rects, frame_list, max_atlas_w, max_atlas_h, jpeg_quality, temp_img_dir))
        
    logger.info(f"Dispatching {len(tasks)} image compilation tasks to {threads} workers...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, threads)) as executor:
        results = list(tqdm(executor.map(process_packed_image_bin, tasks), total=len(tasks), desc="Compiling Image Grids"))
        
    compiled_imgs = sorted(results, key=lambda x: x[0])
    
    logger.info("Image compilation complete. Sorting into asset folders...")
    
    block_index = 1
    curr_block_dir = os.path.join(export_compiled_dir, f"Frame Block {block_index}")
    os.makedirs(curr_block_dir, exist_ok=True)
    curr_folder_size = get_folder_size(curr_block_dir)
    
    for costume_id, temp_path in tqdm(compiled_imgs, desc="Sorting Images"):
        img_size = os.path.getsize(temp_path)
        
        if curr_folder_size + img_size > MAX_FOLDER_SIZE:
            logger.info(f"Frame Block {block_index} near capacity. Creating Frame Block {block_index + 1}.")
            block_index += 1
            curr_block_dir = os.path.join(export_compiled_dir, f"Frame Block {block_index}")
            os.makedirs(curr_block_dir, exist_ok=True)
            curr_folder_size = 0
            
        final_img_path = os.path.join(curr_block_dir, f"compiledframe{costume_id}.jpg")
        shutil.move(temp_path, final_img_path)
        
        curr_folder_size += img_size
        
    shutil.rmtree(temp_img_dir, ignore_errors=True)
    logger.info("Image sorting complete.")
    
    return {
        "compiled_frames": len(compiled_imgs),
        "virtual_frames": len(frame_list),
        "max_atlas_w": max_atlas_w,
        "max_atlas_h": max_atlas_h
    }

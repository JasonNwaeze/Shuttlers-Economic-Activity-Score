import os
import csv
import glob
import pandas as pd
import h3

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))

INPUT_CSV = os.path.join(PROJECT_ROOT, "data", "shared_h3_input.csv")
BUILDINGS_DIR = os.path.join(PROJECT_ROOT, "data", "buildings")
OUTPUT_CSV = os.path.join(PROJECT_ROOT, "data", "output", "h3_building_features.csv")
CHUNK_SIZE = 50000
CONFIDENCE_THRESHOLD = 0.77
H3_RESOLUTION = 7

def find_buildings_csv():
    """Finds the first CSV file inside the buildings directory."""
    csv_files = glob.glob(os.path.join(BUILDINGS_DIR, "*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV file found in {BUILDINGS_DIR}")
    return csv_files[0]

def load_target_h3s():
    """Loads target H3 indices from the shared CSV (h3 column only)."""
    targets = set()
    if not os.path.exists(INPUT_CSV):
        raise FileNotFoundError(f"Shared input CSV not found at {INPUT_CSV}")
    
    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if "h3" in row and row["h3"].strip():
                targets.add(row["h3"].strip())
    return targets

def compute_bounding_box(h3_indices, padding=0.05):
    """Computes a bounding box encompassing all target H3 centroids with padding."""
    lats = []
    lngs = []
    for h3_index in h3_indices:
        lat, lng = h3.cell_to_latlng(h3_index)
        lats.append(lat)
        lngs.append(lng)
        
    if not lats:
        return None
        
    return {
        "min_lat": min(lats) - padding,
        "max_lat": max(lats) + padding,
        "min_lng": min(lngs) - padding,
        "max_lng": max(lngs) + padding
    }

def process_buildings():
    """Processes the Open Buildings dataset in chunks to compute features for target H3 cells."""
    print("Loading target H3 indices...")
    target_h3_set = load_target_h3s()
    
    if not target_h3_set:
        print("No target H3 indices found. Exiting.")
        return

    print("Computing bounding box for target H3 cells...")
    bbox = compute_bounding_box(target_h3_set)
    print(f"Bounding Box: Lat [{bbox['min_lat']:.4f}, {bbox['max_lat']:.4f}], Lng [{bbox['min_lng']:.4f}, {bbox['max_lng']:.4f}]")
    
    buildings_csv = find_buildings_csv()
    print(f"Found buildings dataset: {buildings_csv}")
    
    # Initialize running statistics
    stats = {
        h3_index: {
            "building_count": 0,
            "large_buildings": 0,
            "confidence_sum": 0.0,
        } for h3_index in target_h3_set
    }
    
    print(f"Processing in chunks of {CHUNK_SIZE}...")
    chunk_count = 0
    total_retained = 0
    
    for chunk in pd.read_csv(buildings_csv, chunksize=CHUNK_SIZE):
        chunk_count += 1
        
        # 1. Confidence Filter
        chunk = chunk[chunk["confidence"] >= CONFIDENCE_THRESHOLD]
        if chunk.empty:
            continue
            
        # 2. Bounding Box Filter
        chunk = chunk[
            (chunk["latitude"] >= bbox["min_lat"]) &
            (chunk["latitude"] <= bbox["max_lat"]) &
            (chunk["longitude"] >= bbox["min_lng"]) &
            (chunk["longitude"] <= bbox["max_lng"])
        ]
        if chunk.empty:
            continue
            
        # 3. Compute H3
        chunk["h3"] = chunk.apply(
            lambda row: h3.latlng_to_cell(row["latitude"], row["longitude"], H3_RESOLUTION),
            axis=1
        )
        
        # 4. Keep Only Target H3s
        chunk = chunk[chunk["h3"].isin(target_h3_set)]
        if chunk.empty:
            continue
            
        # 5. Update Running Statistics
        for h3_index, group in chunk.groupby("h3"):
            building_count = len(group)
            large_buildings = len(group[group["area_in_meters"] >= 300])
            confidence_sum = group["confidence"].sum()
            
            stats[h3_index]["building_count"] += building_count
            stats[h3_index]["large_buildings"] += large_buildings
            stats[h3_index]["confidence_sum"] += confidence_sum
            
            total_retained += building_count
            
        print(f"Processed chunk {chunk_count}. Cumulative target buildings found: {total_retained}", end="\r")
        
    print(f"\nProcessing complete. Total chunks processed: {chunk_count}")
    
    # Finalize and export results
    print(f"Exporting results to {OUTPUT_CSV}...")
    results = []
    for h3_index, data in stats.items():
        count = data["building_count"]
        large = data["large_buildings"]
        avg_confidence = data["confidence_sum"] / count if count > 0 else 0.0
        large_pct = (large / count * 100) if count > 0 else 0.0
        
        results.append({
            "h3": h3_index,
            "building_count": count,
            "large_buildings": large,
            "large_buildings_pct": round(large_pct, 2),
            "avg_building_confidence": round(avg_confidence, 4)
        })
        
    df_results = pd.DataFrame(results)
    df_results.to_csv(OUTPUT_CSV, index=False)
    print("Done!")

if __name__ == "__main__":
    process_buildings()

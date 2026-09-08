import os
import re
import csv
import pandas as pd
import h3
from collections import defaultdict
from openlocationcode import openlocationcode

from h3_utils import get_target_h3s

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "POIs")
CATEGORIES = ["restaurants", "hotels", "banks", "gas_stations"]


def clean_category_name(filename):
    """Extract category and search_h3 from filename like restaurants_8758822daffffff.csv."""
    if not filename.endswith(".csv"):
        return None, None
    base = filename[:-4]
    parts = base.rsplit("_", 1)
    if len(parts) != 2:
        return None, None
    cat_raw, h3_idx = parts[0], parts[1]
    cat_norm = cat_raw.replace(" ", "_")
    return cat_norm, h3_idx


def decode_poi_location(plus_code_raw, ref_lat=None, ref_lng=None):
    """Decodes a Plus Code into (latitude, longitude) center coordinates."""
    if not plus_code_raw or pd.isna(plus_code_raw) or str(plus_code_raw).lower() == 'nan':
        return None, None

    code_str = str(plus_code_raw).strip()
    # Remove text locality after comma if present (e.g., '6FR5MG69+CM, Ikorodu, Lagos')
    parts = code_str.replace(',', ' ').split()
    if not parts:
        return None, None

    pure_code = parts[0]
    if not openlocationcode.isValid(pure_code):
        return None, None

    try:
        if openlocationcode.isShort(pure_code):
            if ref_lat is None or ref_lng is None:
                return None, None
            full_code = openlocationcode.recoverNearest(pure_code, ref_lat, ref_lng)
            decoded = openlocationcode.decode(full_code)
        else:
            decoded = openlocationcode.decode(pure_code)

        return decoded.latitudeCenter, decoded.longitudeCenter
    except Exception:
        return None, None


def reindex_pois(resolution=7):
    """
    Reads all scraped POI CSVs, resolves every POI's true H3 cell from its coordinates,
    deduplicates search overlaps, and writes clean CSVs directly to their true H3 cells.
    Nothing is discarded.
    """
    if not os.path.exists(DATA_DIR):
        print(f"[Re-indexer] POI directory does not exist: {DATA_DIR}. Skipping.")
        return

    target_h3_set = set(get_target_h3s())
    all_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".csv")]
    if not all_files:
        print("[Re-indexer] No POI CSV files found to reindex. Skipping.")
        return

    print(f"\n[Re-indexer] Starting Spatial Re-indexing across {len(all_files)} CSV files (Resolution {resolution})...")

    # Master store: (category, true_h3) -> dict of deduplicated POIs (key -> poi_dict)
    reindexed = defaultdict(dict)
    total_pois_read = 0
    reallocated_count = 0

    for filename in all_files:
        cat_norm, search_h3 = clean_category_name(filename)
        if not cat_norm:
            continue

        ref_lat, ref_lng = None, None
        try:
            if h3.is_valid_cell(search_h3):
                ref_lat, ref_lng = h3.cell_to_latlng(search_h3)
        except Exception:
            pass

        filepath = os.path.join(DATA_DIR, filename)
        try:
            df = pd.read_csv(filepath, dtype=str)
        except (pd.errors.EmptyDataError, FileNotFoundError):
            continue

        for _, row in df.iterrows():
            total_pois_read += 1
            name = str(row.get("name", "")).strip()
            plus_code = str(row.get("plus_code", "")).strip() if pd.notna(row.get("plus_code")) else ""
            price_val = row.get("hotel_price")
            price_str = str(price_val).strip() if pd.notna(price_val) and str(price_val).lower() != 'nan' else ""

            # Attempt to decode true location
            lat, lng = decode_poi_location(plus_code, ref_lat, ref_lng)
            true_h3 = None
            if lat is not None and lng is not None:
                try:
                    true_h3 = h3.latlng_to_cell(lat, lng, resolution)
                except Exception:
                    true_h3 = None

            # Fallback: if coordinates can't be decoded, retain in search_h3
            if not true_h3:
                true_h3 = search_h3

            if true_h3 != search_h3:
                reallocated_count += 1

            # Unique key for deduplication within the true H3 cell
            dedup_key = plus_code if plus_code else name.lower()

            existing = reindexed[(cat_norm, true_h3)].get(dedup_key)
            if existing:
                # If existing has no price but current row has price, upgrade price
                if not existing.get("hotel_price") and price_str:
                    existing["hotel_price"] = price_str
            else:
                reindexed[(cat_norm, true_h3)][dedup_key] = {
                    "name": name,
                    "plus_code": plus_code,
                    "hotel_price": price_str
                }

    print(f"[Re-indexer] Ingested {total_pois_read} raw records.")
    print(f"[Re-indexer] Reallocated {reallocated_count} POIs into their true geographic H3 cells.")

    # Write out clean, partitioned CSV files
    written_cells = set()
    total_unique_pois = 0

    for (cat_norm, target_cell), pois_dict in reindexed.items():
        clean_records = list(pois_dict.values())
        total_unique_pois += len(clean_records)
        written_cells.add(target_cell)

        out_path = os.path.join(DATA_DIR, f"{cat_norm}_{target_cell}.csv")
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["name", "plus_code", "hotel_price"])
            writer.writeheader()
            writer.writerows(clean_records)

    print(f"[Re-indexer] Successfully saved {total_unique_pois} unique POIs across {len(written_cells)} H3 cells.")
    print(f"[Re-indexer] Spatial Re-indexing complete.\n")


if __name__ == "__main__":
    reindex_pois(resolution=7)

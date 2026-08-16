"""
SEAS Pipeline Orchestrator
==========================
Edit data/shared_h3_input.csv, then run:

    python3 main.py --resolution 7   # Default 2 workers, headless, resolution 7
    python3 main.py --workers 4      # 4 parallel scrapers
    python3 main.py --headed         # visible browser

Stages:
  1. Google Maps Scraper  -> data/POIs/<category>_<h3>.csv
  2. Feature Engineering  -> data/h3_features.csv
  3. Open Buildings       -> data/h3_building_features.csv
  4. NTL Extraction       -> data/h3_features.csv (updated)
  5. Population Extraction-> data/h3_population.csv
  6. SEAS Scoring         -> data/h3_seas_scores.csv
  7. Upload Formatter     -> upload/res{res}_economic.csv, upload/res{res}_population.csv
"""

import argparse
import sys
import os
import time
import pandas as pd
import h3

# Ensure src/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from h3_utils import get_target_h3s
from google_maps import run_scraper
from feature_engineering import process_pois
from open_buildings import process_buildings
from extract_ntl import main as extract_ntl
from extract_population import extract_population
from calculate_seas import calculate_seas
from download_data import ensure_data

def banner(step, title):
    print(f"\n{'='*60}")
    print(f"  STEP {step}: {title}")
    print(f"{'='*60}")

def format_upload(resolution):
    base_dir = os.path.dirname(__file__)
    upload_dir = os.path.join(base_dir, "upload")
    os.makedirs(upload_dir, exist_ok=True)
    
    # Format Economic
    seas_path = os.path.join(base_dir, "data", "output", "h3_seas_scores.csv")
    if os.path.exists(seas_path):
        df_seas = pd.read_csv(seas_path)
        df_econ = df_seas[['h3', 'SEAS']].rename(columns={'h3': 'h3_index', 'SEAS': 'score'})
        econ_out = os.path.join(upload_dir, f"res{resolution}_economic.csv")
        df_econ.to_csv(econ_out, index=False)
        print(f"[Upload Formatter] Created {econ_out}")
        
    # Format Population
    pop_path = os.path.join(base_dir, "data", "output", "h3_population.csv")
    if os.path.exists(pop_path):
        df_pop = pd.read_csv(pop_path)
        df_pop = df_pop.rename(columns={'h3': 'h3_index'})
        pop_out = os.path.join(upload_dir, f"res{resolution}_population.csv")
        df_pop.to_csv(pop_out, index=False)
        print(f"[Upload Formatter] Created {pop_out}")


def run_pipeline(workers=2, headless=True, resolution=7):
    start = time.time()
    
    # ── Verify Resolution ──────────────────────────────────────────
    target_h3s = get_target_h3s()
    if not target_h3s:
        print("No target H3 indices found in shared_h3_input.csv. Exiting.")
        sys.exit(1)
        
    for h in target_h3s:
        try:
            res = h3.get_resolution(h)
            if res != resolution:
                print(f"ERROR: H3 index {h} has resolution {res}, but pipeline is running for resolution {resolution}.")
                sys.exit(1)
        except Exception:
            print(f"ERROR: Invalid H3 index {h}.")
            sys.exit(1)

    # ── Step 0: Ensure large data files are present ──────────────
    banner(0, "Data Bootstrap (NTL + Buildings + Population)")
    ensure_data()

    # ── Step 1: Scrape POIs from Google Maps ────────────────────
    banner(1, "Google Maps Scraper")
    run_scraper(workers=workers, headless=headless)

    # ── Step 2: Aggregate POI features per H3 ───────────────────
    banner(2, "Feature Engineering (POIs → h3_features.csv)")
    process_pois()

    # ── Step 3: Process Open Buildings footprints ────────────────
    banner(3, "Open Buildings (footprints → h3_building_features.csv)")
    process_buildings()

    # ── Step 4: Extract Nighttime Lights from satellite data ─────
    banner(4, "Nighttime Lights Extraction (NTL → h3_features.csv)")
    extract_ntl()
    
    # ── Step 5: Extract Population data ──────────────────────────
    banner(5, "Population Extraction (→ h3_population.csv)")
    extract_population()

    # ── Step 6: Calculate SEAS scores ───────────────────────────
    banner(6, "SEAS Scoring (→ h3_seas_scores.csv)")
    calculate_seas()
    
    # ── Step 7: Format Output for Map Layers Server Upload ───────
    banner(7, f"Upload Formatter (→ upload/res{resolution}_*.csv)")
    format_upload(resolution)

    elapsed = time.time() - start
    print(f"\n{'='*60}")
    print(f"  ✅ Pipeline complete in {elapsed:.1f}s")
    print(f"  📄 Upload files ready in: upload/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SEAS Pipeline — edit shared_h3_input.csv then run this."
    )
    parser.add_argument(
        "--workers", type=int, default=2,
        help="Number of parallel Chrome workers for the scraper (default: 2)"
    )
    parser.add_argument(
        "--headed", action="store_true",
        help="Run the browser in visible (non-headless) mode"
    )
    parser.add_argument(
        "--resolution", type=int, choices=[7, 8], default=7,
        help="H3 resolution of the input data (default: 7)"
    )
    args = parser.parse_args()

    run_pipeline(workers=args.workers, headless=not args.headed, resolution=args.resolution)

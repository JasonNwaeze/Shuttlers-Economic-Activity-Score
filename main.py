"""
SEAS Pipeline Orchestrator
==========================
Edit data/shared_h3_input.csv, then run:

    python3 main.py                  # 2 workers, headless
    python3 main.py --workers 4      # 4 parallel scrapers
    python3 main.py --headed         # visible browser

Stages:
  1. Google Maps Scraper  -> data/POIs/<category>_<h3>.csv
  2. Feature Engineering  -> data/h3_features.csv
  3. Open Buildings       -> data/h3_building_features.csv
  4. NTL Extraction       -> data/h3_features.csv (updated)
  5. SEAS Scoring         -> data/h3_seas_scores.csv  ← final output
"""

import argparse
import sys
import os
import time

# Ensure src/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from google_maps import run_scraper
from feature_engineering import process_pois
from open_buildings import process_buildings
from extract_ntl import main as extract_ntl
from calculate_seas import calculate_seas
from download_data import ensure_data


def banner(step, title):
    print(f"\n{'='*60}")
    print(f"  STEP {step}: {title}")
    print(f"{'='*60}")


def run_pipeline(workers=2, headless=True):
    start = time.time()

    # ── Step 0: Ensure large data files are present ──────────────
    banner(0, "Data Bootstrap (NTL + Buildings)")
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

    # ── Step 5: Calculate SEAS scores ───────────────────────────
    banner(5, "SEAS Scoring (→ h3_seas_scores.csv)")
    calculate_seas()

    elapsed = time.time() - start
    print(f"\n{'='*60}")
    print(f"  ✅ Pipeline complete in {elapsed:.1f}s")
    print(f"  📄 Final output: data/h3_seas_scores.csv")
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
    args = parser.parse_args()

    run_pipeline(workers=args.workers, headless=not args.headed)

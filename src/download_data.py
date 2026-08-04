"""
Data bootstrapper — run automatically before the pipeline starts.

Checks if large data files (NTL satellite data, Open Buildings footprints)
are present in their expected directories. If a directory is empty, the file
is downloaded from Google Drive so new users don't need to manually source
these files.

Files are only downloaded once — if they already exist the function returns
immediately without touching the network.
"""

import os
import glob
import sys

# ─── Google Drive File IDs ────────────────────────────────────────────────────
# Extract the ID from the shareable link:
#   https://drive.google.com/file/d/<FILE_ID>/view?usp=sharing

NTL_DRIVE_ID = "1qQKxyj1-PwqwKzwjfkG_5hlZE-r0HbV0"
NTL_FILENAME = "VNP46A3.A2026152.h18v08.002.2026201114105.h5"

BUILDINGS_DRIVE_ID = "1D2ZX88B2sXzrFgEReUG6B9OToff_N737"
BUILDINGS_FILENAME = "103_buildings.csv"

# ─── Directory paths ──────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
NTL_DIR = os.path.join(PROJECT_ROOT, "data", "ntl")
BUILDINGS_DIR = os.path.join(PROJECT_ROOT, "data", "buildings")


def _ensure_gdown():
    """Import gdown, installing it automatically if it's not available."""
    try:
        import gdown
        return gdown
    except ImportError:
        print("[Bootstrap] gdown not found. Installing...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "gdown"])
        import gdown
        return gdown


def _download(drive_id, dest_path, label):
    """Download a single file from Google Drive to dest_path."""
    gdown = _ensure_gdown()
    url = f"https://drive.google.com/uc?id={drive_id}"
    print(f"[Bootstrap] Downloading {label}...")
    print(f"[Bootstrap]   → {dest_path}")
    gdown.download(url, dest_path, quiet=False)
    if not os.path.exists(dest_path):
        raise RuntimeError(f"[Bootstrap] Download failed for {label}. Check the Drive link and permissions.")
    print(f"[Bootstrap] ✅ {label} downloaded successfully.")


def ensure_data():
    """
    Check that NTL and Buildings data files are present.
    Downloads from Google Drive if either directory is empty.
    Safe to call on every run — skips download if files already exist.
    """
    os.makedirs(NTL_DIR, exist_ok=True)
    os.makedirs(BUILDINGS_DIR, exist_ok=True)

    # ── NTL ──────────────────────────────────────────────────────────────────
    ntl_files = glob.glob(os.path.join(NTL_DIR, "*.h5"))
    if ntl_files:
        print(f"[Bootstrap] NTL data found: {os.path.basename(ntl_files[0])} — skipping download.")
    else:
        if BUILDINGS_DRIVE_ID == "PLACEHOLDER_BUILDINGS_DRIVE_ID":
            # NTL placeholder check — this one is real so we download it
            pass
        _download(
            drive_id=NTL_DRIVE_ID,
            dest_path=os.path.join(NTL_DIR, NTL_FILENAME),
            label="NTL satellite data (.h5)"
        )

    # ── Buildings ─────────────────────────────────────────────────────────────
    buildings_files = glob.glob(os.path.join(BUILDINGS_DIR, "*.csv"))
    if buildings_files:
        print(f"[Bootstrap] Buildings data found: {os.path.basename(buildings_files[0])} — skipping download.")
    else:
        if BUILDINGS_DRIVE_ID == "PLACEHOLDER_BUILDINGS_DRIVE_ID":
            print(
                "[Bootstrap] ⚠️  Buildings data not found and no Drive link has been configured.\n"
                "           Please update BUILDINGS_DRIVE_ID in src/download_data.py\n"
                "           or manually place the buildings CSV in data/buildings/."
            )
        else:
            _download(
                drive_id=BUILDINGS_DRIVE_ID,
                dest_path=os.path.join(BUILDINGS_DIR, BUILDINGS_FILENAME),
                label="Open Buildings footprints (.csv)"
            )


if __name__ == "__main__":
    ensure_data()

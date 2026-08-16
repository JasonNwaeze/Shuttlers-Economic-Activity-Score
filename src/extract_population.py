import os
import glob
import h3
import pandas as pd
import numpy as np
import tifffile
from shapely.geometry import Polygon, Point

from h3_utils import get_target_h3s

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
POPULATION_DIR = os.path.join(PROJECT_ROOT, "data", "population")
OUTPUT_FILE = os.path.join(PROJECT_ROOT, "data", "output", "h3_population.csv")


def extract_population():
    target_h3s = get_target_h3s()

    if not target_h3s:
        print("No target H3 indices found. Exiting population extraction.")
        return

    tif_files = glob.glob(os.path.join(POPULATION_DIR, "*.tif"))
    if not tif_files:
        print(f"No .tif file found in {POPULATION_DIR}. Have you run download_data.py?")
        return

    tif_path = tif_files[0]
    print(f"Processing population file: {tif_path}")

    results = []

    try:
        with tifffile.TiffFile(tif_path) as tif:
            page = tif.pages[0]
            data = page.asarray()

            # GeoTIFF tag codes:
            # 33550: ModelPixelScaleTag (scale_x, scale_y, scale_z)
            # 33922: ModelTiepointTag (i, j, k, x, y, z)
            pixel_scale = page.tags[33550].value
            tiepoint = page.tags[33922].value

            scale_x, scale_y = pixel_scale[0], pixel_scale[1]
            origin_x, origin_y = tiepoint[3], tiepoint[4] # min_lng, max_lat

            height, width = data.shape

            for h3_index in target_h3s:
                boundary = h3.cell_to_boundary(h3_index)
                # boundary is tuple of (lat, lng). Convert to (lng, lat) for Shapely
                coords_lnglat = [(lng, lat) for lat, lng in boundary]
                polygon = Polygon(coords_lnglat)

                min_lng, min_lat, max_lng, max_lat = polygon.bounds

                # Calculate bounding pixel indices
                col_start = max(0, int(np.floor((min_lng - origin_x) / scale_x)))
                col_end = min(width, int(np.ceil((max_lng - origin_x) / scale_x)))
                row_start = max(0, int(np.floor((origin_y - max_lat) / scale_y)))
                row_end = min(height, int(np.ceil((origin_y - min_lat) / scale_y)))

                if col_start >= col_end or row_start >= row_end:
                    results.append({"h3": h3_index, "population": 0.0})
                    continue

                sub_data = data[row_start:row_end, col_start:col_end]
                
                # Sum pixels inside the bounding box that are within the polygon
                total_pop = 0.0
                for r in range(sub_data.shape[0]):
                    pixel_lat = origin_y - ((row_start + r + 0.5) * scale_y)
                    for c in range(sub_data.shape[1]):
                        val = sub_data[r, c]
                        # Discard invalid/nodata values (WorldPop uses negative numbers or NaN for nodata)
                        if np.isnan(val) or val <= 0:
                            continue

                        pixel_lng = origin_x + ((col_start + c + 0.5) * scale_x)
                        if polygon.contains(Point(pixel_lng, pixel_lat)):
                            total_pop += float(val)

                results.append({
                    "h3": h3_index,
                    "population": round(total_pop, 2)
                })

    except Exception as e:
        print(f"Error processing population raster: {e}")
        return

    df = pd.DataFrame(results)
    df.to_csv(OUTPUT_FILE, index=False)
    print(f"Successfully saved population estimates to {OUTPUT_FILE}")
    print(df.head())


if __name__ == "__main__":
    extract_population()

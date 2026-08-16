import os
from collections import Counter
import pandas as pd
import h3
from openlocationcode import openlocationcode

from h3_utils import get_target_h3s

RESOLUTION = 7
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "POIs")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "output", "h3_features.csv")

def process_pois():
    target_h3_list = get_target_h3s()

    if not target_h3_list:
        print("No target H3 indices found in shared_h3_input.csv. Exiting.")
        return

    aggregated_data = []
    seen_h3s = set()

    for target_h3 in target_h3_list:
        if target_h3 in seen_h3s:
            continue
        seen_h3s.add(target_h3)

        # Get the geographic centre of the H3 cell for recovering short Plus Codes
        ref_lat, ref_lng = h3.cell_to_latlng(target_h3)

        print(f"\n=================== H3: {target_h3} (centre: {ref_lat:.4f}, {ref_lng:.4f}) ===================")

        counts = {
            "restaurants": 0,
            "hotels": 0,
            "banks": 0,
            "gas_stations": 0
        }
        hotel_prices = []

        # Find matching CSV files — files are named <category>_<h3_index>.csv
        for filename in os.listdir(DATA_DIR):
            if not filename.endswith(f"_{target_h3}.csv"):
                continue

            suffix = f"_{target_h3}.csv"
            category = filename.replace(suffix, "")
            # Normalise "gas stations" -> "gas_stations"
            category_key = category.replace(" ", "_")
            if category_key not in counts:
                counts[category_key] = 0

            filepath = os.path.join(DATA_DIR, filename)
            try:
                df = pd.read_csv(filepath)
            except (pd.errors.EmptyDataError, FileNotFoundError):
                continue

            total_scraped = len(df)
            missing_plus_code = 0
            invalid_plus_code = 0
            h3_cell_distribution = Counter()

            for _, row in df.iterrows():
                plus_code_full = str(row.get('plus_code', ''))

                if not plus_code_full or plus_code_full == 'nan':
                    missing_plus_code += 1
                    continue

                parts = plus_code_full.replace(',', ' ').split()
                if not parts:
                    missing_plus_code += 1
                    continue

                pure_code = parts[0]

                if not openlocationcode.isValid(pure_code):
                    invalid_plus_code += 1
                    continue

                try:
                    if openlocationcode.isShort(pure_code):
                        full_code = openlocationcode.recoverNearest(pure_code, ref_lat, ref_lng)
                        decoded = openlocationcode.decode(full_code)
                    else:
                        decoded = openlocationcode.decode(pure_code)

                    lat = decoded.latitudeCenter
                    lng = decoded.longitudeCenter

                    poi_h3 = h3.latlng_to_cell(lat, lng, RESOLUTION)
                    h3_cell_distribution[poi_h3] += 1

                    if poi_h3 == target_h3:
                        counts[category_key] += 1

                        if category_key == "hotels" and "hotel_price" in row:
                            price_val = row["hotel_price"]
                            if pd.notna(price_val):
                                try:
                                    price_str = str(price_val).replace(',', '').strip()
                                    price = float(price_str)
                                    hotel_prices.append(price)
                                except ValueError:
                                    pass
                except Exception:
                    invalid_plus_code += 1

            # Diagnostic breakdown per category
            inside_count = h3_cell_distribution[target_h3]
            outside_count = sum(c for cell, c in h3_cell_distribution.items() if cell != target_h3)

            print(f"\n--- Category: {category_key} ---")
            print(f"Total scraped: {total_scraped}")
            print(f"Missing plus code: {missing_plus_code}")
            print(f"Invalid plus code: {invalid_plus_code}")
            print(f"Inside target H3 ({target_h3}): {inside_count}")
            print(f"Outside target H3: {outside_count}")
            print("Distribution across H3 cells:")
            for cell, cnt in h3_cell_distribution.most_common(5):
                tag = " <-- TARGET" if cell == target_h3 else ""
                dist = h3.grid_distance(cell, target_h3) if cell != target_h3 else 0
                print(f"  {cell} : {cnt} (dist: {dist}){tag}")

        avg_price = sum(hotel_prices) / len(hotel_prices) if hotel_prices else None
        row_data = {
            "h3": target_h3,
            **counts,
            "avg_hotel_price": avg_price
        }
        aggregated_data.append(row_data)

    if aggregated_data:
        out_df = pd.DataFrame(aggregated_data)
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        out_df.to_csv(OUTPUT_FILE, index=False)
        print(f"\nSuccessfully saved features to {OUTPUT_FILE}")
        print(out_df)

if __name__ == "__main__":
    process_pois()

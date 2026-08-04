import csv
import os
import h3

RESOLUTION = 7

SHARED_INPUT = os.path.join(os.path.dirname(__file__), "..", "data", "shared_h3_input.csv")


def get_target_h3s(csv_path=None):
    """Read target H3 indices from the shared input CSV (h3 column only)."""
    if csv_path is None:
        csv_path = SHARED_INPUT
    cells = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if "h3" in row and row["h3"].strip():
                cells.append(row["h3"].strip())
    return cells


def get_center(h3_index):
    return h3.cell_to_latlng(h3_index)


if __name__ == "__main__":
    cells = get_target_h3s()
    for cell in cells:
        lat, lng = get_center(cell)
        print(cell, lat, lng)
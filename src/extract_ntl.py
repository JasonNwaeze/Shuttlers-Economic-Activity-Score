import os
import glob
import h5py
import h3
import pandas as pd
import numpy as np
import time

def find_ntl_file(data_dir):
    h5_files = glob.glob(os.path.join(data_dir, "*.h5"))
    if not h5_files:
        raise FileNotFoundError(f"No .h5 files found in {data_dir}")
    if len(h5_files) > 1:
        raise ValueError(f"Multiple .h5 files found in {data_dir}. Expected exactly one.")
    return h5_files[0]

def main():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    ntl_dir = os.path.join(base_dir, "data", "ntl")
    h3_features_file = os.path.join(base_dir, "data", "h3_features.csv")
    
    # Read target H3s
    df_h3 = pd.read_csv(h3_features_file)
    target_h3s = set(df_h3['h3'].dropna().tolist())
    print(f"Target H3 cells: {target_h3s}")
    
    ntl_file = find_ntl_file(ntl_dir)
    print(f"Processing NTL file: {ntl_file}")
    
    # Stats dictionaries for target H3s
    h3_stats = {h3_cell: [] for h3_cell in target_h3s}
    
    start_time = time.time()
    
    with h5py.File(ntl_file, 'r') as f:
        rad_dataset = f['HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields/AllAngle_Composite_Snow_Free']
        lat_dataset = f['HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields/lat']
        lon_dataset = f['HDFEOS/GRIDS/VIIRS_Grid_DNB_2d/Data Fields/lon']
        
        rad = rad_dataset[:]
        lat = lat_dataset[:]
        lon = lon_dataset[:]
        
        # Read attributes for invalid values
        fill_value = rad_dataset.attrs.get('_FillValue', None)
        valid_min = rad_dataset.attrs.get('valid_min', None)
        valid_max = rad_dataset.attrs.get('valid_max', None)
        
        # HDF5 attributes are often returned as arrays (e.g. array([65535]))
        if fill_value is not None and isinstance(fill_value, np.ndarray) and fill_value.size > 0:
            fill_value = fill_value[0]
        if valid_min is not None and isinstance(valid_min, np.ndarray) and valid_min.size > 0:
            valid_min = valid_min[0]
        if valid_max is not None and isinstance(valid_max, np.ndarray) and valid_max.size > 0:
            valid_max = valid_max[0]
            
        print(f"Attributes -> _FillValue: {fill_value}, valid_min: {valid_min}, valid_max: {valid_max}")
        
        rows, cols = rad.shape
        
        for r in range(rows):
            if r > 0 and r % 200 == 0:
                print(f"Processed {r} / {rows} rows ({(time.time() - start_time):.1f}s elapsed)")
                
            latitude = lat[r]
            
            for c in range(cols):
                val = rad[r, c]
                
                # Filter invalid values
                if fill_value is not None and val == fill_value:
                    continue
                if valid_min is not None and val < valid_min:
                    continue
                if valid_max is not None and val > valid_max:
                    continue
                if val >= 65535 or val < 0:
                    continue
                
                longitude = lon[c]
                
                cell = h3.latlng_to_cell(latitude, longitude, 7)
                
                if cell in target_h3s:
                    h3_stats[cell].append(val)
                    
    print(f"Finished processing in {(time.time() - start_time):.1f}s")
    
    # Compute aggregates
    aggregated_data = []
    for cell in target_h3s:
        values = h3_stats[cell]
        if len(values) > 0:
            aggregated_data.append({
                'h3': cell,
                'mean_ntl': np.mean(values),
                'median_ntl': np.median(values),
                'max_ntl': np.max(values),
                'pixel_count': len(values)
            })
        else:
            aggregated_data.append({
                'h3': cell,
                'mean_ntl': np.nan,
                'median_ntl': np.nan,
                'max_ntl': np.nan,
                'pixel_count': 0
            })
            
    df_agg = pd.DataFrame(aggregated_data)
    
    # Left join
    df_merged = df_h3.merge(df_agg, on='h3', how='left')
    
    # Save
    df_merged.to_csv(h3_features_file, index=False)
    print(f"\nSuccessfully updated {h3_features_file}")
    
    # Display the final features
    print("\nValidation check:")
    print(df_merged[['h3', 'mean_ntl', 'median_ntl', 'max_ntl', 'pixel_count']])

if __name__ == "__main__":
    main()

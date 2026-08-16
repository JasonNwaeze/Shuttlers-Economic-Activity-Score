import os
import pandas as pd
import numpy as np

def calculate_seas():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    pois_file = os.path.join(base_dir, "data", "output", "h3_features.csv")
    buildings_file = os.path.join(base_dir, "data", "output", "h3_building_features.csv")
    output_file = os.path.join(base_dir, "data", "output", "h3_seas_scores.csv")
    
    # Load datasets
    df_pois = pd.read_csv(pois_file)
    df_build = pd.read_csv(buildings_file)
    
    # Merge datasets on 'h3'
    df = pd.merge(df_pois, df_build, on='h3', how='left')
    
    # Fill any missing values with 0 to allow min-max scaling
    features = [
        'mean_ntl', 'building_count', 'large_buildings', 'restaurants', 
        'banks', 'hotels', 'avg_hotel_price', 'gas_stations', 'avg_building_confidence'
    ]
    
    for f in features:
        if f in df.columns:
            df[f] = df[f].fillna(0)
        else:
            df[f] = 0.0
            
    # Normalize features (Min-Max Scaling 0-1)
    df_norm = pd.DataFrame()
    for feature in features:
        min_val = df[feature].min()
        max_val = df[feature].max()
        if max_val - min_val > 0:
            df_norm[f"{feature}_norm"] = (df[feature] - min_val) / (max_val - min_val)
        else:
            # Single-cell or uniform value handling: if non-zero, assign 1.0; else 0.0
            df_norm[f"{feature}_norm"] = df[feature].apply(lambda x: 1.0 if x > 0 else 0.0)
            
    # Calculate SEAS using the Affluence-weighted model
    weights = {
        'mean_ntl_norm': 0.20,
        'avg_hotel_price_norm': 0.20,
        'banks_norm': 0.10,
        'hotels_norm': 0.10,
        'restaurants_norm': 0.10,
        'gas_stations_norm': 0.10,
        'large_buildings_norm': 0.10,
        'building_count_norm': 0.05,
        'avg_building_confidence_norm': 0.05
    }
    
    df['seas_raw'] = 0.0
    for feature, weight in weights.items():
        df['seas_raw'] += df_norm[feature] * weight
        
    df['SEAS'] = df['seas_raw'] * 100
    
    def interpret_score(score):
        if pd.isna(score):
            return "Unknown"
        if score >= 85:
            return "Exceptional economic activity and very high potential for commuter demand."
        elif score >= 70:
            return "High economic activity with strong expansion potential."
        elif score >= 55:
            return "Moderate activity with good demand characteristics."
        elif score >= 40:
            return "Emerging area with developing commercial activity."
        else:
            return "Low economic activity and lower priority for expansion."
            
    df['interpretation'] = df['SEAS'].apply(interpret_score)
    
    # Sort by SEAS descending
    df = df.sort_values(by='SEAS', ascending=False).reset_index(drop=True)
    
    # Save the output
    df.to_csv(output_file, index=False)
    
    print(f"\nSuccessfully calculated SEAS and saved to {output_file}")
    
    print("\nFinal Rankings:")
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    print(df[['h3', 'SEAS', 'interpretation']])

if __name__ == "__main__":
    calculate_seas()

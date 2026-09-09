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
    
    # Fill any missing values with 0
    all_raw_cols = [
        'mean_ntl', 'building_count', 'large_buildings', 'restaurants', 
        'banks', 'hotels', 'avg_hotel_price', 'gas_stations'
    ]
    for col in all_raw_cols:
        if col in df.columns:
            df[col] = df[col].fillna(0.0)
        else:
            df[col] = 0.0

    # ── Step 1: Preprocessing Guard ───────────────────────────────
    # Zero out POIs if building_count == 0 (purges geocoding / boundary artifacts)
    poi_cols = ['restaurants', 'hotels', 'banks', 'gas_stations', 'avg_hotel_price']
    df.loc[df['building_count'] == 0, poi_cols] = 0.0

    # ── Step 2: Feature Engineering ───────────────────────────────
    # Hotel Economic Mass (eliminates 1-hotel small-sample listing noise)
    df['hotel_mass'] = df['hotels'] * df['avg_hotel_price']
    
    # Large building ratio (quality/verticality metric, orthogonal to building count)
    df['large_bldg_ratio'] = np.where(df['building_count'] > 0, df['large_buildings'] / df['building_count'], 0.0)

    # ── Step 3: 99th-Percentile Winsorization + Log1p Scaling ────
    def log_scale(s, p=0.99):
        cap = s.quantile(p)
        if cap == 0 or pd.isna(cap):
            cap = s.max()
        clipped = s.clip(upper=cap)
        lv = np.log1p(clipped)
        max_lv = lv.max()
        return lv / max_lv if max_lv > 0 else lv

    norm_banks = log_scale(df['banks'])
    norm_restaurants = log_scale(df['restaurants'])
    norm_gas = log_scale(df['gas_stations'])
    norm_hotel_mass = log_scale(df['hotel_mass'])

    norm_building_count = log_scale(df['building_count'])
    ratio_cap = df['large_bldg_ratio'].quantile(0.99)
    if ratio_cap == 0 or pd.isna(ratio_cap):
        ratio_cap = df['large_bldg_ratio'].max()
    norm_large_bldg_ratio = df['large_bldg_ratio'].clip(upper=ratio_cap) / ratio_cap if ratio_cap > 0 else df['large_bldg_ratio']

    norm_ntl = log_scale(df['mean_ntl'])

    # ── Step 4: Dimensional Sub-Indices ───────────────────────────
    # Sub-Index 1: Commercial Vitality (Weight 45%)
    i_comm = (
        0.35 * norm_banks +
        0.30 * norm_restaurants +
        0.15 * norm_gas +
        0.20 * norm_hotel_mass
    )

    # Sub-Index 2: Urban Built Form (Weight 30%) - Mass + Quality Ratio ONLY
    # Raw large_buildings is dropped to prevent severe multicollinearity (VIF dropped from 20+ to <2.3)
    i_urban = (
        0.65 * norm_building_count +
        0.35 * norm_large_bldg_ratio
    )

    # Sub-Index 3: Affluence & Electrification (Weight 25%)
    i_affl = norm_ntl

    # ── Step 5: Commercial Co-occurrence Gate ─────────────────────
    # If commercial vitality is zero, penalize non-commercial illumination (e.g. gas flares) by 70%
    comm_gate = np.where(i_comm > 0, 1.0, 0.3)

    # Calculate final composite score
    df['seas_raw'] = (0.45 * i_comm + 0.30 * i_urban + 0.25 * i_affl * comm_gate)
    df['SEAS'] = df['seas_raw'] * 100.0

    # ── Step 6: Dynamic Quantile-Based Classification Tiers ────────
    # Derive regional empirical thresholds to ensure stable, calibrated grading
    q95 = df['SEAS'].quantile(0.95)
    q80 = df['SEAS'].quantile(0.80)
    q50 = df['SEAS'].quantile(0.50)
    q30 = df['SEAS'].quantile(0.30)

    # Fallback for very small test runs (e.g., 1-5 cells where quantiles collapse)
    if q95 == q30 or pd.isna(q95):
        q95, q80, q50, q30 = 85.0, 70.0, 55.0, 40.0

    def classify_cell(score):
        if pd.isna(score):
            return "Unknown", "Unknown"
        if score >= q95:
            return "Exceptional", "Exceptional economic activity and very high potential for commuter demand."
        elif score >= q80:
            return "High", "High economic activity with strong expansion potential."
        elif score >= q50:
            return "Moderate", "Moderate activity with good demand characteristics."
        elif score >= q30:
            return "Emerging", "Emerging area with developing commercial activity."
        else:
            return "Low", "Low economic activity and lower priority for expansion."

    tier_and_interp = df['SEAS'].apply(classify_cell)
    df['tier'] = [t[0] for t in tier_and_interp]
    df['interpretation'] = [t[1] for t in tier_and_interp]

    # Sort by SEAS descending
    df = df.sort_values(by='SEAS', ascending=False).reset_index(drop=True)

    # Save output
    df.to_csv(output_file, index=False)
    print(f"\nSuccessfully calculated SEAS and saved to {output_file}")
    print(f"Empirical Tier Cutoffs: Exceptional >= {q95:.1f}, High >= {q80:.1f}, Moderate >= {q50:.1f}, Emerging >= {q30:.1f}, Low < {q30:.1f}")
    
    print("\nTier Counts:")
    print(df['tier'].value_counts())

    print("\nTop 15 Rankings:")
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    print(df[['h3', 'SEAS', 'tier', 'interpretation']].head(15))

if __name__ == "__main__":
    calculate_seas()

import logging
from mineguard.backend.services.scene_query import advanced_query_scenes
from mineguard.backend.services.scene_filter import filter_scenes

logging.basicConfig(level=logging.INFO)

roi = {"north": 20.96, "south": 20.94, "east": 85.12, "west": 85.08}
raw = advanced_query_scenes(roi, "2021", "2026", "Yearly")
print(f"Raw scenes found: {len(raw)}")
if not raw:
    exit()

from datetime import datetime
start_year = 2021
end_year = 2026

for scene in raw:
    acq_str = scene.get('acquisitionDate', '')
    mode = scene.get('mode')
    pol = scene.get('polarization')
    
    try:
        acq_year = datetime.strptime(acq_str.split('T')[0], "%Y-%m-%d").year
        if not (start_year <= acq_year <= end_year):
            print(f"Drop Year: {acq_year}")
            continue
    except ValueError:
        print(f"Drop Date Parse: {acq_str}")
        continue
        
    if mode != 'IW':
        print(f"Drop Mode: {mode}")
        continue
        
    pol_str = str(pol).upper()
    if 'VV' not in pol_str:
        print(f"Drop Pol: {pol_str}")
        continue
        
    print(f"Kept! {scene.get('filename')}")

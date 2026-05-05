import logging
from mineguard.backend.services.scene_query import advanced_query_scenes
from mineguard.backend.services.scene_filter import filter_scenes

logging.basicConfig(level=logging.INFO)

roi = {"north": 20.96, "south": 20.94, "east": 85.12, "west": 85.08}
raw = advanced_query_scenes(roi, "2021", "2026", "Yearly")
print(f"\n\n--- RESULTS ---")
print(f"Raw scenes found: {len(raw)}")

if raw:
    filtered = filter_scenes(raw, roi, 2021, 2026)
    print(f"Filtered scenes: {len(filtered)}")
else:
    print("No raw scenes returned from advanced_query_scenes.")

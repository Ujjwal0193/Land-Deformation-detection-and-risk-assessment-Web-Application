import logging
import json
from mineguard.backend.services.scene_query import advanced_query_scenes
from mineguard.backend.services.scene_filter import filter_scenes

logging.basicConfig(level=logging.DEBUG)

roi = {"north": 20.96, "south": 20.94, "east": 85.12, "west": 85.08}
start_year = "2018"
end_year = "2019"
freq = "Yearly"

print("--- RUNNING RAW QUERY ---")
raw = advanced_query_scenes(roi, start_year, end_year, freq)
print(f"Raw scenes found: {len(raw)}")

if raw:
    print("--- RUNNING FILTER ---")
    filtered = filter_scenes(raw, roi, int(start_year), int(end_year))
    print(f"Filtered scenes: {len(filtered)}")
else:
    print("No raw scenes returned!")

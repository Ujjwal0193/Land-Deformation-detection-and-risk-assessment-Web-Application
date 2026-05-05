import os
import sys
import logging
import zipfile
import re
from datetime import datetime

# Import what we can
sys.path.insert(0, r"c:\Projects\snap\MineGuardProto-1\MineGuardProto-1\MineGuard_Proto")
try:
    from src.main_script import detect_bursts_for_aoi
except ImportError:
    print("Could not import detect_bursts_for_aoi from src.main_script")
    sys.exit(1)

logging.basicConfig(level=logging.ERROR)

def get_product_date(filename):
    try:
        parts = filename.split('_')
        for part in parts:
            if len(part) == 15 and 'T' in part:
                return datetime.strptime(part, "%Y%m%dT%H%M%S")
    except Exception:
        pass
    return None

def get_relative_orbit_from_zip(zip_path: str):
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            for name in z.namelist():
                if name.endswith('manifest.safe'):
                    with z.open(name) as f:
                        content = f.read().decode('utf-8')
                        m = re.search(r'<s1:relativeOrbitNumber[^>]*>(\d+)</s1:relativeOrbitNumber>', content)
                        if m:
                            return int(m.group(1))
    except Exception:
        pass
    return None

input_slc = r"c:\Projects\snap\MineGuardProto-1\MineGuardProto-1\input_slc"
aoi_lat, aoi_lon = 20.96, 85.09

files = [f for f in os.listdir(input_slc) if f.endswith('.zip') and 'S1A_IW_SLC' in f]
files.sort()

print(f"{'Date':<12} | {'Orbit':<6} | {'Subswath':<10} | {'Bursts':<8} | {'Filename'}")
print("-" * 80)
for f in files:
    path = os.path.join(input_slc, f)
    orbit = get_relative_orbit_from_zip(path)
    date = get_product_date(f)
    date_str = date.strftime('%Y-%m-%d') if date else "Unknown"
    
    try:
        first, last, sw = detect_bursts_for_aoi(path, "iw2", aoi_lat, aoi_lon)
        burst_str = f"{first}-{last}" if last != 9999 else "NOT_FOUND"
    except Exception as e:
        burst_str = "ERROR"
        sw = "ERROR"
    
    print(f"{date_str:<12} | {str(orbit):<6} | {sw:<10} | {burst_str:<8} | {f[:45]}...")

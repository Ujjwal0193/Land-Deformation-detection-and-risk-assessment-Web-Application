import requests
import json
from datetime import datetime

url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
wkt = "POINT(85.09 20.96)"

# Query from 2015-01-01 to 2020-12-31
start_date = "2015-01-01T00:00:00.000Z"
end_date = "2020-12-31T23:59:59.000Z"

params = {
    '$filter': f"Collection/Name eq 'SENTINEL-1' "
               f"and ContentDate/Start ge {start_date} and ContentDate/End le {end_date} "
               f"and Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' and att/Value eq 'SLC') "
               f"and OData.CSC.Intersects(area=geography'SRID=4326;{wkt}')",
    '$top': 1000,
    '$orderby': 'ContentDate/Start asc',
    '$expand': 'Attributes'
}

print("Querying CDSE...")
r = requests.get(url, params=params, timeout=60)
data = r.json()

products = data.get('value', [])
print(f"Found {len(products)} products.")

orbits = {}
for p in products:
    orbit = None
    for att in p.get('Attributes', []):
        if att['Name'] == 'relativeOrbitNumber':
            orbit = att['Value']
            break
    if orbit:
        if orbit not in orbits:
            orbits[orbit] = []
        orbits[orbit].append(p)

for orbit, prods in orbits.items():
    print(f"Relative Orbit {orbit}: {len(prods)} products")

# Pick the orbit with the most products
if orbits:
    best_orbit = max(orbits.keys(), key=lambda o: len(orbits[o]))
    print(f"\nBest Relative Orbit: {best_orbit}")
    
    # Pick one product per year
    years_picked = set()
    selected_products = []
    
    for p in orbits[best_orbit]:
        date_str = p['ContentDate']['Start']
        year = date_str[:4]
        if year not in years_picked and int(year) >= 2015 and int(year) <= 2020:
            years_picked.add(year)
            selected_products.append({
                "name": p['Name'],
                "date": date_str,
                "uuid": p['Id']
            })
            if len(years_picked) == 6: # 2015 to 2020 inclusive
                break
                
    print("\nRecommended Compatible Time Series:")
    for sp in selected_products:
        print(f"Year: {sp['date'][:10]} | File: {sp['name']}")
else:
    print("No products found.")

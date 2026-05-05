import requests
import json
url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
params = {
    "$filter": "Collection/Name eq 'SENTINEL-1' and ContentDate/Start ge 2015-01-01T00:00:00.000Z and ContentDate/End le 2020-12-31T23:59:59.000Z and Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' and att/Value eq 'SLC') and OData.CSC.Intersects(area=geography'SRID=4326;POINT(85.09 20.96)')",
    "$top": 500,
    "$expand": "Attributes",
    "$orderby": "ContentDate/Start asc"
}
print("Downloading list from OData...")
r = requests.get(url, params=params).json()
prods = r.get('value', [])
o121 = []
for p in prods:
    for a in p.get('Attributes', []):
        if a['Name'] == 'relativeOrbitNumber' and a['Value'] == 121:
            o121.append(p)
            break

yp = set()
with open("compatible_products.txt", "w") as f:
    for p in o121:
        y = p['ContentDate']['Start'][:4]
        if y not in yp:
            yp.add(y)
            f.write(f"{y} -> {p['Name']}\n")
print("Written to compatible_products.txt")

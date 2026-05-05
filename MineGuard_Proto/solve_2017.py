import requests
url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
params = {
    "$filter": "Collection/Name eq 'SENTINEL-1' and ContentDate/Start ge 2017-01-07T00:00:00.000Z and ContentDate/End le 2017-01-07T23:59:59.000Z and Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' and att/Value eq 'SLC') and Attributes/OData.CSC.IntegerAttribute/any(att:att/Name eq 'relativeOrbitNumber' and att/Value eq 121)",
    "$expand": "Attributes"
}
prods = requests.get(url, params=params).json().get('value', [])
for p in prods:
    print(p['Name'])

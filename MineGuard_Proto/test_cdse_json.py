import requests
from mineguard.backend.services.scene_query import get_access_token
import json

ODATA_URL = 'https://catalogue.dataspace.copernicus.eu/odata/v1'
token = get_access_token()

query = (
    "$filter=Collection/Name eq 'SENTINEL-1' and "
    "Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' and att/Value eq 'SLC')"
    "&$expand=Attributes&$top=1"
)
url = f"{ODATA_URL}/Products?{query}"

headers = {"Authorization": f"Bearer {token}"}
r = requests.get(url, headers=headers)

if r.status_code == 200:
    data = r.json().get('value', [])
    if data:
        product = data[0]
        attributes = product.get('Attributes', [])
        names = [attr.get('Name') for attr in attributes]
        print("ATTRIBUTE NAMES:", names)
        for attr in attributes:
            if 'pol' in attr.get('Name').lower() or 'mode' in attr.get('Name').lower() or 'orbit' in attr.get('Name').lower():
                print(f"  {attr.get('Name')}: {attr.get('Value')}")

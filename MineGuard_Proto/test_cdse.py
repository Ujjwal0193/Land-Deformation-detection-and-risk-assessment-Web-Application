import requests
import sys
import os
sys.path.insert(0, r"c:\Projects\snap\MineGuardProto-1\MineGuardProto-1\MineGuard_Proto")
from mineguard.backend.services.scene_query import get_access_token

def test():
    try:
        to = get_access_token()
        query = "Collection/Name eq 'SENTINEL-1' and ContentDate/Start ge 2020-10-01T00:00:00.000Z and ContentDate/End le 2020-12-31T00:00:00.000Z and Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' and att/Value eq 'SLC') and Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'operationalMode' and att/Value eq 'IW') and Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'orbitDirection' and att/Value eq 'DESCENDING') and OData.CSC.Intersects(area=geography'SRID=4326;POLYGON((86.39388612270882 23.698334045037907, 86.47283021998533 23.698334045037907, 86.47283021998533 23.783627983146765, 86.39388612270882 23.783627983146765, 86.39388612270882 23.698334045037907))')"
        query = "Collection/Name eq 'SENTINEL-1' and Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' and att/Value eq 'SLC') and Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'operationalMode' and att/Value eq 'IW')"
        url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
        params = {"$filter": query, "$expand": "Attributes", "$top": "1"}
        r = requests.get(url, params=params, headers={'Authorization': f'Bearer {to}'}, timeout=60)
        print(f"WITH TOKEN: {r.status_code}")
        if r.status_code == 200:
            for att in r.json().get('value', [])[0].get('Attributes', []):
                if att.get('Name') == 'orbitDirection':
                    print(f"FOUND EXACT ORBIT ATTRIBUTE: {att}")
        
        r2 = requests.get(url, timeout=60)
        print(f"WITHOUT TOKEN: {r2.status_code}")
        if r2.status_code != 200:
            print(r2.text)
    except Exception as e:
        print(e)

if __name__ == '__main__':
    test()

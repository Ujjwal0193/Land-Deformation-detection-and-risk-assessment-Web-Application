import requests
import os
from dotenv import load_dotenv

load_dotenv()
USER = os.getenv('CDSE_USER')
PASS = os.getenv('CDSE_PASS')

# 1. Test DHUS (Legacy Compat)
dhus_url = "https://sh.dataspace.copernicus.eu/dhus/search?q=*&rows=1&format=json"
print(f"Testing DHUS: {dhus_url}")
try:
    r = requests.get(dhus_url, auth=(USER, PASS))
    print(f"DHUS Status: {r.status_code}")
    # print(r.text[:200])
except Exception as e:
    print(f"DHUS Failed: {e}")

# 2. Test OData (New)
odata_url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products?$top=1"
print(f"\nTesting OData: {odata_url}")
try:
    # OData usually doesn't need auth for search, but might for download
    r = requests.get(odata_url) 
    print(f"OData Status: {r.status_code}")
    # print(r.text[:200])
except Exception as e:
    print(f"OData Failed: {e}")

# 3. Test OpenSearch
opensearch_url = "https://catalogue.dataspace.copernicus.eu/endo/opensearch/search?q=*&httpAccept=application/json"
print(f"\nTesting OpenSearch: {opensearch_url}")
try:
    r = requests.get(opensearch_url)
    print(f"OpenSearch Status: {r.status_code}")
except Exception as e:
    print(f"OpenSearch Failed: {e}")

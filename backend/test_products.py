import requests

BASE = "http://127.0.0.1:5000"

r = requests.get(f"{BASE}/api/products")
print("All products:", r.status_code)
print(r.json())

r2 = requests.get(f"{BASE}/api/products?category=men")
print("\nFiltered (men):", r2.status_code)
print(r2.json())
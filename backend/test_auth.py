import requests

BASE = "http://127.0.0.1:5000"

# 1. Signup
r = requests.post(f"{BASE}/api/auth/signup", json={
    "email": "testuser@example.com",
    "password": "test1234"
})
print("Signup:", r.status_code, r.json())

# 2. Customer login
r = requests.post(f"{BASE}/api/auth/login", json={
    "email": "testuser@example.com",
    "password": "test1234"
})
print("Login:", r.status_code, r.json())

# 3. Admin login (use your real ADMIN_USERNAME/ADMIN_PASSWORD from .env)
r = requests.post(f"{BASE}/api/auth/admin/login", json={
    "username": "admin",
    "password": "admin12345"
})
print("Admin login:", r.status_code, r.json())
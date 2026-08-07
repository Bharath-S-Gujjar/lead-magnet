import requests

response = requests.post(
    "http://127.0.0.1:5000/api/session/start",
    json={"visitor_id": "visitor_test_1"}
)

print(response.status_code)
print(response.json())

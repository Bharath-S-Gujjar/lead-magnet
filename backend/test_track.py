import requests

response = requests.post(
    "http://127.0.0.1:5000/track",
    json={
        "visitor_id": "visitor_1",
        "Lead Origin": "Landing Page Submission",
        "Lead Source": "Google",
        "Total Time Spent on Website": 800,
        "TotalVisits": 5,
        "Page Views Per Visit": 4
    }
)

print(response.status_code)
print(response.json())
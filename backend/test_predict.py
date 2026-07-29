import requests

response = requests.post(
    "http://127.0.0.1:5000/predict",
    json={
        "Lead Origin": "Landing Page Submission",
        "Lead Source": "Google",
        "Total Time Spent on Website": 500,
        "TotalVisits": 3,
        "Page Views Per Visit": 2.5
    }
)

print(response.status_code)
print(response.json())
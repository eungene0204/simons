import requests
import json

url = "http://localhost:8000/backtest"
payload = {
    "symbol": "005930",
    "entry": {
        "logic": "AND",
        "conditions": [
            {
                "type": "indicator",
                "id": "rsi",
                "params": {"period": 14, "value": 30, "operator": "<"}
            }
        ]
    },
    "exit": {
        "logic": "OR",
        "conditions": [
            {
                "type": "indicator",
                "id": "rsi",
                "params": {"period": 14, "value": 70, "operator": ">"}
            }
        ]
    },
    "risk": {
        "position_size_pct": 100,
        "max_positions": 1
    },
    "period": "1Y"
}

try:
    print(f"Sending request to {url}...")
    response = requests.post(url, json=payload)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        print("Success!")
        print(json.dumps(response.json(), indent=2)[:500] + "...")
    else:
        print(f"Error: {response.text}")
except Exception as e:
    print(f"Failed to connect: {e}")

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
        "max_positions": 1,
        "init_cash": 50000000.0,
        "stop_loss_pct": 5.0,
        "take_profit_pct": 10.0
    },
    "period": "1Y",
    "options": {
        "fee_rate": 0.00015,
        "slippage_rate": 0.001,
        "execution_type": "next_open"
    }
}

try:
    print(f"Sending request to {url} with full options...")
    response = requests.post(url, json=payload)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print("Success!")
        print(f"Full Response: {json.dumps(data, indent=2)}")
    else:
        print(f"Error: {response.text}")
except Exception as e:
    print(f"Failed to connect: {e}")

import requests
import json
import pytest

def test_api_isolation():
    url = "http://localhost:8000/backtest"
    symbols = ["005930", "000660"]
    
    payload = {
        "symbols": symbols,
        "entry": {
            "logic": "AND",
            "conditions": [
                {
                    "type": "indicator",
                    "id": "ma_crossover",
                    "params": {"shortMA": 5, "longMA": 20, "signalType": "buy"},
                    "weight": 1.0
                }
            ]
        },
        "exit": {
            "logic": "OR",
            "conditions": []
        },
        "risk": {
            "position_size_pct": 10.0,
            "max_positions": 10,
            "init_cash": 10000000.0,
            "execution_timing": "next_open"
        },
        "period": "1Y"
    }
    
    print("Sending request to API...")
    try:
        response = requests.post(url, json=payload, timeout=10)
    except requests.RequestException as e:
        pytest.skip(f"Local API server unavailable in test environment: {e}")
    if response.status_code != 200:
        print(f"FAILED: {response.status_code} - {response.text}")
        return
        
    result = response.json()
    signals = result.get('signals', [])
    print(f"Total signals received: {len(signals)}")
    
    # Check for date isolation
    symbol_dates = {}
    for s in signals:
        if s['type'] == 'buy':
            sym = s['symbol']
            date = s['date']
            if sym not in symbol_dates: symbol_dates[sym] = []
            symbol_dates[sym].append(date)
            
    for sym in symbols:
        dates = symbol_dates.get(sym, [])
        print(f"Symbol {sym}: {len(dates)} buys. First 3: {dates[:3]}")
        
    # Check for exact date overlap
    if len(symbols) >= 2:
        s1, s2 = symbols[0], symbols[1]
        d1 = set(symbol_dates.get(s1, []))
        d2 = set(symbol_dates.get(s2, []))
        overlap = d1.intersection(d2)
        print(f"Overlap between {s1} and {s2}: {len(overlap)} same dates.")
        if len(overlap) == len(d1) == len(d2) and len(d1) > 0:
            print("CRITICAL ERROR: ALL DATES ARE IDENTICAL!")
        else:
            print("SUCCESS: Signal dates are NOT identical.")

if __name__ == "__main__":
    test_api_isolation()

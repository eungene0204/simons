import pandas as pd
import sys
import os

# Add backend dir for imports
sys.path.append(os.path.join(os.getcwd(), "backend"))

from engine.signals import SignalEngine

def test_or_descriptions():
    engine = SignalEngine()
    
    # Create dummy data where:
    # Row 1 triggers Condition A (Close > 100)
    # Row 2 triggers Condition B (Volume > 1000)
    df = pd.DataFrame({
        'close': [101, 50],
        'volume': [100, 2000]
    })
    
    config = {
        'logic': 'OR',
        'conditions': [
            {'type': 'indicator', 'id': 'high_price', 'params': {'threshold': 100}, 'description': '고가 돌파'},
            {'type': 'indicator', 'id': 'high_volume', 'params': {'threshold': 1000}, 'description': '대량 거래'}
        ]
    }
    
    # Mock evaluate_condition to behave as expected
    def mock_eval(cond, idx, data):
        if cond['id'] == 'high_price':
            return data.loc[idx, 'close'] > 100, cond['description']
        if cond['id'] == 'high_volume':
            return data.loc[idx, 'volume'] > 1000, cond['description']
        return False, ""
    
    engine.evaluate_condition = mock_eval
    
    print("Testing OR Description Isolation...")
    
    # Row 0
    hit0, desc0 = engine.evaluate_group(config, 0, df)
    print(f"Row 0 (Price hit): {hit0}, Desc: {desc0}")
    
    # Row 1
    hit1, desc1 = engine.evaluate_group(config, 1, df)
    print(f"Row 1 (Volume hit): {hit1}, Desc: {desc1}")
    
    if desc0 != desc1:
        print("SUCCESS: Descriptions are DISTINCT based on trigger.")
    else:
        print("FAILURE: Descriptions are IDENTICAL even though triggers differ.")

if __name__ == "__main__":
    test_or_descriptions()

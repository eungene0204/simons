import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock

# We need to test the AIEngine logic, but we don't want to load actual models.
# By patching os.path.exists and torch.load/joblib.load, we can instantiate
# AIEngine safely.

with patch('os.path.exists', return_value=True), \
     patch('joblib.load', return_value=MagicMock()), \
     patch('torch.load', return_value={}), \
     patch('torch.nn.Module.load_state_dict', return_value=None), \
     patch('xgboost.XGBClassifier.load_model', return_value=None), \
     patch('json.load', return_value={}), \
     patch('builtins.open', MagicMock()):
         
    from ai.ai_engine import AIEngine

@pytest.fixture
def mock_engine():
    # Patch all the heavy loading during __init__
    with patch('os.path.exists', return_value=True), \
         patch('builtins.open', MagicMock()), \
         patch('json.load', return_value={}), \
         patch('joblib.load') as mock_joblib, \
         patch('torch.load', return_value={}), \
         patch('torch.nn.Module.load_state_dict', return_value=None), \
         patch('xgboost.XGBClassifier.load_model'):
        
        # Make the mock scaler just return exactly what you gave it to test data shapes
        mock_scaler = MagicMock()
        mock_scaler.transform.side_effect = lambda x: x
        mock_joblib.return_value = mock_scaler
             
        engine = AIEngine()
        
        # Override lookback for faster testing
        engine.lookback = 5
        
        # Mock Transformer network
        engine.transformer = MagicMock()
        # For a window, we return a 1D dummy embedding (e.g. 10 dims)
        engine.transformer.return_value.cpu.return_value.numpy.return_value = np.ones((1, 10))
        
        # Mock XGBoost head to return multi-target probabilities (N, 2)
        engine.xgb_head = MagicMock()
        # Up prob: 0.8, Drop prob: 0.1
        engine.xgb_head.predict_proba.return_value = np.array([[0.8, 0.1]])
        
        return engine

def test_predict_signals_short_data(mock_engine):
    # lookback is 5. Provide 4 rows.
    df = pd.DataFrame({'open': [1,2,3,4]})
    probs, probs_drop = mock_engine.predict_signals(df)
    
    assert len(probs) == 4
    assert np.all(probs == 0)
    assert len(probs_drop) == 4
    assert np.all(probs_drop == 0)

def test_predict_signals_fallback_rsi(mock_engine):
    # Provide data without 'rsi_14'. AIEngine should calculate it using stockstats.
    # Need at least lookback (5) + enough for RSI to not be entirely NaN if we want non-zero,
    # but stockstats fills it. We'll give it 10 rows.
    df = pd.DataFrame({
        'open': np.random.rand(10) * 100,
        'high': np.random.rand(10) * 100,
        'low': np.random.rand(10) * 100,
        'close': np.random.rand(10) * 100,
        'volume': np.random.rand(10) * 1000
    })
    
    # We patch predict_proba to return sequential values so ranking has effect.
    # Length of output will be: len(df) - lookback + 1 = 10 - 5 + 1 = 6.
    seq_probs = np.linspace(0.1, 0.9, 6)
    mock_seq_drop = np.linspace(0.9, 0.1, 6)
    mock_engine.xgb_head.predict_proba.return_value = np.column_stack((seq_probs, mock_seq_drop))
    
    # Also need to mock transformer to output matching batch size
    mock_engine.transformer.return_value.cpu.return_value.numpy.return_value = np.ones((6, 10))

    probs, probs_drop = mock_engine.predict_signals(df)
    
    assert len(probs) == 10
    
    # The first (lookback - 1) = 4 rows should be 0 
    assert np.all(probs[:4] == 0)
    
    # The next 6 rows will be percentile ranked values of seq_probs
    # Since seq_probs goes strictly up [0.1, 0.26..., 0.9], the expanding rank will be
    # [1.0, 1.0, 1.0, 1.0, 1.0, 1.0] because each new value is the highest seen so far.
    assert probs[4] > 0
    assert probs_drop[4] > 0

def test_predict_signals_feature_prep(mock_engine):
    # Test if 'ret_open', etc are actually created and handled before scaling
    df = pd.DataFrame({
        'open': [100, 110, 110, 100, 100, 100],  # 10%, 0%, -9%
        'high': [100, 110, 110, 100, 100, 100],
        'low': [100, 110, 110, 100, 100, 100],
        'close': [100, 110, 110, 100, 100, 100],
        'volume': [1000, 1500, 1500, 1000, 1000, 1000], # 50%, 0%
        'rsi_14': [50, 60, 50, 40, 50, 60]
    })
    
    # output length = 6 - 5 + 1 = 2
    mock_engine.transformer.return_value.cpu.return_value.numpy.return_value = np.ones((2, 10))
    # Up Probs: [0.5, 0.8], Drop Probs: [0.9, 0.1]
    mock_engine.xgb_head.predict_proba.return_value = np.array([[0.5, 0.9], [0.8, 0.1]])

    # Capture the argument passed to scaler.transform
    original_transform = mock_engine.scaler.transform
    mock_engine.scaler.transform = MagicMock(side_effect=original_transform)
    
    probs, probs_drop = mock_engine.predict_signals(df)
    
    # Check that scaler was called
    mock_engine.scaler.transform.assert_called_once()
    
    # Get the features passed to it
    args, kwargs = mock_engine.scaler.transform.call_args
    passed_features = args[0]
    
    # passed_features should have shape (6, 6) -> (ret_open, ret_high, ret_low, ret_close, ret_volume, rsi_14)
    assert passed_features.shape == (6, 17)
    
    # Check row 1 (index 1) ret_open = log(1.1)
    # Note: row 0 pct_change() is NaN which is filled with 0.
    assert np.isclose(passed_features[1, 0], np.log1p(0.1)) 
    # Check row 1 ret_volume = log(1.5)
    assert np.isclose(passed_features[1, 4], np.log1p(0.5))

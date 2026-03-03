import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import pandas as pd
import numpy as np
import xgboost as xgb
import os
import joblib
import optuna
from tqdm import tqdm
from sklearn.metrics import average_precision_score
from backend.ai.models import HybridAIModel

class StockDataset(Dataset):
    def __init__(self, df, lookback=60, features=None, target='fwd_return_10'):
        self.lookback = lookback
        self.features = features
        self.target = target
        
        # Group by symbol to avoid sequence bleeding across stocks
        self.grouped = df.groupby('symbol')
        self.indices = []
        
        for symbol, group in self.grouped:
            if len(group) > lookback:
                # Store (symbol, start_idx)
                for i in range(len(group) - lookback):
                    self.indices.append((symbol, i))
        
    def __len__(self):
        return len(self.indices)

    def __getitem__(self, idx):
        symbol, start = self.indices[idx]
        group = self.grouped.get_group(symbol)
        
        x = group.iloc[start:start+self.lookback][self.features].values.astype(np.float32)
        y = group.iloc[start+self.lookback-1][self.target] # Target is linked to the end of the window
        
        # We also extract binary targets directly from the dataframe
        y_up = group.iloc[start+self.lookback-1]['target_up']
        y_down = group.iloc[start+self.lookback-1]['target_down']
        
        return torch.from_numpy(x), torch.tensor(y, dtype=torch.float32), torch.tensor(y_up, dtype=torch.float32), torch.tensor(y_down, dtype=torch.float32)

def train_hybrid_model(data_path, model_dir, lookback=60, epochs=30, n_trials_transformer=10, n_trials_xgb=20, buy_threshold=0.07, sell_threshold=0.07):
    os.makedirs(model_dir, exist_ok=True)
    
    print(f"Loading processed data from {data_path}...")
    df = pd.read_parquet(data_path)
    
    # Backward compatibility with older datasets
    if 'target_up' not in df.columns:
        if 'target_7pct_10d' in df.columns:
            df['target_up'] = df['target_7pct_10d']
        else:
            df['target_up'] = (df['fwd_return_10'] >= buy_threshold).astype(int)
            
    if 'target_down' not in df.columns:
        if 'target_drop_7pct_10d' in df.columns:
            df['target_down'] = df['target_drop_7pct_10d']
        else:
            df['target_down'] = (df['fwd_return_10'] <= -sell_threshold).astype(int)
    
    # Split by time (Training: < 2023, Val: 2023)
    df['date'] = pd.to_datetime(df['date'])
    train_df = df[df['date'].dt.year < 2023]
    val_df = df[df['date'].dt.year == 2023]
    
    ts_features = [
        'ret_open', 'ret_high', 'ret_low', 'ret_close', 'ret_volume', 'ret_obv', 
        'rsi_14', 'macd', 'macds', 'macdh', 'kdjk', 'kdjd', 'cci_14', 'adx', 
        'dist_sma_20', 'dist_ema_20', 'boll_pos'
    ]
    
    train_ds = StockDataset(train_df, lookback=lookback, features=ts_features)
    val_ds = StockDataset(val_df, lookback=lookback, features=ts_features)
    
    train_loader = DataLoader(train_ds, batch_size=128, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=128)
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    
    # Stage 0.5: Transformer Optuna Tuning
    print("--- Stage 0.5: Optuna Hyperparameter Tuning for Transformer ---")
    def objective_transformer(trial):
        d_model = trial.suggest_categorical('d_model', [32, 64, 128])
        nhead = trial.suggest_categorical('nhead', [2, 4, 8])
        
        # Ensure d_model is divisible by nhead
        if d_model % nhead != 0:
            raise optuna.exceptions.TrialPruned()
            
        num_layers = trial.suggest_int('num_layers', 1, 4)
        dim_feedforward = trial.suggest_categorical('dim_feedforward', [64, 128, 256, 512])
        dropout = trial.suggest_float('dropout', 0.1, 0.5)
        lr = trial.suggest_float('lr', 1e-4, 1e-2, log=True)
        
        model_tmp = HybridAIModel(
            input_dim=len(ts_features), 
            d_model=d_model,
            nhead=nhead,
            num_layers=num_layers,
            dim_feedforward=dim_feedforward,
            dropout=dropout
        ).to(device)
        pretrain_head_tmp = nn.Linear(d_model, 1).to(device)
        
        criterion_tmp = nn.MSELoss()
        optimizer_tmp = optim.Adam(list(model_tmp.parameters()) + list(pretrain_head_tmp.parameters()), lr=lr)
        
        tune_epochs = 5 # Evaluated more thoroughly for hyperparam search
        
        model_tmp.train()
        for epoch in range(tune_epochs):
            for x, y, y_up, y_down in train_loader:
                x, y = x.to(device), y.to(device)
                optimizer_tmp.zero_grad()
                emb = model_tmp(x)
                pred = pretrain_head_tmp(emb).squeeze()
                loss = criterion_tmp(pred, y)
                loss.backward()
                optimizer_tmp.step()
                
        # Validation evaluation
        model_tmp.eval()
        val_loss = 0
        with torch.no_grad():
            for x, y, y_up, y_down in val_loader:
                x, y = x.to(device), y.to(device)
                emb = model_tmp(x)
                pred = pretrain_head_tmp(emb).squeeze()
                loss = criterion_tmp(pred, y)
                val_loss += loss.item()
                
        return val_loss / len(val_loader)
        
    study_transformer = optuna.create_study(direction='minimize')
    study_transformer.optimize(objective_transformer, n_trials=n_trials_transformer)
    
    print("Transformer Optuna Best Parameters:", study_transformer.best_params)
    t_best = study_transformer.best_params

    # Stage 1: Train Transformer with Best Parameters
    print("--- Stage 1: Training Final Transformer (Feature Extractor) ---")
    model = HybridAIModel(
        input_dim=len(ts_features),
        d_model=t_best['d_model'],
        nhead=t_best['nhead'],
        num_layers=t_best['num_layers'],
        dim_feedforward=t_best['dim_feedforward'],
        dropout=t_best['dropout']
    ).to(device)
    # Head for pre-training (regression task to learn embeddings)
    pretrain_head = nn.Linear(t_best['d_model'], 1).to(device) 
    
    criterion = nn.MSELoss()
    optimizer = optim.Adam(list(model.parameters()) + list(pretrain_head.parameters()), lr=t_best['lr'])
    
    best_val_loss = float('inf')
    best_model_state = None
    patience = 5
    patience_counter = 0
    
    for epoch in range(epochs):
        model.train()
        total_loss = 0
        for x, y, y_up, y_down in tqdm(train_loader, desc=f"Epoch {epoch+1}"):
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad()
            emb = model(x)
            pred = pretrain_head(emb).squeeze()
            loss = criterion(pred, y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
            
        # Validation for early stopping
        model.eval()
        val_loss = 0
        with torch.no_grad():
            for x, y, y_up, y_down in val_loader:
                x, y = x.to(device), y.to(device)
                emb = model(x)
                pred = pretrain_head(emb).squeeze()
                loss = criterion(pred, y)
                val_loss += loss.item()
        
        val_loss /= len(val_loader)
        train_loss = total_loss/len(train_loader)
        print(f"Epoch {epoch+1} Train Loss: {train_loss:.6f} | Val Loss: {val_loss:.6f}")
        
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            # Save the best model state
            best_model_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print(f"Early stopping at epoch {epoch+1} (Best Val Loss: {best_val_loss:.6f})")
                break
                
    if best_model_state is not None:
        model.load_state_dict(best_model_state)
        print("Loaded best transformer from early stopping checkpoint.")

    # Save Transformer (the engine)
    torch.save(model.state_dict(), os.path.join(model_dir, 'transformer_engine.pt'))
    
    # Stage 2: Train XGBoost Head
    print("--- Stage 2: Training XGBoost Head (Multi-Target) ---")
    model.eval()
    
    def extract_embeddings(loader):
        embeddings = []
        labels_up = []
        labels_down = []
        with torch.no_grad():
            for x, y, y_up, y_down in tqdm(loader, desc="Extracting embeddings"):
                x = x.to(device)
                emb = model(x)
                embeddings.append(emb.cpu().numpy())
                # Use robust labels directly
                labels_up.append(y_up.numpy())
                labels_down.append(y_down.numpy())
        
        y_combined = np.column_stack((np.concatenate(labels_up), np.concatenate(labels_down)))
        return np.vstack(embeddings), y_combined

    train_emb, train_y = extract_embeddings(train_loader)
    val_emb, val_y = extract_embeddings(val_loader)
    
    print("--- Stage 2.5: Optuna Hyperparameter Tuning for XGBoost (Multi-Target) ---")
    def objective_xgb(trial):
        param = {
            'n_estimators': trial.suggest_int('n_estimators', 100, 1000, step=100),
            'max_depth': trial.suggest_int('max_depth', 3, 10),
            'learning_rate': trial.suggest_float('learning_rate', 1e-3, 0.3, log=True),
            'subsample': trial.suggest_float('subsample', 0.6, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
            'tree_method': 'hist',
            'device': str(device) if device.type == 'cuda' else 'cpu',
            'objective': 'binary:logistic'
        }
        
        xgb_tmp = xgb.XGBClassifier(**param)
        xgb_tmp.fit(
            train_emb, train_y,
            eval_set=[(val_emb, val_y)],
            verbose=False
        )
        
        preds_proba = xgb_tmp.predict_proba(val_emb)
        score_up = average_precision_score(val_y[:, 0], preds_proba[:, 0])
        score_down = average_precision_score(val_y[:, 1], preds_proba[:, 1])
        return (score_up + score_down) / 2.0

    study_xgb = optuna.create_study(direction='maximize')
    study_xgb.optimize(objective_xgb, n_trials=n_trials_xgb)
    
    print("--- Stage 3: Training Final XGBoost Head (Multi-Target) ---")
    best_params_xgb = study_xgb.best_params
    best_params_xgb['tree_method'] = 'hist'
    best_params_xgb['device'] = str(device) if device.type == 'cuda' else 'cpu'
    best_params_xgb['objective'] = 'binary:logistic'

    xgb_model_final = xgb.XGBClassifier(**best_params_xgb)
    xgb_model_final.fit(train_emb, train_y, eval_set=[(val_emb, val_y)], verbose=False)
    xgb_model_final.save_model(os.path.join(model_dir, 'xgboost_head.json'))

    # Save Metadata
    import json
    meta = {
        "buy_threshold": buy_threshold,
        "sell_threshold": sell_threshold,
        "lookback": lookback,
        "features": ts_features,
        "d_model": t_best['d_model'],
        "nhead": t_best['nhead'],
        "num_layers": t_best['num_layers'],
        "dim_feedforward": t_best['dim_feedforward'],
        "dropout": t_best['dropout'],
        "xgb_params": best_params_xgb,
        "trained_at": str(pd.Timestamp.now())
    }
    with open(os.path.join(model_dir, 'model_meta.json'), 'w') as f:
        json.dump(meta, f, indent=4)

    print("Hybrid model UP & DROP training complete. Metadata saved.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_path", default="/Users/eugene/nullalgo/simons/model/training_data_processed.parquet")
    parser.add_argument("--model_dir", default="/Users/eugene/nullalgo/simons/model")
    parser.add_argument("--buy_threshold", type=float, default=0.07)
    parser.add_argument("--sell_threshold", type=float, default=0.07)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--n_trials_transformer", type=int, default=10)
    parser.add_argument("--n_trials_xgb", type=int, default=20)
    args = parser.parse_args()
    
    train_hybrid_model(
        args.data_path, 
        args.model_dir, 
        epochs=args.epochs, 
        n_trials_transformer=args.n_trials_transformer, 
        n_trials_xgb=args.n_trials_xgb,
        buy_threshold=args.buy_threshold,
        sell_threshold=args.sell_threshold
    )

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
        
        return torch.from_numpy(x), torch.tensor(y, dtype=torch.float32)

def train_hybrid_model(data_path, model_dir, lookback=60, epochs=30, n_trials_transformer=10, n_trials_xgb=20):
    os.makedirs(model_dir, exist_ok=True)
    
    print(f"Loading processed data from {data_path}...")
    df = pd.read_parquet(data_path)
    
    # Split by time (Training: < 2023, Val: 2023)
    df['date'] = pd.to_datetime(df['date'])
    train_df = df[df['date'].dt.year < 2023]
    val_df = df[df['date'].dt.year == 2023]
    
    ts_features = ['ret_open', 'ret_high', 'ret_low', 'ret_close', 'ret_volume', 'rsi_14']
    
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
            for x, y in train_loader:
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
            for x, y in val_loader:
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
        for x, y in tqdm(train_loader, desc=f"Epoch {epoch+1}"):
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
            for x, y in val_loader:
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
    print("--- Stage 2: Training XGBoost Head ---")
    model.eval()
    
    def extract_embeddings(loader):
        embeddings = []
        labels = []
        with torch.no_grad():
            for x, y in tqdm(loader, desc="Extracting embeddings"):
                x = x.to(device)
                emb = model(x)
                embeddings.append(emb.cpu().numpy())
                # For XGBoost target: target_7pct_10d (binary)
                # Note: StockDataset returns 'fwd_return_10', we need to map back to binary
                labels.append((y >= 0.07).float().numpy())
        
        return np.vstack(embeddings), np.concatenate(labels)

    train_emb, train_y = extract_embeddings(train_loader)
    val_emb, val_y = extract_embeddings(val_loader)
    
    print("--- Stage 2.5: Optuna Hyperparameter Tuning for XGBoost ---")
    def objective(trial):
        param = {
            'n_estimators': trial.suggest_int('n_estimators', 100, 1000, step=100),
            'max_depth': trial.suggest_int('max_depth', 3, 10),
            'learning_rate': trial.suggest_float('learning_rate', 1e-3, 0.3, log=True),
            'subsample': trial.suggest_float('subsample', 0.6, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
            'tree_method': 'hist',
            'device': str(device) if device.type == 'cuda' else 'cpu'
        }
        
        xgb_tmp = xgb.XGBClassifier(**param)
        xgb_tmp.fit(
            train_emb, train_y,
            eval_set=[(val_emb, val_y)],
            verbose=False
        )
        
        # Use predict_proba and average_precision_score (PR-AUC)
        # This focuses on the accuracy of top ranked probabilities, avoiding threshold mismatch
        preds_proba = xgb_tmp.predict_proba(val_emb)[:, 1]
        score = average_precision_score(val_y, preds_proba)
        
        return score

    study = optuna.create_study(direction='maximize')
    study.optimize(objective, n_trials=n_trials_xgb)
    
    print("Optuna Best Parameters:", study.best_params)
    
    print("--- Stage 3: Training Final XGBoost Head ---")
    best_params = study.best_params
    best_params['tree_method'] = 'hist'
    # Ensure device logic is correct for XGBoost 'device' parameter mapping
    best_params['device'] = str(device) if device.type == 'cuda' else 'cpu'

    xgb_model = xgb.XGBClassifier(**best_params)
    
    print("Fitting XGBoost with best params...")
    xgb_model.fit(
        train_emb, train_y,
        eval_set=[(val_emb, val_y)],
        verbose=False
    )
    
    # Save XGBoost
    xgb_model.save_model(os.path.join(model_dir, 'xgboost_head.json'))
    print("Hybrid model training complete.")

if __name__ == "__main__":
    DATA_PATH = "/Users/eugene/nullalgo/simons/model/training_data_processed.parquet"
    MODEL_DIR = "/Users/eugene/nullalgo/simons/model"
    train_hybrid_model(DATA_PATH, MODEL_DIR, epochs=30, n_trials_transformer=10, n_trials_xgb=20)

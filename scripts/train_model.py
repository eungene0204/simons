import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import pandas as pd
import numpy as np
import xgboost as xgb
import os
import joblib
from tqdm import tqdm
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

def train_hybrid_model(data_path, model_dir, lookback=60, epochs=5):
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
    
    # Stage 1: Train Transformer
    print("--- Stage 1: Training Transformer (Feature Extractor) ---")
    model = HybridAIModel(input_dim=len(ts_features)).to(device)
    # Head for pre-training (regression task to learn embeddings)
    pretrain_head = nn.Linear(64, 1).to(device) 
    
    criterion = nn.MSELoss()
    optimizer = optim.Adam(list(model.parameters()) + list(pretrain_head.parameters()), lr=0.001)
    
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
        
        print(f"Epoch {epoch+1} Loss: {total_loss/len(train_loader):.6f}")

    # Save Transformer (the engine)
    torch.save(model.state_dict(), os.path.join(model_dir, 'transformer_engine.pt'))
    
    # Stage 2: Train XGBoost Head
    print("--- Stage 2: Training XGBoost Head ---")
    model.eval()
    
    def extract_embeddings(loader):
        embeddings = []
        labels = []
        static_feats = []
        with torch.no_grad():
            for x, y in tqdm(loader, desc="Extracting embeddings"):
                x = x.to(device)
                emb = model(x)
                embeddings.append(emb.cpu().numpy())
                # For XGBoost target: target_7pct_10d (binary)
                # Note: StockDataset returns 'fwd_return_10', we need to map back to binary
                # To be efficient, we'll re-extract target_7pct_10d from raw df later if needed,
                # but for now let's use a simpler approach.
                labels.append((y >= 0.07).float().numpy())
        
        return np.vstack(embeddings), np.concatenate(labels)

    train_emb, train_y = extract_embeddings(train_loader)
    val_emb, val_y = extract_embeddings(val_loader)
    
    xgb_model = xgb.XGBClassifier(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        tree_method='hist',
        device=device if torch.cuda.is_available() else 'cpu'
    )
    
    print("Fitting XGBoost...")
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
    train_hybrid_model(DATA_PATH, MODEL_DIR, epochs=1) # 1 epoch for quick verification

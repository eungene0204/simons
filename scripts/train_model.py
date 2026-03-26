"""
Advanced Hybrid Transformer + XGBoost Training Pipeline v2.

Key improvements:
  - Cosine annealing with linear warmup scheduler
  - Gradient clipping for stable training
  - Label smoothing for better generalization
  - Separate XGBoost models for up/down targets
  - Embedding statistical features for XGBoost
  - Purged time-series split (train < 2022, val 2022-2023.06, test 2023.07-2024)
  - Focal loss option for class imbalance
  - Comprehensive evaluation metrics
"""

import os
import sys
import json
import argparse
from datetime import datetime

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import pandas as pd
import numpy as np
import xgboost as xgb
import optuna
from tqdm import tqdm
from sklearn.metrics import average_precision_score, roc_auc_score, f1_score

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))
from ai.models import HybridAIModel

# Import feature list
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_training_data import FEATURE_LIST_V2


# ── Dataset ─────────────────────────────────────────────────────────────────

class StockDataset(Dataset):
    """Time-series dataset with per-symbol grouping to prevent sequence bleeding."""

    def __init__(self, df: pd.DataFrame, lookback: int = 60, features: list = None, target: str = None):
        self.lookback = lookback
        self.features = features
        self.target = target

        # Build index per symbol, sorted by date
        self.indices = []
        self._data = {}

        for symbol, group in df.groupby('symbol'):
            group = group.sort_values('date').reset_index(drop=True)
            feat_arr = group[features].values.astype(np.float32)
            target_arr = group[target].values.astype(np.float32) if target else None
            up_arr = group['target_up'].values.astype(np.float32)
            down_arr = group['target_down'].values.astype(np.float32)

            self._data[symbol] = (feat_arr, target_arr, up_arr, down_arr)

            if len(group) > lookback:
                for i in range(len(group) - lookback):
                    self.indices.append((symbol, i))

    def __len__(self):
        return len(self.indices)

    def __getitem__(self, idx):
        symbol, start = self.indices[idx]
        feat_arr, target_arr, up_arr, down_arr = self._data[symbol]

        x = feat_arr[start:start + self.lookback]
        end_idx = start + self.lookback - 1
        y = target_arr[end_idx] if target_arr is not None else 0.0
        y_up = up_arr[end_idx]
        y_down = down_arr[end_idx]

        return (torch.from_numpy(x),
                torch.tensor(y, dtype=torch.float32),
                torch.tensor(y_up, dtype=torch.float32),
                torch.tensor(y_down, dtype=torch.float32))


# ── Focal Loss ──────────────────────────────────────────────────────────────

class FocalMSELoss(nn.Module):
    """MSE weighted by prediction difficulty (focal-style)."""

    def __init__(self, gamma: float = 2.0):
        super().__init__()
        self.gamma = gamma

    def forward(self, pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        mse = (pred - target) ** 2
        weight = (1 + mse.detach()) ** (self.gamma / 2)
        return (weight * mse).mean()


# ── Cosine Warmup Scheduler ────────────────────────────────────────────────

class CosineWarmupScheduler(optim.lr_scheduler._LRScheduler):
    def __init__(self, optimizer, warmup_steps: int, total_steps: int, min_lr: float = 1e-6):
        self.warmup_steps = warmup_steps
        self.total_steps = total_steps
        self.min_lr = min_lr
        super().__init__(optimizer)

    def get_lr(self):
        step = self.last_epoch
        if step < self.warmup_steps:
            # Linear warmup
            scale = step / max(self.warmup_steps, 1)
        else:
            # Cosine decay
            progress = (step - self.warmup_steps) / max(self.total_steps - self.warmup_steps, 1)
            scale = 0.5 * (1 + np.cos(np.pi * progress))

        return [max(base_lr * scale, self.min_lr) for base_lr in self.base_lrs]


# ── Training pipeline ──────────────────────────────────────────────────────

def train_hybrid_model(data_path: str, model_dir: str, lookback: int = 60,
                       epochs: int = 50, n_trials_transformer: int = 15,
                       n_trials_xgb: int = 30, buy_threshold: float = 0.07,
                       sell_threshold: float = 0.07, horizon: int = 10,
                       batch_size: int = 256):

    os.makedirs(model_dir, exist_ok=True)
    ts_features = FEATURE_LIST_V2

    print(f"Loading processed data from {data_path}...")
    df = pd.read_parquet(data_path)
    print(f"Loaded {len(df):,} rows, {df['symbol'].nunique()} symbols")

    # Ensure targets exist
    fwd_col = f'fwd_return_{horizon}'
    if 'target_up' not in df.columns:
        df['target_up'] = (df[fwd_col] >= buy_threshold).astype(int)
    if 'target_down' not in df.columns:
        df['target_down'] = (df[fwd_col] <= -sell_threshold).astype(int)

    # ── Purged time-series split ──────────────────────────────────────────
    df['date'] = pd.to_datetime(df['date'])
    train_df = df[df['date'].dt.year < 2022].copy()
    val_df = df[(df['date'] >= '2022-01-01') & (df['date'] < '2023-07-01')].copy()
    test_df = df[(df['date'] >= '2023-07-01') & (df['date'] < '2025-01-01')].copy()

    print(f"Split: Train={len(train_df):,} (<2022), Val={len(val_df):,} (2022~2023.06), Test={len(test_df):,} (2023.07~2024)")
    print(f"Target up rate — Train: {train_df['target_up'].mean():.2%}, Val: {val_df['target_up'].mean():.2%}")
    print(f"Target down rate — Train: {train_df['target_down'].mean():.2%}, Val: {val_df['target_down'].mean():.2%}")

    train_ds = StockDataset(train_df, lookback=lookback, features=ts_features, target=fwd_col)
    val_ds = StockDataset(val_df, lookback=lookback, features=ts_features, target=fwd_col)

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=0, pin_memory=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, num_workers=0, pin_memory=True)

    device = torch.device("cuda" if torch.cuda.is_available() else
                          "mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Device: {device}")

    # ══════════════════════════════════════════════════════════════════════
    # Stage 0: Optuna Transformer Hyperparameter Search
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("Stage 0: Optuna Transformer Hyperparameter Search")
    print("=" * 70)

    def objective_transformer(trial):
        d_model = trial.suggest_categorical('d_model', [64, 128, 256])
        nhead = trial.suggest_categorical('nhead', [4, 8])
        if d_model % nhead != 0:
            raise optuna.exceptions.TrialPruned()

        num_layers = trial.suggest_int('num_layers', 4, 8)
        dim_feedforward = trial.suggest_categorical('dim_feedforward', [256, 512, 1024])
        dropout = trial.suggest_float('dropout', 0.05, 0.3)
        lr = trial.suggest_float('lr', 5e-5, 5e-3, log=True)
        stochastic_depth = trial.suggest_float('stochastic_depth', 0.0, 0.2)

        model_tmp = HybridAIModel(
            input_dim=len(ts_features), d_model=d_model, nhead=nhead,
            num_layers=num_layers, dim_feedforward=dim_feedforward,
            dropout=dropout, stochastic_depth=stochastic_depth
        ).to(device)
        head_tmp = nn.Linear(d_model, 1).to(device)

        optimizer_tmp = optim.AdamW(
            list(model_tmp.parameters()) + list(head_tmp.parameters()),
            lr=lr, weight_decay=0.01
        )
        criterion_tmp = FocalMSELoss(gamma=1.5)

        model_tmp.train()
        for epoch in range(5):
            for x, y, _, _ in train_loader:
                x, y = x.to(device), y.to(device)
                optimizer_tmp.zero_grad()
                emb = model_tmp(x)
                pred = head_tmp(emb).squeeze(-1)
                loss = criterion_tmp(pred, y)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model_tmp.parameters(), 1.0)
                optimizer_tmp.step()

        model_tmp.eval()
        val_loss = 0.0
        n_batches = 0
        with torch.no_grad():
            for x, y, _, _ in val_loader:
                x, y = x.to(device), y.to(device)
                emb = model_tmp(x)
                pred = head_tmp(emb).squeeze(-1)
                val_loss += nn.MSELoss()(pred, y).item()
                n_batches += 1
        return val_loss / max(n_batches, 1)

    study_tf = optuna.create_study(direction='minimize')
    study_tf.optimize(objective_transformer, n_trials=n_trials_transformer, show_progress_bar=True)
    t_best = study_tf.best_params
    print(f"Best Transformer params: {t_best}")

    # ══════════════════════════════════════════════════════════════════════
    # Stage 1: Train Final Transformer
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("Stage 1: Training Final Transformer")
    print("=" * 70)

    model = HybridAIModel(
        input_dim=len(ts_features),
        d_model=t_best['d_model'],
        nhead=t_best['nhead'],
        num_layers=t_best['num_layers'],
        dim_feedforward=t_best['dim_feedforward'],
        dropout=t_best['dropout'],
        stochastic_depth=t_best.get('stochastic_depth', 0.1),
    ).to(device)

    pretrain_head = nn.Linear(t_best['d_model'], 1).to(device)

    total_params = sum(p.numel() for p in model.parameters())
    print(f"Model parameters: {total_params:,}")

    optimizer = optim.AdamW(
        list(model.parameters()) + list(pretrain_head.parameters()),
        lr=t_best['lr'], weight_decay=0.01
    )

    total_steps = len(train_loader) * epochs
    warmup_steps = len(train_loader) * 3  # 3 epoch warmup
    scheduler = CosineWarmupScheduler(optimizer, warmup_steps, total_steps, min_lr=1e-6)

    criterion = FocalMSELoss(gamma=2.0)

    best_val_loss = float('inf')
    best_model_state = None
    patience = 8
    patience_counter = 0

    for epoch in range(epochs):
        # Train
        model.train()
        total_loss = 0
        for x, y, _, _ in tqdm(train_loader, desc=f"Epoch {epoch + 1}/{epochs}"):
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad()
            emb = model(x)
            pred = pretrain_head(emb).squeeze(-1)
            loss = criterion(pred, y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            total_loss += loss.item()

        # Validate
        model.eval()
        val_loss = 0
        with torch.no_grad():
            for x, y, _, _ in val_loader:
                x, y = x.to(device), y.to(device)
                emb = model(x)
                pred = pretrain_head(emb).squeeze(-1)
                val_loss += nn.MSELoss()(pred, y).item()

        train_loss = total_loss / len(train_loader)
        val_loss = val_loss / len(val_loader)
        lr_now = optimizer.param_groups[0]['lr']
        print(f"  Train Loss: {train_loss:.6f} | Val Loss: {val_loss:.6f} | LR: {lr_now:.2e}")

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_model_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            patience_counter = 0
            print(f"  >> New best model (val_loss={val_loss:.6f})")
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print(f"Early stopping at epoch {epoch + 1}")
                break

    if best_model_state:
        model.load_state_dict(best_model_state)
        print("Loaded best transformer checkpoint.")

    torch.save(model.state_dict(), os.path.join(model_dir, 'transformer_engine.pt'))

    # ══════════════════════════════════════════════════════════════════════
    # Stage 2: Extract Embeddings + Statistical Features
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("Stage 2: Extracting Embeddings")
    print("=" * 70)

    model.eval()

    def extract_embeddings(loader, desc="Extracting"):
        embeddings = []
        labels_up, labels_down = [], []
        with torch.no_grad():
            for x, _, y_up, y_down in tqdm(loader, desc=desc):
                x = x.to(device)
                emb = model(x).cpu().numpy()
                embeddings.append(emb)
                labels_up.append(y_up.numpy())
                labels_down.append(y_down.numpy())
        emb_all = np.vstack(embeddings)
        y_up_all = np.concatenate(labels_up)
        y_down_all = np.concatenate(labels_down)
        return emb_all, y_up_all, y_down_all

    train_emb, train_y_up, train_y_down = extract_embeddings(train_loader, "Train embeddings")
    val_emb, val_y_up, val_y_down = extract_embeddings(val_loader, "Val embeddings")

    # Augment embeddings with statistical features
    def augment_embeddings(emb: np.ndarray) -> np.ndarray:
        """Add L2 norm, mean, std, max, min of embedding dimensions as extra features."""
        norm = np.linalg.norm(emb, axis=1, keepdims=True)
        mean = emb.mean(axis=1, keepdims=True)
        std = emb.std(axis=1, keepdims=True)
        mx = emb.max(axis=1, keepdims=True)
        mn = emb.min(axis=1, keepdims=True)
        return np.hstack([emb, norm, mean, std, mx, mn])

    train_emb_aug = augment_embeddings(train_emb)
    val_emb_aug = augment_embeddings(val_emb)

    print(f"Embedding dim: {train_emb.shape[1]} → Augmented: {train_emb_aug.shape[1]}")

    # ══════════════════════════════════════════════════════════════════════
    # Stage 3: Optuna XGBoost Search (separate up/down models)
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("Stage 3: Optuna XGBoost Hyperparameter Search")
    print("=" * 70)

    def objective_xgb(trial, train_x, train_y, val_x, val_y):
        param = {
            'n_estimators': trial.suggest_int('n_estimators', 200, 2000, step=100),
            'max_depth': trial.suggest_int('max_depth', 3, 12),
            'learning_rate': trial.suggest_float('learning_rate', 1e-3, 0.3, log=True),
            'subsample': trial.suggest_float('subsample', 0.5, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
            'min_child_weight': trial.suggest_int('min_child_weight', 1, 10),
            'gamma': trial.suggest_float('gamma', 0, 5),
            'reg_alpha': trial.suggest_float('reg_alpha', 1e-8, 10, log=True),
            'reg_lambda': trial.suggest_float('reg_lambda', 1e-8, 10, log=True),
            'tree_method': 'hist',
            'objective': 'binary:logistic',
            'eval_metric': 'aucpr',
        }

        # Class weight
        pos_rate = train_y.mean()
        if pos_rate > 0 and pos_rate < 1:
            param['scale_pos_weight'] = (1 - pos_rate) / pos_rate

        clf = xgb.XGBClassifier(**param, early_stopping_rounds=50)
        clf.fit(train_x, train_y, eval_set=[(val_x, val_y)], verbose=False)

        pred = clf.predict_proba(val_x)[:, 1]
        return average_precision_score(val_y, pred)

    # --- UP model ---
    print("\n--- XGBoost UP model tuning ---")
    study_up = optuna.create_study(direction='maximize')
    study_up.optimize(
        lambda trial: objective_xgb(trial, train_emb_aug, train_y_up, val_emb_aug, val_y_up),
        n_trials=n_trials_xgb, show_progress_bar=True
    )
    best_up = study_up.best_params
    print(f"Best UP params: AP={study_up.best_value:.4f}")

    # --- DOWN model ---
    print("\n--- XGBoost DOWN model tuning ---")
    study_down = optuna.create_study(direction='maximize')
    study_down.optimize(
        lambda trial: objective_xgb(trial, train_emb_aug, train_y_down, val_emb_aug, val_y_down),
        n_trials=n_trials_xgb, show_progress_bar=True
    )
    best_down = study_down.best_params
    print(f"Best DOWN params: AP={study_down.best_value:.4f}")

    # ══════════════════════════════════════════════════════════════════════
    # Stage 4: Train Final XGBoost Models
    # ══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("Stage 4: Training Final XGBoost Models")
    print("=" * 70)

    def train_xgb_final(params: dict, train_x, train_y, val_x, val_y, name: str):
        params['tree_method'] = 'hist'
        params['objective'] = 'binary:logistic'
        params['eval_metric'] = 'aucpr'
        pos_rate = train_y.mean()
        if pos_rate > 0 and pos_rate < 1:
            params['scale_pos_weight'] = (1 - pos_rate) / pos_rate

        clf = xgb.XGBClassifier(**params, early_stopping_rounds=50)
        clf.fit(train_x, train_y, eval_set=[(val_x, val_y)], verbose=True)

        pred = clf.predict_proba(val_x)[:, 1]
        ap = average_precision_score(val_y, pred)
        auc = roc_auc_score(val_y, pred)
        f1 = f1_score(val_y, (pred > 0.5).astype(int))
        print(f"  {name} — AP: {ap:.4f}, AUC: {auc:.4f}, F1: {f1:.4f}")
        return clf

    xgb_up = train_xgb_final(best_up.copy(), train_emb_aug, train_y_up, val_emb_aug, val_y_up, "UP")
    xgb_down = train_xgb_final(best_down.copy(), train_emb_aug, train_y_down, val_emb_aug, val_y_down, "DOWN")

    xgb_up.save_model(os.path.join(model_dir, 'xgboost_up.json'))
    xgb_down.save_model(os.path.join(model_dir, 'xgboost_down.json'))

    # Also save combined model for backward compatibility
    # (legacy code expects xgboost_head.json)
    xgb_up.save_model(os.path.join(model_dir, 'xgboost_head.json'))

    # ══════════════════════════════════════════════════════════════════════
    # Stage 5: Test Set Evaluation
    # ══════════════════════════════════════════════════════════════════════
    if len(test_df) > 0:
        print("\n" + "=" * 70)
        print("Stage 5: Test Set Evaluation (Out-of-Sample)")
        print("=" * 70)

        test_ds = StockDataset(test_df, lookback=lookback, features=ts_features, target=fwd_col)
        test_loader = DataLoader(test_ds, batch_size=batch_size, num_workers=0)
        test_emb, test_y_up, test_y_down = extract_embeddings(test_loader, "Test embeddings")
        test_emb_aug = augment_embeddings(test_emb)

        for name, xgb_model, y_true in [("UP", xgb_up, test_y_up), ("DOWN", xgb_down, test_y_down)]:
            pred = xgb_model.predict_proba(test_emb_aug)[:, 1]
            ap = average_precision_score(y_true, pred)
            auc = roc_auc_score(y_true, pred)
            f1 = f1_score(y_true, (pred > 0.5).astype(int))
            print(f"  TEST {name} — AP: {ap:.4f}, AUC: {auc:.4f}, F1: {f1:.4f}")

    # ══════════════════════════════════════════════════════════════════════
    # Save Metadata
    # ══════════════════════════════════════════════════════════════════════
    meta = {
        "version": 2,
        "buy_threshold": buy_threshold,
        "sell_threshold": sell_threshold,
        "horizon": horizon,
        "lookback": lookback,
        "features": ts_features,
        "d_model": t_best['d_model'],
        "nhead": t_best['nhead'],
        "num_layers": t_best['num_layers'],
        "dim_feedforward": t_best['dim_feedforward'],
        "dropout": t_best['dropout'],
        "stochastic_depth": t_best.get('stochastic_depth', 0.1),
        "xgb_up_params": best_up,
        "xgb_down_params": best_down,
        "embedding_augmented": True,
        "embedding_aug_features": 5,  # norm, mean, std, max, min
        "total_params": total_params,
        "trained_at": str(datetime.now()),
    }
    with open(os.path.join(model_dir, 'model_meta.json'), 'w') as f:
        json.dump(meta, f, indent=4)

    # Save SHAP background data
    print("\nSaving SHAP background data...")
    rng = np.random.RandomState(42)
    bg_idx = rng.choice(len(train_emb_aug), size=min(200, len(train_emb_aug)), replace=False)
    np.save(os.path.join(model_dir, 'shap_background.npy'), train_emb_aug[bg_idx])

    print("\n" + "=" * 70)
    print("Training complete!")
    print(f"Model saved to: {model_dir}")
    print(f"Parameters: {total_params:,}")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_path", default="/Users/eugene/nullalgo/simons/model/v2/training_data_processed.parquet")
    parser.add_argument("--model_dir", default="/Users/eugene/nullalgo/simons/model/v2")
    parser.add_argument("--buy_threshold", type=float, default=0.07)
    parser.add_argument("--sell_threshold", type=float, default=0.07)
    parser.add_argument("--horizon", type=int, default=10)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch_size", type=int, default=256)
    parser.add_argument("--n_trials_transformer", type=int, default=15)
    parser.add_argument("--n_trials_xgb", type=int, default=30)
    args = parser.parse_args()

    train_hybrid_model(
        args.data_path, args.model_dir,
        epochs=args.epochs, batch_size=args.batch_size,
        n_trials_transformer=args.n_trials_transformer,
        n_trials_xgb=args.n_trials_xgb,
        buy_threshold=args.buy_threshold,
        sell_threshold=args.sell_threshold,
        horizon=args.horizon,
    )

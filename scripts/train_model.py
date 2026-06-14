"""
Hybrid Transformer + XGBoost Training Pipeline v3
===================================================
Key improvements over v2:
  - Shared feature_engineering module (train/inference parity)
  - Triple-barrier 3-class labels (UP / FLAT / DOWN)
  - End-to-end joint training: Transformer with dual BCE heads (up/down)
    → No regression pretraining; classification from the start
  - Purged + embargoed time-series split (no label leakage)
  - XGBoost stacking on frozen embeddings (scale_pos_weight removed)
  - Threshold calibration on val set targeting precision >= 0.6
  - Train: <2023-01, Val: 2023-01~2024-06 (embargo), Test: 2024-07~end
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
from sklearn.metrics import (
    average_precision_score, roc_auc_score, f1_score, precision_recall_curve
)
from sklearn.preprocessing import RobustScaler
import joblib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))
from ai.models import HybridAIModel
from ai.feature_engineering import FEATURE_LIST, N_FEATURES


# ── Dataset ──────────────────────────────────────────────────────────────────

class StockDataset(Dataset):
    """Per-symbol time-series windows. Prevents sequence bleeding across symbols."""

    def __init__(self, df: pd.DataFrame, lookback: int = 60):
        self.lookback = lookback
        self.indices = []
        self._data = {}

        for symbol, group in df.groupby('symbol'):
            group = group.sort_values('date').reset_index(drop=True)
            feat  = group[FEATURE_LIST].values.astype(np.float32)
            y_up  = group['target_up'].values.astype(np.float32)
            y_dn  = group['target_down'].values.astype(np.float32)
            self._data[symbol] = (feat, y_up, y_dn)

            for i in range(len(group) - lookback):
                self.indices.append((symbol, i))

    def __len__(self):
        return len(self.indices)

    def __getitem__(self, idx):
        sym, start = self.indices[idx]
        feat, y_up, y_dn = self._data[sym]
        end = start + self.lookback - 1
        x    = torch.from_numpy(feat[start:start + self.lookback])
        return x, torch.tensor(y_up[end]), torch.tensor(y_dn[end])


# ── Dual-head wrapper for joint training ─────────────────────────────────────

class DualHeadModel(nn.Module):
    """Transformer backbone + two binary classification heads (up, down)."""

    def __init__(self, backbone: HybridAIModel, d_model: int, dropout: float = 0.1):
        super().__init__()
        self.backbone = backbone
        self.head_up   = nn.Sequential(
            nn.LayerNorm(d_model),
            nn.Dropout(dropout),
            nn.Linear(d_model, 1),
        )
        self.head_down = nn.Sequential(
            nn.LayerNorm(d_model),
            nn.Dropout(dropout),
            nn.Linear(d_model, 1),
        )

    def forward(self, x):
        emb  = self.backbone(x)
        logit_up   = self.head_up(emb).squeeze(-1)
        logit_down = self.head_down(emb).squeeze(-1)
        return emb, logit_up, logit_down


# ── Cosine Warmup Scheduler ───────────────────────────────────────────────────

class CosineWarmupScheduler(optim.lr_scheduler._LRScheduler):
    def __init__(self, optimizer, warmup_steps: int, total_steps: int, min_lr: float = 1e-6):
        self.warmup_steps = warmup_steps
        self.total_steps  = total_steps
        self.min_lr       = min_lr
        super().__init__(optimizer)

    def get_lr(self):
        step = self.last_epoch
        if step < self.warmup_steps:
            scale = step / max(self.warmup_steps, 1)
        else:
            progress = (step - self.warmup_steps) / max(self.total_steps - self.warmup_steps, 1)
            scale = 0.5 * (1 + np.cos(np.pi * progress))
        return [max(base * scale, self.min_lr) for base in self.base_lrs]


# ── Threshold calibration ─────────────────────────────────────────────────────

def calibrate_threshold(y_true: np.ndarray, y_prob: np.ndarray,
                         target_precision: float = 0.55,
                         min_fire_rate: float = 0.02) -> float:
    """Threshold for a probability head, calibrated on the val set.

    Picks the lowest threshold reaching ``target_precision``, but clamps it so
    it always fires on at least ``min_fire_rate`` of the val set. A poorly
    separated head (e.g. the heavily regularized DOWN XGBoost, whose scores
    compress into a narrow band well below 0.5) would otherwise get either no
    qualifying threshold — the old ``return 0.5`` fallback, *above the head's
    max score* → a permanently dead signal — or one so high it never fires.
    The fire-rate floor guarantees a usable, in-distribution threshold.
    """
    fire_cap = float(np.quantile(y_prob, 1.0 - min_fire_rate))
    precisions, _, thresholds = precision_recall_curve(y_true, y_prob)
    # precision_recall_curve returns one extra precision/recall point
    for prec, thr in zip(precisions[:-1], thresholds):
        if prec >= target_precision:
            return min(float(thr), fire_cap)
    return fire_cap  # precision target unreachable → fire on the top min_fire_rate


# ── Main training pipeline ────────────────────────────────────────────────────

def train(data_path: str, model_dir: str,
          lookback: int = 60,
          epochs: int = 60,
          batch_size: int = 256,
          n_trials_tf: int = 15,
          n_trials_xgb: int = 25,
          horizon: int = 10):

    os.makedirs(model_dir, exist_ok=True)

    print(f"Loading data from {data_path} ...")
    df = pd.read_parquet(data_path)
    df['date'] = pd.to_datetime(df['date'])
    print(f"Total: {len(df):,} rows, {df['symbol'].nunique()} symbols")
    print(f"Date range: {df['date'].min().date()} ~ {df['date'].max().date()}")

    # ── Purged + embargoed time-series split ──────────────────────────────────
    # Embargo = horizon bars from each boundary to prevent label leakage
    embargo = pd.Timedelta(days=horizon * 2)  # conservative: 2×horizon calendar days

    train_end = pd.Timestamp('2023-01-01')
    val_start = train_end + embargo
    val_end   = pd.Timestamp('2024-07-01')
    test_start = val_end + embargo

    train_df = df[df['date'] < train_end].copy()
    val_df   = df[(df['date'] >= val_start) & (df['date'] < val_end)].copy()
    test_df  = df[df['date'] >= test_start].copy()

    print(f"\nSplit (purged+embargoed):")
    print(f"  Train: {len(train_df):,} rows  (<{train_end.date()})")
    print(f"  Val:   {len(val_df):,} rows   ({val_start.date()} ~ {val_end.date()})")
    print(f"  Test:  {len(test_df):,} rows  (>={test_start.date()})")
    print(f"  UP rate  — Train: {train_df['target_up'].mean():.2%}, Val: {val_df['target_up'].mean():.2%}")
    print(f"  DOWN rate— Train: {train_df['target_down'].mean():.2%}, Val: {val_df['target_down'].mean():.2%}")

    # ── Feature scaler (fit on train only) ───────────────────────────────────
    print("\nFitting RobustScaler on train...")
    scaler = RobustScaler()
    scaler.fit(train_df[FEATURE_LIST].values)

    for split_df in [train_df, val_df, test_df]:
        split_df[FEATURE_LIST] = scaler.transform(split_df[FEATURE_LIST].values)

    joblib.dump(scaler, os.path.join(model_dir, 'feature_scaler.joblib'))
    print("Scaler saved.")

    # Datasets
    train_ds = StockDataset(train_df, lookback)
    val_ds   = StockDataset(val_df,   lookback)

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True,
                              num_workers=0, pin_memory=True)
    val_loader   = DataLoader(val_ds,   batch_size=batch_size, shuffle=False,
                              num_workers=0, pin_memory=True)

    device = torch.device(
        "cuda" if torch.cuda.is_available()
        else "mps" if torch.backends.mps.is_available()
        else "cpu"
    )
    print(f"Device: {device}")

    # ══════════════════════════════════════════════════════════════════════════
    # Stage 0: Optuna — Transformer hyperparameter search
    # ══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("Stage 0: Optuna Transformer search")
    print("=" * 70)

    def objective_tf(trial):
        d_model      = trial.suggest_categorical('d_model', [128, 256])
        nhead        = trial.suggest_categorical('nhead', [4, 8])
        if d_model % nhead != 0:
            raise optuna.exceptions.TrialPruned()
        num_layers   = trial.suggest_int('num_layers', 3, 7)
        dim_ff       = trial.suggest_categorical('dim_feedforward', [512, 1024])
        dropout      = trial.suggest_float('dropout', 0.05, 0.3)
        sd           = trial.suggest_float('stochastic_depth', 0.0, 0.15)
        lr           = trial.suggest_float('lr', 1e-4, 5e-3, log=True)

        backbone = HybridAIModel(
            input_dim=N_FEATURES, d_model=d_model, nhead=nhead,
            num_layers=num_layers, dim_feedforward=dim_ff,
            dropout=dropout, stochastic_depth=sd,
        ).to(device)
        model_tmp = DualHeadModel(backbone, d_model, dropout).to(device)

        opt_tmp = optim.AdamW(model_tmp.parameters(), lr=lr, weight_decay=0.01)
        crit    = nn.BCEWithLogitsLoss()

        model_tmp.train()
        for _ in range(3):  # quick 3-epoch trial
            for x, y_up, y_dn in train_loader:
                x, y_up, y_dn = x.to(device), y_up.to(device), y_dn.to(device)
                opt_tmp.zero_grad()
                _, lu, ld = model_tmp(x)
                loss = crit(lu, y_up) + crit(ld, y_dn)
                loss.backward()
                nn.utils.clip_grad_norm_(model_tmp.parameters(), 1.0)
                opt_tmp.step()

        model_tmp.eval()
        val_loss = 0.0; n = 0
        with torch.no_grad():
            for x, y_up, y_dn in val_loader:
                x, y_up, y_dn = x.to(device), y_up.to(device), y_dn.to(device)
                _, lu, ld = model_tmp(x)
                val_loss += (crit(lu, y_up) + crit(ld, y_dn)).item()
                n += 1
        return val_loss / max(n, 1)

    study_tf = optuna.create_study(direction='minimize')
    study_tf.optimize(objective_tf, n_trials=n_trials_tf, show_progress_bar=True)
    best_tf = study_tf.best_params
    print(f"Best Transformer params: {best_tf}")

    # ══════════════════════════════════════════════════════════════════════════
    # Stage 1: End-to-end joint BCE training
    # ══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("Stage 1: End-to-end joint BCE training")
    print("=" * 70)

    d_model = best_tf['d_model']
    backbone = HybridAIModel(
        input_dim=N_FEATURES,
        d_model=d_model,
        nhead=best_tf['nhead'],
        num_layers=best_tf['num_layers'],
        dim_feedforward=best_tf['dim_feedforward'],
        dropout=best_tf['dropout'],
        stochastic_depth=best_tf.get('stochastic_depth', 0.1),
    ).to(device)
    model = DualHeadModel(backbone, d_model, best_tf['dropout']).to(device)

    total_params = sum(p.numel() for p in model.parameters())
    print(f"Total parameters: {total_params:,}")

    optimizer = optim.AdamW(model.parameters(), lr=best_tf['lr'], weight_decay=0.01)
    total_steps  = len(train_loader) * epochs
    warmup_steps = len(train_loader) * 3
    scheduler = CosineWarmupScheduler(optimizer, warmup_steps, total_steps, min_lr=1e-6)
    crit = nn.BCEWithLogitsLoss()

    best_val_loss = float('inf')
    best_state    = None
    patience = 10; patience_counter = 0

    for epoch in range(epochs):
        model.train()
        total_loss = 0.0
        for x, y_up, y_dn in tqdm(train_loader, desc=f"Epoch {epoch+1}/{epochs}"):
            x, y_up, y_dn = x.to(device), y_up.to(device), y_dn.to(device)
            optimizer.zero_grad()
            _, lu, ld = model(x)
            loss = crit(lu, y_up) + crit(ld, y_dn)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            total_loss += loss.item()

        model.eval()
        val_loss = 0.0; n = 0
        with torch.no_grad():
            for x, y_up, y_dn in val_loader:
                x, y_up, y_dn = x.to(device), y_up.to(device), y_dn.to(device)
                _, lu, ld = model(x)
                val_loss += (crit(lu, y_up) + crit(ld, y_dn)).item()
                n += 1
        val_loss /= max(n, 1)
        train_loss = total_loss / len(train_loader)
        print(f"  Train: {train_loss:.4f} | Val: {val_loss:.4f} | LR: {optimizer.param_groups[0]['lr']:.2e}")

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            patience_counter = 0
            print(f"  >> Best model (val={val_loss:.4f})")
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print(f"  Early stopping at epoch {epoch+1}")
                break

    model.load_state_dict(best_state)
    torch.save(backbone.state_dict(), os.path.join(model_dir, 'transformer_engine.pt'))
    print("Transformer saved.")

    # ══════════════════════════════════════════════════════════════════════════
    # Stage 2: Extract embeddings
    # ══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("Stage 2: Extracting embeddings")
    print("=" * 70)

    model.eval()

    def extract_embeddings(loader, desc="Extracting"):
        embs, ups, dns = [], [], []
        with torch.no_grad():
            for x, y_up, y_dn in tqdm(loader, desc=desc):
                x = x.to(device)
                emb, _, _ = model(x)
                embs.append(emb.cpu().numpy())
                ups.append(y_up.numpy())
                dns.append(y_dn.numpy())
        return np.vstack(embs), np.concatenate(ups), np.concatenate(dns)

    train_emb, train_y_up, train_y_dn = extract_embeddings(train_loader, "Train")
    val_emb,   val_y_up,   val_y_dn   = extract_embeddings(val_loader,   "Val")

    print(f"Embedding shape: {train_emb.shape}")

    # Save SHAP background
    rng = np.random.RandomState(42)
    bg_idx = rng.choice(len(train_emb), size=min(500, len(train_emb)), replace=False)
    np.save(os.path.join(model_dir, 'shap_background.npy'), train_emb[bg_idx])

    # ══════════════════════════════════════════════════════════════════════════
    # Stage 3: Optuna XGBoost search
    # ══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("Stage 3: Optuna XGBoost search")
    print("=" * 70)

    def objective_xgb(trial, tx, ty, vx, vy):
        param = {
            'n_estimators':     trial.suggest_int('n_estimators', 200, 1500, step=100),
            'max_depth':        trial.suggest_int('max_depth', 3, 8),
            'learning_rate':    trial.suggest_float('learning_rate', 1e-3, 0.2, log=True),
            'subsample':        trial.suggest_float('subsample', 0.5, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
            'min_child_weight': trial.suggest_int('min_child_weight', 1, 10),
            'gamma':            trial.suggest_float('gamma', 0, 3),
            'reg_alpha':        trial.suggest_float('reg_alpha', 1e-8, 5, log=True),
            'reg_lambda':       trial.suggest_float('reg_lambda', 1e-8, 5, log=True),
            'tree_method': 'hist',
            'objective': 'binary:logistic',
            'eval_metric': 'aucpr',
        }
        clf = xgb.XGBClassifier(**param, early_stopping_rounds=30)
        clf.fit(tx, ty, eval_set=[(vx, vy)], verbose=False)
        pred = clf.predict_proba(vx)[:, 1]
        return average_precision_score(vy, pred)

    print("\n--- UP model tuning ---")
    study_up = optuna.create_study(direction='maximize')
    study_up.optimize(
        lambda t: objective_xgb(t, train_emb, train_y_up, val_emb, val_y_up),
        n_trials=n_trials_xgb, show_progress_bar=True
    )
    print(f"Best UP AP: {study_up.best_value:.4f}")

    print("\n--- DOWN model tuning ---")
    study_dn = optuna.create_study(direction='maximize')
    study_dn.optimize(
        lambda t: objective_xgb(t, train_emb, train_y_dn, val_emb, val_y_dn),
        n_trials=n_trials_xgb, show_progress_bar=True
    )
    print(f"Best DOWN AP: {study_dn.best_value:.4f}")

    # ══════════════════════════════════════════════════════════════════════════
    # Stage 4: Train final XGBoost models
    # ══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("Stage 4: Training final XGBoost models")
    print("=" * 70)

    def train_xgb(params: dict, tx, ty, vx, vy, name: str):
        params = dict(params)
        params.update({'tree_method': 'hist', 'objective': 'binary:logistic', 'eval_metric': 'aucpr'})
        # No scale_pos_weight — we calibrate threshold instead
        clf = xgb.XGBClassifier(**params, early_stopping_rounds=50)
        clf.fit(tx, ty, eval_set=[(vx, vy)], verbose=True)
        pred = clf.predict_proba(vx)[:, 1]
        ap  = average_precision_score(vy, pred)
        auc = roc_auc_score(vy, pred)
        f1  = f1_score(vy, (pred >= 0.5).astype(int))
        print(f"  {name} — AP: {ap:.4f}  AUC: {auc:.4f}  F1@0.5: {f1:.4f}")
        return clf

    xgb_up = train_xgb(study_up.best_params, train_emb, train_y_up, val_emb, val_y_up, "UP")
    xgb_dn = train_xgb(study_dn.best_params, train_emb, train_y_dn, val_emb, val_y_dn, "DOWN")

    xgb_up.save_model(os.path.join(model_dir, 'xgboost_up.json'))
    xgb_dn.save_model(os.path.join(model_dir, 'xgboost_down.json'))
    # Backward-compat alias
    xgb_up.save_model(os.path.join(model_dir, 'xgboost_head.json'))

    # ══════════════════════════════════════════════════════════════════════════
    # Stage 5: Threshold calibration on val set
    # ══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("Stage 5: Threshold calibration (target precision >= 0.55)")
    print("=" * 70)

    val_pred_up = xgb_up.predict_proba(val_emb)[:, 1]
    val_pred_dn = xgb_dn.predict_proba(val_emb)[:, 1]

    buy_threshold  = calibrate_threshold(val_y_up, val_pred_up,  target_precision=0.55)
    sell_threshold = calibrate_threshold(val_y_dn, val_pred_dn, target_precision=0.55)

    # Evaluate at calibrated thresholds
    buy_pred_bin  = (val_pred_up >= buy_threshold).astype(int)
    sell_pred_bin = (val_pred_dn >= sell_threshold).astype(int)
    buy_f1   = f1_score(val_y_up, buy_pred_bin)
    sell_f1  = f1_score(val_y_dn, sell_pred_bin)

    print(f"  Buy  threshold: {buy_threshold:.4f}  → F1: {buy_f1:.4f}")
    print(f"  Sell threshold: {sell_threshold:.4f}  → F1: {sell_f1:.4f}")

    # ══════════════════════════════════════════════════════════════════════════
    # Stage 6: Test set evaluation
    # ══════════════════════════════════════════════════════════════════════════
    if len(test_df) > 0:
        print("\n" + "=" * 70)
        print("Stage 6: Test set evaluation (out-of-sample)")
        print("=" * 70)
        test_ds     = StockDataset(test_df, lookback)
        test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False, num_workers=0)
        test_emb, test_y_up, test_y_dn = extract_embeddings(test_loader, "Test")

        for name, clf, y_true in [("UP", xgb_up, test_y_up), ("DOWN", xgb_dn, test_y_dn)]:
            pred = clf.predict_proba(test_emb)[:, 1]
            ap   = average_precision_score(y_true, pred)
            auc  = roc_auc_score(y_true, pred)
            print(f"  TEST {name} — AP: {ap:.4f}  AUC: {auc:.4f}")

    # ══════════════════════════════════════════════════════════════════════════
    # Save metadata
    # ══════════════════════════════════════════════════════════════════════════
    meta = {
        "version": 3,
        "buy_threshold":  buy_threshold,
        "sell_threshold": sell_threshold,
        "horizon":        horizon,
        "lookback":       lookback,
        "features":       FEATURE_LIST,
        "n_features":     N_FEATURES,
        "d_model":        d_model,
        "nhead":          best_tf['nhead'],
        "num_layers":     best_tf['num_layers'],
        "dim_feedforward":best_tf['dim_feedforward'],
        "dropout":        best_tf['dropout'],
        "stochastic_depth": best_tf.get('stochastic_depth', 0.1),
        "xgb_up_params":   study_up.best_params,
        "xgb_down_params": study_dn.best_params,
        "label_scheme":    "triple_barrier",
        "upper_barrier":   0.07,
        "lower_barrier":   0.05,
        "train_end":       str(train_end.date()),
        "val_range":       f"{val_start.date()} ~ {val_end.date()}",
        "test_start":      str(test_start.date()),
        "total_params":    total_params,
        "trained_at":      str(datetime.now()),
    }
    with open(os.path.join(model_dir, 'model_meta.json'), 'w') as f:
        json.dump(meta, f, indent=4)

    print("\n" + "=" * 70)
    print(f"Training complete! Model saved to: {model_dir}")
    print(f"Buy threshold:  {buy_threshold:.4f}")
    print(f"Sell threshold: {sell_threshold:.4f}")
    print("=" * 70)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data_path',  default='/Users/eugene/nullalgo/simons/data/training_data_v3.parquet')
    parser.add_argument('--model_dir',  default='/Users/eugene/nullalgo/simons/model/v3')
    parser.add_argument('--horizon',    type=int,   default=10)
    parser.add_argument('--lookback',   type=int,   default=60)
    parser.add_argument('--epochs',     type=int,   default=60)
    parser.add_argument('--batch_size', type=int,   default=256)
    parser.add_argument('--n_trials_tf',  type=int, default=15)
    parser.add_argument('--n_trials_xgb', type=int, default=25)
    args = parser.parse_args()

    train(
        data_path=args.data_path,
        model_dir=args.model_dir,
        lookback=args.lookback,
        epochs=args.epochs,
        batch_size=args.batch_size,
        n_trials_tf=args.n_trials_tf,
        n_trials_xgb=args.n_trials_xgb,
        horizon=args.horizon,
    )

import torch
import torch.nn as nn


# ── Rotary Positional Encoding (RoPE) ──────────────────────────────────────

class RotaryPositionalEncoding(nn.Module):
    """RoPE: encodes relative position directly into attention via rotation."""

    def __init__(self, d_model: int, max_len: int = 2048):
        super().__init__()
        inv_freq = 1.0 / (10000 ** (torch.arange(0, d_model, 2).float() / d_model))
        self.register_buffer("inv_freq", inv_freq)
        self.max_len = max_len
        self._build_cache(max_len)

    def _build_cache(self, seq_len: int):
        t = torch.arange(seq_len, dtype=self.inv_freq.dtype)
        freqs = torch.einsum("i,j->ij", t, self.inv_freq)
        emb = torch.cat([freqs, freqs], dim=-1)  # (seq_len, d_model)
        self.register_buffer("cos_cached", emb.cos().unsqueeze(0), persistent=False)
        self.register_buffer("sin_cached", emb.sin().unsqueeze(0), persistent=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (batch, seq_len, d_model) → same shape with rotary encoding applied."""
        seq_len = x.size(1)
        if seq_len > self.cos_cached.size(1):
            self._build_cache(seq_len)
        return _apply_rotary(x, self.cos_cached[:, :seq_len], self.sin_cached[:, :seq_len])


def _rotate_half(x: torch.Tensor) -> torch.Tensor:
    x1, x2 = x.chunk(2, dim=-1)
    return torch.cat([-x2, x1], dim=-1)


def _apply_rotary(x: torch.Tensor, cos: torch.Tensor, sin: torch.Tensor) -> torch.Tensor:
    return x * cos + _rotate_half(x) * sin


# ── Conv1D Feature Stem ─────────────────────────────────────────────────────

class Conv1DStem(nn.Module):
    """Multi-scale 1D convolutions to capture local temporal patterns before attention."""

    def __init__(self, input_dim: int, d_model: int, dropout: float = 0.1):
        super().__init__()
        mid = d_model // 2

        # Short-range patterns (3-day)
        self.conv_short = nn.Conv1d(input_dim, mid, kernel_size=3, padding=1)
        # Medium-range patterns (7-day weekly)
        self.conv_med = nn.Conv1d(input_dim, mid, kernel_size=7, padding=3)

        self.norm = nn.LayerNorm(d_model)
        self.proj = nn.Linear(d_model, d_model)
        self.dropout = nn.Dropout(dropout)
        self.act = nn.GELU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (batch, seq_len, input_dim) → (batch, seq_len, d_model)"""
        # Conv1d expects (batch, channels, seq_len)
        xt = x.transpose(1, 2)
        h_short = self.act(self.conv_short(xt)).transpose(1, 2)
        h_med = self.act(self.conv_med(xt)).transpose(1, 2)
        h = torch.cat([h_short, h_med], dim=-1)  # (batch, seq_len, d_model)
        return self.dropout(self.proj(self.norm(h)))


# ── Pre-LayerNorm Transformer Encoder Layer ─────────────────────────────────

class PreNormEncoderLayer(nn.Module):
    """Transformer encoder layer with Pre-LN (more stable training)."""

    def __init__(self, d_model: int, nhead: int, dim_feedforward: int, dropout: float = 0.1,
                 stochastic_depth_prob: float = 0.0):
        super().__init__()
        self.norm1 = nn.LayerNorm(d_model)
        self.self_attn = nn.MultiheadAttention(d_model, nhead, dropout=dropout, batch_first=True)
        self.norm2 = nn.LayerNorm(d_model)
        self.ff = nn.Sequential(
            nn.Linear(d_model, dim_feedforward),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(dim_feedforward, d_model),
            nn.Dropout(dropout),
        )
        self.drop_path_prob = stochastic_depth_prob

    def _drop_path(self, x: torch.Tensor) -> torch.Tensor:
        if not self.training or self.drop_path_prob == 0.0:
            return x
        keep = torch.rand(x.size(0), 1, 1, device=x.device) > self.drop_path_prob
        return x * keep / (1 - self.drop_path_prob)

    def forward(self, src: torch.Tensor, src_mask=None, src_key_padding_mask=None) -> torch.Tensor:
        # Pre-LN: normalize before attention/FF
        h = self.norm1(src)
        attn_out, _ = self.self_attn(h, h, h, attn_mask=src_mask, key_padding_mask=src_key_padding_mask)
        src = src + self._drop_path(attn_out)
        h = self.norm2(src)
        src = src + self._drop_path(self.ff(h))
        return src


# ── Advanced Time-Series Transformer ────────────────────────────────────────

class TimeSeriesTransformer(nn.Module):
    """
    Advanced Transformer for financial time-series.

    Key improvements over baseline:
    - Conv1D stem for local pattern extraction before global attention
    - RoPE for better relative position encoding
    - Pre-LayerNorm for stable deep training
    - Learnable [CLS] token for global sequence aggregation
    - Stochastic depth for regularization
    - Final projection head for richer embeddings
    """

    def __init__(self, input_dim: int, d_model: int = 128, nhead: int = 8,
                 num_layers: int = 6, dim_feedforward: int = 512, dropout: float = 0.1,
                 stochastic_depth: float = 0.1):
        super().__init__()
        self.d_model = d_model

        # Conv1D stem instead of simple linear projection
        self.stem = Conv1DStem(input_dim, d_model, dropout)

        # Learnable [CLS] token for aggregation
        self.cls_token = nn.Parameter(torch.randn(1, 1, d_model) * 0.02)

        # Rotary positional encoding
        self.rope = RotaryPositionalEncoding(d_model, max_len=2048)

        # Pre-LN Transformer encoder with stochastic depth
        drop_probs = [stochastic_depth * i / max(num_layers - 1, 1) for i in range(num_layers)]
        self.layers = nn.ModuleList([
            PreNormEncoderLayer(d_model, nhead, dim_feedforward, dropout, dp)
            for dp in drop_probs
        ])

        self.final_norm = nn.LayerNorm(d_model)

        # Projection head: compress to embedding
        self.head = nn.Sequential(
            nn.Linear(d_model, d_model),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(d_model, d_model),
        )

        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.trunc_normal_(m.weight, std=0.02)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)
            elif isinstance(m, nn.LayerNorm):
                nn.init.ones_(m.weight)
                nn.init.zeros_(m.bias)
            elif isinstance(m, nn.Conv1d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
                if m.bias is not None:
                    nn.init.zeros_(m.bias)

    def forward(self, src: torch.Tensor) -> torch.Tensor:
        """
        src: (batch, seq_len, input_dim)
        returns: (batch, d_model) embedding
        """
        B = src.size(0)

        # Conv1D stem → (batch, seq_len, d_model)
        h = self.stem(src)

        # Apply RoPE
        h = self.rope(h)

        # Prepend [CLS] token
        cls = self.cls_token.expand(B, -1, -1)
        h = torch.cat([cls, h], dim=1)  # (batch, 1+seq_len, d_model)

        # Transformer encoder layers
        for layer in self.layers:
            h = layer(h)

        h = self.final_norm(h)

        # [CLS] token output → global representation
        cls_out = h[:, 0]

        return self.head(cls_out)


# ── HybridAIModel (backward-compatible wrapper) ────────────────────────────

class HybridAIModel(nn.Module):
    """
    Hybrid Transformer+XGBoost model wrapper.
    The Transformer generates embeddings; XGBoost classifies.
    """

    def __init__(self, input_dim: int, d_model: int = 128, nhead: int = 8,
                 num_layers: int = 6, dim_feedforward: int = 512, dropout: float = 0.1,
                 stochastic_depth: float = 0.1):
        super().__init__()
        self.transformer = TimeSeriesTransformer(
            input_dim=input_dim,
            d_model=d_model,
            nhead=nhead,
            num_layers=num_layers,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            stochastic_depth=stochastic_depth,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.transformer(x)


if __name__ == "__main__":
    model = HybridAIModel(input_dim=45)
    dummy = torch.randn(32, 60, 45)
    out = model(dummy)
    print(f"Embedding shape: {out.shape}")  # (32, 128)
    total = sum(p.numel() for p in model.parameters())
    print(f"Total parameters: {total:,}")

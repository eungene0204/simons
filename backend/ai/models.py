import torch
import torch.nn as nn
import torch.nn.functional as F


# ── Rotary Positional Encoding (RoPE) ──────────────────────────────────────

def _rotate_half(x: torch.Tensor) -> torch.Tensor:
    x1, x2 = x.chunk(2, dim=-1)
    return torch.cat([-x2, x1], dim=-1)


class RoPEMultiheadAttention(nn.Module):
    """Multi-head self-attention with rotary position embedding applied to
    Q and K *after* projection.

    This is the correct RoPE formulation: rotating Q/K post-projection yields
    the relative-position property ⟨R_m·q, R_n·k⟩ = f(m-n). (Applying rotation
    to the token embeddings before the Q/K projection — the previous
    implementation — does not, and degenerates to a one-shot absolute signal.)

    Position 0 rotates by angle 0 (identity), so a prepended [CLS] token at
    index 0 is left unrotated automatically.
    """

    def __init__(self, d_model: int, nhead: int, dropout: float = 0.0):
        super().__init__()
        if d_model % nhead != 0:
            raise ValueError(f"d_model ({d_model}) must be divisible by nhead ({nhead})")
        self.nhead = nhead
        self.head_dim = d_model // nhead
        if self.head_dim % 2 != 0:
            raise ValueError(f"head_dim ({self.head_dim}) must be even for RoPE")
        self.q_proj = nn.Linear(d_model, d_model)
        self.k_proj = nn.Linear(d_model, d_model)
        self.v_proj = nn.Linear(d_model, d_model)
        self.out_proj = nn.Linear(d_model, d_model)
        self.dropout = dropout

        inv_freq = 1.0 / (10000 ** (torch.arange(0, self.head_dim, 2).float() / self.head_dim))
        self.register_buffer("inv_freq", inv_freq, persistent=False)

    def _rope_cos_sin(self, seq_len: int, device, dtype):
        t = torch.arange(seq_len, device=device, dtype=self.inv_freq.dtype)
        freqs = torch.einsum("i,j->ij", t, self.inv_freq)
        emb = torch.cat([freqs, freqs], dim=-1)  # (seq_len, head_dim)
        return emb.cos().to(dtype), emb.sin().to(dtype)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (batch, seq_len, d_model) → (batch, seq_len, d_model)."""
        B, T, C = x.shape
        q = self.q_proj(x).view(B, T, self.nhead, self.head_dim).transpose(1, 2)  # (B, h, T, hd)
        k = self.k_proj(x).view(B, T, self.nhead, self.head_dim).transpose(1, 2)
        v = self.v_proj(x).view(B, T, self.nhead, self.head_dim).transpose(1, 2)

        cos, sin = self._rope_cos_sin(T, x.device, q.dtype)
        cos = cos[None, None]  # (1, 1, T, head_dim)
        sin = sin[None, None]
        q = q * cos + _rotate_half(q) * sin
        k = k * cos + _rotate_half(k) * sin

        out = F.scaled_dot_product_attention(
            q, k, v, dropout_p=self.dropout if self.training else 0.0
        )
        out = out.transpose(1, 2).reshape(B, T, C)
        return self.out_proj(out)


# ── Conv1D Feature Stem ─────────────────────────────────────────────────────

class Conv1DStem(nn.Module):
    """Multi-scale 1D convolutions to capture local temporal patterns before attention."""

    def __init__(self, input_dim: int, d_model: int, dropout: float = 0.1):
        super().__init__()
        if d_model % 2 != 0:
            raise ValueError(f"d_model must be even for Conv1DStem (got {d_model})")
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
        self.self_attn = RoPEMultiheadAttention(d_model, nhead, dropout=dropout)
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

    def forward(self, src: torch.Tensor) -> torch.Tensor:
        # Pre-LN: normalize before attention/FF
        h = self.norm1(src)
        attn_out = self.self_attn(h)
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

        # Pre-LN Transformer encoder with stochastic depth.
        # RoPE is applied inside each attention layer (see RoPEMultiheadAttention).
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

        # Prepend [CLS] token (index 0 → RoPE rotation is identity there).
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

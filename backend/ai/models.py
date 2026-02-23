import torch
import torch.nn as nn
import math

class PositionalEncoding(nn.Module):
    def __init__(self, d_model, max_len=5000):
        super(PositionalEncoding, self).__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0).transpose(0, 1)
        self.register_buffer('pe', pe)

    def forward(self, x):
        return x + self.pe[:x.size(0), :]

class TimeSeriesTransformer(nn.Module):
    def __init__(self, input_dim, d_model=64, nhead=4, num_layers=2, dim_feedforward=128, dropout=0.1):
        super(TimeSeriesTransformer, self).__init__()
        self.model_type = 'Transformer'
        self.src_mask = None
        self.pos_encoder = PositionalEncoding(d_model)
        self.encoder_layer = nn.TransformerEncoderLayer(d_model, nhead, dim_feedforward, dropout)
        self.transformer_encoder = nn.TransformerEncoder(self.encoder_layer, num_layers)
        self.input_projection = nn.Linear(input_dim, d_model)
        self.d_model = d_model

    def forward(self, src):
        # src shape: (batch_size, seq_len, input_dim)
        # Transformer expects (seq_len, batch_size, d_model)
        src = self.input_projection(src).transpose(0, 1) * math.sqrt(self.d_model)
        src = self.pos_encoder(src)
        output = self.transformer_encoder(src)
        # Return embedding of the last time step: (batch_size, d_model)
        return output[-1]

class HybridAIModel(nn.Module):
    """
    Hybrid model wrapper. 
    During training/inference, the Transformer part is used to generate embeddings.
    """
    def __init__(self, input_dim, d_model=64, nhead=4, num_layers=2, dim_feedforward=128, dropout=0.1):
        super(HybridAIModel, self).__init__()
        self.transformer = TimeSeriesTransformer(
            input_dim=input_dim, 
            d_model=d_model, 
            nhead=nhead, 
            num_layers=num_layers, 
            dim_feedforward=dim_feedforward, 
            dropout=dropout
        )
        
    def forward(self, x):
        return self.transformer(x)

if __name__ == "__main__":
    # Test
    model = HybridAIModel(input_dim=6)
    dummy_input = torch.randn(32, 60, 6) # Batch size 32, 60 days, 6 features
    output = model(dummy_input)
    print(f"Embedding output shape: {output.shape}") # Expect (32, 64)

"""Small neural baselines. Input [B, seq_len] (scaled), output [B, pred_len] (scaled)."""

import torch
from torch import nn


class LSTMForecaster(nn.Module):
    """Encoder LSTM over the input window; a linear head maps the last hidden state to the horizon."""

    def __init__(self, pred_len: int, hidden: int = 64, layers: int = 2, dropout: float = 0.1):
        super().__init__()
        self.lstm = nn.LSTM(1, hidden, num_layers=layers, batch_first=True, dropout=dropout if layers > 1 else 0.0)
        self.head = nn.Linear(hidden, pred_len)

    def forward(self, x):
        out, _ = self.lstm(x.unsqueeze(-1))
        return self.head(out[:, -1])


class PatchTST(nn.Module):
    """Compact PatchTST (Nie et al., ICLR 2023), one channel: instance normalisation, patches of
    `patch_len` with `stride`, a Transformer encoder over the patches, a flatten + linear head.
    Our own small implementation, not the authors' code."""

    def __init__(self, seq_len: int, pred_len: int, patch_len: int = 16, stride: int = 8, d_model: int = 64,
                 heads: int = 4, layers: int = 2, dropout: float = 0.1):
        super().__init__()
        self.patch_len, self.stride = patch_len, stride
        n_patches = (seq_len - patch_len) // stride + 2          # + 1 for the padded end patch
        self.pad = nn.ReplicationPad1d((0, stride))
        self.embed = nn.Linear(patch_len, d_model)
        self.pos = nn.Parameter(torch.zeros(1, n_patches, d_model))
        layer = nn.TransformerEncoderLayer(d_model, heads, dim_feedforward=2 * d_model, dropout=dropout,
                                           batch_first=True)
        self.encoder = nn.TransformerEncoder(layer, layers)
        self.head = nn.Sequential(nn.Flatten(), nn.Dropout(dropout), nn.Linear(n_patches * d_model, pred_len))

    def forward(self, x):
        mean = x.mean(dim=1, keepdim=True)
        std = x.std(dim=1, keepdim=True) + 1e-5
        z = (x - mean) / std
        patches = self.pad(z.unsqueeze(1)).squeeze(1).unfold(1, self.patch_len, self.stride)
        h = self.encoder(self.embed(patches) + self.pos)
        return self.head(h) * std + mean

"""
CME-Patchformer: Time Series Forecasting with Pre-trained Language Models

This module implements the GPT-based variants of the CME-Patchformer model as described in:
"CME Patchformer Model Enhances Time Series Forecasting and High-Quality Turbine-Level SCADA Dataset"

The model leverages pre-trained language models (GPT-2) for multivariate time series forecasting
by treating time series data as sequential tokens through a patching mechanism.

Key Components:
    1. Patch Embedding: Converts time series into patches (Conv+MLP or Linear)
    2. Pre-trained LLM Backbone: Captures temporal dependencies
    3. Projection Layer: Maps LLM outputs to forecasting horizon

Reference: CME Patchformer research paper
"""

import os
import sys
import torch
import torch.nn as nn

from transformers.models.gpt2.modeling_gpt2 import GPT2Model, GPT2Config
from einops import rearrange

from transformers import AutoModel

_models_dir = os.path.dirname(os.path.abspath(__file__))
if _models_dir not in sys.path:
    sys.path.insert(0, _models_dir)

from peft_utils import apply_peft, freeze_backbone


class ConvMLPPatchEmbedding(nn.Module):
    """
    Conv+MLP Patch Embedding Layer

    Non-linear patch embedding using 1D convolution followed by MLP projection.

    Args:
        patch_size (int): Size of each time series patch
        d_model (int): Dimension of the LLM embedding space
        hidden_size (int): Hidden dimension for MLP intermediate layer
        kernel_size (int): Kernel size for Conv1D operation
        dropout (float): Dropout rate for regularization (default: 0.15)
    """
    def __init__(self, patch_size, d_model=768, hidden_size=256, kernel_size=3, dropout=0.15):
        super().__init__()
        # Conv1d for capturing local temporal patterns within patches
        # Input shape: [batch, in_channels=patch_size, sequence_length=num_patches]
        self.conv1d = nn.Conv1d(
            in_channels=patch_size,
            out_channels=patch_size,
            kernel_size=kernel_size,
            padding=kernel_size // 2  # Preserve sequence length
        )
        # Two-layer MLP for non-linear projection to LLM embedding space
        self.mlp = nn.Sequential(
            nn.Linear(patch_size, hidden_size),
            nn.ReLU(),
            nn.Dropout(p=dropout),  # Dropout after activation
            nn.Linear(hidden_size, d_model)
        )

    def forward(self, x):
        Bm, N, P = x.shape
        x = x.reshape(-1, P, N)
        v = self.conv1d(x)
        v = v.permute(0, 2, 1)
        out = self.mlp(v)
        out = out.view(Bm, N, -1)
        return out


class GPT4TS_Linear(nn.Module):
    """
    GPT4TS Linear Variant

    Linear patch embedding variant for GPT-based time series forecasting.

    Args:
        configs: Configuration object containing model hyperparameters
        device: Torch device (CPU/GPU) for model placement
    """
    def __init__(self, configs, device):
        super(GPT4TS_Linear, self).__init__()
        self.is_gpt = configs.is_gpt
        self.patch_size = configs.patch_size
        self.pretrain = configs.pretrain
        self.stride = configs.stride
        self.patch_num = (configs.seq_len - self.patch_size) // self.stride + 1

        self.padding_patch_layer = nn.ReplicationPad1d((0, self.stride))
        self.patch_num += 1

        if configs.is_gpt:
            if configs.pretrain:
                self.gpt2 = GPT2Model.from_pretrained('gpt2', output_attentions=True, output_hidden_states=True)
            else:
                print("------------------no pretrain------------------")
                self.gpt2 = GPT2Model(GPT2Config())
            self.gpt2.h = self.gpt2.h[:configs.llm_layers]
            self.gpt2 = apply_peft(self.gpt2, configs, ["c_attn", "c_fc", "c_proj"])

        self.in_layer = nn.Linear(configs.patch_size, configs.d_model)
        self.out_layer = nn.Linear(configs.d_model * self.patch_num, configs.pred_len)

        # Dropout for regularization
        dropout_rate = getattr(configs, 'dropout', 0.15)
        self.dropout_patch = nn.Dropout(p=dropout_rate)
        self.dropout_gpt = nn.Dropout(p=dropout_rate)
        self.dropout_pre_out = nn.Dropout(p=dropout_rate)

        freeze_backbone(self.gpt2, configs, ['ln', 'wpe'])

        for layer in (self.gpt2, self.in_layer, self.out_layer):
            layer.to(device=device)
            layer.train()

        self.cnt = 0

    def forward(self, x, itr):
        B, L, M = x.shape

        means = x.mean(1, keepdim=True).detach()
        x = x - means
        stdev = torch.sqrt(torch.var(x, dim=1, keepdim=True, unbiased=False) + 1e-5).detach()
        x /= stdev

        x = rearrange(x, 'b l m -> b m l')

        x = self.padding_patch_layer(x)
        x = x.unfold(dimension=-1, size=self.patch_size, step=self.stride)
        x = rearrange(x, 'b m n p -> (b m) n p')

        outputs = self.in_layer(x)
        outputs = self.dropout_patch(outputs)

        if self.is_gpt:
            outputs = self.gpt2(inputs_embeds=outputs).last_hidden_state
            outputs = self.dropout_gpt(outputs)

        outputs = outputs.reshape(B*M, -1)
        outputs = self.dropout_pre_out(outputs)
        outputs = self.out_layer(outputs)
        outputs = rearrange(outputs, '(b m) l -> b l m', b=B)

        outputs = outputs * stdev
        outputs = outputs + means

        return outputs


class GPT4TS_Nonlinear(nn.Module):
    """
    GPT4TS Nonlinear Variant

    Non-linear patch embedding variant using Conv+MLP for GPT-based time series forecasting.

    Args:
        configs: Configuration object containing model hyperparameters
        device: Torch device (CPU/GPU) for model placement
    """
    def __init__(self, configs, device):
        super(GPT4TS_Nonlinear, self).__init__()
        self.is_gpt = configs.is_gpt
        self.patch_size = configs.patch_size
        self.pretrain = configs.pretrain
        self.stride = configs.stride
        self.patch_num = (configs.seq_len - self.patch_size) // self.stride + 1
        self.padding_patch_layer = nn.ReplicationPad1d((0, self.stride))
        self.patch_num += 1

        if configs.is_gpt:
            if configs.pretrain:
                self.gpt2 = GPT2Model.from_pretrained(
                    'gpt2',
                    output_attentions=True,
                    output_hidden_states=True,
                    low_cpu_mem_usage=True,
                    use_safetensors=True,
                    )
            else:
                self.gpt2 = GPT2Model(GPT2Config())
            self.gpt2.h = self.gpt2.h[:configs.llm_layers]

            self.gpt2 = apply_peft(self.gpt2, configs, ["c_attn", "c_fc", "c_proj"])

        # Dropout for regularization
        dropout_rate = getattr(configs, 'dropout', 0.15)

        self.in_layer = ConvMLPPatchEmbedding(
            patch_size=configs.patch_size,
            d_model=configs.d_model,
            hidden_size=configs.hidden_size,
            kernel_size=configs.kernel_size,
            dropout=dropout_rate
        )
        self.out_layer = nn.Linear(configs.d_model * self.patch_num,
                                   configs.pred_len)

        # Additional dropout layers
        self.dropout_gpt = nn.Dropout(p=dropout_rate)
        self.dropout_pre_out = nn.Dropout(p=dropout_rate)

        freeze_backbone(self.gpt2, configs, ['ln', 'wpe'])

        for module in (getattr(self, 'gpt2', None), self.in_layer, self.out_layer):
            if module is not None:
                module.to(device)
                module.train()

    def forward(self, x, itr):
        B, L, M = x.shape

        means = x.mean(1, keepdim=True).detach()
        x = x - means
        stdev = torch.sqrt(torch.var(x, dim=1, keepdim=True,
                                     unbiased=False) + 1e-5).detach()
        x = x / stdev

        x = rearrange(x, 'b l m -> b m l')
        x = self.padding_patch_layer(x)
        x = x.unfold(dimension=-1,
                     size=self.patch_size,
                     step=self.stride)
        x = rearrange(x, 'b m n p -> (b m) n p')

        outputs = self.in_layer(x)

        if self.is_gpt:
            outputs = self.gpt2(inputs_embeds=outputs).last_hidden_state
            outputs = self.dropout_gpt(outputs)

        outputs = outputs.reshape(B * M, -1)
        outputs = self.dropout_pre_out(outputs)
        outputs = self.out_layer(outputs)
        outputs = rearrange(outputs, '(b m) l -> b l m', b=B)

        outputs = outputs * stdev
        outputs = outputs + means
        return outputs

class GPT4TS_Nonlinear_AttnRes(nn.Module):
    """
    GPT4TS Nonlinear + AttnRes Variant

    Same as GPT4TS_Nonlinear but replaces last_hidden_state with a learned
    attention-weighted aggregation over ALL hidden states (embedding + each layer).

    Args:
        configs: Configuration object containing model hyperparameters
        device: Torch device (CPU/GPU) for model placement
    """
    def __init__(self, configs, device):
        super(GPT4TS_Nonlinear_AttnRes, self).__init__()
        self.is_gpt = configs.is_gpt
        self.patch_size = configs.patch_size
        self.pretrain = configs.pretrain
        self.stride = configs.stride
        self.patch_num = (configs.seq_len - self.patch_size) // self.stride + 1
        self.padding_patch_layer = nn.ReplicationPad1d((0, self.stride))
        self.patch_num += 1

        if configs.is_gpt:
            if configs.pretrain:
                self.gpt2 = GPT2Model.from_pretrained(
                    'gpt2',
                    output_attentions=True,
                    output_hidden_states=True,
                    low_cpu_mem_usage=True,
                    use_safetensors=True,
                    )
            else:
                self.gpt2 = GPT2Model(GPT2Config())
            self.gpt2.h = self.gpt2.h[:configs.llm_layers]

            self.gpt2 = apply_peft(self.gpt2, configs, ["c_attn", "c_fc", "c_proj"])

        # Dropout for regularization
        dropout_rate = getattr(configs, 'dropout', 0.15)

        self.in_layer = ConvMLPPatchEmbedding(
            patch_size=configs.patch_size,
            d_model=configs.d_model,
            hidden_size=configs.hidden_size,
            kernel_size=configs.kernel_size,
            dropout=dropout_rate
        )
        self.out_layer = nn.Linear(configs.d_model * self.patch_num,
                                   configs.pred_len)

        # Additional dropout layers
        self.dropout_gpt = nn.Dropout(p=dropout_rate)
        self.dropout_pre_out = nn.Dropout(p=dropout_rate)

        # AttnRes components
        self.attn_res_proj = nn.Linear(configs.d_model, 1, bias=False)
        self.attn_res_norm = nn.RMSNorm(configs.d_model)

        freeze_backbone(self.gpt2, configs, ['ln', 'wpe'])

        for module in (getattr(self, 'gpt2', None), self.in_layer, self.out_layer,
                       self.attn_res_proj, self.attn_res_norm):
            if module is not None:
                module.to(device)
                module.train()

    def attn_res_aggregate(self, all_hidden_states):
        """
        Learned attention-weighted aggregation over all hidden states.

        Args:
            all_hidden_states: [L, B, T, D] stacked hidden states

        Returns:
            [B, T, D] aggregated representation
        """
        V = all_hidden_states                    # [L, B, T, D]
        K = self.attn_res_norm(V)                # normalize to prevent magnitude bias

        # single learned query vector produces logits per layer
        logits = torch.einsum(
            'd, l b t d -> l b t',
            self.attn_res_proj.weight.squeeze(),
            K
        )                                        # [L, B, T]

        weights = logits.softmax(dim=0)          # [L, B, T] sums to 1 over L

        # weighted sum over layers
        out = torch.einsum(
            'l b t, l b t d -> b t d',
            weights, V
        )                                        # [B, T, D]
        return out

    def forward(self, x, itr):
        B, L, M = x.shape

        means = x.mean(1, keepdim=True).detach()
        x = x - means
        stdev = torch.sqrt(torch.var(x, dim=1, keepdim=True,
                                     unbiased=False) + 1e-5).detach()
        x = x / stdev

        x = rearrange(x, 'b l m -> b m l')
        x = self.padding_patch_layer(x)
        x = x.unfold(dimension=-1,
                     size=self.patch_size,
                     step=self.stride)
        x = rearrange(x, 'b m n p -> (b m) n p')

        outputs = self.in_layer(x)

        if self.is_gpt:
            gpt_out = self.gpt2(inputs_embeds=outputs)
            # hidden_states: tuple of L+1 tensors (embedding + each layer)
            all_hidden = torch.stack(gpt_out.hidden_states)  # [L+1, B, T, D]
            outputs = self.attn_res_aggregate(all_hidden)
            outputs = self.dropout_gpt(outputs)

        outputs = outputs.reshape(B * M, -1)
        outputs = self.dropout_pre_out(outputs)
        outputs = self.out_layer(outputs)
        outputs = rearrange(outputs, '(b m) l -> b l m', b=B)

        outputs = outputs * stdev
        outputs = outputs + means
        return outputs

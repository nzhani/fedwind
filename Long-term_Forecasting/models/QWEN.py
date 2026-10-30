import os
import sys
import numpy as np
import torch
import torch.nn as nn

from einops import rearrange

from transformers import AutoModel, AutoConfig

_models_dir = os.path.dirname(os.path.abspath(__file__))
if _models_dir not in sys.path:
    sys.path.insert(0, _models_dir)

from peft_utils import apply_peft, freeze_backbone

# --------- Conv + MLP Patch Embedding ---------
class ConvMLPPatchEmbedding(nn.Module):
    def __init__(self, patch_size, d_model, hidden_size=128, kernel_size=3, dropout=0.15):
        super().__init__()
        # Conv1d expects input shape [batch, in_channels, sequence_length]
        self.conv1d = nn.Conv1d(
            in_channels=patch_size,
            out_channels=patch_size,
            kernel_size=kernel_size,
            padding=kernel_size // 2
        )
        self.mlp = nn.Sequential(
            nn.Linear(patch_size, hidden_size),
            nn.ReLU(),
            nn.Dropout(p=dropout),
            nn.Linear(hidden_size, d_model)
        )

    def forward(self, x):
        # x: [B*M, N, patch_size]  (N = số patch, patch_size = chiều patch)
        Bm, N, P = x.shape  # Bm = B * M
        # rearrange to [batch, in_channels, length] for Conv1d
        x = x.reshape(-1, P, N)
        v = self.conv1d(x)           # [B*M, patch_size, N]
        # permute so last dim = patch_size for MLP
        v = v.permute(0, 2, 1)       # [B*M, N, patch_size]
        out = self.mlp(v)            # [B*M, N, d_model]
        out = out.view(Bm, N, -1)    # [B*M, N, d_model]
        return out

# ---------- Qwen chính sửa ----------
class Qwen_Linear(nn.Module):
    def __init__(self, configs, device):
        super(Qwen_Linear, self).__init__()
        self.is_qwen = configs.is_qwen
        self.patch_size = configs.patch_size
        self.pretrain = configs.pretrain
        self.stride = configs.stride
        self.patch_num = (configs.seq_len - self.patch_size) // self.stride + 1

        self.padding_patch_layer = nn.ReplicationPad1d((0, self.stride))
        self.patch_num += 1

        if configs.is_qwen:
            if configs.pretrain:
                self.qwen = AutoModel.from_pretrained(
                    "Qwen/Qwen3-0.6B",
                    output_hidden_states=True,
                    low_cpu_mem_usage=True,
                    use_safetensors=True,
                )
            else:
                print("------------------no pretrain------------------")
                self.qwen = AutoModel.from_config(
                    AutoConfig.from_pretrained("Qwen/Qwen3-0.6B")
                )
            self.qwen.layers = self.qwen.layers[:configs.llm_layers]
            target_modules = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
            self.qwen = apply_peft(self.qwen, configs, target_modules)

        self.in_layer = nn.Linear(configs.patch_size, configs.d_model)
        self.out_layer = nn.Linear(configs.d_model * self.patch_num, configs.pred_len)

        if configs.is_qwen:
            freeze_backbone(self.qwen, configs, ['norm', 'embed'])

        self.to(device)
        for layer in (self.qwen, self.in_layer, self.out_layer):
            layer.to(device=device)
            layer.train()


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

        outputs = self.in_layer(x)   # [B*M, N, d_model]

        if self.is_qwen:
            outputs = self.qwen(inputs_embeds=outputs).last_hidden_state

        outputs = self.out_layer(outputs.reshape(B*M, -1))
        outputs = rearrange(outputs, '(b m) l -> b l m', b=B)

        outputs = outputs * stdev
        outputs = outputs + means

        return outputs


# ---------- Qwen Model ----------
class Qwen_Nonlinear(nn.Module):
    def __init__(self, configs, device):
        super(Qwen_Nonlinear, self).__init__()
        self.is_qwen = configs.is_qwen
        self.patch_size = configs.patch_size
        self.pretrain = configs.pretrain
        self.stride = configs.stride
        # compute number of patches
        self.patch_num = (configs.seq_len - self.patch_size) // self.stride + 1
        self.padding_patch_layer = nn.ReplicationPad1d((0, self.stride))
        self.patch_num += 1

        if configs.is_qwen:
            if configs.pretrain:
                self.qwen = AutoModel.from_pretrained(
                    "Qwen/Qwen3-0.6B",
                    output_hidden_states=True,
                    low_cpu_mem_usage=True,
                    use_safetensors=True,
                )
            else:
                print("------------------no pretrain------------------")
                self.qwen = AutoModel.from_config(
                    AutoConfig.from_pretrained("Qwen/Qwen3-0.6B")
                )
            self.qwen.layers = self.qwen.layers[:configs.llm_layers]
            target_modules = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
            self.qwen = apply_peft(self.qwen, configs, target_modules)

        # Dropout for regularization
        dropout_rate = getattr(configs, "dropout", 0.15)

        # embedding: conv + mlp patch
        self.in_layer = ConvMLPPatchEmbedding(
            patch_size=configs.patch_size,
            d_model=configs.d_model,
            hidden_size=configs.hidden_size,
            kernel_size=configs.kernel_size,
            dropout=dropout_rate
        )
        # final linear to map all patches to prediction length
        self.out_layer = nn.Linear(configs.d_model * self.patch_num,
                                   configs.pred_len)

        # Additional dropout layers
        self.dropout_qwen = nn.Dropout(p=dropout_rate)
        self.dropout_pre_out = nn.Dropout(p=dropout_rate)

        # freeze Qwen if requested
        if configs.is_qwen:
            freeze_backbone(self.qwen, configs, ['norm', 'embed'])

        # move modules to device
        self.to(device)
        for layer in (self.qwen, self.in_layer, self.out_layer):
            layer.to(device=device)
            layer.train()

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
        # reshape to [B*M, N, patch_size]
        x = rearrange(x, 'b m n p -> (b m) n p')

        # conv+mlp embedding
        outputs = self.in_layer(x)

        if self.is_qwen:
            outputs = self.qwen(inputs_embeds=outputs).last_hidden_state
            outputs = self.dropout_qwen(outputs)

        # final prediction
        outputs = outputs.reshape(B * M, -1)
        outputs = self.dropout_pre_out(outputs)
        outputs = self.out_layer(outputs)
        outputs = rearrange(outputs, '(b m) l -> b l m', b=B)

        # denormalize
        outputs = outputs * stdev
        outputs = outputs + means
        return outputs

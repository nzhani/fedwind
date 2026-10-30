import os
import sys
import numpy as np
import torch
import torch.nn as nn

from einops import rearrange

from transformers import AutoModelForCausalLM, AutoConfig

_models_dir = os.path.dirname(os.path.abspath(__file__))
if _models_dir not in sys.path:
    sys.path.insert(0, _models_dir)

from peft_utils import apply_peft, freeze_backbone
from huggingface_hub import login

_hf_token = os.environ.get("HF_TOKEN")
if _hf_token:
    login(token=_hf_token)

# --------- Conv + MLP Patch Embedding ---------
class ConvMLPPatchEmbedding(nn.Module):
    def __init__(self, patch_size, d_model, hidden_size=128, kernel_size=3, dropout=0.15):
        super().__init__()
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
        Bm, N, P = x.shape
        x = x.reshape(-1, P, N)
        v = self.conv1d(x)
        v = v.permute(0, 2, 1)
        out = self.mlp(v)
        out = out.view(Bm, N, -1)
        return out

_GEMMA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]

def _load_gemma_backbone(configs):
    if configs.pretrain:
        base = AutoModelForCausalLM.from_pretrained(
            "google/gemma-3-270m",
            output_hidden_states=True,
            low_cpu_mem_usage=True,
            use_safetensors=True,
        )
    else:
        print("------------------no pretrain------------------")
        cfg = AutoConfig.from_pretrained("google/gemma-3-270m")
        base = AutoModelForCausalLM.from_config(cfg)
    model = base.model
    model.layers = model.layers[:configs.llm_layers]
    return model

# ---------- Gemma Linear ----------
class Gemma_Linear(nn.Module):
    def __init__(self, configs, device):
        super(Gemma_Linear, self).__init__()
        self.is_gemma = configs.is_gemma
        self.patch_size = configs.patch_size
        self.pretrain = configs.pretrain
        self.stride = configs.stride
        self.patch_num = (configs.seq_len - self.patch_size) // self.stride + 1

        self.padding_patch_layer = nn.ReplicationPad1d((0, self.stride))
        self.patch_num += 1

        if configs.is_gemma:
            self.gemma = _load_gemma_backbone(configs)
            self.gemma = apply_peft(self.gemma, configs, _GEMMA_TARGETS)
            # print("gemma= {}".format(self.gemma))

        model_dim = self.gemma.config.hidden_size if self.is_gemma else configs.d_model
        self.in_layer = nn.Linear(configs.patch_size, model_dim)
        self.out_layer = nn.Linear(model_dim * self.patch_num, configs.pred_len)

        if configs.is_gemma:
            freeze_backbone(self.gemma, configs, ['norm', 'embed'])

        self.to(device)
        for layer in (self.gemma, self.in_layer, self.out_layer):
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

        outputs = self.in_layer(x)

        if self.is_gemma:
            outputs = self.gemma(inputs_embeds=outputs).last_hidden_state

        outputs = self.out_layer(outputs.reshape(B*M, -1))
        outputs = rearrange(outputs, '(b m) l -> b l m', b=B)

        outputs = outputs * stdev
        outputs = outputs + means

        return outputs

# ---------- Gemma Nonlinear ----------
class Gemma_Nonlinear(nn.Module):
    def __init__(self, configs, device):
        super(Gemma_Nonlinear, self).__init__()
        self.is_gemma = configs.is_gemma
        self.patch_size = configs.patch_size
        self.pretrain = configs.pretrain
        self.stride = configs.stride
        self.patch_num = (configs.seq_len - self.patch_size) // self.stride + 1
        self.padding_patch_layer = nn.ReplicationPad1d((0, self.stride))
        self.patch_num += 1

        if configs.is_gemma:
            self.gemma = _load_gemma_backbone(configs)
            self.gemma = apply_peft(self.gemma, configs, _GEMMA_TARGETS)
            # print("gemma= {}".format(self.gemma))

        dropout_rate = getattr(configs, "dropout", 0.15)

        model_dim = self.gemma.config.hidden_size if self.is_gemma else configs.d_model
        self.in_layer = ConvMLPPatchEmbedding(
            patch_size=configs.patch_size,
            d_model=model_dim,
            hidden_size=configs.hidden_size,
            kernel_size=configs.kernel_size,
            dropout=dropout_rate
        )
        self.out_layer = nn.Linear(model_dim * self.patch_num,
                                   configs.pred_len)

        self.dropout_gemma = nn.Dropout(p=dropout_rate)
        self.dropout_pre_out = nn.Dropout(p=dropout_rate)

        if configs.is_gemma:
            freeze_backbone(self.gemma, configs, ['norm', 'embed'])

        self.to(device)
        for layer in (self.gemma, self.in_layer, self.out_layer):
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
        x = rearrange(x, 'b m n p -> (b m) n p')

        outputs = self.in_layer(x)

        if self.is_gemma:
            outputs = self.gemma(inputs_embeds=outputs).last_hidden_state
            outputs = self.dropout_gemma(outputs)

        outputs = outputs.reshape(B * M, -1)
        outputs = self.dropout_pre_out(outputs)
        outputs = self.out_layer(outputs)
        outputs = rearrange(outputs, '(b m) l -> b l m', b=B)

        outputs = outputs * stdev
        outputs = outputs + means
        return outputs

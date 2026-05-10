"""示例 ML 训练脚本 — 用于测试 Code Param Tuner"""

import argparse
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, random_split

# ── 训练参数 ──
lr = 0.001
epochs = 50
batch_size = 32
weight_decay = 1e-4
patience = 10
max_grad_norm = 1.0
optimizer = "adam"
scheduler = "cosine"

# ── 模型结构 ──
hidden_size = 256
num_layers = 3
dropout = 0.3
activation = "relu"
embedding_dim = 128
num_heads = 8
dim_feedforward = 1024

# ── 数据设置 ──
DATA_PATH = "./data/train.csv"
MAX_SEQ_LEN = 512
test_size = 0.2
val_size = 0.1
num_workers = 4
vocab_size = 30000

# ── 输出设置 ──
OUTPUT_DIR = "./checkpoints"
seed = 42

# ── 嵌套配置 ──
config = {
    "temperature": 1.0,
    "top_k": 50,
    "top_p": 0.9,
}


class TransformerModel(nn.Module):
    def __init__(
        self,
        vocab_size: int = 30000,
        embed_dim: int = 128,
        num_heads: int = 8,
        hidden_dim: int = 256,
        num_layers: int = 3,
        dropout: float = 0.3,
    ):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=embed_dim,
            nhead=num_heads,
            dim_feedforward=hidden_dim,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.fc = nn.Linear(embed_dim, vocab_size)

    def forward(self, x):
        x = self.embedding(x)
        x = self.transformer(x)
        return self.fc(x)


def train():
    torch.manual_seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model = TransformerModel(
        vocab_size=vocab_size,
        embed_dim=embedding_dim,
        num_heads=num_heads,
        hidden_dim=hidden_size,
        num_layers=num_layers,
        dropout=dropout,
    ).to(device)

    if optimizer == "adam":
        opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)
    elif optimizer == "adamw":
        opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    else:
        opt = torch.optim.SGD(model.parameters(), lr=lr, momentum=0.9)

    criterion = nn.CrossEntropyLoss()

    print(f"Model params: {sum(p.numel() for p in model.parameters()):,}")
    print(f"Training: lr={lr}, epochs={epochs}, batch_size={batch_size}")
    print(f"Device: {device}")

    for epoch in range(epochs):
        model.train()
        total_loss = 0
        # Training loop placeholder
        print(f"Epoch {epoch+1}/{epochs} - loss: {total_loss:.4f}")


if __name__ == "__main__":
    train()

"""GraphSAGE link-prediction embeddings. Dummy zeros if torch/pyg missing. Train edges only."""
import logging
from pathlib import Path
import numpy as np
from . import config

log = logging.getLogger(__name__)
EMB_DIM = config.GRAPH["embedding_dim"]

try:
    import torch
    import torch.nn as nn
    from torch_geometric.nn import SAGEConv
    from torch_geometric.data import Data
    AVAILABLE = True
except Exception as e:
    torch = None
    nn = object
    SAGEConv = None
    AVAILABLE = False
    log.warning("torch_geometric unavailable, using dummy embeddings: %s", e)


if AVAILABLE:
    class GraphSAGEModel(nn.Module):
        def __init__(self, in_dim=16, hidden_dim=128, out_dim=64):
            super().__init__()
            self.conv1 = SAGEConv(in_dim, hidden_dim)
            self.conv2 = SAGEConv(hidden_dim, out_dim)
            self.relu = nn.ReLU()
            self.in_dim = in_dim

        def forward(self, x, edge_index):
            x = self.relu(self.conv1(x, edge_index))
            return self.conv2(x, edge_index)
else:
    class GraphSAGEModel:
        def __init__(self, *a, **k):
            self.out_dim = k.get("out_dim", EMB_DIM)
        def eval(self): return self
        def __call__(self, *a, **k): raise RuntimeError("torch unavailable")


def _dummy_embeddings(G) -> dict:
    return {str(n): np.zeros(EMB_DIM, dtype=float) for n in G.nodes()} if len(G) else {}


def train_link_prediction(G, epochs=None, lr=None, out_dim=None):
    out_dim = out_dim or EMB_DIM
    if not AVAILABLE or len(G) == 0 or G.number_of_edges() == 0:
        log.warning("train_link_prediction fallback to dummy")
        return None
    try:
        epochs = epochs or config.GRAPH["epochs"]
        lr = lr or config.GRAPH["lr"]
        nodes = [str(n) for n in G.nodes()]
        idx = {n: i for i, n in enumerate(nodes)}
        edges = [(idx[str(u)], idx[str(v)]) for u, v in G.edges()]
        edge_index = torch.tensor(edges, dtype=torch.long).t().contiguous()
        n = len(nodes)
        in_dim = 16
        x = torch.randn(n, in_dim, generator=torch.Generator().manual_seed(config.RANDOM_STATE))
        model = GraphSAGEModel(in_dim, config.GRAPH["hidden_dim"], out_dim)
        opt = torch.optim.Adam(model.parameters(), lr=lr)
        model.train()
        for ep in range(epochs):
            opt.zero_grad()
            z = model(x, edge_index)
            pos = (z[edge_index[0]] * z[edge_index[1]]).sum(1)
            neg_idx = torch.randint(0, n, (len(edges) * 2,), generator=torch.Generator().manual_seed(config.RANDOM_STATE + ep))
            neg = (z[edge_index[0].repeat_interleave(1)[:len(neg_idx) // 2]] * z[neg_idx[:len(neg_idx) // 2]]).sum(1) if False else None
            src = edge_index[0][torch.randint(0, edge_index.size(1), (len(edges),), generator=torch.Generator().manual_seed(ep))]
            dst = torch.randint(0, n, (len(edges),), generator=torch.Generator().manual_seed(ep + 999))
            neg = (z[src] * z[dst]).sum(1)
            loss = torch.nn.functional.binary_cross_entropy_with_logits(
                torch.cat([pos, neg]), torch.cat([torch.ones_like(pos), torch.zeros_like(neg)]))
            loss.backward()
            opt.step()
        model._node_list = nodes
        log.info("graphsage trained epochs=%s loss=%.4f", epochs, float(loss))
        return model
    except Exception:
        log.exception("train_link_prediction failed, dummy fallback")
        return None


def get_embeddings(G, model=None) -> dict:
    if not AVAILABLE or model is None:
        return _dummy_embeddings(G)
    try:
        import torch as _t
        nodes = getattr(model, "_node_list", [str(n) for n in G.nodes()])
        idx = {n: i for i, n in enumerate(nodes)}
        edges = [(idx[str(u)], idx[str(v)]) for u, v in G.edges() if str(u) in idx and str(v) in idx]
        if not edges:
            return _dummy_embeddings(G)
        edge_index = _t.tensor(edges, dtype=_t.long).t().contiguous()
        in_dim = getattr(model, "in_dim", 16)
        x = _t.randn(len(nodes), in_dim, generator=_t.Generator().manual_seed(config.RANDOM_STATE))
        model.eval()
        with _t.no_grad():
            z = model(x, edge_index).cpu().numpy()
        return {n: z[i].astype(float) for i, n in enumerate(nodes)}
    except Exception:
        log.exception("get_embeddings failed, dummy fallback")
        return _dummy_embeddings(G)


def save(model, path=None):
    path = Path(path or config.ARTIFACTS_DIR / "graphsage.pt")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not AVAILABLE or model is None:
        import joblib
        joblib.dump({}, path.with_suffix(".joblib"))
        return path
    torch.save({"state": model.state_dict(), "nodes": getattr(model, "_node_list", []),
                "in_dim": getattr(model, "in_dim", 16)}, path)
    return path


def load(path=None):
    path = Path(path or config.ARTIFACTS_DIR / "graphsage.pt")
    if not AVAILABLE or not path.exists():
        return None
    d = torch.load(path, map_location="cpu")
    m = GraphSAGEModel(d.get("in_dim", 16), config.GRAPH["hidden_dim"], EMB_DIM)
    m.load_state_dict(d["state"])
    m._node_list = d.get("nodes", [])
    m.eval()
    return m

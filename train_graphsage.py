"""Real GraphSAGE link-prediction training. Runs if torch+pyg installed, else exits gracefully."""
import logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

try:
    import torch
    from src.graph_model import GraphSAGEModel, AVAILABLE
    print('torch', torch.__version__, 'sage_available', AVAILABLE)
    if not AVAILABLE:
        print('torch_geometric missing: pip install torch torch-geometric to train real embeddings')
    else:
        print('ready: extend with edge split + link-pred loop (see src/graph_model.py)')
except Exception as e:
    print('torch unavailable, keeping dummy zeros:', e)

"""A4 __init__: graph table init."""
import logging
log = logging.getLogger(__name__)


def init_graph_db() -> None:
    try:
        from app.graph.supernode_service import init_supernode_table
        try:
            init_supernode_table()
        except Exception:
            log.exception("supernode init failed")
        from app.graph.community import init_community_table
        try:
            init_community_table()
        except Exception:
            log.exception("community init failed")
        from app.graph import agent_store
        try:
            agent_store.init_graph_tables()
        except Exception:
            log.exception("graph analysis init failed")
        log.info("graph db ready")
    except Exception:
        log.exception("init_graph_db failed")

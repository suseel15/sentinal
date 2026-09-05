"""A4 graph backend abstraction: NetworkX (+ persisted gpickle) and Neo4j stub."""
import logging
import os
import pickle
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CSV_PATH = REPO_ROOT / "labeled_transactions.csv"
ARTIFACT = REPO_ROOT / "artifacts" / "a4_graph.gpickle"


class ServiceUnavailable(RuntimeError):
    pass


class GraphBackend(ABC):
    @abstractmethod
    def sync(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def get_graph(self):
        raise NotImplementedError

    def stats(self) -> dict:
        try:
            g = self.get_graph()
            return {"nodes": int(g.number_of_nodes()), "edges": int(g.number_of_edges())}
        except Exception:
            log.exception("backend stats failed")
            return {"nodes": 0, "edges": 0}


def _parse_ts(v):
    try:
        if v is None or (isinstance(v, float) and v != v):
            return None
        return datetime.fromisoformat(str(v).strip().replace("Z", "+00:00"))
    except Exception:
        try:
            import pandas as pd
            return pd.to_datetime(v, errors="coerce").to_pydatetime()
        except Exception:
            log.exception("ts parse failed")
            return None


class NetworkXBackend(GraphBackend):
    def __init__(self, csv_path: Path | None = None, artifact: Path | None = None):
        self.csv_path = Path(csv_path) if csv_path else CSV_PATH
        self.artifact = Path(artifact) if artifact else ARTIFACT
        self._g = None

    def sync(self) -> dict:
        try:
            import networkx as nx
            import pandas as pd
            if not self.csv_path.exists():
                log.warning("csv missing %s, empty graph", self.csv_path)
                g = nx.DiGraph()
            else:
                try:
                    df = pd.read_csv(self.csv_path, usecols=["account_id", "counterparty_name", "transaction_id", "date", "amount", "type"], low_memory=True)
                except Exception:
                    log.exception("csv read failed")
                    df = pd.DataFrame()
                g = nx.DiGraph()
                if len(df):
                    for _, r in df.iterrows():
                        try:
                            src = str(r.get("account_id", "")).strip()
                            dst = str(r.get("counterparty_name", "")).strip()
                            if not src or not dst or src == "nan" or dst == "nan":
                                continue
                            amt = abs(float(r.get("amount", 0) or 0))
                            ts = _parse_ts(r.get("date"))
                            tid = str(r.get("transaction_id", ""))
                            ttype = str(r.get("type", "TRANSFER"))
                            if not g.has_node(src):
                                g.add_node(src, kind="ACCOUNT", degree=0, volume=0.0)
                            if not g.has_node(dst):
                                g.add_node(dst, kind="ACCOUNT", degree=0, volume=0.0)
                            g.add_edge(src, dst, txn=tid, amount=amt, timestamp=ts.isoformat() if ts else str(r.get("date", "")), risk=0.0, ttype=ttype)
                        except Exception:
                            log.exception("row build failed, skipping")
                            continue
            for n in list(g.nodes()):
                try:
                    ideg = int(g.in_degree(n))
                    odeg = int(g.out_degree(n))
                    vol_in = float(sum(float(d.get("amount", 0) or 0) for _, _, d in g.in_edges(n, data=True)))
                    vol_out = float(sum(float(d.get("amount", 0) or 0) for _, _, d in g.out_edges(n, data=True)))
                    g.nodes[n]["kind"] = "ACCOUNT"
                    g.nodes[n]["degree"] = ideg + odeg
                    g.nodes[n]["in_degree"] = ideg
                    g.nodes[n]["out_degree"] = odeg
                    g.nodes[n]["volume"] = vol_in + vol_out
                except Exception:
                    log.exception("node prop failed for %s", n)
            self._g = g
            try:
                self.artifact.parent.mkdir(parents=True, exist_ok=True)
                with open(self.artifact, "wb") as f:
                    pickle.dump(g, f, protocol=pickle.HIGHEST_PROTOCOL)
            except Exception:
                log.exception("persist gpickle failed")
            log.info("NetworkX sync nodes=%d edges=%d", g.number_of_nodes(), g.number_of_edges())
            return {"nodes": int(g.number_of_nodes()), "edges": int(g.number_of_edges()), "artifact": str(self.artifact)}
        except Exception:
            log.exception("NetworkX sync failed")
            raise

    def get_graph(self):
        try:
            if self._g is not None:
                return self._g
            try:
                if self.artifact.exists():
                    with open(self.artifact, "rb") as f:
                        self._g = pickle.load(f)
                    log.info("loaded persisted graph nodes=%d", self._g.number_of_nodes())
                    return self._g
            except Exception:
                log.exception("gpickle load failed, rebuilding")
            self.sync()
            return self._g
        except Exception:
            log.exception("get_graph failed")
            raise


class Neo4jBackend(GraphBackend):
    def __init__(self, uri: str | None = None, user: str | None = None, password: str | None = None):
        self.uri = uri or os.environ.get("NEO4J_URI", "")
        self.user = user or os.environ.get("NEO4J_USER", "neo4j")
        self.password = password or os.environ.get("NEO4J_PASSWORD", "neo4j")
        self._driver = None
        try:
            from neo4j import GraphDatabase
            try:
                self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
                self._driver.verify_connectivity()
                log.info("neo4j connected %s", self.uri)
            except ImportError:
                raise
            except Exception as e:
                log.warning("neo4j unreachable %s: %s", self.uri, e)
                raise ServiceUnavailable(f"neo4j unreachable at {self.uri}: {e}")
        except ImportError:
            log.warning("neo4j driver not installed")
            raise ServiceUnavailable("neo4j driver not installed")

    def sync(self) -> dict:
        try:
            import pandas as pd
            if self._driver is None:
                raise ServiceUnavailable("no neo4j driver")
            df = pd.read_csv(CSV_PATH, usecols=["account_id", "counterparty_name", "transaction_id", "date", "amount", "type"], low_memory=True)
            n = 0
            try:
                with self._driver.session() as s:
                    for _, r in df.iterrows():
                        try:
                            s.run("MERGE (a:Account {id:$id}) MERGE (b:Account {id:$bid}) MERGE (a)-[t:TRANSFER {txn:$txn}]->(b) SET t.amount=$amt, t.timestamp=$ts",
                                  id=str(r.get("account_id")), bid=str(r.get("counterparty_name")),
                                  txn=str(r.get("transaction_id")), amt=float(r.get("amount", 0) or 0), ts=str(r.get("date", "")))
                            n += 1
                        except Exception:
                            log.exception("neo4j merge row failed")
                            continue
            except Exception as e:
                log.exception("neo4j sync failed")
                raise ServiceUnavailable(str(e))
            log.info("neo4j sync rows=%d", n)
            return {"rows": n, "backend": "neo4j"}
        except ServiceUnavailable:
            raise
        except Exception:
            log.exception("neo4j sync failed")
            raise ServiceUnavailable("neo4j sync failed")

    def get_graph(self):
        try:
            if self._driver is None:
                raise ServiceUnavailable("no neo4j driver")
            import networkx as nx
            g = nx.DiGraph()
            try:
                with self._driver.session() as s:
                    recs = s.run("MATCH (a:Account)-[t:TRANSFER]->(b:Account) RETURN a.id AS src, b.id AS dst, t.amount AS amt, t.timestamp AS ts, t.txn AS txn LIMIT 200000")
                    for r in recs:
                        try:
                            src, dst = str(r["src"]), str(r["dst"])
                            if not g.has_node(src):
                                g.add_node(src, kind="ACCOUNT")
                            if not g.has_node(dst):
                                g.add_node(dst, kind="ACCOUNT")
                            g.add_edge(src, dst, txn=str(r.get("txn", "")), amount=float(r.get("amt", 0) or 0), timestamp=str(r.get("ts", "")), risk=0.0)
                        except Exception:
                            log.exception("neo4j row map failed")
                            continue
            except Exception as e:
                log.exception("neo4j fetch failed")
                raise ServiceUnavailable(str(e))
            return g
        except ServiceUnavailable:
            raise
        except Exception:
            log.exception("neo4j get_graph failed")
            raise ServiceUnavailable("neo4j get_graph failed")


def get_backend() -> GraphBackend:
    uri = os.environ.get("NEO4J_URI", "").strip()
    if uri:
        try:
            b = Neo4jBackend(uri=uri)
            log.info("using Neo4jBackend")
            return b
        except ServiceUnavailable as e:
            log.warning("neo4j unavailable, falling back to NetworkX: %s", e)
        except Exception:
            log.exception("neo4j init failed, falling back to NetworkX")
    else:
        log.info("NEO4J_URI not set, using NetworkXBackend")
    return NetworkXBackend()

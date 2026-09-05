"""FastAPI entrypoint. Run: uvicorn app.main:app --reload (from E:\\senfin)."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.agents.a1_ingestion import A1Agent
from app.schemas.transaction import RawTransaction
from app.services.store import get_investigation, init_db
from app.services.evidence_store import init as init_evidence
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sentinel")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    init_evidence()
    try:
        from app.graph import init_graph_db
        init_graph_db()
    except Exception:
        log.exception("graph init failed")
    app.state.agent = A1Agent()
    log.info("SENTINEL backend ready")
    yield

app = FastAPI(title="SENTINEL A1 Ingestion", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GatherRequest(BaseModel):
    investigation_id: str


def _agent(req: Request) -> A1Agent:
    a = getattr(req.app.state, "agent", None)
    if a is None:
        a = req.app.state.agent = A1Agent()
    return a


@app.post("/transactions")
def post_transaction(body: RawTransaction, req: Request):
    try:
        return _agent(req).ingest(body.data, body.source_system or "UNKNOWN")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/investigations/{inv_id}")
def get_investigation_by_id(inv_id: str):
    inv = get_investigation(inv_id)
    if not inv:
        raise HTTPException(status_code=404, detail=f"investigation {inv_id} not found")
    return inv


class StartRequest(BaseModel):
    transaction_id: str | None = None
    payload: dict | None = None
    sync: bool = False


@app.post("/investigations/start")
def post_investigations_start(body: StartRequest):
    """Phase 7 end-to-end entrypoint.
    Provide either transaction_id (looked up in labeled_transactions.csv)
    or payload (a canonical transaction dict)."""
    from app.agents import orchestrator
    try:
        if body.transaction_id:
            return orchestrator.start_from_transaction_id(body.transaction_id, run_async=not body.sync)
        if body.payload:
            return orchestrator.start_from_payload(body.payload, run_async=not body.sync)
        raise HTTPException(status_code=422, detail="transaction_id or payload required")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/investigations")
def list_investigations_ep(status: str | None = None, limit: int = 200):
    from app.services import store as st
    items = st.list_investigations(status=status, limit=min(limit, 500))
    return {"count": len(items),
            "investigations": [{"investigation_id": i["inv_id"], "transaction_id": i["txn_id"],
                                "status": i["status"], "updated": i["updated"],
                                "risk_score": (i.get("result") or {}).get("risk_score"),
                                "risk_level": (i.get("result") or {}).get("risk_level")}
                               for i in items]}


@app.get("/reports")
def list_reports(limit: int = 200):
    """Persisted high-risk cases for the Reports section."""
    from app.services import store as st
    out = []
    for status in ("WAITING_FOR_HUMAN", "ESCALATED", "IN_PROGRESS", "REQUESTED_MORE_EVIDENCE"):
        out.extend(st.list_investigations(status=status, limit=limit))
    seen, items = set(), []
    for i in sorted(out, key=lambda x: x.get("updated", ""), reverse=True):
        if i["inv_id"] in seen:
            continue
        seen.add(i["inv_id"])
        rep = st.get_section(i["inv_id"], "A7", "report")
        rec = st.get_section(i["inv_id"], "A8", "recommendation")
        items.append({"investigation_id": i["inv_id"], "transaction_id": i["txn_id"],
                      "status": i["status"], "updated": i["updated"],
                      "risk_score": (i.get("result") or {}).get("risk_score"),
                      "risk_level": (i.get("result") or {}).get("risk_level"),
                      "recommendation": (rec or {}).get("recommendation"),
                      "report_ready": bool(rep)})
        if len(items) >= limit:
            break
    return {"count": len(items), "reports": items}


@app.post("/investigations/{inv_id}/refresh")
def refresh_investigation(inv_id: str):
    """Re-run A2 models on the stored canonical payload; update state + sections."""
    from app.services import store as st
    from app.agents import orchestrator
    state = st.get_state(inv_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"investigation {inv_id} not found")
    try:
        payload = state.get("payload") or {}
        canonical = payload.get("canonical") or payload
        if not canonical:
            raise ValueError("no stored canonical payload")
        triage = {"decision": "FULL_INVESTIGATION", "triage_score": 1.0}
        a2 = orchestrator._run_a2(canonical, triage)
        st.save_section(inv_id, "A2", "detection", a2)
        risk = float(a2.get("risk_score") or 0)
        st.update_status(inv_id, state.get("status") or "A2_COMPLETED", risk,
                         str(a2.get("risk_level") or "LOW"))
        st.log_event(inv_id, "API", "MODELS_RERUN")
        return {"investigation_id": inv_id, "risk_score": a2.get("risk_score"),
                "risk_level": a2.get("risk_level"),
                "top_reasons": a2.get("top_reasons", [])[:8],
                "possible_typologies": a2.get("possible_typologies", [])}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"refresh failed: {e}")


@app.post("/simulate")
def post_simulate(body: dict):
    from app import demo
    from app.agents import orchestrator
    sid = str((body or {}).get("scenario_id", "suspicious_structuring"))
    try:
        scenarios = {s["scenario_id"]: s for s in demo.list_scenarios()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"scenarios unavailable: {e}")
    if sid not in scenarios:
        raise HTTPException(status_code=422, detail=f"unknown scenario. valid: {sorted(scenarios)}")
    try:
        return {"scenario_id": sid, **demo.run_scenario(sid, sync=True)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"simulation failed: {e}")


@app.get("/simulate/scenarios")
def list_simulate_scenarios():
    from app import demo
    return {"scenarios": demo.list_scenarios()}


def _section_or_auto_closed(inv_id: str, agent: str, section: str, label: str):
    from app.services import store as st
    inv = st.get_investigation(inv_id)
    if not inv:
        raise HTTPException(status_code=404, detail=f"investigation {inv_id} not found")
    rep = st.get_section(inv_id, agent, section)
    if rep:
        return rep
    if (inv.get("status") or "") in ("AUTO_CLOSED", "CLOSED", "DUPLICATE_LOGGED"):
        return {"available": False,
                "reason": f"case {inv.get('status', '').lower().replace('_', ' ')} below investigation threshold; no {label} generated. Risk was {(inv.get('result') or {}).get('risk_score')}. Use refresh to re-run models."}
    raise HTTPException(status_code=404, detail=f"{label} for {inv_id} not ready yet; pipeline may still be running")


@app.get("/investigations/{inv_id}/state")
def get_investigation_state(inv_id: str):
    from app.services import store as st
    state = st.get_state(inv_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"investigation {inv_id} not found")
    state["sections"] = st.list_all_sections(inv_id)
    try:
        state["human_decision"] = st.get_human_decision(inv_id)
    except Exception:
        state["human_decision"] = None
    return state


@app.get("/investigations/{inv_id}/report")
def get_investigation_report(inv_id: str):
    return _section_or_auto_closed(inv_id, "A7", "report", "report")


@app.get("/investigations/{inv_id}/recommendation")
def get_investigation_recommendation(inv_id: str):
    return _section_or_auto_closed(inv_id, "A8", "recommendation", "recommendation")


@app.get("/investigations/{inv_id}/regulatory")
def get_investigation_regulatory(inv_id: str):
    return _section_or_auto_closed(inv_id, "A5", "regulatory", "regulatory analysis")


class HumanDecisionRequest(BaseModel):
    investigator_id: str
    decision: str
    justification: str | None = None
    confirmed_outcome: str | None = None


@app.post("/investigations/{inv_id}/human-decision")
def post_human_decision(inv_id: str, body: HumanDecisionRequest):
    from app.agents import orchestrator
    res = orchestrator.submit_human_decision(
        investigation_id=inv_id,
        investigator_id=body.investigator_id,
        decision=body.decision,
        justification=body.justification,
        confirmed_outcome=body.confirmed_outcome,
    )
    if "error" in res:
        code = 404 if "not_found" in res["error"] else 422
        raise HTTPException(status_code=code, detail=res["error"])
    return res


@app.get("/investigations/{inv_id}/audit")
def get_investigation_audit(inv_id: str):
    import sqlite3, json
    from pathlib import Path as _P
    from app.services.store import _db_path
    try:
        with sqlite3.connect(str(_db_path())) as c:
            c.row_factory = sqlite3.Row
            rows = c.execute("SELECT actor, event, at FROM audit_events WHERE inv_id=? ORDER BY id ASC", (inv_id,)).fetchall()
        return {"investigation_id": inv_id, "events": [dict(r) for r in rows]}
    except Exception as e:
        log.exception("audit fetch failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/llm/status")
def get_llm_status():
    from app.services import llm
    return {"available": llm.available(), "model": llm.NVIDIA_MODEL, "url": llm.NVIDIA_URL}


@app.get("/models/evaluation")
def get_models_evaluation(refresh: bool = False):
    """Return per-model evaluation metrics (XGBoost, IF, Rules, Fusion)."""
    from app import evaluation
    if refresh:
        return evaluation.evaluate_all()
    m = evaluation.load_metrics()
    if not m:
        # Compute lazily so the dashboard is always useful even before
        # someone has explicitly run the evaluation script.
        return evaluation.evaluate_all()
    return m


@app.post("/models/evaluation/run")
def post_models_evaluation_run():
    """Force a fresh evaluation run. Returns metrics + writes to artifacts/."""
    from app import evaluation
    return evaluation.evaluate_all()


@app.get("/")
def root_dashboard():
    from pathlib import Path as _P
    html = _P(__file__).resolve().parent.parent / "frontend" / "index.html"
    if not html.exists():
        raise HTTPException(status_code=404, detail="frontend not built")
    from fastapi.responses import HTMLResponse
    return HTMLResponse(html.read_text(encoding="utf-8"))


class StreamStartRequest(BaseModel):
    csv_path: str | None = None
    rps: float = 0.5
    limit: int | None = 10
    start_index: int = 0
    resume: bool = True


@app.post("/stream/start")
def post_stream_start(body: StreamStartRequest):
    from app import streamer
    return streamer.start_async(body.csv_path, body.rps, body.limit, body.start_index, body.resume)


@app.post("/stream/reset")
def post_stream_reset():
    from app import streamer
    return streamer.reset_offset()


@app.post("/stream/stop")
def post_stream_stop():
    from app import streamer
    return streamer.request_stop()


@app.get("/stream/status")
def get_stream_status():
    from app import streamer
    return streamer.get_status()


@app.get("/stream/recent")
def get_stream_recent():
    from app import streamer
    return {"recent": streamer.STATE.recent}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/system/full-health")
def get_system_full_health():
    """Validate every component of the SENTINEL platform."""
    from pathlib import Path
    import json as _json
    components: dict[str, dict] = {}

    def _check(name: str, fn):
        try:
            ok, detail = fn()
            components[name] = {"status": "HEALTHY" if ok else "DEGRADED", "detail": detail}
        except Exception as e:
            components[name] = {"status": "UNHEALTHY", "error": str(e)}

    # 1. SQLite store
    def _db():
        from app.services.store import _db_path
        p = _db_path()
        return (p.exists(), str(p))
    _check("database", _db)

    # 2. Rules engine (apply_rules)
    def _rules():
        import pandas as _pd
        from src.rules_engine import apply_rules
        df = _pd.DataFrame([{"transaction_id": "x", "account_id": "a",
                             "counterparty_name": "b", "date": "2025-01-01",
                             "amount": 100, "type": "DEBIT", "category": "TRANSFER"}])
        out = apply_rules(df)
        return (not out.empty, f"{len(out)} rows")
    _check("rules_engine", _rules)

    # 3. XGBoost model
    def _xgb():
        from pathlib import Path
        p = Path("artifacts/xgb.json")
        return (p.exists(), f"xgb.json={'yes' if p.exists() else 'no'}")
    _check("xgboost", _xgb)

    # 4. Isolation Forest
    def _iforest():
        from pathlib import Path
        p = Path("artifacts/anomaly_detector.joblib")
        return (p.exists(), f"anomaly_detector.joblib={'yes' if p.exists() else 'no'}")
    _check("isolation_forest", _iforest)

    # 5. Autoencoder (graph embeddings used as fallback)
    def _ae():
        from pathlib import Path
        p = Path("artifacts/graph_emb.joblib")
        return (p.exists(), f"graph_emb.joblib={'yes' if p.exists() else 'no'}")
    _check("autoencoder_or_graph_emb", _ae)

    # 6. Fusion / calibrated meta-model
    def _fusion():
        from pathlib import Path
        p = Path("artifacts/calibrated_model.joblib")
        return (p.exists(), f"calibrated_model.joblib={'yes' if p.exists() else 'no'}")
    _check("fusion_engine", _fusion)

    # 7. Graph backend
    def _graph():
        from app.graph.backend import get_backend
        b = get_backend()
        g = b.get_graph()
        return (g is not None, f"backend={type(b).__name__}")
    _check("graph_engine", _graph)

    # 8. Evidence store
    def _evstore():
        from app.services.evidence_store import init as i
        i()
        return (True, "evidence_store_initialised")
    _check("evidence_store", _evstore)

    # 9. Regulatory corpus
    def _reg():
        from pathlib import Path
        p = Path("app/data/regulatory_corpus.json")
        if not p.exists():
            return (False, "regulatory_corpus.json missing")
        data = _json.loads(p.read_text())
        return (bool(data), f"{len(data) if isinstance(data, (list, dict)) else 0} entries")
    _check("regulatory_corpus", _reg)

    # 10. NVIDIA LLM
    def _llm():
        from app.services import llm
        return (llm.available(), "NVIDIA_API_KEY set" if llm.available() else "template fallback")
    _check("nvidia_llm", _llm)

    # 11. FastAPI itself
    components["fastapi"] = {"status": "HEALTHY", "detail": "routes=" + str(len(app.routes))}

    overall = "HEALTHY"
    for c in components.values():
        if c["status"] == "UNHEALTHY":
            overall = "UNHEALTHY"
            break
        if c["status"] == "DEGRADED" and overall == "HEALTHY":
            overall = "DEGRADED"
    return {"overall_status": overall, "components": components}


@app.get("/demo/scenarios")
def get_demo_scenarios():
    """List the predefined demo scenarios for the live demonstration mode."""
    from app import demo
    return {"scenarios": demo.list_scenarios(), "jurisdiction": list(demo.jurisdiction())}


class DemoRunRequest(BaseModel):
    scenario_id: str
    sync: bool = True


@app.post("/demo/run")
def post_demo_run(body: DemoRunRequest):
    """Run a predefined demo scenario through the full pipeline."""
    from app import demo
    return demo.run_scenario(body.scenario_id, sync=body.sync)


@app.post("/evidence/gather")
def post_evidence_gather(body: GatherRequest):
    from app.agents import a3_evidence
    from app.services import evidence_store as es
    try:
        es.init()
        pack = a3_evidence.gather(body.investigation_id)
        return pack.model_dump() if hasattr(pack, "model_dump") else pack
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/evidence/{inv_id}")
def get_evidence(inv_id: str):
    from app.services import evidence_store as es
    pack = es.get_pack(inv_id)
    if not pack:
        raise HTTPException(status_code=404, detail=f"evidence {inv_id} not found")
    return pack


@app.get("/evidence/{inv_id}/summary")
def get_evidence_summary(inv_id: str):
    from app.services import evidence_store as es
    s = es.get_summary(inv_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"evidence {inv_id} not found")
    return s


@app.get("/evidence/{inv_id}/timeline")
def get_evidence_timeline(inv_id: str):
    from app.services import evidence_store as es
    items = es.get_timeline(inv_id)
    if not items:
        raise HTTPException(status_code=404, detail=f"evidence {inv_id} not found")
    return items


@app.post("/investigations/{inv_id}/graph-analysis")
def post_graph_analysis(inv_id: str):
    from app.agents import a4_graph
    try:
        r = a4_graph.analyze(inv_id)
        return r.model_dump() if hasattr(r, "model_dump") else r
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.exception("graph-analysis failed for %s", inv_id)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/investigations/{inv_id}/graph")
def get_graph(inv_id: str):
    from app.graph import agent_store as gs
    try:
        gs.init_graph_tables()
    except Exception:
        log.exception("graph tables init failed")
    a = gs.get_analysis(inv_id)
    if not a:
        raise HTTPException(status_code=404, detail=f"graph analysis {inv_id} not found")
    return a.get("result") or {}


@app.get("/investigations/{inv_id}/graph/visualization")
def get_graph_viz(inv_id: str):
    from app.graph import agent_store as gs
    from app.graph import supernode_service as sns
    try:
        gs.init_graph_tables()
    except Exception:
        log.exception("graph tables init failed")
    a = gs.get_analysis(inv_id)
    if not a:
        raise HTTPException(status_code=404, detail=f"graph analysis {inv_id} not found")
    res = a.get("result") or {}
    nodes_out, edges_out = [], []
    try:
        ents = list(res.get("supporting_entities") or [])[:500]
        tx_by_edge = {}
        try:
            for t in (res.get("supporting_transactions") or [])[:500]:
                tx_by_edge[str(t)] = True
        except Exception:
            pass
        mf_edges = []
        try:
            from app.graph.backend import get_backend
            from app.graph.traversal import bounded_bfs
            import json as _json
            from pathlib import Path as _P
            cfg = _json.loads((_P(__file__).resolve().parent.parent / "config" / "a4.json").read_text())
            trow = gs.get_txn_by_inv(inv_id)
            can = ((trow or {}).get("payload") or {}).get("canonical") or {}
            seed = str(can.get("source_account") or res.get("money_flow", {}).get("seed", "") or (ents[0] if ents else ""))
            sts = can.get("timestamp")
            g = get_backend().get_graph()
            def _hub(n):
                try:
                    return sns.is_hub(n, cfg)
                except Exception:
                    return False
            _n, _e, _m, _t = bounded_bfs(g, seed, sts, int(cfg.get("MAX_HOPS", 4)), 500, int(cfg.get("TIME_WINDOW_HOURS", 72)), _hub)
            mf_edges = _e
        except Exception:
            log.exception("viz rebuild failed, using stored entities")
        if mf_edges:
            nset = set()
            for e in mf_edges:
                try:
                    nset.add(str(e["source"]))
                    nset.add(str(e["target"]))
                    edges_out.append({"source": str(e["source"]), "target": str(e["target"]),
                                      "amount": float(e.get("amount", 0) or 0),
                                      "timestamp": str(e.get("timestamp", "")),
                                      "txn_id": str(e.get("txn", "")), "via_hub": bool(e.get("via_hub", False))})
                except Exception:
                    continue
            ents = sorted(nset)
        for n in ents[:500]:
            try:
                nodes_out.append({"id": str(n), "degree": 0, "in_degree": 0, "out_degree": 0,
                                  "volume": 0.0, "is_hub": bool(sns.is_hub(n))})
            except Exception:
                nodes_out.append({"id": str(n)})
    except Exception:
        log.exception("viz build failed")
    return {"investigation_id": inv_id, "nodes": nodes_out, "edges": edges_out,
            "analysis_mode": res.get("analysis_mode"), "status": res.get("status")}


@app.get("/graph/super-nodes")
def list_super_nodes():
    from app.graph import supernode_service as sns
    try:
        sns.init_supernode_table()
    except Exception:
        log.exception("supernode init failed")
    try:
        return {"super_nodes": sns.get_super_nodes()}
    except Exception as e:
        log.exception("super-nodes failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/graph/sync")
def post_graph_sync():
    from app.graph.backend import get_backend
    from app.graph import supernode_service as sns
    from app.graph import community as com
    try:
        b = get_backend()
        stats = b.sync()
        try:
            import json as _json
            from pathlib import Path as _P
            cfg = _json.loads((_P(__file__).resolve().parent.parent / "config" / "a4.json").read_text())
        except Exception:
            cfg = {}
        try:
            sns.compute_supernodes(b, cfg)
        except Exception:
            log.exception("supernode compute after sync failed")
        try:
            com.ensure_communities(b.get_graph(), timeout_s=60)
        except Exception:
            log.exception("community compute after sync failed")
        return {"synced": True, "stats": stats}
    except Exception as e:
        log.exception("graph sync failed")
        raise HTTPException(status_code=500, detail=str(e))

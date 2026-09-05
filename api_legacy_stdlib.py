"""SENTINEL investigation API (stdlib only, no deps). Serves inference + case output."""
import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sentinel-api")


def build_case(pred: dict) -> dict:
    return {
        "case_id": f"CASE-{pred.get('transaction_id', 'unknown')}",
        "risk_score": pred.get("risk_score"),
        "risk_level": pred.get("risk_level"),
        "fraud_probability": pred.get("fraud_probability"),
        "rule_score": pred.get("rule_score"),
        "anomaly_score": pred.get("anomaly_score"),
        "possible_typologies": pred.get("possible_typologies", []),
        "top_reasons": pred.get("top_reasons", []),
        "shap": pred.get("shap", {}),
        "status": "OPEN" if pred.get("risk_score", 0) >= 60 else "AUTO_CLOSED",
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/health"):
            self._send(200, {"status": "ok"})
        elif self.path.startswith("/case"):
            qs = parse_qs(urlparse(self.path).query)
            tid = (qs.get("transaction_id", [""])[0])
            try:
                import pandas as pd
                from src.inference import sentinel_predict
                df = pd.read_csv("labeled_transactions.csv")
                row = df[df.transaction_id == tid]
                if not len(row):
                    return self._send(404, {"error": "transaction not found"})
                hist = df[(df.account_id == row.iloc[0].account_id) & (df.date < row.iloc[0].date)].tail(20)
                pred = sentinel_predict(row.iloc[0].to_dict(), history_df=hist)
                self._send(200, build_case(pred))
            except Exception as e:
                log.exception("case failed")
                self._send(500, {"error": str(e)})
        else:
            self._send(404, {"error": "use POST /predict, GET /case?transaction_id=, GET /health"})

    def do_POST(self):
        if self.path.startswith("/predict"):
            try:
                n = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(n) or b"{}")
                import pandas as pd
                from src.inference import sentinel_predict
                hist = None
                if payload.get("account_id"):
                    df = pd.read_csv("labeled_transactions.csv")
                    hist = df[df.account_id == payload["account_id"]].tail(20)
                pred = sentinel_predict(payload.get("transaction", payload), history_df=hist)
                self._send(200, build_case(pred))
            except Exception as e:
                log.exception("predict failed")
                self._send(500, {"error": str(e)})
        else:
            self._send(404, {"error": "unknown endpoint"})


if __name__ == "__main__":
    srv = HTTPServer(("0.0.0.0", 8000), Handler)
    log.info("SENTINEL API on :8000")
    srv.serve_forever()

"""SHAP TreeExplainer wrapper."""
import logging
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


class ShapExplainer:
    def __init__(self, model, feature_names):
        try:
            import shap
            self.explainer = shap.TreeExplainer(model)
            self.ok = True
        except Exception as e:
            log.warning("shap unavailable: %s", e)
            self.explainer = None
            self.ok = False
        self.feature_names = list(feature_names)

    def global_importance(self, X: pd.DataFrame, max_n=2000) -> pd.Series:
        try:
            if not self.ok:
                return pd.Series(0.0, index=self.feature_names)
            Xs = X[self.feature_names].fillna(0).values[:max_n]
            v = np.asarray(self.explainer.shap_values(Xs))
            if v.ndim == 3:
                v = v[:, :, 1] if v.shape[2] == 2 else v.mean(2)
            imp = pd.Series(np.abs(v).mean(0), index=self.feature_names).sort_values(ascending=False)
            return imp
        except Exception:
            log.exception("global_importance failed")
            raise

    def explain_one(self, row: pd.Series) -> dict:
        try:
            if not self.ok:
                return {"top_features": [], "sentence": "Explanation unavailable (SHAP not installed)."}
            x = row[self.feature_names].fillna(0).values.reshape(1, -1)
            v = np.asarray(self.explainer.shap_values(x))
            if v.ndim == 3:
                v = v[:, :, 1] if v.shape[2] == 2 else v.mean(2)
            vals = v.ravel()
            idx = np.argsort(np.abs(vals))[::-1][:5]
            top = [{"feature": self.feature_names[i], "value": float(x.ravel()[i]),
                    "shap": float(vals[i])} for i in idx]
            s = "; ".join(f"{t['feature']}={t['value']:.3g} (impact {t['shap']:+.3f})" for t in top)
            return {"top_features": top,
                    "sentence": f"Top drivers: {s}." if s else "No strong drivers."}
        except Exception:
            log.exception("explain_one failed")
            raise

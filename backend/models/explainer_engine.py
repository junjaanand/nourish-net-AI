"""
Engine C: SHAP Explainability & Fairness Engine
=================================================
Trains a lightweight GradientBoosting model on match features and uses
SHAP TreeExplainer to produce per-decision waterfall explanations.
Also checks geographic distribution fairness.
"""

import numpy as np
import io
import base64
import warnings
from typing import Optional

# Safe matplotlib import (non-interactive backend)
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    HAS_MATPLOTLIB = True
except Exception:
    HAS_MATPLOTLIB = False

warnings.filterwarnings("ignore", category=FutureWarning)

from sklearn.ensemble import GradientBoostingClassifier

# Try importing shap; fall back to manual explanation if unavailable
try:
    import shap
    HAS_SHAP = True
except ImportError:
    HAS_SHAP = False

# ── Feature schema ────────────────────────────────────────────────────────
FEATURE_NAMES = [
    "Urgency",
    "Capacity Fit",
    "Community Need",
    "Proximity",
    "Dietary Match",
    "Freshness",
    "Transit Time",
]

# ── Synthetic Training Data ──────────────────────────────────────────────

def generate_training_data(n_samples: int = 300) -> tuple[np.ndarray, np.ndarray]:
    """
    Generate synthetic (feature, label) pairs with realistic decision patterns.

    Features: [urgency, capacity_fit, need, proximity, dietary, freshness, transit]
    Label: 1 = good match, 0 = poor match
    """
    rng = np.random.RandomState(42)
    X = np.zeros((n_samples, 7))

    # urgency ∈ [0,1]
    X[:, 0] = rng.uniform(0, 1, n_samples)
    # capacity_fit ∈ [0,1]
    X[:, 1] = rng.uniform(0, 1, n_samples)
    # community_need ∈ [0,1]
    X[:, 2] = rng.uniform(0, 1, n_samples)
    # proximity ∈ [0,1]
    X[:, 3] = rng.uniform(0, 1, n_samples)
    # dietary ∈ {0, 0.3, 1}
    X[:, 4] = rng.choice([0.0, 0.3, 1.0], n_samples, p=[0.1, 0.2, 0.7])
    # freshness ∈ [0, 100]
    X[:, 5] = rng.uniform(0, 100, n_samples)
    # transit_time ∈ [10, 120]
    X[:, 6] = rng.uniform(10, 120, n_samples)

    # Decision rule (with noise):
    # Good match if weighted composite is high enough
    composite = (
        0.30 * X[:, 0] +
        0.20 * X[:, 1] +
        0.20 * X[:, 2] +
        0.20 * X[:, 3] +
        0.10 * X[:, 4]
    )
    freshness_ok = X[:, 5] > 20
    transit_ok = X[:, 6] < 90

    prob = composite * 0.6 + 0.2 * freshness_ok.astype(float) + 0.2 * transit_ok.astype(float)
    noise = rng.normal(0, 0.08, n_samples)
    y = (prob + noise > 0.55).astype(int)

    return X, y


# ── Model Training ───────────────────────────────────────────────────────

def train_explainer_model(
    X: Optional[np.ndarray] = None,
    y: Optional[np.ndarray] = None,
) -> tuple:
    """
    Train a GradientBoostingClassifier and create a SHAP explainer.

    Returns (model, explainer) — explainer may be None if shap is unavailable.
    """
    if X is None or y is None:
        X, y = generate_training_data()

    model = GradientBoostingClassifier(
        n_estimators=80,
        max_depth=4,
        learning_rate=0.1,
        random_state=42,
    )
    model.fit(X, y)

    explainer = None
    if HAS_SHAP:
        try:
            explainer = shap.TreeExplainer(model)
        except Exception:
            pass

    return model, explainer


# ── Explanation Generation ────────────────────────────────────────────────

def explain_match(
    model,
    explainer,
    features: list[float],
) -> dict:
    """
    Generate SHAP explanation for a single match decision.

    Parameters
    ----------
    model     : trained sklearn model
    explainer : shap.TreeExplainer (or None)
    features  : 7 floats [urgency, cap_fit, need, prox, dietary, freshness, transit]

    Returns
    -------
    dict with shap_values, feature_names, base_value, prediction, feature_values
    """
    X = np.array(features).reshape(1, -1)
    prediction = float(model.predict_proba(X)[0, 1])

    if explainer is not None and HAS_SHAP:
        sv = explainer.shap_values(X)
        if isinstance(sv, list):
            shap_vals = sv[1][0].tolist() if len(sv) > 1 else sv[0][0].tolist()
        elif len(sv.shape) == 3:
            shap_vals = sv[0, :, 1].tolist() if sv.shape[2] > 1 else sv[0, :, 0].tolist()
        elif len(sv.shape) == 2:
            shap_vals = sv[0].tolist()
        else:
            shap_vals = sv.tolist()

        ev = np.atleast_1d(explainer.expected_value)
        base = float(ev[1]) if len(ev) > 1 else float(ev[0])
    else:
        # Fallback: use feature importances as pseudo-SHAP
        importances = model.feature_importances_
        shap_vals = (importances * np.array(features) / (np.sum(importances * np.abs(np.array(features))) + 1e-9)).tolist()
        base = 0.5

    return {
        "shap_values": [round(v, 4) for v in shap_vals],
        "feature_names": FEATURE_NAMES,
        "feature_values": [round(f, 4) for f in features],
        "base_value": round(base, 4),
        "prediction": round(prediction, 4),
    }


# ── Waterfall Plot ────────────────────────────────────────────────────────

def generate_shap_waterfall_plot(
    shap_values: list[float],
    feature_names: list[str],
    base_value: float,
    prediction: Optional[float] = None,
    max_display: int = 7,
) -> str:
    """
    Render a SHAP-style horizontal waterfall chart as a base64-encoded PNG.

    Returns base64 string that can be embedded as <img src="data:image/png;base64,...">
    """
    if not HAS_MATPLOTLIB:
        return ""

    # Sort features by absolute SHAP value
    paired = list(zip(feature_names, shap_values))
    paired.sort(key=lambda x: abs(x[1]), reverse=True)
    paired = paired[:max_display]

    names = [p[0] for p in reversed(paired)]
    vals  = [p[1] for p in reversed(paired)]

    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    fig = Figure(figsize=(8, 4), dpi=100)
    canvas = FigureCanvasAgg(fig)
    fig.patch.set_facecolor("#1a1a2e")
    ax = fig.add_subplot(111)
    ax.set_facecolor("#1a1a2e")

    colors = ["#FF6B6B" if v > 0 else "#4ECDC4" for v in vals]
    y_pos = range(len(names))

    bars = ax.barh(y_pos, vals, color=colors, height=0.6, edgecolor="none")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=10, color="white")
    ax.set_xlabel("SHAP Value (impact on match decision)", fontsize=10, color="white")
    ax.set_title("Why This Match? — SHAP Explanation", fontsize=13, color="white", fontweight="bold", pad=15)

    # Value labels on bars
    for bar, val in zip(bars, vals):
        x_pos = bar.get_width()
        ha = "left" if val >= 0 else "right"
        offset = 0.005 if val >= 0 else -0.005
        ax.text(
            x_pos + offset, bar.get_y() + bar.get_height() / 2,
            f"{val:+.3f}", va="center", ha=ha,
            fontsize=9, color="white", fontweight="bold",
        )

    # Legend
    pos_patch = mpatches.Patch(color="#FF6B6B", label="Increases match likelihood")
    neg_patch = mpatches.Patch(color="#4ECDC4", label="Decreases match likelihood")
    ax.legend(handles=[pos_patch, neg_patch], loc="lower right", fontsize=8,
              facecolor="#16213e", edgecolor="none", labelcolor="white")

    # Base value annotation
    if prediction is not None:
        ax.annotate(
            f"Base: {base_value:.2f} → Prediction: {prediction:.2f}",
            xy=(0.98, 0.02), xycoords="axes fraction",
            fontsize=8, color="#aaa", ha="right",
        )

    ax.tick_params(colors="white", labelsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color("#444")
    ax.spines["left"].set_color("#444")
    ax.axvline(x=0, color="#666", linewidth=0.8, linestyle="--")

    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor(), bbox_inches="tight")
    buf.seek(0)

    return base64.b64encode(buf.read()).decode("utf-8")


# ── Fairness Check ────────────────────────────────────────────────────────

def check_distribution_fairness(
    matches: list[dict],
    ngos: list[dict],
) -> dict:
    """
    Check whether food distribution is geographically equitable.

    Computes a Gini coefficient over allocation counts and flags
    under-served NGOs (receiving <10% of their fair share).
    """
    if not ngos:
        return {"is_fair": True, "gini_coefficient": 0.0, "underserved_ngos": [], "details": "No NGOs registered."}

    # Count allocations per NGO
    alloc = {n.get("id"): 0 for n in ngos}
    for m in matches:
        nid = m.get("ngo_id")
        if nid in alloc:
            alloc[nid] += 1

    counts = sorted(alloc.values())
    n = len(counts)

    # Gini coefficient
    if n == 0 or sum(counts) == 0:
        gini = 0.0
    else:
        total = sum(counts)
        cum = 0.0
        weighted_sum = 0.0
        for i, c in enumerate(counts, 1):
            cum += c
            weighted_sum += i * c
        gini = (2 * weighted_sum) / (n * total) - (n + 1) / n
        gini = round(max(0.0, min(1.0, gini)), 4)

    # Fair share: equal distribution
    total_matches = len(matches)
    fair_share = total_matches / max(n, 1)
    threshold = max(1, fair_share * 0.1)

    underserved = []
    for ngo in ngos:
        nid = ngo.get("id")
        if alloc.get(nid, 0) < threshold and total_matches > 0:
            underserved.append({"ngo_id": nid, "ngo_name": ngo.get("name", ""), "allocations": alloc.get(nid, 0)})

    is_fair = gini < 0.4 and len(underserved) == 0

    return {
        "is_fair": is_fair,
        "gini_coefficient": gini,
        "underserved_ngos": underserved,
        "total_matches": total_matches,
        "total_ngos": n,
        "details": (
            f"Gini={gini:.3f}. "
            + (f"{len(underserved)} NGO(s) are under-served." if underserved else "Distribution is equitable.")
        ),
    }

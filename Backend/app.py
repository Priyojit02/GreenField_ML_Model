from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import pickle
import numpy as np
import pandas as pd
import math
from typing import Dict, Optional

# Canonical columns expected in the model bundle
CANONICAL_COLS = [
    "Client Revenue",
    "Number of Users",
    "RICEFW",
    "Duration (Months)",
    "Countries/Market",
    "Estimated Effort (man days)",
]

app = FastAPI()

# --- Enable CORS so React frontend can call this API ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



class InputData(BaseModel):
    inputs: Dict[str, Optional[float]]


# Adjust this path to where your bundle actually is
BUNDLE_PATH = r"C:\ML_PRED\Backend\model_bundle.pkl"


def load_bundle(path: str = BUNDLE_PATH):
    with open(path, "rb") as f:
        return pickle.load(f)


# Load bundle once at startup
bundle = load_bundle()
models = bundle["models"]
raw_reports = bundle.get("reports", [])


def clean_number(v):
    """Convert NaN/inf to None, everything else to float."""
    if v is None:
        return None
    if isinstance(v, (np.floating, np.integer)):
        v = float(v)
    if isinstance(v, (int, float)):
        if math.isnan(v) or math.isinf(v):
            return None
        return float(v)
    try:
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except (TypeError, ValueError):
        return None


def sanitize_reports(reports):
    """Make reports JSON-safe (no NaN/inf)."""
    safe = []
    for r in reports:
        safe_r = {}
        for k, v in r.items():
            if isinstance(v, (int, float, np.number)):
                safe_r[k] = clean_number(v)
            else:
                safe_r[k] = v
        safe.append(safe_r)
    return safe


def predict_missing(known: Dict[str, Optional[float]]):
    # Initialize all values as NaN
    vals = {c: np.nan for c in CANONICAL_COLS}

    # Fill known values
    for k, v in known.items():
        if k in vals and v is not None:
            try:
                vals[k] = float(v)
            except ValueError:
                vals[k] = np.nan

    # Iteratively predict missing values
    for _ in range(50):
        changed = False
        for target, model in models.items():
            x_cols = [c for c in CANONICAL_COLS if c != target]
            x = pd.DataFrame(
                [[vals[c] if not np.isnan(vals[c]) else 0.0 for c in x_cols]],
                columns=x_cols,
            )
            pred = float(model.predict(x)[0])
            if np.isnan(vals[target]) and target not in known:
                vals[target] = pred
                changed = True
        if not changed:
            break

    # sanitize NaN to None so JSON can serialize
    clean_vals = {k: (None if pd.isna(v) else float(v)) for k, v in vals.items()}

    # sanitize reports (for reliability display)
    safe_reports = sanitize_reports(raw_reports)

    return {"predictions": clean_vals, "reports": safe_reports}


@app.post("/predict")
def predict(data: InputData):
    return predict_missing(data.inputs)
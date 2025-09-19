from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
from datetime import datetime
import os
from functools import lru_cache

app = FastAPI(title="Officer Collections API 🚀")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR-21kv5EFe1-Vp9TiY1GxsazJcG2fZj6qQ-24Z9Cveco76E22SDRbAya9s8PMPYXb-IvR8LdcOIFgd/pub?gid=421148399&single=true&output=csv"
MESSAGES_FILE = "team_messages.csv"

@lru_cache(maxsize=1)
def load_data():
    try:
        df = pd.read_csv(DATA_URL)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load data: {e}")

    df["officer"] = df["officer"].astype(str).str.strip().str.title()
    repaid_cols = [c for c in df.columns if c.lower().startswith("repaid") and c.lower() != "repaid_amounts"]
    for col in repaid_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["total_repaid"] = df[repaid_cols].sum(axis=1)

    days_late_col = next((c for c in df.columns if "days" in c.lower() and "late" in c.lower() and c.lower() != "days_late_lastinstallment"), None)
    if not days_late_col:
        raise HTTPException(status_code=500, detail="No valid 'days_late' column found")

    df["days_late_bucket"] = df[days_late_col].apply(
        lambda x: "Unknown" if pd.isna(x) else ("1-30" if x <= 30 else "31-60" if x <= 60 else "61-90" if x <= 90 else "90+")
    )
    return df, repaid_cols, days_late_col

def load_messages():
    if not os.path.exists(MESSAGES_FILE):
        return pd.DataFrame(columns=["Name", "Message", "Timestamp"])
    df = pd.read_csv(MESSAGES_FILE)
    for col in ["Name", "Message", "Timestamp"]:
        if col not in df.columns:
            df[col] = ""
    return df[["Name", "Message", "Timestamp"]]
@app.get("/data")
def get_data():
    df, repaid_cols, days_late_col = load_data()

    # Replace NaN/inf values with None so JSON can handle it
    safe_df = df.replace([pd.NA, pd.NaT, float("inf"), float("-inf")], None)
    safe_df = safe_df.where(pd.notnull(safe_df), None)

    data = safe_df.to_dict(orient="records")

    return {
        "columns": df.columns.tolist(),
        "data": data,
        "repaid_cols": repaid_cols,
        "days_late_col": days_late_col
    }



@app.get("/messages")
def get_messages():
    df = load_messages()
    df = df.sort_values("Timestamp", ascending=False)
    return df.to_dict(orient="records")

@app.post("/messages")
def post_message(name: str, message: str):
    if not name or not message:
        raise HTTPException(status_code=400, detail="Name and message cannot be empty")
    df = load_messages()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_msg = pd.DataFrame([{"Name": name.strip().title(), "Message": message.strip(), "Timestamp": timestamp}])
    df = pd.concat([df, new_msg], ignore_index=True)
    df.to_csv(MESSAGES_FILE, index=False)
    return {"status": "success", "message": "Message posted!"}

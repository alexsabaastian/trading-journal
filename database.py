import os
import requests
import pandas as pd


def _get_secret(key):
    try:
        import streamlit as st
        return st.secrets[key]
    except Exception:
        from dotenv import load_dotenv
        load_dotenv()
        return os.getenv(key)


SUPABASE_URL = _get_secret("SUPABASE_URL").rstrip("/")
SUPABASE_KEY = _get_secret("SUPABASE_SERVICE_KEY")


def _headers(prefer=None):
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def init_db():
    pass


def get_or_create_account(name, firm="", initial_balance=0.0):
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/accounts",
        headers=_headers(),
        params={"name": f"eq.{name}", "select": "id"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if data:
        return int(data[0]["id"])

    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/accounts",
        headers=_headers("return=representation"),
        json={"name": name, "firm": firm, "initial_balance": initial_balance},
        timeout=30,
    )
    r.raise_for_status()
    return int(r.json()[0]["id"])


def load_accounts():
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/accounts",
        headers=_headers(),
        params={"select": "*", "order": "name"},
        timeout=30,
    )
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    if not df.empty:
        df["id"] = df["id"].astype(int)
    return df


def insert_trades(account_id, trades_df):
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/trades",
        headers=_headers(),
        params={"account_id": f"eq.{account_id}", "select": "position_id"},
        timeout=30,
    )
    r.raise_for_status()
    existing = {int(row["position_id"]) for row in r.json()}

    new_df = trades_df[~trades_df["Position"].isin(existing)]
    skipped = len(trades_df) - len(new_df)

    inserted = 0
    for _, row in new_df.iterrows():
        payload = {
            "account_id": int(account_id),
            "position_id": int(row["Position"]),
            "entry_time": str(row["Entry_Time"]),
            "exit_time": str(row["Exit_Time"]),
            "symbol": row["Symbol"],
            "type": row["Type"],
            "volume": float(row["Volume"]) if pd.notna(row["Volume"]) else 0,
            "entry_price": float(row["Entry_Price"]) if pd.notna(row["Entry_Price"]) else 0,
            "exit_price": float(row["Exit_Price"]) if pd.notna(row["Exit_Price"]) else 0,
            "sl": float(row["SL"]) if "SL" in row and pd.notna(row["SL"]) else None,
            "tp": float(row["TP"]) if "TP" in row and pd.notna(row["TP"]) else None,
            "commission": float(row["Commission"]) if pd.notna(row["Commission"]) else 0,
            "swap": float(row["Swap"]) if pd.notna(row["Swap"]) else 0,
            "profit": float(row["Profit"]) if pd.notna(row["Profit"]) else 0,
            "hold_time_min": float(row["Hold_Time_Min"]) if pd.notna(row["Hold_Time_Min"]) else 0,
        }
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/trades",
            headers=_headers("return=minimal"),
            json=payload,
            timeout=30,
        )
        if resp.status_code < 400:
            inserted += 1

    return inserted, skipped


def load_all_trades():
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/trades",
        headers=_headers(),
        params={"select": "*", "order": "exit_time.asc"},
        timeout=30,
    )
    r.raise_for_status()
    trades = pd.DataFrame(r.json())

    if trades.empty:
        return pd.DataFrame()

    # Cast id columns to int (Supabase returns BIGINT as string)
    trades["account_id"] = trades["account_id"].astype(int)
    if "id" in trades.columns:
        trades["id"] = trades["id"].astype(int)
    if "position_id" in trades.columns:
        trades["position_id"] = trades["position_id"].astype(int)

    accounts = load_accounts()
    merged = trades.merge(
        accounts[["id", "name", "firm"]].rename(
            columns={"id": "account_id", "name": "account_name"}
        ),
        on="account_id",
        how="left",
    )
    return merged


def update_trade_notes(trade_id, note, strategy, session):
    """Save or update the journal notes for a trade."""
    payload = {
        "note": note or None,
        "strategy": strategy or None,
        "session": session or None,
    }
    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/trades",
        headers=_headers("return=minimal"),
        params={"id": f"eq.{trade_id}"},
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    return True

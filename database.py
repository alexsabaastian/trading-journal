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


def load_accounts(include_archived=False):
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/accounts",
        headers=_headers(),
        params={"select": "*", "order": "name"},
        timeout=30,
    )
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    if df.empty:
        return df
    df["id"] = df["id"].astype(int)
    if "archived" not in df.columns:
        df["archived"] = False
    df["archived"] = df["archived"].apply(lambda v: bool(v) if pd.notna(v) else False)
    if not include_archived:
        df = df[~df["archived"]].reset_index(drop=True)
    return df


def insert_trades(account_id, trades_df):
    # Fetch existing trades + their exit_reason status
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/trades",
        headers=_headers(),
        params={"account_id": f"eq.{account_id}", "select": "position_id,exit_reason,sl,tp"},
        timeout=30,
    )
    r.raise_for_status()
    existing_rows = r.json()
    existing_ids = {int(row["position_id"]) for row in existing_rows}
    needs_backfill = {
        int(row["position_id"])
        for row in existing_rows
        if (not row.get("exit_reason")) or (row.get("sl") is None)
    }

    new_df = trades_df[~trades_df["Position"].isin(existing_ids)]
    skipped = len(trades_df) - len(new_df)

    inserted = 0
    backfilled = 0

    for _, row in new_df.iterrows():
        _er = None
        if "Exit_Reason" in row.index:
            v = row["Exit_Reason"]
            _er = None if pd.isna(v) else str(v)
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
            "sl": float(row["SL"]) if "SL" in row.index and pd.notna(row["SL"]) else None,
            "tp": float(row["TP"]) if "TP" in row.index and pd.notna(row["TP"]) else None,
            "commission": float(row["Commission"]) if pd.notna(row["Commission"]) else 0,
            "swap": float(row["Swap"]) if pd.notna(row["Swap"]) else 0,
            "profit": float(row["Profit"]) if pd.notna(row["Profit"]) else 0,
            "hold_time_min": float(row["Hold_Time_Min"]) if pd.notna(row["Hold_Time_Min"]) else 0,
            "exit_reason": _er,
        }
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/trades",
            headers=_headers("return=minimal"),
            json=payload,
            timeout=30,
        )
        if resp.status_code < 400:
            inserted += 1

    # Backfill existing trades missing exit_reason, sl, tp
    backfilled_sl = 0
    for _, row in trades_df.iterrows():
        pid = int(row["Position"])
        if pid not in needs_backfill:
            continue

        patch = {}
        if "Exit_Reason" in row.index:
            reason = row["Exit_Reason"]
            if not pd.isna(reason) and reason:
                patch["exit_reason"] = str(reason)

        if "SL" in row.index and pd.notna(row["SL"]) and float(row["SL"]) != 0:
            patch["sl"] = float(row["SL"])
        if "TP" in row.index and pd.notna(row["TP"]) and float(row["TP"]) != 0:
            patch["tp"] = float(row["TP"])

        if not patch:
            continue

        resp = requests.patch(
            f"{SUPABASE_URL}/rest/v1/trades",
            headers=_headers("return=minimal"),
            params={"account_id": f"eq.{account_id}", "position_id": f"eq.{pid}"},
            json=patch,
            timeout=30,
        )
        if resp.status_code < 400:
            backfilled += 1
            if "sl" in patch:
                backfilled_sl += 1

    return inserted, skipped, backfilled


def load_all_trades(active_only=True):
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

    trades["account_id"] = trades["account_id"].astype(int)
    if "id" in trades.columns:
        trades["id"] = trades["id"].astype(int)
    if "position_id" in trades.columns:
        trades["position_id"] = trades["position_id"].astype(int)

    accounts = load_accounts(include_archived=True)
    if "archived" not in accounts.columns:
        accounts["archived"] = False
    merged = trades.merge(
        accounts[["id", "name", "firm", "archived"]].rename(
            columns={"id": "account_id", "name": "account_name"}
        ),
        on="account_id",
        how="left",
    )
    if active_only:
        merged = merged[~merged["archived"].fillna(False).astype(bool)].reset_index(drop=True)
    if "archived" in merged.columns:
        merged = merged.drop(columns=["archived"])
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

def set_account_archived(account_id, archived):
    """Archive or unarchive an account."""
    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/accounts",
        headers=_headers("return=minimal"),
        params={"id": f"eq.{account_id}"},
        json={"archived": bool(archived)},
        timeout=30,
    )
    r.raise_for_status()
    return True


def delete_account(account_id):
    """Permanently delete an account and all its trades."""
    r = requests.delete(
        f"{SUPABASE_URL}/rest/v1/trades",
        headers=_headers("return=minimal"),
        params={"account_id": f"eq.{account_id}"},
        timeout=30,
    )
    r.raise_for_status()
    r = requests.delete(
        f"{SUPABASE_URL}/rest/v1/accounts",
        headers=_headers("return=minimal"),
        params={"id": f"eq.{account_id}"},
        timeout=30,
    )
    r.raise_for_status()
    return True


def insert_transactions(account_id, tx_df):
    """Insert cash flow rows with dedup. Returns (inserted, skipped)."""
    if tx_df is None or tx_df.empty:
        return 0, 0

    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/account_transactions",
        headers=_headers(),
        params={"account_id": f"eq.{account_id}", "select": "transaction_time,amount"},
        timeout=30,
    )
    r.raise_for_status()
    existing = {(row["transaction_time"], float(row["amount"])) for row in r.json()}

    inserted = 0
    skipped = 0
    for _, row in tx_df.iterrows():
        t = row["Transaction_Time"]
        amt = float(row["Amount"])
        if (str(t), amt) in existing:
            skipped += 1
            continue

        bal = row.get("Balance_After")
        payload = {
            "account_id": int(account_id),
            "transaction_time": str(t),
            "type": row.get("Flow", "adjustment"),
            "amount": amt,
            "balance_after": float(bal) if pd.notna(bal) else None,
            "comment": row.get("Comment") or None,
        }
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/account_transactions",
            headers=_headers("return=minimal"),
            json=payload,
            timeout=30,
        )
        if resp.status_code < 400:
            inserted += 1
        else:
            skipped += 1

    return inserted, skipped


def load_transactions(account_id=None):
    """Load all transactions, optionally filtered by account."""
    params = {"select": "*", "order": "transaction_time.asc"}
    if account_id is not None:
        params["account_id"] = f"eq.{account_id}"

    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/account_transactions",
        headers=_headers(),
        params=params,
        timeout=30,
    )
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    if not df.empty:
        df["account_id"] = df["account_id"].astype(int)
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
        df["balance_after"] = pd.to_numeric(df["balance_after"], errors="coerce")
        df["transaction_time"] = pd.to_datetime(df["transaction_time"], errors="coerce")
    return df

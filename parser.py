import pandas as pd
from io import BytesIO

def parse_mt5_xlsx(file_bytes):
    raw = pd.read_excel(BytesIO(file_bytes), header=None)

    positions_start = None
    for i, val in enumerate(raw.iloc[:, 0]):
        if str(val).strip() == "Positions":
            positions_start = i
            break

    if positions_start is None:
        raise ValueError("Could not find 'Positions' section in report.")

    header_row = positions_start + 1
    headers = raw.iloc[header_row].tolist()

    data_start = positions_start + 2

    positions_end = None
    for i in range(data_start, len(raw)):
        if str(raw.iloc[i, 0]).strip() == "Orders":
            positions_end = i
            break

    if positions_end is None:
        positions_end = len(raw)

    trades = raw.iloc[data_start:positions_end].copy()
    trades.columns = headers
    trades = trades.dropna(how="all")

    trades.columns = [
        "Entry_Time", "Position", "Symbol", "Type", "Volume",
        "Entry_Price", "SL", "TP",
        "Exit_Time", "Exit_Price", "Commission", "Swap", "Profit", "_extra"
    ][:len(trades.columns)]

    trades = trades.drop(columns=["_extra"], errors="ignore")
    trades = trades[trades["Symbol"].notna()]
    trades = trades[trades["Symbol"].astype(str).str.strip() != ""]

    for col in ["Volume", "Entry_Price", "SL", "TP", "Exit_Price",
                "Commission", "Swap", "Profit"]:
        if col in trades.columns:
            trades[col] = pd.to_numeric(trades[col], errors="coerce")

    trades["Entry_Time"] = pd.to_datetime(trades["Entry_Time"], errors="coerce")
    trades["Exit_Time"] = pd.to_datetime(trades["Exit_Time"], errors="coerce")

    trades["Hold_Time_Min"] = (
        trades["Exit_Time"] - trades["Entry_Time"]
    ).dt.total_seconds() / 60

    # ---- Parse Deals section for exit reasons (TP / SL / Manual) ----
    deals_start = None
    for i, val in enumerate(raw.iloc[:, 0]):
        if str(val).strip() == "Deals":
            deals_start = i
            break

    exit_reason_map = {}
    if deals_start is not None:
        deals_header_row = deals_start + 1
        deals_headers = raw.iloc[deals_header_row].tolist()
        deals_data_start = deals_start + 2

        deals_end = len(raw)
        for i in range(deals_data_start, len(raw)):
            first_cell = str(raw.iloc[i, 0]).strip()
            if first_cell == "Results":
                deals_end = i
                break

        deals = raw.iloc[deals_data_start:deals_end].copy()
        deals.columns = deals_headers[:len(deals.columns)]
        deals = deals.dropna(how="all")

        def _find_col(df, target):
            for c in df.columns:
                if str(c).strip().lower() == target.lower():
                    return c
            return None

        col_dir = _find_col(deals, "Direction")
        col_sym = _find_col(deals, "Symbol")
        col_vol = _find_col(deals, "Volume")
        col_time = _find_col(deals, "Time")
        col_comm = _find_col(deals, "Comment")

        if col_dir and col_sym and col_vol and col_time and col_comm:
            for _, drow in deals.iterrows():
                if str(drow[col_dir]).strip().lower() != "out":
                    continue
                symbol = str(drow[col_sym]).strip()
                try:
                    vol = round(float(drow[col_vol]), 4)
                except (TypeError, ValueError):
                    continue
                dtime = pd.to_datetime(str(drow[col_time]), errors="coerce")
                if pd.isna(dtime):
                    continue
                comment = str(drow[col_comm]).strip().lower()
                reason = "Manual"
                if "[tp" in comment:
                    reason = "TP"
                elif "[sl" in comment:
                    reason = "SL"
                exit_reason_map[(symbol, vol, dtime)] = reason

    def _lookup_reason(row):
        try:
            symbol = str(row["Symbol"]).strip()
            vol = round(float(row["Volume"]), 4)
            dtime = row["Exit_Time"]
            if pd.isna(dtime):
                return "Manual"
            return exit_reason_map.get((symbol, vol, dtime), "Manual")
        except Exception:
            return "Manual"

    trades["Exit_Reason"] = trades.apply(_lookup_reason, axis=1)

    trades = trades.reset_index(drop=True)
    return trades


def calculate_metrics(df):
    if df.empty:
        return {}

    wins = df[df["Profit"] > 0]
    losses = df[df["Profit"] < 0]

    gross_profit = wins["Profit"].sum()
    gross_loss = abs(losses["Profit"].sum())
    net = df["Profit"].sum()

    return {
        "total_trades": len(df),
        "net_profit": round(net, 2),
        "win_rate": round(len(wins) / len(df) * 100, 2) if len(df) else 0,
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss else 0,
        "avg_win": round(wins["Profit"].mean(), 2) if len(wins) else 0,
        "avg_loss": round(losses["Profit"].mean(), 2) if len(losses) else 0,
        "largest_win": round(wins["Profit"].max(), 2) if len(wins) else 0,
        "largest_loss": round(losses["Profit"].min(), 2) if len(losses) else 0,
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
    }
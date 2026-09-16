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
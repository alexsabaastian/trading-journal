import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from calendar import monthrange
from parser import parse_mt5_xlsx, calculate_metrics
import database as db

st.set_page_config(page_title="Allensdenfx", layout="wide")

db.init_db()

# ===============================================================
# THEME SYSTEM
# ===============================================================
THEMES = {
    "Light": {
        "bg": "#f7f9fc",
        "card_bg": "#ffffff",
        "text": "#1a1a1a",
        "subtext": "#666666",
        "border": "#e6ebf2",
        "equity_line": "#2962ff",
        "shadow": "0 2px 8px rgba(0,0,0,0.06)",
    },
    "Dark": {
        "bg": "#0e1117",
        "card_bg": "#1a1d24",
        "text": "#f5f5f5",
        "subtext": "#a0a8b8",
        "border": "#2b3140",
        "equity_line": "#64b5f6",
        "shadow": "0 2px 8px rgba(0,0,0,0.4)",
    },
}

ACCENTS = {
    "Blue": "#2962ff",
    "Green": "#43a047",
    "Purple": "#7b1fa2",
    "Orange": "#fb8c00",
    "Teal": "#009688",
    "Red": "#e53935",
}

CALENDAR_SCHEMES = {
    "Classic (Green/Red)": {
        "neg_dark": "#b71c1c", "neg_light": "#ef5350", "mid": "#f5f5f5",
        "pos_light": "#66bb6a", "pos_dark": "#1b5e20",
    },
    "Modern (Blue/Orange)": {
        "neg_dark": "#e65100", "neg_light": "#ffb74d", "mid": "#f5f5f5",
        "pos_light": "#64b5f6", "pos_dark": "#0d47a1",
    },
    "Mono (Gray/Black)": {
        "neg_dark": "#000000", "neg_light": "#9e9e9e", "mid": "#f5f5f5",
        "pos_light": "#bdbdbd", "pos_dark": "#424242",
    },
}

WIN_COLOR = "#26a69a"
LOSS_COLOR = "#ef5350"

# ===============================================================
# SIDEBAR
# ===============================================================
st.sidebar.header("⚙️ Settings")

accounts_df = db.load_accounts()
existing_accounts = accounts_df["name"].tolist() if not accounts_df.empty else []
account_options = ["All Accounts"] + existing_accounts + ["➕ Add new account"]

if st.session_state.pop("_pending_switch_to_all", False):
    st.session_state["_account_dropdown"] = "All Accounts"
elif st.session_state.get("_account_dropdown") not in account_options:
    st.session_state["_account_dropdown"] = "All Accounts"

selected_account = st.sidebar.selectbox(
    "Select Account", account_options, key="_account_dropdown"
)
view_all = selected_account == "All Accounts"

if selected_account == "➕ Add new account":
    new_name = st.sidebar.text_input("Account name (e.g., The5ers 10K)")
    new_firm = st.sidebar.text_input("Prop firm (e.g., The5ers)")
    new_balance = st.sidebar.number_input("Initial balance", value=10000.0, step=100.0)
    if st.sidebar.button("Create Account"):
        if new_name.strip():
            db.get_or_create_account(new_name.strip(), new_firm.strip(), new_balance)
            st.sidebar.success(f"Account '{new_name}' created.")
            st.rerun()
        else:
            st.sidebar.error("Enter an account name.")
    account_id = None
elif view_all:
    account_id = None
    st.sidebar.success("Active: All Accounts (combined)")
else:
    account_id = int(accounts_df[accounts_df["name"] == selected_account]["id"].iloc[0])
    st.sidebar.success(f"Active: {selected_account}")
    _a1, _a2 = st.sidebar.columns(2)
    with _a1:
        if st.button("📦 Archive", key="arch_active", use_container_width=True):
            db.set_account_archived(account_id, True)
            st.session_state["_pending_switch_to_all"] = True
            st.rerun()
    with _a2:
        if st.button("🗑 Delete", key="del_active", use_container_width=True):
            st.session_state["_confirm_delete_id"] = account_id
            st.session_state["_confirm_delete_name"] = selected_account
            st.rerun()
    if st.session_state.get("_confirm_delete_id") == account_id:
        st.sidebar.warning(f"Delete **{selected_account}** and all its trades?")
        _b1, _b2 = st.sidebar.columns(2)
        with _b1:
            if st.button("Yes, delete", key="cfm_del_active", type="primary", use_container_width=True):
                db.delete_account(account_id)
                st.session_state.pop("_confirm_delete_id", None)
                st.session_state.pop("_confirm_delete_name", None)
                st.session_state["_pending_switch_to_all"] = True
                st.rerun()
        with _b2:
            if st.button("Cancel", key="cnl_del_active", use_container_width=True):
                st.session_state.pop("_confirm_delete_id", None)
                st.session_state.pop("_confirm_delete_name", None)
                st.rerun()

if st.session_state.get("ai_chat_account") != selected_account:
    st.session_state.ai_chat_history = []
    st.session_state.ai_chat_account = selected_account

st.sidebar.markdown("---")
with st.sidebar.expander("⚙ Manage All Accounts", expanded=False):
    _all_acc = db.load_accounts(include_archived=True)
    if _all_acc.empty:
        st.caption("No accounts yet.")
    else:
        for _, _row in _all_acc.iterrows():
            _aid = int(_row["id"])
            _aname = str(_row["name"])
            _arch = bool(_row["archived"]) if "archived" in _row.index else False
            _badge = "📦 Archived" if _arch else "✅ Active"
            st.markdown(f"**{_aname}** — _{_badge}_")
            _c1, _c2 = st.columns(2)
            with _c1:
                if _arch:
                    if st.button("Unarchive", key=f"unarch_{_aid}", use_container_width=True):
                        db.set_account_archived(_aid, False)
                        st.rerun()
                else:
                    if st.button("Archive", key=f"arch_{_aid}", use_container_width=True):
                        db.set_account_archived(_aid, True)
                        if selected_account == _aname:
                            st.session_state["_pending_switch_to_all"] = True
                        st.rerun()
            with _c2:
                if st.button("Delete", key=f"del_{_aid}", use_container_width=True):
                    st.session_state["_confirm_delete_id"] = _aid
                    st.session_state["_confirm_delete_name"] = _aname
                    st.rerun()
            if st.session_state.get("_confirm_delete_id") == _aid:
                st.warning(f"Delete **{_aname}** and all its trades?")
                _d1, _d2 = st.columns(2)
                with _d1:
                    if st.button("Confirm", key=f"cfm_{_aid}", type="primary", use_container_width=True):
                        db.delete_account(_aid)
                        st.session_state.pop("_confirm_delete_id", None)
                        st.session_state.pop("_confirm_delete_name", None)
                        if selected_account == _aname:
                            st.session_state["_pending_switch_to_all"] = True
                        st.rerun()
                with _d2:
                    if st.button("Cancel", key=f"cnl_{_aid}", use_container_width=True):
                        st.session_state.pop("_confirm_delete_id", None)
                        st.session_state.pop("_confirm_delete_name", None)
                        st.rerun()
            st.markdown("---")

st.sidebar.markdown("---")
st.sidebar.header("🎨 Appearance")

theme_name = st.sidebar.radio("Theme", ["Light", "Dark"], horizontal=True)
accent_name = st.sidebar.selectbox("Accent Color", list(ACCENTS.keys()), index=0)
calendar_scheme = st.sidebar.selectbox("Calendar Style", list(CALENDAR_SCHEMES.keys()), index=0)
card_style = st.sidebar.radio("Card Style", ["Filled", "Outlined"], horizontal=True)

theme = THEMES[theme_name]
accent = ACCENTS[accent_name]
cal_colors = CALENDAR_SCHEMES[calendar_scheme]

# ===============================================================
# GLOBAL CSS — FONTS, CARDS, THEME, DROPDOWNS
# ===============================================================
st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"], .stApp {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }}

    .stApp {{
        background-color: {theme['bg']} !important;
        color: {theme['text']} !important;
    }}

    section[data-testid="stSidebar"] {{
        background-color: {theme['card_bg']} !important;
        border-right: 1px solid {theme['border']};
    }}
    section[data-testid="stSidebar"] * {{
        color: {theme['text']} !important;
    }}

    h1, h2, h3, h4, h5, h6, p, div, span, label, .stMarkdown {{
        color: {theme['text']} !important;
    }}
    .stCaption, small {{
        color: {theme['subtext']} !important;
    }}

    div[data-baseweb="select"] > div {{
        background-color: {theme['card_bg']} !important;
        border-color: {theme['border']} !important;
        color: {theme['text']} !important;
    }}
    div[data-baseweb="select"] * {{
        color: {theme['text']} !important;
    }}
    ul[data-baseweb="menu"] {{
        background-color: {theme['card_bg']} !important;
    }}
    ul[data-baseweb="menu"] li {{
        color: {theme['text']} !important;
        background-color: {theme['card_bg']} !important;
    }}
    ul[data-baseweb="menu"] li:hover {{
        background-color: {theme['border']} !important;
    }}

    .stTextInput input, .stNumberInput input {{
        background-color: {theme['card_bg']} !important;
        color: {theme['text']} !important;
        border-color: {theme['border']} !important;
    }}

    .stButton > button {{
        background-color: {theme['card_bg']} !important;
        color: {theme['text']} !important;
        border: 1px solid {theme['border']} !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
    }}
    .stButton > button:hover {{
        background-color: {accent} !important;
        color: #ffffff !important;
        border-color: {accent} !important;
    }}

    .stRadio label, .stRadio div {{
        color: {theme['text']} !important;
    }}

    section[data-testid="stFileUploaderDropzone"] {{
        background-color: {theme['card_bg']} !important;
        border: 1px dashed {theme['border']} !important;
        border-radius: 12px !important;
    }}
    section[data-testid="stFileUploaderDropzone"] * {{
        color: {theme['text']} !important;
    }}

    div[data-testid="stAlert"] {{
        background-color: {theme['card_bg']} !important;
        color: {theme['text']} !important;
        border-radius: 12px !important;
    }}
    div[data-testid="stAlert"] * {{
        color: {theme['text']} !important;
    }}

    .stDateInput input {{
        background-color: {theme['card_bg']} !important;
        color: {theme['text']} !important;
    }}

    div[role="listbox"], div[role="option"] {{
        background-color: {theme['card_bg']} !important;
        color: {theme['text']} !important;
    }}
    div[role="option"]:hover, div[role="option"][aria-selected="true"] {{
        background-color: {accent} !important;
        color: #ffffff !important;
    }}

    div[data-baseweb="popover"], div[data-baseweb="menu"] {{
        background-color: {theme['card_bg']} !important;
    }}

    /* Custom cards */
    .kpi-card {{
        background: {theme['card_bg']};
        border: 1px solid {theme['border']};
        border-radius: 16px;
        padding: 22px 24px;
        box-shadow: {theme['shadow']};
        text-align: center;
    }}

    .kpi-label {{
        font-size: 12px;
        font-weight: 500;
        letter-spacing: 0.5px;
        text-transform: uppercase;
        color: {theme['subtext']};
        margin-bottom: 6px;
    }}

    .kpi-value {{
        font-size: 32px;
        font-weight: 800;
        letter-spacing: -0.5px;
    }}

    .streak-banner {{
        background: {theme['card_bg']};
        border-radius: 14px;
        padding: 14px 22px;
        text-align: center;
        font-size: 17px;
        font-weight: 600;
        border: 1px solid {theme['border']};
        box-shadow: {theme['shadow']};
    }}

    .section-title {{
        font-size: 20px;
        font-weight: 700;
        color: {theme['text']};
        margin-top: 10px;
        margin-bottom: 8px;
    }}
</style>
""", unsafe_allow_html=True)

# ===============================================================
# UPLOAD
# ===============================================================
st.markdown('<div class="section-title">📊 Allensdenfx</div>', unsafe_allow_html=True)
st.caption("Upload an MT5 trade history report to see your trades and metrics.")

with st.expander("📥 Upload Report", expanded=False):
    uploaded = st.file_uploader("Upload your MT5 Trade History Report (.xlsx)", type=["xlsx"], key=f"uploader_{selected_account}")
    if uploaded is not None and account_id is not None:
        try:
            file_bytes = uploaded.read()
            df_up = parse_mt5_xlsx(file_bytes)
            inserted, skipped = db.insert_trades(account_id, df_up)
            if inserted:
                st.success(f"✅ Imported {inserted} new trades. ({skipped} duplicates skipped)")
            else:
                st.info(f"ℹ️ No new trades to import. ({skipped} duplicates skipped)")
        except Exception as e:
            st.error(f"❌ Error parsing file: {e}")
            st.exception(e)

# ===============================================================
# LOAD TRADES
# ===============================================================
all_trades = db.load_all_trades()

if all_trades.empty or (account_id is None and not view_all):
    st.info("👆 Create an account in the sidebar, then upload your MT5 .xlsx report.")
    st.stop()

if view_all:
    df = all_trades.copy()
else:
    df = all_trades[all_trades["account_id"] == account_id].copy()

if df.empty:
    st.info(f"No trades yet for '{selected_account}'. Upload a report above.")
    st.stop()

df["exit_time"] = pd.to_datetime(df["exit_time"], errors="coerce")
df["entry_time"] = pd.to_datetime(df["entry_time"], errors="coerce")

# ===============================================================
# FILTERS
# ===============================================================
st.markdown('<div class="section-title">🔎 Filters</div>', unsafe_allow_html=True)
col_f1, col_f2, col_f3 = st.columns([1, 1, 2])

with col_f1:
    date_preset = st.selectbox("Date Range",
        ["All time", "Today", "This week", "This month", "Last 30 days", "Custom"])
with col_f2:
    symbol_options = ["All"] + sorted(df["symbol"].dropna().unique().tolist())
    symbol_filter = st.selectbox("Symbol", symbol_options)
with col_f3:
    type_options = ["All"] + sorted(df["type"].dropna().unique().tolist())
    type_filter = st.selectbox("Type", type_options)

now = datetime.now()
start_date = None
end_date = None

if date_preset == "Today":
    start_date = datetime(now.year, now.month, now.day)
    end_date = start_date + timedelta(days=1)
elif date_preset == "This week":
    start_date = now - timedelta(days=now.weekday())
    start_date = datetime(start_date.year, start_date.month, start_date.day)
    end_date = start_date + timedelta(days=7)
elif date_preset == "This month":
    start_date = datetime(now.year, now.month, 1)
    end_date = (start_date + timedelta(days=32)).replace(day=1)
elif date_preset == "Last 30 days":
    start_date = now - timedelta(days=30)
    end_date = now
elif date_preset == "Custom":
    c1, c2 = st.columns(2)
    with c1:
        start_date = st.date_input("From", value=(now - timedelta(days=30)).date())
    with c2:
        end_date = st.date_input("To", value=now.date())
    start_date = pd.to_datetime(start_date)
    end_date = pd.to_datetime(end_date) + timedelta(days=1)

filtered = df.copy()
if start_date is not None and end_date is not None:
    filtered = filtered[(filtered["exit_time"] >= start_date) & (filtered["exit_time"] < end_date)]
if symbol_filter != "All":
    filtered = filtered[filtered["symbol"] == symbol_filter]
if type_filter != "All":
    filtered = filtered[filtered["type"] == type_filter]

if filtered.empty:
    st.warning("⚠️ No trades match your filters.")
    st.stop()

filtered = filtered.rename(columns={
    "entry_time": "Entry_Time", "exit_time": "Exit_Time",
    "symbol": "Symbol", "type": "Type", "volume": "Volume",
    "entry_price": "Entry_Price", "exit_price": "Exit_Price",
    "profit": "Profit", "hold_time_min": "Hold_Time_Min",
})

metrics = calculate_metrics(filtered)

# ===============================================================
# KPI HERO BAR (today / week / month)
# ===============================================================
def sum_pnl(d, start, end):
    if start is None or end is None:
        return d["Profit"].sum()
    sub = d[(d["Exit_Time"] >= start) & (d["Exit_Time"] < end)]
    return sub["Profit"].sum()

today_start = datetime(now.year, now.month, now.day)
week_start = datetime((now - timedelta(days=now.weekday())).year,
                      (now - timedelta(days=now.weekday())).month,
                      (now - timedelta(days=now.weekday())).day)
month_start_kpi = datetime(now.year, now.month, 1)

today_pnl = sum_pnl(filtered, today_start, today_start + timedelta(days=1))
week_pnl = sum_pnl(filtered, week_start, week_start + timedelta(days=7))
month_pnl = sum_pnl(filtered, month_start_kpi, (month_start_kpi + timedelta(days=32)).replace(day=1))

st.markdown('<div class="section-title">💰 P&L Snapshot</div>', unsafe_allow_html=True)
k1, k2, k3 = st.columns(3)

def kpi_html(label, value):
    color = WIN_COLOR if value >= 0 else LOSS_COLOR
    sign = "+" if value >= 0 else ""
    return f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value" style="color:{color};">{sign}${value:.2f}</div>
    </div>
    """

with k1:
    st.markdown(kpi_html("Today", today_pnl), unsafe_allow_html=True)
with k2:
    st.markdown(kpi_html("This Week", week_pnl), unsafe_allow_html=True)
with k3:
    st.markdown(kpi_html("This Month", month_pnl), unsafe_allow_html=True)

# ===============================================================
# STREAK TRACKER
# ===============================================================
daily_streak = (
    filtered.assign(day=filtered["Exit_Time"].dt.date)
    .groupby("day").agg(pnl=("Profit", "sum"))
    .reset_index()
    .sort_values("day")
)

streak_count = 0
streak_type = None

if not daily_streak.empty:
    last_sign = 1 if daily_streak.iloc[-1]["pnl"] >= 0 else -1
    streak_type = "win" if last_sign > 0 else "loss"
    for i in range(len(daily_streak) - 1, -1, -1):
        sign = 1 if daily_streak.iloc[i]["pnl"] >= 0 else -1
        if sign == last_sign:
            streak_count += 1
        else:
            break

st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

if streak_type == "win":
    streak_html = f'<div class="streak-banner" style="color:{WIN_COLOR};">🔥 {streak_count}-day win streak — keep going!</div>'
elif streak_type == "loss":
    streak_html = f'<div class="streak-banner" style="color:{LOSS_COLOR};">❄️ {streak_count}-day loss streak — time to review your rules</div>'
else:
    streak_html = '<div class="streak-banner" style="color:{};">No trading days yet</div>'.format(theme['subtext'])

st.markdown(streak_html, unsafe_allow_html=True)

# ===============================================================
# RADIAL GAUGE DASHBOARD
# ===============================================================
st.markdown('<div class="section-title">📈 Performance Summary</div>', unsafe_allow_html=True)

def card_style_css():
    if card_style == "Filled":
        return f"background:{theme['card_bg']};border:1px solid {theme['border']};box-shadow:{theme['shadow']};"
    else:
        return f"background:transparent;border:1.5px solid {theme['border']};"

def make_gauge(value, max_value, title, threshold_good):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number={"font": {"size": 28, "color": theme['text']}},
        title={"text": title, "font": {"size": 15, "color": theme['text']}},
        gauge={
            "axis": {"range": [0, max_value], "tickwidth": 1, "tickcolor": theme['subtext']},
            "bar": {"color": accent, "thickness": 0.28},
            "bgcolor": theme['card_bg'],
            "borderwidth": 2,
            "bordercolor": theme['border'],
            "steps": [
                {"range": [0, threshold_good], "color": "#ffebee" if theme_name == "Light" else "#3a1a1e"},
                {"range": [threshold_good, max_value], "color": "#e8f5e9" if theme_name == "Light" else "#1a3320"},
            ],
            "threshold": {
                "line": {"color": "#1b5e20" if theme_name == "Light" else "#66bb6a", "width": 3},
                "thickness": 0.75, "value": threshold_good,
            },
        },
    ))
    fig.update_layout(height=230, margin=dict(l=15, r=15, t=45, b=10),
                      paper_bgcolor=theme['bg'], font_color=theme['text'])
    return fig

def make_win_rate_donut(win_rate):
    fig = go.Figure(go.Pie(
        values=[win_rate, 100 - win_rate],
        labels=["Wins", "Losses"],
        hole=0.72, textinfo="none",
        marker=dict(colors=[accent, theme['border']]),
        sort=False, direction="clockwise", rotation=0,
    ))
    fig.update_layout(
        height=230, margin=dict(l=10, r=10, t=45, b=10),
        paper_bgcolor=theme['bg'], showlegend=False,
        annotations=[dict(
            text=f"<b>{win_rate:.1f}%</b><br><span style='font-size:12px;color:{theme['subtext']}'>Win Rate</span>",
            x=0.5, y=0.5, font=dict(size=22, color=theme['text']), showarrow=False,
        )],
    )
    return fig

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.plotly_chart(make_win_rate_donut(metrics["win_rate"]), use_container_width=True)

with c2:
    pf = min(metrics["profit_factor"], 3)
    st.plotly_chart(make_gauge(pf, 3, "Profit Factor", 1.5), use_container_width=True)

with c3:
    net = metrics["net_profit"]
    color = WIN_COLOR if net >= 0 else LOSS_COLOR
    sign = "+" if net >= 0 else ""
    st.markdown(
        f"""<div style="{card_style_css()}border-radius:16px;padding:22px;
                    text-align:center;height:230px;
                    display:flex;flex-direction:column;justify-content:center;">
            <div style="font-size:12px;color:{theme['subtext']};letter-spacing:0.5px;
                        text-transform:uppercase;margin-bottom:8px;">Net P&L</div>
            <div style="font-size:36px;font-weight:800;color:{color};
                        letter-spacing:-0.5px;">
                {sign}${net:.2f}
            </div>
        </div>""", unsafe_allow_html=True)

with c4:
    st.markdown(
        f"""<div style="{card_style_css()}border-radius:16px;padding:22px;
                    text-align:center;height:230px;
                    display:flex;flex-direction:column;justify-content:center;">
            <div style="font-size:12px;color:{theme['subtext']};letter-spacing:0.5px;
                        text-transform:uppercase;margin-bottom:8px;">Total Trades</div>
            <div style="font-size:36px;font-weight:800;color:{accent};
                        letter-spacing:-0.5px;">
                {metrics['total_trades']}
            </div>
        </div>""", unsafe_allow_html=True)

st.markdown(
    f"""<div style="{card_style_css()}border-radius:16px;padding:18px;
                display:flex;justify-content:space-around;margin-top:10px;">
        <div style="text-align:center;">
            <div style="font-size:12px;color:{theme['subtext']};text-transform:uppercase;
                        letter-spacing:0.5px;">Avg Win</div>
            <div style="font-size:20px;font-weight:700;color:{WIN_COLOR};">
                ${metrics['avg_win']}</div>
        </div>
        <div style="text-align:center;">
            <div style="font-size:12px;color:{theme['subtext']};text-transform:uppercase;
                        letter-spacing:0.5px;">Avg Loss</div>
            <div style="font-size:20px;font-weight:700;color:{LOSS_COLOR};">
                ${metrics['avg_loss']}</div>
        </div>
        <div style="text-align:center;">
            <div style="font-size:12px;color:{theme['subtext']};text-transform:uppercase;
                        letter-spacing:0.5px;">Largest Win</div>
            <div style="font-size:20px;font-weight:700;color:{WIN_COLOR};">
                ${metrics['largest_win']}</div>
        </div>
        <div style="text-align:center;">
            <div style="font-size:12px;color:{theme['subtext']};text-transform:uppercase;
                        letter-spacing:0.5px;">Largest Loss</div>
            <div style="font-size:20px;font-weight:700;color:{LOSS_COLOR};">
                ${metrics['largest_loss']}</div>
        </div>
    </div>""", unsafe_allow_html=True)

# ===============================================================
# P&L WATERFALL (daily bars)
# ===============================================================
st.markdown('<div class="section-title">📊 Daily P&L</div>', unsafe_allow_html=True)

waterfall = (
    filtered.assign(day=filtered["Exit_Time"].dt.date)
    .groupby("day").agg(pnl=("Profit", "sum"))
    .reset_index()
    .sort_values("day")
)
waterfall["day"] = pd.to_datetime(waterfall["day"])
waterfall["color"] = waterfall["pnl"].apply(lambda x: WIN_COLOR if x >= 0 else LOSS_COLOR)

fig_wf = go.Figure(data=go.Bar(
    x=waterfall["day"],
    y=waterfall["pnl"],
    marker=dict(color=waterfall["color"]),
    text=[f"${v:.0f}" for v in waterfall["pnl"]],
    textposition="outside",
    textfont=dict(size=11, color=theme['text']),
    hovertemplate="<b>%{x|%b %d}</b><br>P&L: $%{y:.2f}<extra></extra>",
))
fig_wf.update_layout(
    height=320,
    margin=dict(l=10, r=10, t=20, b=30),
    paper_bgcolor=theme['bg'], plot_bgcolor=theme['bg'],
    font_color=theme['text'], showlegend=False,
    xaxis=dict(gridcolor=theme['border']),
    yaxis=dict(gridcolor=theme['border'], title="P&L ($)"),
    bargap=0.35,
)
st.plotly_chart(fig_wf, use_container_width=True)

# ===============================================================
# EQUITY CURVE
# ===============================================================
st.markdown('<div class="section-title">📉 Equity Curve</div>', unsafe_allow_html=True)
df_sorted = filtered.sort_values("Exit_Time").copy()
df_sorted["Cumulative_PnL"] = df_sorted["Profit"].cumsum()

eq_fig = go.Figure()
eq_fig.add_trace(go.Scatter(
    x=df_sorted["Exit_Time"], y=df_sorted["Cumulative_PnL"],
    mode="lines", line=dict(color=theme['equity_line'], width=2.5),
    fill="tozeroy",
    fillcolor=f"rgba(41,98,255,0.10)" if theme_name == "Light" else "rgba(100,181,246,0.15)",
))
eq_fig.update_layout(
    height=320, margin=dict(l=10, r=10, t=10, b=10),
    paper_bgcolor=theme['bg'], plot_bgcolor=theme['bg'],
    font_color=theme['text'],
    xaxis=dict(gridcolor=theme['border']),
    yaxis=dict(gridcolor=theme['border']),
)
st.plotly_chart(eq_fig, use_container_width=True)

# ===============================================================
# CALENDAR
# ===============================================================
st.markdown('<div class="section-title">📅 Monthly P&L Calendar</div>', unsafe_allow_html=True)

daily = (filtered.assign(day=filtered["Exit_Time"].dt.date)
         .groupby("day").agg(daily_pnl=("Profit", "sum"), trades=("Profit", "count"))
         .reset_index())
daily["day"] = pd.to_datetime(daily["day"])

if not daily.empty:
    months = sorted(daily["day"].dt.to_period("M").unique(), reverse=True)
    month_options = [str(m) for m in months]
    selected_month = st.selectbox("Month", month_options, index=0)
    selected_period = pd.Period(selected_month, freq="M")
else:
    selected_period = pd.Period(datetime.now(), freq="M")

month_start = selected_period.to_timestamp()
days_in_month = monthrange(month_start.year, month_start.month)[1]
month_end = month_start + timedelta(days=days_in_month)
month_daily = daily[(daily["day"] >= month_start) & (daily["day"] < month_end)]
pnl_map = {row["day"].day: (row["daily_pnl"], row["trades"]) for _, row in month_daily.iterrows()}

first_weekday = month_start.weekday()
z_values, text_values, hover_text = [], [], []
max_abs = max(abs(month_daily["daily_pnl"]).max(), 1) if not month_daily.empty else 1

for week in range(6):
    row_z, row_text, row_hover = [], [], []
    for dow in range(7):
        day_num = week * 7 + dow - first_weekday + 1
        if day_num < 1 or day_num > days_in_month:
            row_z.append(None); row_text.append(""); row_hover.append("")
        else:
            if day_num in pnl_map:
                pnl, cnt = pnl_map[day_num]
                row_z.append(pnl)
                row_text.append(f"{day_num}<br><b>${pnl:.0f}</b><br>{cnt} trades")
                row_hover.append(f"Day {day_num}: ${pnl:.2f} ({cnt} trades)")
            else:
                row_z.append(0)
                row_text.append(f"{day_num}<br>—")
                row_hover.append(f"Day {day_num}: no trades")
    z_values.append(row_z); text_values.append(row_text); hover_text.append(row_hover)

fig = go.Figure(data=go.Heatmap(
    z=z_values, text=text_values, texttemplate="%{text}",
    textfont={"size": 14, "color": theme['text']},
    hoverinfo="text", hovertext=hover_text,
    colorscale=[
        [0.0, cal_colors["neg_dark"]], [0.25, cal_colors["neg_light"]],
        [0.5, cal_colors["mid"]],
        [0.75, cal_colors["pos_light"]], [1.0, cal_colors["pos_dark"]],
    ],
    zmid=0, zmin=-max_abs, zmax=max_abs, showscale=True, xgap=3, ygap=3,
))
fig.update_layout(
    height=500,
    xaxis=dict(tickmode="array", tickvals=list(range(7)),
               ticktext=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
               side="top", tickfont=dict(size=14, color=theme['text'])),
    yaxis=dict(showticklabels=False, autorange="reversed"),
    margin=dict(l=20, r=20, t=50, b=20),
    plot_bgcolor=theme['bg'], paper_bgcolor=theme['bg'],
    font_color=theme['text'],
)
st.plotly_chart(fig, use_container_width=True)

if not month_daily.empty:
    month_total = month_daily["daily_pnl"].sum()
    total_trades = int(month_daily["trades"].sum())
    green_days = int((month_daily["daily_pnl"] > 0).sum())
    red_days = int((month_daily["daily_pnl"] < 0).sum())
    st.caption(f"**{selected_month}** — Total: **${month_total:.2f}** | "
               f"Trades: **{total_trades}** | Green days: **{green_days}** | Red days: **{red_days}**")

# ===============================================================
# COLORED TRADE LOG
# ===============================================================
st.markdown(f'<div class="section-title">📋 Trade Log ({len(filtered)} trades)</div>', unsafe_allow_html=True)

display_df = filtered[[
    "Entry_Time", "Exit_Time", "Symbol", "Type",
    "Volume", "Entry_Price", "Exit_Price", "Profit", "Hold_Time_Min"
]].copy()

display_df["Entry_Time"] = display_df["Entry_Time"].dt.strftime("%Y-%m-%d %H:%M")
display_df["Exit_Time"] = display_df["Exit_Time"].dt.strftime("%Y-%m-%d %H:%M")
display_df["Hold_Time_Min"] = display_df["Hold_Time_Min"].round(1)

def style_trade_log(row):
    pnl = row["Profit"]
    if pnl > 0:
        bg = "rgba(38,166,154,0.12)" if theme_name == "Light" else "rgba(38,166,154,0.18)"
        color = WIN_COLOR
    elif pnl < 0:
        bg = "rgba(239,83,80,0.12)" if theme_name == "Light" else "rgba(239,83,80,0.18)"
        color = LOSS_COLOR
    else:
        bg = theme['card_bg']; color = theme['text']
    return [f"background-color:{bg};color:{color};font-weight:600;" if col == "Profit"
            else f"background-color:{bg};color:{theme['text']};"
            for col in row.index]

styled = display_df.style.apply(style_trade_log, axis=1).format({"Profit": "${:.2f}"})
st.dataframe(styled, use_container_width=True, height=420)


# ===============================================================
# TRADE NOTES
# ===============================================================
st.markdown("### 📝 Trade Notes")
st.caption("Select a trade below and journal your thoughts on it.")

notes_df = filtered.copy()
notes_df["label"] = notes_df.apply(
    lambda r: f"#{int(r['position_id'])}  ·  {r['Symbol']}  ·  {r['Exit_Time'].strftime('%b %d %H:%M')}  ·  ${r['Profit']:.2f}",
    axis=1,
)

selected_label = st.selectbox(
    "Select Trade",
    notes_df["label"].tolist(),
    key="trade_note_selector",
)
selected_trade = notes_df[notes_df["label"] == selected_label].iloc[0]

existing_note = (selected_trade["note"] if "note" in selected_trade.index and pd.notna(selected_trade["note"]) else "") or ""
existing_strategy = (selected_trade["strategy"] if "strategy" in selected_trade.index and pd.notna(selected_trade["strategy"]) else "") or ""
existing_session = (selected_trade["session"] if "session" in selected_trade.index and pd.notna(selected_trade["session"]) else "") or ""

SESSION_OPTIONS = ["", "Asia", "London", "New York", "London/NY Overlap", "Other"]
session_index = SESSION_OPTIONS.index(existing_session) if existing_session in SESSION_OPTIONS else 0

col_a, col_b = st.columns([2, 1])
with col_a:
    strategy_input = st.text_input(
        "Strategy / Confluence",
        value=existing_strategy,
        placeholder="e.g. London breakout after Asian range compression",
        key="strategy_input",
    )
with col_b:
    session_input = st.selectbox(
        "Session",
        SESSION_OPTIONS,
        index=session_index,
        key="session_input",
    )

note_input = st.text_area(
    "Notes",
    value=existing_note,
    placeholder="Why did you take this trade? How did you feel? What would you do differently?",
    height=120,
    key="note_input",
)

if st.button("💾 Save Note", type="primary"):
    db.update_trade_notes(
        int(selected_trade["id"]),
        note_input,
        strategy_input,
        session_input,
    )
    st.success("Note saved to Supabase ✅")
    st.rerun()



# ===============================================================
# DOWNLOAD REPORT AS CSV
# ===============================================================
export_cols = [
    "Entry_Time", "Exit_Time", "Symbol", "Type", "Volume",
    "Entry_Price", "Exit_Price", "Profit", "Hold_Time_Min",
    "strategy", "session", "note",
]
available_cols = [c for c in export_cols if c in filtered.columns]
export_df = filtered[available_cols].copy()

csv_data = export_df.to_csv(index=False).encode("utf-8")

st.download_button(
    label="⬇️ Download Report (CSV with Notes)",
    data=csv_data,
    file_name=f"{selected_account.replace(' ', '_')}_trades_{pd.Timestamp.now().strftime('%Y-%m-%d')}.csv",
    mime="text/csv",
    key="download_csv",
)




# ===============================================================
# AI TRADING COACH
# ===============================================================
from google import genai

st.markdown("---")
st.subheader("AI Trading Coach")
st.caption("Ask anything about your trades. The AI reads every trade and answers based on your real data.")

try:
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
except Exception as e:
    st.error(f"Could not configure AI model. Check GEMINI_API_KEY. Error: {e}")
    st.stop()


GEMINI_MODEL = st.secrets.get("GEMINI_MODEL", "gemini-2.5-flash")


_ai_cols = [
    "position_id", "Exit_Time", "Symbol", "Type",
    "Profit", "Hold_Time_Min", "strategy", "session", "note"
]
if "account_name" in filtered.columns:
    _ai_cols.insert(1, "account_name")
ai_data = filtered[_ai_cols].copy()
ai_csv = ai_data.to_csv(index=False)
trade_count = len(ai_data)


if "ai_chat_history" not in st.session_state:
    st.session_state.ai_chat_history = []


st.info(f"The AI is reading {trade_count} trades from {selected_account}. Ask it anything.")


for message in st.session_state.ai_chat_history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])


if prompt := st.chat_input("Ask about your trading..."):
    st.session_state.ai_chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown("_Analyzing your trades..._")

        full_prompt = f"""
TRADER'S QUESTION:
{prompt}

TRADER'S COMPLETE TRADE HISTORY ({trade_count} trades, CSV format):
{ai_csv}

NOTE: Rows are uniquely identified by (account_name, position_id).
The same position_id may appear in multiple accounts — those are NOT duplicates, they are different trades.

INSTRUCTIONS:
- Analyze the actual data above to answer the question.
- Use specific numbers (win rates, P&L, averages) from the data.
- If the question asks about patterns, look across multiple trades.
- If notes are relevant, quote them.
- If session or strategy columns are filled, use them.
- Be specific and actionable. Do not be generic.
"""

        import time
        answer = None
        last_error = None
        for attempt in range(2):  # initial call + 1 retry = 2 calls max
            try:
                _history = []
                for _msg in st.session_state.ai_chat_history[:-1]:
                    _history.append({
                        "role": "user" if _msg["role"] == "user" else "model",
                        "parts": [{"text": _msg["content"]}],
                    })
                _history.append({"role": "user", "parts": [{"text": full_prompt}]})
                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=_history,
                )
                answer = (response.text or "").strip() or "_(AI returned an empty response.)_"
                break
            except Exception as e:
                last_error = str(e)
                if ("503" in last_error or "UNAVAILABLE" in last_error) and attempt == 0:
                    placeholder.markdown("_AI is warming up... retrying once in 2s_")
                    time.sleep(2)
                    continue
                break
        if not answer:
            answer = f"AI error: {last_error}" if last_error else "AI service unavailable. Try again shortly."

        placeholder.markdown(answer)

    st.session_state.ai_chat_history.append({"role": "assistant", "content": answer})


if st.button("Clear chat"):
    st.session_state.ai_chat_history = []
    st.rerun()

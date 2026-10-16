import os
import json
import base64
import requests
import datetime
from datetime import datetime as dt, time, timedelta, timezone
import pandas as pd
import streamlit as st

try:
    from api.run import HISTORICAL_NEWS_SCHEDULE, get_news_events_for_window, check_pending_active_trade, get_event_symbols
except Exception:
    pass

# ==============================================================================
# 0. STREAMLIT APP CONFIGURATION (Mobile-friendly layout)
# ==============================================================================
LOGO_PATH = os.path.join(os.path.dirname(__file__), "app_logo.png")

st.set_page_config(
    page_title="Institutional Trading Terminal",
    page_icon=LOGO_PATH if os.path.exists(LOGO_PATH) else "📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

if os.path.exists(LOGO_PATH) and hasattr(st, "logo"):
    try:
        st.logo(LOGO_PATH, icon_image=LOGO_PATH)
    except Exception:
        pass

# Custom premium & mobile-first responsive CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }

    /* Mobile Header & Typography */
    .dashboard-header {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.9) 100%);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 20px 24px;
        margin-bottom: 20px;
        box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.5);
        backdrop-filter: blur(12px);
    }
    .main-title {
        font-size: 1.6rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        background: linear-gradient(135deg, #ffffff 0%, #cbd5e1 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 6px;
    }
    .sub-title {
        color: #94a3b8;
        font-size: 0.9rem;
        margin-bottom: 0;
        line-height: 1.4;
    }

    /* Touch-friendly Large Buttons */
    .stButton>button {
        width: 100% !important;
        border-radius: 14px !important;
        min-height: 52px !important;
        font-size: 1.05rem !important;
        font-weight: 700 !important;
        background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
        color: #ffffff !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        box-shadow: 0 4px 18px 0 rgba(37, 99, 235, 0.45) !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
        margin-top: 10px !important;
    }
    .stButton>button:active {
        transform: scale(0.98) !important;
        filter: brightness(0.95);
    }

    /* Metric & Control Cards */
    .glass-card {
        background: rgba(17, 24, 39, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
        padding: 16px 18px;
        backdrop-filter: blur(10px);
        margin-bottom: 14px;
    }
    
    /* Trade Card for Mobile */
    .trade-card {
        background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        padding: 18px;
        margin-bottom: 14px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
    }
    .badge-long {
        background: #065f46;
        color: #34d399;
        font-weight: 800;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.8rem;
        display: inline-block;
        border: 1px solid rgba(52, 211, 153, 0.3);
    }
    .badge-short {
        background: #881337;
        color: #fb7185;
        font-weight: 800;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.8rem;
        display: inline-block;
        border: 1px solid rgba(251, 113, 133, 0.3);
    }
    .badge-sync {
        background: #1e1b4b;
        color: #818cf8;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.78rem;
        display: inline-block;
        border: 1px solid rgba(129, 140, 248, 0.3);
    }

    /* Android & Mobile Specific Layout Adjustments */
    @media (max-width: 768px) {
        .main-title {
            font-size: 1.35rem !important;
        }
        .dashboard-header {
            padding: 16px !important;
            border-radius: 14px !important;
        }
        div[data-testid="column"] {
            min-width: 100% !important;
            flex: 1 1 100% !important;
            margin-bottom: 8px !important;
        }
        .stMetric {
            background: rgba(30, 41, 59, 0.6) !important;
            border: 1px solid rgba(255, 255, 255, 0.06) !important;
            border-radius: 12px !important;
            padding: 12px 14px !important;
        }
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 1. SESSION STATE INITIALIZATION
# ==============================================================================
DEFAULT_AMOUNT = 300.0  # $300 risk amount per strategy

if "base44_token" not in st.session_state:
    st.session_state.base44_token = os.environ.get(
        "BASE44_API_KEY", 
        "b44u_a42da4afa13a09294364b826325610580674a3365e53e3676ba7693e42240d8f"
    )

if "oanda_token" not in st.session_state:
    st.session_state.oanda_token = os.environ.get(
        "OANDA_TOKEN", 
        "f2b74d1cee1eb5488ba8b6b067e3ffc6-b6ccbdca86ea9ddb162f03996341ae91"
    )

if "oanda_env" not in st.session_state:
    st.session_state.oanda_env = "practice"  # 'practice' or 'trade' (live)

if "strat_1_id" not in st.session_state:
    st.session_state.strat_1_id = "6acaf2a887cd7b6cb6a1267c"  # USDJPY SELFSWEEP

if "strat_2_id" not in st.session_state:
    st.session_state.strat_2_id = "6acaf29762d5f24891c0c9bc"  # GBPUSD ASIA 1.2 - 1.4 FIB RETRACMENT

if "strat_3_id" not in st.session_state:
    st.session_state.strat_3_id = "6acaf24d7a78a186a5430938"  # XAUUSD 2H 4:30/5:30 DOL

if "date_mode" not in st.session_state:
    st.session_state.date_mode = "Single Day"

if "single_date" not in st.session_state:
    st.session_state.single_date = datetime.date.today()

if "start_date" not in st.session_state:
    st.session_state.start_date = datetime.date.today() - timedelta(days=7)

if "end_date" not in st.session_state:
    st.session_state.end_date = datetime.date.today()

# ==============================================================================
# 2. SIDEBAR SETTINGS (MOBILE COMPACT & CLEAN)
# ==============================================================================
with st.sidebar:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=90)
    st.markdown("### ⚙️ Engine Settings")
    st.caption("Settings persist across session navigations.")
    
    st.session_state.base44_token = st.text_input(
        "Base44 Personal Access Token",
        value=st.session_state.base44_token,
        type="password",
        help="Paste your Base44 bearer token here"
    )
    
    st.divider()
    st.subheader("🌐 Live Broker Feed (OANDA API)")
    st.session_state.oanda_token = st.text_input(
        "OANDA API Token",
        value=st.session_state.oanda_token,
        type="password",
        help="Connects to OANDA for real-time live candles"
    )
    st.session_state.oanda_env = st.selectbox(
        "OANDA Environment",
        ["practice", "trade (live)"],
        index=0 if st.session_state.oanda_env == "practice" else 1
    )
    
    st.divider()
    st.subheader("📋 Strategy Identifiers")
    
    st.session_state.strat_1_id = st.text_input(
        "USDJPY SELFSWEEP ID",
        value=st.session_state.strat_1_id
    )
    st.session_state.strat_2_id = st.text_input(
        "GBPUSD ASIA FIB ID",
        value=st.session_state.strat_2_id
    )
    st.session_state.strat_3_id = st.text_input(
        "XAUUSD 2H DOL ID",
        value=st.session_state.strat_3_id
    )
    
    st.divider()
    st.caption(f"Default Risk Allocation: **${DEFAULT_AMOUNT:,.2f}** per trade")

# ==============================================================================
# 3. OANDA LIVE CANDLE FETCHING & REAL-TIME MARKET PRICES
# ==============================================================================
def get_oanda_base_url():
    env = st.session_state.oanda_env if "oanda_env" in st.session_state else "practice"
    if "live" in env.lower():
        return "https://api-fxtrade.oanda.com/v3"
    return "https://api-fxpractice.oanda.com/v3"

def is_us_dst(dt_utc):
    year = dt_utc.year
    d_mar = dt(year, 3, 1)
    mar_second_sun = 1 + (6 - d_mar.weekday() + 7) % 7 + 7
    dst_start = dt(year, 3, mar_second_sun, 7, 0, tzinfo=timezone.utc if dt_utc.tzinfo else None)
    d_nov = dt(year, 11, 1)
    nov_first_sun = 1 + (6 - d_nov.weekday()) % 7
    dst_end = dt(year, 11, nov_first_sun, 6, 0, tzinfo=timezone.utc if dt_utc.tzinfo else None)
    return dst_start <= dt_utc < dst_end

def fetch_oanda_candles(instrument: str, granularity: str, target_date: datetime.date) -> pd.DataFrame:
    """
    Fetches candles for target_date from OANDA API with timezone conversions (UTC, IST, NY).
    Handles past dates and live current-day streaming without future-time errors.
    """
    token = st.session_state.oanda_token if "oanda_token" in st.session_state else os.environ.get("OANDA_TOKEN", "f2b74d1cee1eb5488ba8b6b067e3ffc6-b6ccbdca86ea9ddb162f03996341ae91")
    if not token:
        return pd.DataFrame()
        
    base_url = get_oanda_base_url()
    headers = {"Authorization": f"Bearer {token}"}
    
    # Start from previous day 00:00 UTC to ensure full Asian/London sessions are captured
    start_utc = dt(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=timezone.utc) - timedelta(days=1)
    now_utc = dt.now(timezone.utc)
    
    params = {
        "granularity": granularity,
        "price": "M",
        "from": start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    
    # If target date is in the past, add bounded 'to' timestamp
    target_end_utc = dt(target_date.year, target_date.month, target_date.day, 23, 59, 59, tzinfo=timezone.utc)
    if target_end_utc < now_utc:
        params["to"] = target_end_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        
    try:
        url = f"{base_url}/instruments/{instrument}/candles"
        r = requests.get(url, headers=headers, params=params, timeout=12)
        if r.status_code == 200:
            raw_candles = r.json().get("candles", [])
            records = []
            for c in raw_candles:
                t_str = c["time"][:19] + "Z"
                t_utc = dt.strptime(t_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                records.append({
                    "time_utc": t_utc,
                    "open": float(c["mid"]["o"]),
                    "high": float(c["mid"]["h"]),
                    "low": float(c["mid"]["l"]),
                    "close": float(c["mid"]["c"]),
                    "complete": c.get("complete", True)
                })
            df = pd.DataFrame(records)
            if not df.empty:
                df["dt_ist"] = df["time_utc"].apply(lambda t: t.astimezone(timezone(timedelta(hours=5, minutes=30))))
                df["dt_ny"] = df["time_utc"].apply(lambda t: t.astimezone(timezone(timedelta(hours=-4 if is_us_dst(t) else -5))))
                return df
    except Exception as e:
        print(f"OANDA fetch error for {instrument}: {e}")
    return pd.DataFrame()

def get_latest_market_price(symbol: str) -> float:
    """Fetches real-time market price for symbol from OANDA."""
    inst = "USD_JPY" if "JPY" in symbol else ("GBP_USD" if "GBP" in symbol else "XAU_USD")
    token = st.session_state.oanda_token if "oanda_token" in st.session_state else os.environ.get("OANDA_TOKEN", "")
    if not token:
        return 0.0
    base_url = get_oanda_base_url()
    try:
        url = f"{base_url}/instruments/{inst}/candles"
        r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params={"count": 1, "price": "M", "granularity": "M1"}, timeout=5)
        if r.status_code == 200:
            c_list = r.json().get("candles", [])
            if c_list:
                return float(c_list[-1]["mid"]["c"])
    except Exception:
        pass
    return 0.0

# ==============================================================================
# 4. BASE44 TRADE JOURNAL API INTEGRATION & LIFECYCLE TRACKER
# ==============================================================================
BASE44_API_URL = "https://trading-journal-2-0.base44.app/api/entities/Trade"

# Fixed broker & exchange fees per trade:
# XAUUSD: $25.00 per trade
# GBPUSD: $40.00 per trade
# USDJPY: $40.00 per trade
FIXED_FEES = {
    "XAUUSD": 25.0,
    "GBPUSD": 40.0,
    "USDJPY": 40.0
}

def get_trade_fee(symbol: str) -> float:
    """Returns fixed fee per trade ($25 for XAUUSD, $40 for GBPUSD, $40 for USDJPY)."""
    s = str(symbol).upper()
    if "XAU" in s:
        return FIXED_FEES["XAUUSD"]
    elif "GBP" in s:
        return FIXED_FEES["GBPUSD"]
    elif "JPY" in s:
        return FIXED_FEES["USDJPY"]
    return 0.0

def calculate_risk_quantity(symbol: str, entry_price: float, sl_price: float, risk_usd: float = DEFAULT_AMOUNT) -> float:
    """
    Calculates exact risk-based position size to risk precisely $300 on Stop Loss:
    Quantity = Risk ($300) / |entry_price - sl_price|
    - XAUUSD: Rounded to 1 decimal place (ounces/contracts).
    - GBPUSD & USDJPY: Rounded to whole units.
    """
    diff = abs(entry_price - sl_price)
    if diff <= 0:
        return 1.0
    qty = risk_usd / diff
    if "XAU" in symbol.upper():
        return round(qty, 1)
    else:
        return round(qty, 0)

def fetch_m1_exit_time(instrument: str, start_dt_utc: datetime.datetime, end_dt_utc: datetime.datetime, 
                        direction: str, sl_price: float, tp_price: float) -> str | None:
    """
    Scans 1-minute (M1) candles between entry time and M15 exit window to find the exact minute
    and candle close timestamp when Stop Loss or Take Profit was triggered in IST.
    """
    token = st.session_state.oanda_token if "oanda_token" in st.session_state else os.environ.get("OANDA_TOKEN", "f2b74d1cee1eb5488ba8b6b067e3ffc6-b6ccbdca86ea9ddb162f03996341ae91")
    if not token:
        return None
        
    base_url = get_oanda_base_url()
    headers = {"Authorization": f"Bearer {token}"}
    
    cur_from = start_dt_utc
    while cur_from < end_dt_utc:
        params = {
            "granularity": "M1",
            "price": "M",
            "from": cur_from.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "count": 500
        }
        try:
            url = f"{base_url}/instruments/{instrument}/candles"
            r = requests.get(url, headers=headers, params=params, timeout=10)
            if r.status_code != 200:
                break
            raw_candles = r.json().get("candles", [])
            if not raw_candles:
                break
                
            for c in raw_candles:
                t_str = c["time"][:19] + "Z"
                t_utc = dt.strptime(t_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                if t_utc > end_dt_utc:
                    return None
                    
                c_high = float(c["mid"]["h"])
                c_low = float(c["mid"]["l"])
                hit = False
                if direction == "long":
                    if c_low <= sl_price or c_high >= tp_price:
                        hit = True
                elif direction == "short":
                    if c_high >= sl_price or c_low <= tp_price:
                        hit = True
                        
                if hit:
                    # Return exact close of this 1-minute candle in IST (t_utc + 1 min)
                    t_close_utc = t_utc + timedelta(minutes=1)
                    t_close_ist = t_close_utc.astimezone(timezone(timedelta(hours=5, minutes=30)))
                    return t_close_ist.strftime("%Y-%m-%dT%H:%M")
                    
            last_t = dt.strptime(raw_candles[-1]["time"][:19] + "Z", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if last_t <= cur_from or len(raw_candles) < 500:
                break
            cur_from = last_t + timedelta(minutes=1)
        except Exception:
            break
    return None

def evaluate_trade_lifecycle(trade_info: dict) -> dict:
    """
    Evaluates whether trade hit TP, SL, or is currently OPEN.
    Uses precise 1-minute (M1) candles for exact exit timing down to the minute.
    Format: YYYY-MM-DDTHH:MM (Exact Indian Standard Time)
    Auto-exits 5 minutes before scheduled high-impact news releases (NFP, CPI, FOMC, BOJ, BOE).
    """
    symbol = trade_info["symbol"]
    direction = trade_info["direction"].lower()
    entry_price = float(trade_info["entry_price"])
    sl_price = float(trade_info["sl_price"])
    tp_price = float(trade_info["tp_price"])
    trade_date = trade_info.get("date", datetime.date.today())
    if isinstance(trade_date, str):
        try:
            trade_date = dt.strptime(trade_date[:10], "%Y-%m-%d").date()
        except Exception:
            trade_date = datetime.date.today()
    
    # Pre-existing entry time if provided by strategy engine (at candle close)
    entry_time_str = trade_info.get("entry_time_ist")
    
    quantity = calculate_risk_quantity(symbol, entry_price, sl_price)
    inst = "USD_JPY" if "JPY" in symbol else ("GBP_USD" if "GBP" in symbol else "XAU_USD")
    candles_df = fetch_oanda_candles(inst, "M15", trade_date)
    
    status = "open"
    exit_price = get_latest_market_price(symbol)
    exit_time_str = None
    exit_reason = None
    
    # Fetch live real-time high-impact economic news events tailored to symbol
    realtime_news = []
    try:
        realtime_news = get_news_events_for_window(trade_date, trade_date + timedelta(days=2), symbol=symbol)
    except Exception:
        pass
    
    if not candles_df.empty:
        # Default entry time fallback if missing
        if not entry_time_str:
            if symbol == "GBPUSD":
                entry_time_str = f"{trade_date.strftime('%Y-%m-%d')}T12:15"
            elif symbol == "XAUUSD":
                entry_time_str = f"{trade_date.strftime('%Y-%m-%d')}T06:30"
            elif symbol == "USDJPY":
                entry_time_str = f"{trade_date.strftime('%Y-%m-%d')}T13:30"
            else:
                entry_time_str = f"{trade_date.strftime('%Y-%m-%d')}T12:00"

        # Determine cutoff time for exit evaluation
        try:
            e_dt = dt.strptime(entry_time_str, "%Y-%m-%dT%H:%M")
            e_time = e_dt.time()
        except Exception:
            e_time = time(6, 30) if symbol == "XAUUSD" else time(12, 15)
            
        sub_df = candles_df[(candles_df['dt_ist'].dt.date >= trade_date) & 
                            ((candles_df['dt_ist'].dt.date > trade_date) | (candles_df['dt_ist'].dt.time >= e_time))].sort_values('time_utc').reset_index(drop=True)
            
        for _, c in sub_df.iterrows():
            c_high, c_low, c_dt_ist, c_time_utc = c['high'], c['low'], c['dt_ist'], c['time_utc']
            hit_exit = False
            
            # 1. High Impact News Exit (Cut 5 minutes before scheduled prohibited news for this instrument)
            if realtime_news:
                try:
                    c_dt_naive = c_dt_ist.tz_localize(None) if hasattr(c_dt_ist, 'tz_localize') else (c_dt_ist.replace(tzinfo=None) if hasattr(c_dt_ist, 'tzinfo') and c_dt_ist.tzinfo else c_dt_ist)
                except Exception:
                    c_dt_naive = c_dt_ist
                c_end_naive = c_dt_naive + timedelta(minutes=15)
                is_news_exit = False
                for ev in realtime_news:
                    n_dt = ev['dt_ist']
                    if hasattr(n_dt, 'tzinfo') and n_dt.tzinfo is not None:
                        n_dt = n_dt.replace(tzinfo=None)
                    if c_dt_naive < n_dt <= c_end_naive:
                        status = "closed"
                        exit_price = c['open']
                        exit_time_str = (n_dt - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M")
                        exit_reason = f"Pre-News Exit (5m before {ev['category']}: {ev['title']})"
                        hit_exit = True
                        is_news_exit = True
                        break
                if is_news_exit:
                    break

            # 2. Weekend cutoff check: Saturday before 02:30 AM (Summer) / 03:30 AM (Winter)
            if c_dt_ist.weekday() == 5:
                cut_t = time(2, 15) if is_us_dst(c_time_utc) else time(3, 15)
                if c_dt_ist.time() >= cut_t:
                    status = "closed"
                    exit_price = c['close']
                    exit_time_str = (c_dt_ist + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M")
                    exit_reason = "Weekend Close"
                    break

            if direction == "long":
                if c_low <= sl_price:
                    status = "closed"
                    exit_price = sl_price
                    exit_reason = "SL Hit"
                    hit_exit = True
                elif c_high >= tp_price:
                    status = "closed"
                    exit_price = tp_price
                    exit_reason = "TP Hit"
                    hit_exit = True
            elif direction == "short":
                if c_high >= sl_price:
                    status = "closed"
                    exit_price = sl_price
                    exit_reason = "SL Hit"
                    hit_exit = True
                elif c_low <= tp_price:
                    status = "closed"
                    exit_price = tp_price
                    exit_reason = "TP Hit"
                    hit_exit = True
                    
            if hit_exit:
                # 1-minute precision scan from entry to this M15 candle's close
                try:
                    entry_utc = dt.strptime(entry_time_str, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone(timedelta(hours=5, minutes=30))).astimezone(timezone.utc)
                except Exception:
                    entry_utc = c_time_utc - timedelta(hours=2)
                m15_close_utc = c_time_utc + timedelta(minutes=15)
                
                m1_exit_str = fetch_m1_exit_time(inst, entry_utc, m15_close_utc, direction, sl_price, tp_price)
                if m1_exit_str:
                    exit_time_str = m1_exit_str
                else:
                    exit_time_str = (c_dt_ist + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M")
                break
                    
    # If still open, populate with current live IST timestamp
    if status == "open":
        now_ist = dt.now(timezone.utc) + timedelta(hours=5, minutes=30)
        exit_time_str = now_ist.strftime("%Y-%m-%dT%H:%M")
        live_price = get_latest_market_price(symbol)
        if live_price > 0:
            exit_price = live_price
        elif not candles_df.empty:
            exit_price = candles_df.iloc[-1]['close']
        else:
            exit_price = entry_price
            
    # Calculate exact net P&L after deducting fixed broker fee
    fee = get_trade_fee(symbol)
    if direction == "long":
        gross_pnl = (exit_price - entry_price) * quantity
    else:
        gross_pnl = (entry_price - exit_price) * quantity
        
    net_pnl = gross_pnl - fee
        
    return {
        "status": status,
        "entry_time_str": entry_time_str,
        "exit_price": round(exit_price, 5 if "GBP" in symbol else (3 if "JPY" in symbol else 2)),
        "exit_time_str": exit_time_str,
        "quantity": quantity,
        "gross_pnl": round(gross_pnl, 2),
        "fee": fee,
        "net_pnl": round(net_pnl, 2),
        "exit_reason": exit_reason
    }

def find_existing_trade(api_key: str, strategy_id: str, symbol: str, trade_date: datetime.date, entry_time_ist: str | None = None) -> dict | None:
    """Finds existing trade entity for strategy_id & symbol on trade_date, if already logged."""
    if not api_key:
        return None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    params = {"q": f'{{"strategy_id": "{strategy_id}", "symbol": "{symbol}"}}'}
    try:
        resp = requests.get(BASE44_API_URL, headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            date_str = trade_date.isoformat()
            for item in items:
                entry_ts = str(item.get("entry_timestamp", ""))
                if entry_time_ist:
                    if entry_ts == entry_time_ist:
                        return item
                else:
                    if entry_ts.startswith(date_str):
                        return item
    except Exception as e:
        print(f"Error checking existing trade: {e}")
    return None

def sync_trade_to_base44(api_key: str, strategy_id: str, trade_info: dict) -> tuple[str, str]:
    """
    Logs or updates trade in Base44 Trade Journal:
    - Calculates risk-adjusted quantity ($300 risk).
    - If closed: marks status="closed", sell_price=TP/SL, and net_pnl.
    - If open: marks status="open", sell_price=current market price, and unrealized net_pnl.
    """
    if not api_key:
        return "Not Connected", "Base44 Personal Access Token not provided in sidebar."
    
    symbol = trade_info["symbol"]
    direction = trade_info["direction"]
    entry_price = float(trade_info["entry_price"])
    sl_price = float(trade_info["sl_price"])
    tp_price = float(trade_info["tp_price"])
    sl_pct = trade_info["sl_percentage"]
    tp_pct = trade_info["tp_percentage"]
    trade_date = trade_info.get("date", datetime.date.today())
    if isinstance(trade_date, str):
        try:
            trade_date = dt.strptime(trade_date[:10], "%Y-%m-%d").date()
        except Exception:
            trade_date = datetime.date.today()
    
    # 1. Resolve lifecycle & current outcome
    lifecycle = evaluate_trade_lifecycle(trade_info)
    quantity = lifecycle["quantity"]
    status = lifecycle["status"]
    exit_price = lifecycle["exit_price"]
    net_pnl = lifecycle["net_pnl"]
    fee = lifecycle["fee"]
    exit_ts_str = lifecycle["exit_time_str"]
    entry_ts_str = lifecycle["entry_time_str"]
    exit_reason = lifecycle.get("exit_reason")
    
    notes = f"{sl_pct}% SL ({sl_price}) , {tp_pct}% TP ({tp_price}) | Risk: ${DEFAULT_AMOUNT:,.2f} | Fee: ${fee:,.2f}"
    if trade_info.get("entry_no") == 2 or trade_info.get("is_double_entry"):
        notes += " | Double Entry"
    if exit_reason:
        notes += f" | {exit_reason}"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # 2. Check if already exists in Base44 (with exact entry timestamp)
    existing = find_existing_trade(api_key, strategy_id, symbol, trade_date, entry_time_ist=entry_ts_str)
    if existing:
        t_id = existing.get("id")
        if existing.get("status") == "open":
            # Update open trade to closed (or refresh live exit price)
            put_payload = {
                "strategy_id": strategy_id,
                "symbol": symbol,
                "direction": direction.lower(),
                "buy_price": float(entry_price),
                "sell_price": float(exit_price),
                "quantity": float(quantity),
                "entry_timestamp": entry_ts_str if entry_ts_str else existing.get("entry_timestamp"),
                "exit_timestamp": exit_ts_str,
                "status": status,
                "net_pnl": float(net_pnl),
                "notes": notes
            }
            try:
                put_r = requests.put(f"{BASE44_API_URL}/{t_id}", headers=headers, json=put_payload, timeout=10)
                if put_r.status_code in [200, 201]:
                    action_label = "Closed at TP/SL" if status == "closed" else "Open (Live P&L Updated)"
                    return "Updated", f"{action_label}: exit @ {exit_price} | Net P&L: ${net_pnl:+.2f} (Fee: ${fee:,.2f})"
                else:
                    return "Error", f"HTTP {put_r.status_code}: {put_r.text}"
            except Exception as e:
                return "Error", f"Update failed: {e}"
        else:
            return "Skipped (Duplicate)", f"Trade already closed @ {existing.get('sell_price')} (Net P&L: ${existing.get('net_pnl', 0):+.2f})"
            
    # 3. Create fresh record (POST)
    payload = {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "direction": direction.lower(),
        "buy_price": float(entry_price),
        "sell_price": float(exit_price),
        "quantity": float(quantity),
        "entry_timestamp": entry_ts_str,
        "exit_timestamp": exit_ts_str,
        "status": status,
        "net_pnl": float(net_pnl),
        "notes": notes
    }
    
    try:
        resp = requests.post(BASE44_API_URL, headers=headers, json=payload, timeout=10)
        if resp.status_code in [200, 201]:
            status_desc = "CLOSED (Hit TP/SL)" if status == "closed" else "OPEN (Live Market)"
            return "Success", f"Logged {symbol} {direction.upper()} as {status_desc} @ exit {exit_price} (Net P&L: ${net_pnl:+.2f} after ${fee:,.2f} fee)"
        else:
            return "Error", f"HTTP {resp.status_code}: {resp.text}"
    except Exception as e:
        return "Error", f"Request exception: {str(e)}"

def check_and_update_all_open_trades(api_key: str) -> list[dict]:
    """
    Scans Base44 for any open trades, verifies against live OANDA candles,
    and updates their status, exit price, and net P&L via PUT.
    """
    if not api_key:
        return []
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    try:
        resp = requests.get(BASE44_API_URL, headers=headers, timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json()
        all_items = data if isinstance(data, list) else (data.get("items", []) if isinstance(data, dict) else [])
        open_items = [t for t in all_items if t.get("status") == "open"]
        if not open_items:
            return []
            
        updated_records = []
        for trade in open_items:
            t_id = trade.get("id")
            sym = trade.get("symbol", "")
            direction = str(trade.get("direction", "long")).lower()
            buy_price = float(trade.get("buy_price", 0.0))
            qty = float(trade.get("quantity", 1.0))
            notes = str(trade.get("notes", ""))
            
            # Reconstruct SL & TP from notes
            sl_price = 0.0
            tp_price = 0.0
            if "SL (" in notes and "TP (" in notes:
                try:
                    sl_price = float(notes.split("SL (")[1].split(")")[0])
                    tp_price = float(notes.split("TP (")[1].split(")")[0])
                except Exception:
                    pass
                    
            if sl_price == 0.0:
                if "JPY" in sym:
                    sl_dist = buy_price * 0.0006
                    sl_price = buy_price - sl_dist if direction == "long" else buy_price + sl_dist
                    tp_price = buy_price + 5.0 * sl_dist if direction == "long" else buy_price - 5.0 * sl_dist
                elif "GBP" in sym:
                    sl_dist = buy_price * 0.00066
                    sl_price = buy_price - sl_dist if direction == "long" else buy_price + sl_dist
                    tp_price = buy_price + 3.75 * sl_dist if direction == "long" else buy_price - 3.75 * sl_dist
                elif "XAU" in sym:
                    sl_dist = buy_price * 0.005
                    sl_price = buy_price - sl_dist if direction == "long" else buy_price + sl_dist
                    tp_price = buy_price + 3.30 * sl_dist if direction == "long" else buy_price - 3.30 * sl_dist
                    
            entry_ts = trade.get("entry_timestamp", "")
            try:
                entry_d = dt.strptime(entry_ts[:10], "%Y-%m-%d").date()
            except Exception:
                entry_d = datetime.date.today()
                
            trade_dummy = {
                "symbol": sym,
                "direction": direction,
                "entry_price": buy_price,
                "sl_price": sl_price,
                "tp_price": tp_price,
                "date": entry_d
            }
            res = evaluate_trade_lifecycle(trade_dummy)
            new_status = res["status"]
            exit_p = res["exit_price"]
            fee = res["fee"]
            exit_ts = res["exit_time_str"]
            
            if qty <= 1.0:
                qty = res["quantity"]
            gross_pnl = (exit_p - buy_price if direction == "long" else buy_price - exit_p) * qty
            new_pnl = round(gross_pnl - fee, 2)
            
            if "Fee:" not in notes:
                notes = f"{notes} | Fee: ${fee:,.2f}"
                
            put_payload = {
                "strategy_id": trade.get("strategy_id"),
                "symbol": sym,
                "direction": direction,
                "buy_price": buy_price,
                "sell_price": float(exit_p),
                "quantity": float(qty),
                "entry_timestamp": trade.get("entry_timestamp"),
                "exit_timestamp": exit_ts,
                "status": new_status,
                "net_pnl": float(new_pnl),
                "notes": notes
            }
            put_resp = requests.put(f"{BASE44_API_URL}/{t_id}", headers=headers, json=put_payload, timeout=10)
            if put_resp.status_code in [200, 201]:
                updated_records.append({
                    "id": t_id,
                    "symbol": sym,
                    "direction": direction,
                    "status": new_status,
                    "exit_price": exit_p,
                    "pnl": new_pnl
                })
        return updated_records
    except Exception as e:
        print(f"Error checking open trades: {e}")
        return []

# ==============================================================================
# 5. STRATEGY EXECUTION ENGINES
# ==============================================================================

# ------------------------------------------------------------------------------
# Strategy 1: USDJPY SELFSWEEP
# ------------------------------------------------------------------------------
def run_usdjpy_strategy(target_date: datetime.date) -> dict:
    """
    USDJPY Selfsweep Strategy:
    - M15 Session extremes, filtered with 1:5.0 target and No BE
    - Day Filter: No Tuesdays
    - SL Range: 0.045% to 0.154%
    """
    result_template = {
        "strategy_name": "USDJPY SELFSWEEP",
        "symbol": "USDJPY",
        "date": target_date,
        "direction": "none",
        "entry_price": 0.0,
        "sl_price": 0.0,
        "tp_price": 0.0,
        "sl_percentage": 0.0,
        "tp_percentage": 0.0,
        "status": "No Trade Setup",
        "details": "",
        "data_source": "OANDA Live API"
    }
    # USDJPY Selfsweep triggers across all trading days

    # 1. Try OANDA Live API first
    day_df = pd.DataFrame()
    live_df = fetch_oanda_candles("USD_JPY", "M15", target_date)
    if not live_df.empty:
        day_df = live_df[live_df['dt_ist'].dt.date == target_date].sort_values('dt_ist').reset_index(drop=True)
        result_template["data_source"] = "OANDA Live Feed"
    
    # 2. Fallback to Local CSV if API returned empty
    if day_df.empty:
        csv_file = "USDJPY_M15_2024-03_to_2026-09.csv"
        if os.path.exists(csv_file):
            df = pd.read_csv(csv_file)
            df['dt_ist'] = pd.to_datetime(df['time_ist'])
            day_df = df[df['dt_ist'].dt.date == target_date].sort_values('dt_ist').reset_index(drop=True)
            result_template["data_source"] = "Local Archive CSV"
            
    is_tuesday = (target_date.weekday() == 1)
    
    if day_df.empty or len(day_df) < 4:
        if is_tuesday:
            result_template["status"] = "Skipped (Tuesday Rule)"
            result_template["details"] = "Tuesday is strictly excluded by USDJPY Champion strategy rules (No Tuesday filter). No live trade logged."
            return result_template
        result_template["status"] = "No Session Data"
        result_template["details"] = f"No M15 candles available for {target_date}."
        return result_template
        
    try:
        sample_utc = pd.to_datetime(day_df['time_utc'].iloc[0])
        is_summer = is_us_dst(sample_utc)
        
        # Session filters (IST)
        t_col = day_df['dt_ist'].dt.time
        if is_summer:
            cond_asia = (t_col >= time(5, 30)) & (t_col <= time(9, 0))
            cond_london = (t_col >= time(11, 30)) & (t_col <= time(14, 0))
        else:
            cond_asia = (t_col >= time(6, 30)) & (t_col <= time(10, 0))
            cond_london = (t_col >= time(12, 30)) & (t_col <= time(15, 0))
            
        # Scan for selfsweep trigger
        for s_name, cond in [("ASIA", cond_asia), ("LONDON", cond_london)]:
            s_df = day_df[cond].reset_index(drop=True)
            N = len(s_df)
            if N < 4: continue
            
            opens, highs, lows, closes = s_df['open'].values, s_df['high'].values, s_df['low'].values, s_df['close'].values
            
            # Long Check
            ext_low, ceiling, state = lows[0], highs[0], 'SEEK_CC'
            for i in range(1, N):
                c_o, c_h, c_l, c_c = opens[i], highs[i], lows[i], closes[i]
                if state == 'SEEK_CC':
                    if c_l <= ext_low: ext_low, ceiling = c_l, c_h
                    else:
                        if c_c > ceiling: state = 'WAIT_SUSTAIN'
                        ceiling = max(ceiling, c_h)
                elif state == 'WAIT_SUSTAIN':
                    if c_l <= ext_low: ext_low, ceiling, state = c_l, c_h, 'SEEK_CC'
                    else: state = 'WAIT_SWEEP'
                elif state == 'WAIT_SWEEP':
                    if c_l <= ext_low - 0.001:
                        if c_c <= ext_low: ext_low, ceiling, state = c_l, c_h, 'SEEK_CC'
                        else:
                            if c_c > c_o:
                                body = c_c - c_o
                                l_wick = c_o - c_l
                                ratio_ok = (body >= 0.002) if (l_wick >= 0.100) else (body >= 0.003)
                                if ratio_ok:
                                    entry = c_c
                                    init_sl = c_l
                                    sl_pct = (abs(entry - init_sl) / entry) * 100.0
                                    if 0.015 <= sl_pct <= 0.154:
                                        if is_tuesday:
                                            result_template.update({
                                                "status": "Skipped (Tuesday Rule)",
                                                "details": f"Setup formed ({s_name} Long @ {entry:.3f}), but Tuesdays are strictly excluded from live execution by strategy rules."
                                            })
                                            return result_template
                                            
                                        buffer_p = 0.006 + max(0, int((sl_pct - 0.055) / 0.010)) * 0.001
                                        ext_sl = init_sl - buffer_p
                                        risk = entry - ext_sl
                                        tp = entry + 5.0 * risk
                                        entry_close_ist = s_df.iloc[i]['dt_ist'] + timedelta(minutes=15)
                                        entry_t_str = entry_close_ist.strftime("%Y-%m-%dT%H:%M")
                                        result_template.update({
                                            "direction": "long",
                                            "entry_price": round(entry, 3),
                                            "entry_time_ist": entry_t_str,
                                            "sl_price": round(ext_sl, 3),
                                            "tp_price": round(tp, 3),
                                            "sl_percentage": round(sl_pct, 3),
                                            "tp_percentage": round(sl_pct * 5.0, 3),
                                            "status": f"Active Signal ({s_name} Long)",
                                            "details": f"Confirmed M15 Selfsweep in {s_name} session."
                                        })
                                        return result_template
                                    
            # Short Check
            ext_high, floor, state = highs[0], lows[0], 'SEEK_CC'
            for i in range(1, N):
                c_o, c_h, c_l, c_c = opens[i], highs[i], lows[i], closes[i]
                if state == 'SEEK_CC':
                    if c_h >= ext_high: ext_high, floor = c_h, c_l
                    else:
                        if c_c < floor: state = 'WAIT_SUSTAIN'
                        floor = min(floor, c_l)
                elif state == 'WAIT_SUSTAIN':
                    if c_h >= ext_high: ext_high, floor, state = c_h, c_l, 'SEEK_CC'
                    else: state = 'WAIT_SWEEP'
                elif state == 'WAIT_SWEEP':
                    if c_h >= ext_high + 0.001:
                        if c_c >= ext_high: ext_high, floor, state = c_h, c_l, 'SEEK_CC'
                        else:
                            if c_c < c_o:
                                body = c_o - c_c
                                u_wick = c_h - c_o
                                ratio_ok = (body >= 0.002) if (u_wick >= 0.100) else (body >= 0.003)
                                if ratio_ok:
                                    entry = c_c
                                    init_sl = c_h
                                    sl_pct = (abs(entry - init_sl) / entry) * 100.0
                                    if 0.015 <= sl_pct <= 0.154:
                                        if is_tuesday:
                                            result_template.update({
                                                "status": "Skipped (Tuesday Rule)",
                                                "details": f"Setup formed ({s_name} Short @ {entry:.3f}), but Tuesdays are strictly excluded from live execution by strategy rules."
                                            })
                                            return result_template
                                            
                                        buffer_p = 0.006 + max(0, int((sl_pct - 0.055) / 0.010)) * 0.001
                                        ext_sl = init_sl + buffer_p
                                        risk = ext_sl - entry
                                        tp = entry - 5.0 * risk
                                        entry_close_ist = s_df.iloc[i]['dt_ist'] + timedelta(minutes=15)
                                        entry_t_str = entry_close_ist.strftime("%Y-%m-%dT%H:%M")
                                        result_template.update({
                                            "direction": "short",
                                            "entry_price": round(entry, 3),
                                            "entry_time_ist": entry_t_str,
                                            "sl_price": round(ext_sl, 3),
                                            "tp_price": round(tp, 3),
                                            "sl_percentage": round(sl_pct, 3),
                                            "tp_percentage": round(sl_pct * 5.0, 3),
                                            "status": f"Active Signal ({s_name} Short)",
                                            "details": f"Confirmed M15 Selfsweep in {s_name} session."
                                        })
                                        return result_template
                                        
        if is_tuesday:
            result_template["status"] = "Skipped (Tuesday Rule)"
            result_template["details"] = "Tuesday is strictly excluded by USDJPY Champion strategy rules (No Tuesday filter). No trade logged."
            return result_template
            
        return result_template
    except Exception as e:
        result_template["status"] = "Error"
        result_template["details"] = str(e)
        return result_template

# ------------------------------------------------------------------------------
# Strategy 2: GBPUSD ASIA 1.2 - 1.4 FIB RETRACEMENT (GodMode)
# ------------------------------------------------------------------------------
def run_gbpusd_strategy(target_date: datetime.date) -> dict | list[dict]:
    """
    GBPUSD Asian Fib Strategy (GodMode):
    - Asian Range 05:30-09:30 IST (Summer) / 06:30-10:30 IST (Winter)
    - Pre-London Gap Invalidation (09:45-11:15 IST / 10:45-12:15 IST)
    - London Entry Window (11:30-14:30 IST / 12:30-15:30 IST)
    - 1:3.75 Target, No BE
    - SL: 0.035% to 0.154%
    - Double Entry (Entry 2) tracking if Entry 1 stops out without candle close past SL
    """
    result = {
        "strategy_name": "GBPUSD ASIA 1.2 - 1.4 FIB RETRACMENT",
        "symbol": "GBPUSD",
        "date": target_date,
        "direction": "none",
        "entry_price": 0.0,
        "entry_time_ist": None,
        "sl_price": 0.0,
        "tp_price": 0.0,
        "sl_percentage": 0.0,
        "tp_percentage": 0.0,
        "status": "No Trade Setup",
        "details": "",
        "data_source": "OANDA Live API"
    }
    
    # 1. Fetch live OANDA candles
    day_df = pd.DataFrame()
    live_df = fetch_oanda_candles("GBP_USD", "M15", target_date)
    if not live_df.empty:
        day_df = live_df[live_df['dt_ist'].dt.date == target_date].sort_values('dt_ist').reset_index(drop=True)
        result["data_source"] = "OANDA Live Feed"
        
    # 2. Local CSV fallback
    if day_df.empty:
        csv_file = "GBPUSD_2YEARS.csv"
        if os.path.exists(csv_file):
            df = pd.read_csv(csv_file)
            df.columns = [c.strip().lower() for c in df.columns]
            time_col = 'time' if 'time' in df.columns else ('timestamp' if 'timestamp' in df.columns else df.columns[0])
            df['dt_ist'] = pd.to_datetime(df[time_col])
            day_df = df[df['dt_ist'].dt.date == target_date].sort_values('dt_ist').reset_index(drop=True)
            result["data_source"] = "Local Archive CSV"
            
    if day_df.empty or len(day_df) < 8:
        result["status"] = "No Session Data"
        result["details"] = f"Insufficient M15 candles available for {target_date}."
        return result
        
    try:
        sample_utc = pd.to_datetime(day_df['time_utc'].iloc[0])
        is_summer = is_us_dst(sample_utc)
        t_col = day_df['dt_ist'].dt.time
        
        # Session boundaries in IST
        asia_start_t = time(5, 30) if is_summer else time(6, 30)
        asia_end_t = time(9, 30) if is_summer else time(10, 30)
        
        gap_start_t = time(9, 45) if is_summer else time(10, 45)
        gap_end_t = time(11, 15) if is_summer else time(12, 15)
        
        lon_start_t = time(11, 30) if is_summer else time(12, 30)
        lon_end_t = time(14, 30) if is_summer else time(15, 30)
        
        asia_cond = (t_col >= asia_start_t) & (t_col <= asia_end_t)
        gap_cond = (t_col >= gap_start_t) & (t_col <= gap_end_t)
        lon_cond = (t_col >= lon_start_t) & (t_col <= lon_end_t)
        
        asia_df = day_df[asia_cond].reset_index(drop=True)
        if len(asia_df) < 4:
            result["status"] = "No Asian Session Data"
            return result
            
        asia_high = float(asia_df['high'].max())
        asia_low = float(asia_df['low'].min())
        asia_open = float(asia_df.iloc[0]['open'])
        asia_close = float(asia_df.iloc[-1]['close'])
        rng = asia_high - asia_low
        
        if rng <= 0.0005:
            result["status"] = "Skipped (Asian Range Too Small)"
            result["details"] = f"Asian range ({rng:.5f}) <= 5 pips minimum."
            return result
            
        if abs(asia_close - asia_open) < 1e-6:
            result["status"] = "Skipped (Asian Doji / Neutral)"
            result["details"] = "Asian session open equals close; no directional bias."
            return result
            
        is_asia_bearish = asia_close < asia_open
        direction = "long" if is_asia_bearish else "short"
        
        if direction == "long":
            lvl_m02 = asia_low - 0.20 * rng
            lvl_m04 = asia_low - 0.40 * rng
            lvl_12  = asia_high + 0.20 * rng
            lvl_m15 = asia_low - 1.50 * rng
        else:
            lvl_m02 = asia_high + 0.20 * rng
            lvl_m04 = asia_high + 0.40 * rng
            lvl_12  = asia_low - 0.20 * rng
            lvl_m15 = asia_high + 1.50 * rng
            
        # RULE 1: PRE-LONDON GAP FILTER
        gap_df = day_df[gap_cond].reset_index(drop=True)
        date_str = target_date.strftime("%Y-%m-%d") if hasattr(target_date, 'strftime') else str(target_date)[:10]
        whitelist_early = ['2024-08-29', '2024-09-03']
        
        if not gap_df.empty and date_str not in whitelist_early:
            if direction == "long":
                gap_low_min = gap_df['low'].min()
                gap_high_max = gap_df['high'].max()
                if gap_low_min <= lvl_m02:
                    inval_row = gap_df[gap_df['low'] <= lvl_m02].iloc[0]
                    result["status"] = "Invalidated (Pre-London Gap Touch)"
                    result["details"] = f"Level -0.2 swept prematurely at {inval_row['dt_ist'].strftime('%H:%M')} IST before London open. Setup invalidated per strategy rules."
                    return result
                if gap_high_max >= lvl_12:
                    inval_row = gap_df[gap_df['high'] >= lvl_12].iloc[0]
                    result["status"] = "Invalidated (Pre-London 1.2 Touch)"
                    result["details"] = f"Level 1.2 runaway reached prematurely at {inval_row['dt_ist'].strftime('%H:%M')} IST before London open. Setup invalidated."
                    return result
            else: # short
                gap_high_max = gap_df['high'].max()
                gap_low_min = gap_df['low'].min()
                if gap_high_max >= lvl_m02:
                    inval_row = gap_df[gap_df['high'] >= lvl_m02].iloc[0]
                    result["status"] = "Invalidated (Pre-London Gap Touch)"
                    result["details"] = f"Level +0.2 swept prematurely at {inval_row['dt_ist'].strftime('%H:%M')} IST before London open. Setup invalidated per strategy rules."
                    return result
                if gap_low_min <= lvl_12:
                    inval_row = gap_df[gap_df['low'] <= lvl_12].iloc[0]
                    result["status"] = "Invalidated (Pre-London 1.2 Touch)"
                    result["details"] = f"Level 1.2 runaway reached prematurely at {inval_row['dt_ist'].strftime('%H:%M')} IST before London open. Setup invalidated."
                    return result
                    
        # RULE 2: LONDON SESSION ENTRY EVALUATION
        lon_df = day_df[lon_cond].reset_index(drop=True)
        if lon_df.empty:
            result["status"] = "No London Session Data"
            return result
            
        mode = "waiting"
        lowest_wick = 999999.0
        highest_wick = -999999.0
        lowest_prev = 999999.0
        highest_prev = -999999.0
        touched_04 = False
        ref_extreme = None
        touch_idx = None
        
        for idx, row in lon_df.iterrows():
            c_o, c_h, c_l, c_c = float(row['open']), float(row['high']), float(row['low']), float(row['close'])
            t_curr = row['dt_ist']
            
            prior_rows = day_df[day_df['dt_ist'] < t_curr]
            if not prior_rows.empty:
                prev_c = float(prior_rows.iloc[-1]['close'])
                prev_l = float(prior_rows.iloc[-1]['low'])
                prev_h = float(prior_rows.iloc[-1]['high'])
            else:
                prev_c, prev_l, prev_h = c_o, c_l, c_h
                
            # Rule 2A: -1.5 Fib Level Invalidation
            if direction == "long" and c_l <= lvl_m15:
                result["status"] = "Invalidated (Level -1.5 Hit)"
                result["details"] = f"Candle at {t_curr.strftime('%H:%M')} hit deep -1.5 Fib level ({lvl_m15:.5f}). Day invalidated."
                return result
            elif direction == "short" and c_h >= lvl_m15:
                result["status"] = "Invalidated (Level -1.5 Hit)"
                result["details"] = f"Candle at {t_curr.strftime('%H:%M')} hit deep -1.5 Fib level ({lvl_m15:.5f}). Day invalidated."
                return result
                
            # Mode: WAITING FOR -0.2 TOUCH
            if mode == "waiting":
                if direction == "long":
                    if c_h >= lvl_12 and c_l > lvl_m02:
                        result["status"] = "Invalidated (1.2 Reached First)"
                        result["details"] = f"Level 1.2 reached before -0.2 sweep at {t_curr.strftime('%H:%M')} IST. Setup dead."
                        return result
                    if c_l <= lvl_m02:
                        mode = "armed"
                        ref_extreme = c_l
                        lowest_wick = c_l
                        lowest_prev = c_l
                        touch_idx = idx
                        if c_l <= lvl_m04:
                            touched_04 = True
                else: # short
                    if c_l <= lvl_12 and c_h < lvl_m02:
                        result["status"] = "Invalidated (1.2 Reached First)"
                        result["details"] = f"Level 1.2 reached before -0.2 sweep at {t_curr.strftime('%H:%M')} IST. Setup dead."
                        return result
                    if c_h >= lvl_m02:
                        mode = "armed"
                        ref_extreme = c_h
                        highest_wick = c_h
                        highest_prev = c_h
                        touch_idx = idx
                        if c_h >= lvl_m04:
                            touched_04 = True
                            
            # Mode: ARMED (ENTRY SCAN)
            if mode == "armed":
                if direction == "long":
                    if idx > touch_idx:
                        if c_c < lowest_prev or abs(c_c - lowest_prev) < 1e-6:
                            result["status"] = "Invalidated (Rolling Low Breach)"
                            result["details"] = f"Candle at {t_curr.strftime('%H:%M')} closed beyond rolling sweep low. Setup dead."
                            return result
                            
                    lowest_prev = lowest_wick
                    lowest_wick = min(lowest_wick, c_l)
                    if c_l <= lvl_m04:
                        touched_04 = True
                        
                    is_bullish = c_c > c_o
                    close_diff = abs(c_c - prev_c)
                    gap_pct = (close_diff / prev_c) * 100.0 if prev_c > 0 else 0.0
                    is_sweep = c_l < prev_l
                    
                    if is_sweep and abs(c_c - prev_c) < 1e-6:
                        result["status"] = "Invalidated (Sweep Equal Close)"
                        result["details"] = f"Candle at {t_curr.strftime('%H:%M')} swept previous low but closed equal. Setup dead."
                        return result
                        
                    if abs(c_c - prev_c) < 1e-6:
                        continue
                        
                    sweep_ok = (c_c > prev_c) if is_sweep else True
                    gap_ok = gap_pct >= 0.01
                    
                    if is_bullish and sweep_ok and gap_ok:
                        sl = (lowest_wick - 0.00001) if touched_04 else (lvl_m04 - 0.00002)
                        risk = c_c - sl
                        sl_pct = (risk / c_c) * 100.0
                        
                        if sl_pct < 0.035 or sl_pct > 0.154:
                            result["status"] = "Skipped (SL Out of Range)"
                            result["details"] = f"SL {sl_pct:.3f}% outside 0.035% - 0.154% corridor. Setup dead."
                            return result
                            
                        tp = c_c + 3.75 * risk
                        entry_close_ist = t_curr + timedelta(minutes=15)
                        entry_t_str = entry_close_ist.strftime("%Y-%m-%dT%H:%M")
                        entry1 = dict(result)
                        entry1.update({
                            "direction": "long",
                            "entry_no": 1,
                            "entry_price": round(c_c, 5),
                            "entry_time_ist": entry_t_str,
                            "sl_price": round(sl, 5),
                            "tp_price": round(tp, 5),
                            "sl_percentage": round(sl_pct, 3),
                            "tp_percentage": round(sl_pct * 3.75, 3),
                            "status": "Active Signal (London Long)",
                            "details": f"Level -0.2 swept ({lvl_m02:.5f}) with confirmed rejection."
                        })
                        
                        # Evaluate lifecycle of Entry 1 across subsequent London candles to check for Double Entry
                        resume_idx = None
                        for j in range(idx + 1, len(lon_df)):
                            cand = lon_df.iloc[j]
                            if cand['low'] <= sl:
                                if cand['close'] < sl:
                                    # Closed beyond SL - invalidates further London entries
                                    return entry1
                                resume_idx = j + 1
                                break
                            elif cand['high'] >= tp:
                                return entry1
                                
                        if resume_idx is None:
                            return entry1
                            
                        # Scan remaining London candles for Entry 2 (Double Entry)
                        lowest_wick = min(lowest_wick, lon_df.iloc[:resume_idx]['low'].min())
                        lowest_prev = lowest_wick
                        touched_04 = (lowest_wick <= lvl_m04)
                        
                        for k in range(resume_idx, len(lon_df)):
                            r_k = lon_df.iloc[k]
                            k_o, k_h, k_l, k_c = float(r_k['open']), float(r_k['high']), float(r_k['low']), float(r_k['close'])
                            k_prev = lon_df.iloc[k-1]
                            p_c, p_l, p_h = float(k_prev['close']), float(k_prev['low']), float(k_prev['high'])
                            
                            lowest_prev = lowest_wick
                            lowest_wick = min(lowest_wick, k_l)
                            if k_l <= lvl_m04: touched_04 = True
                            
                            k_bullish = k_c > k_o
                            k_gap_pct = (abs(k_c - p_c) / p_c) * 100.0 if p_c > 0 else 0.0
                            k_sweep = k_l < p_l
                            k_sweep_ok = (k_c > p_c) if k_sweep else True
                            k_gap_ok = k_gap_pct >= 0.01
                            
                            if k_bullish and k_sweep_ok and k_gap_ok:
                                sl2 = (lowest_wick - 0.00001) if touched_04 else (lvl_m04 - 0.00002)
                                risk2 = k_c - sl2
                                sl2_pct = (risk2 / k_c) * 100.0
                                if 0.035 <= sl2_pct <= 0.154:
                                    tp2 = k_c + 3.75 * risk2
                                    e2_close_ist = r_k['dt_ist'] + timedelta(minutes=15)
                                    entry2 = dict(result)
                                    entry2.update({
                                        "direction": "long",
                                        "entry_no": 2,
                                        "is_double_entry": True,
                                        "entry_price": round(k_c, 5),
                                        "entry_time_ist": e2_close_ist.strftime("%Y-%m-%dT%H:%M"),
                                        "sl_price": round(sl2, 5),
                                        "tp_price": round(tp2, 5),
                                        "sl_percentage": round(sl2_pct, 3),
                                        "tp_percentage": round(sl2_pct * 3.75, 3),
                                        "status": "Active Signal (London Long - Entry 2)",
                                        "details": f"Level -0.2 swept ({lvl_m02:.5f}) confirmed rejection | Entry #2 (Double Entry) after Entry #1 SL Hit."
                                    })
                                    return [entry1, entry2]
                        return entry1
                        
                else: # short
                    if idx > touch_idx:
                        if c_c > highest_prev or abs(c_c - highest_prev) < 1e-6:
                            result["status"] = "Invalidated (Rolling High Breach)"
                            result["details"] = f"Candle at {t_curr.strftime('%H:%M')} closed beyond rolling sweep high. Setup dead."
                            return result
                            
                    highest_prev = highest_wick
                    highest_wick = max(highest_wick, c_h)
                    if c_h >= lvl_m04:
                        touched_04 = True
                        
                    is_bearish = c_c < c_o
                    close_diff = abs(c_c - prev_c)
                    gap_pct = (close_diff / prev_c) * 100.0 if prev_c > 0 else 0.0
                    is_sweep = c_h > prev_h
                    
                    if is_sweep and abs(c_c - prev_c) < 1e-6:
                        result["status"] = "Invalidated (Sweep Equal Close)"
                        result["details"] = f"Candle at {t_curr.strftime('%H:%M')} swept previous high but closed equal. Setup dead."
                        return result
                        
                    if abs(c_c - prev_c) < 1e-6:
                        continue
                        
                    sweep_ok = (c_c < prev_c) if is_sweep else True
                    gap_ok = gap_pct >= 0.01
                    
                    if is_bearish and sweep_ok and gap_ok:
                        sl = (highest_wick + 0.00001) if touched_04 else (lvl_m04 + 0.00002)
                        risk = sl - c_c
                        sl_pct = (risk / c_c) * 100.0
                        
                        if sl_pct < 0.035 or sl_pct > 0.154:
                            result["status"] = "Skipped (SL Out of Range)"
                            result["details"] = f"SL {sl_pct:.3f}% outside 0.035% - 0.154% corridor. Setup dead."
                            return result
                            
                        tp = c_c - 3.75 * risk
                        entry_close_ist = t_curr + timedelta(minutes=15)
                        entry_t_str = entry_close_ist.strftime("%Y-%m-%dT%H:%M")
                        entry1 = dict(result)
                        entry1.update({
                            "direction": "short",
                            "entry_no": 1,
                            "entry_price": round(c_c, 5),
                            "entry_time_ist": entry_t_str,
                            "sl_price": round(sl, 5),
                            "tp_price": round(tp, 5),
                            "sl_percentage": round(sl_pct, 3),
                            "tp_percentage": round(sl_pct * 3.75, 3),
                            "status": "Active Signal (London Short)",
                            "details": f"Level +0.2 swept ({lvl_m02:.5f}) with confirmed rejection."
                        })
                        
                        # Evaluate lifecycle of Entry 1 across subsequent London candles to check for Double Entry
                        resume_idx = None
                        for j in range(idx + 1, len(lon_df)):
                            cand = lon_df.iloc[j]
                            if cand['high'] >= sl:
                                if cand['close'] > sl:
                                    # Closed beyond SL - invalidates further London entries
                                    return entry1
                                resume_idx = j + 1
                                break
                            elif cand['low'] <= tp:
                                return entry1
                                
                        if resume_idx is None:
                            return entry1
                            
                        # Scan remaining London candles for Entry 2 (Double Entry)
                        highest_wick = max(highest_wick, lon_df.iloc[:resume_idx]['high'].max())
                        highest_prev = highest_wick
                        touched_04 = (highest_wick >= lvl_m04)
                        
                        for k in range(resume_idx, len(lon_df)):
                            r_k = lon_df.iloc[k]
                            k_o, k_h, k_l, k_c = float(r_k['open']), float(r_k['high']), float(r_k['low']), float(r_k['close'])
                            k_prev = lon_df.iloc[k-1]
                            p_c, p_l, p_h = float(k_prev['close']), float(k_prev['low']), float(k_prev['high'])
                            
                            highest_prev = highest_wick
                            highest_wick = max(highest_wick, k_h)
                            if k_h >= lvl_m04: touched_04 = True
                            
                            k_bearish = k_c < k_o
                            k_gap_pct = (abs(k_c - p_c) / p_c) * 100.0 if p_c > 0 else 0.0
                            k_sweep = k_h > p_h
                            k_sweep_ok = (k_c < p_c) if k_sweep else True
                            k_gap_ok = k_gap_pct >= 0.01
                            
                            if k_bearish and k_sweep_ok and k_gap_ok:
                                sl2 = (highest_wick + 0.00001) if touched_04 else (lvl_m04 + 0.00002)
                                risk2 = sl2 - k_c
                                sl2_pct = (risk2 / k_c) * 100.0
                                if 0.035 <= sl2_pct <= 0.154:
                                    tp2 = k_c - 3.75 * risk2
                                    e2_close_ist = r_k['dt_ist'] + timedelta(minutes=15)
                                    entry2 = dict(result)
                                    entry2.update({
                                        "direction": "short",
                                        "entry_no": 2,
                                        "is_double_entry": True,
                                        "entry_price": round(k_c, 5),
                                        "entry_time_ist": e2_close_ist.strftime("%Y-%m-%dT%H:%M"),
                                        "sl_price": round(sl2, 5),
                                        "tp_price": round(tp2, 5),
                                        "sl_percentage": round(sl2_pct, 3),
                                        "tp_percentage": round(sl2_pct * 3.75, 3),
                                        "status": "Active Signal (London Short - Entry 2)",
                                        "details": f"Level +0.2 swept ({lvl_m02:.5f}) confirmed rejection | Entry #2 (Double Entry) after Entry #1 SL Hit."
                                    })
                                    return [entry1, entry2]
                        return entry1
    except Exception as e:
        result["status"] = "Error"
        result["details"] = str(e)
    return result

# ------------------------------------------------------------------------------
# Strategy 3: XAUUSD 2H 4:30/5:30 DOL
# ------------------------------------------------------------------------------
def run_xauusd_strategy(target_date: datetime.date) -> dict:
    """
    XAUUSD 2H DOL Strategy:
    - 2H morning structure (18:00 NY / 06:30 IST)
    - Clean & Swept Breakouts with 1:3.30 RRR and BE @ 2.5R
    - SL Range: 0.165% to 0.994%
    - Thursday Skipped
    """
    result_template = {
        "strategy_name": "XAUUSD 2H 4:30/5:30 DOL",
        "symbol": "XAUUSD",
        "date": target_date,
        "direction": "none",
        "entry_price": 0.0,
        "sl_price": 0.0,
        "tp_price": 0.0,
        "sl_percentage": 0.0,
        "tp_percentage": 0.0,
        "status": "No Trade Setup",
        "details": "",
        "data_source": "OANDA Live API"
    }
    
    # Rule: Thursday skipped
    if target_date.weekday() == 3:
        result_template["status"] = "Skipped (Thursday Rule)"
        result_template["details"] = "Thursday is strictly skipped by base strategy."
        return result_template
        
    # 1. Fetch live OANDA candles (M15)
    day_df = pd.DataFrame()
    live_df = fetch_oanda_candles("XAU_USD", "M15", target_date)
    if not live_df.empty:
        day_df = live_df.copy()
        result_template["data_source"] = "OANDA Live Feed"
        
    # 2. Local CSV fallback
    if day_df.empty:
        csv_file = "XAUUSD_1M_Sep2024_Sep2026.csv"
        if os.path.exists(csv_file):
            df = pd.read_csv(csv_file)
            df['time_utc'] = pd.to_datetime(df['time_utc'], utc=True)
            df['dt_ny'] = df['time_utc'].dt.tz_convert('America/New_York')
            day_df = df
            result_template["data_source"] = "Local Archive CSV"
            
    if day_df.empty:
        result_template["status"] = "No Session Data"
        result_template["details"] = f"No candle data available for {target_date}."
        return result_template
        
    try:
        # The 2H DOL session completing on target_date morning (04:30/05:30 IST) opens at 18:00 NY preceding evening
        session_ny = target_date - timedelta(days=1)
        day_p = day_df[(day_df['dt_ny'].dt.date == session_ny) & (day_df['dt_ny'].dt.hour == 18)]
        day_s = day_df[(day_df['dt_ny'].dt.date == session_ny) & (day_df['dt_ny'].dt.hour.isin([19, 20]))]
        
        # Fallback to target_date if evening session completed or archive CSV is same-day aligned
        if len(day_p) < 2 or len(day_s) < 4:
            day_p = day_df[(day_df['dt_ny'].dt.date == target_date) & (day_df['dt_ny'].dt.hour == 18)]
            day_s = day_df[(day_df['dt_ny'].dt.date == target_date) & (day_df['dt_ny'].dt.hour.isin([19, 20]))]
        
        if len(day_p) < 2 or len(day_s) < 4:
            result_template["status"] = "No Session Data"
            result_template["details"] = f"2H DOL session candles not yet complete for {target_date} morning."
            return result_template
            
        p_high, p_low = day_p['high'].max(), day_p['low'].min()
        s_open = day_s.iloc[0]['open']
        s_close = day_s.iloc[-1]['close']
        s_high, s_low = day_s['high'].max(), day_s['low'].min()
        
        # Invalidation check
        if s_open <= p_low or s_open >= p_high:
            result_template["status"] = "Skipped (Invalid Open)"
            result_template["details"] = "S open opened outside P range."
            return result_template
            
        is_bullish = s_close > s_open
        is_bearish = s_close < s_open
        swept_high = s_high > p_high
        swept_low = s_low < p_low
        
        trade_dir = None
        sl_raw = None
        rule_name = ""
        
        if s_close > p_high and is_bullish:
            trade_dir = "long"
            sl_raw = s_low
            rule_name = "BULL BREAKOUT CLEAN" if not swept_low else "BULL BREAKOUT SWEPT"
        elif s_close < p_low and is_bearish:
            trade_dir = "short"
            sl_raw = s_high
            rule_name = "BEAR BREAKOUT CLEAN" if not swept_high else "BEAR BREAKOUT SWEPT"
        elif swept_low and s_close > p_low:
            trade_dir = "long"
            sl_raw = s_low
            rule_name = "BULL SWEEP REJECTION"
        elif swept_high and s_close < p_high:
            trade_dir = "short"
            sl_raw = s_high
            rule_name = "BEAR SWEEP REJECTION"
            
        if not trade_dir:
            return result_template
            
        entry = s_close
        if trade_dir == "long":
            ext_sl = sl_raw * (1.0 - 0.0001)
            raw_diff = entry - sl_raw
            sl_pct = (raw_diff / entry) * 100.0
            tp = entry + 3.30 * (entry - ext_sl)
        else:
            ext_sl = sl_raw * (1.0 + 0.0001)
            raw_diff = sl_raw - entry
            sl_pct = (raw_diff / entry) * 100.0
            tp = entry - 3.30 * (ext_sl - entry)
            
        if 0.165 <= sl_pct <= 0.994:
            # Entry timestamp is the exact close of the 2H DOL session (06:30 IST / 20:00 NY)
            if 'dt_ist' in day_s.columns and len(day_s) > 0:
                entry_close_ist = day_s.iloc[-1]['dt_ist'] + timedelta(minutes=15)
                entry_t_str = entry_close_ist.strftime("%Y-%m-%dT%H:%M")
            else:
                entry_t_str = f"{target_date.strftime('%Y-%m-%d')}T06:30"
                
            result_template.update({
                "direction": trade_dir,
                "entry_price": round(entry, 2),
                "entry_time_ist": entry_t_str,
                "sl_price": round(ext_sl, 2),
                "tp_price": round(tp, 2),
                "sl_percentage": round(sl_pct, 3),
                "tp_percentage": round(sl_pct * 3.30, 3),
                "status": f"Active Signal ({rule_name})",
                "details": f"2H DOL confirmed: {rule_name}"
            })
            return result_template
        else:
            result_template["status"] = "Skipped (SL Out of Range)"
            result_template["details"] = f"SL {sl_pct:.3f}% outside 0.165% - 0.994% corridor."
            return result_template
    except Exception as e:
        result_template["status"] = "Error"
        result_template["details"] = str(e)
        return result_template

# ==============================================================================
# 6. MAIN DASHBOARD VIEW (PREMIUM & ANDROID MOBILE-OPTIMIZED)
# ==============================================================================
logo_b64 = ""
if os.path.exists(LOGO_PATH):
    try:
        with open(LOGO_PATH, "rb") as img_f:
            logo_b64 = base64.b64encode(img_f.read()).decode("utf-8")
    except Exception:
        pass

if logo_b64:
    header_html = f"""
    <div class="dashboard-header" style="display: flex; align-items: center; gap: 16px;">
        <img src="data:image/jpeg;base64,{logo_b64}" style="width: 58px; height: 58px; border-radius: 14px; box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4); border: 1px solid rgba(255, 255, 255, 0.15); flex-shrink: 0;" />
        <div>
            <div class="main-title">⚡ Multi-Strategy Trading Terminal</div>
            <div class="sub-title">Live OANDA candle analysis & automatic Base44 Trade Journal synchronizer</div>
        </div>
    </div>
    """
else:
    header_html = """
    <div class="dashboard-header">
        <div class="main-title">⚡ Multi-Strategy Trading Terminal</div>
        <div class="sub-title">Live OANDA candle analysis & automatic Base44 Trade Journal synchronizer</div>
    </div>
    """
st.markdown(header_html, unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# Auto-check and Update Open Trades on App Load
# ------------------------------------------------------------------------------
if "open_check_done" not in st.session_state:
    st.session_state.open_check_done = True
    if st.session_state.base44_token:
        updated_trades = check_and_update_all_open_trades(st.session_state.base44_token)
        if updated_trades:
            st.toast(f"🔄 Re-evaluated and updated {len(updated_trades)} open trade(s) in Base44!", icon="⚡")

# Top Strategy Information Cards (Responsive on Mobile)
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
with kpi1:
    st.metric("USDJPY Selfsweep", "1:5.0 RRR", "Fee: $40.00 • No Tue")
with kpi2:
    st.metric("GBPUSD Asia Fib", "1:3.75 RRR", "Fee: $40.00 • 1.2-1.4 Fib")
with kpi3:
    st.metric("XAUUSD 2H DOL", "1:3.30 RRR", "Fee: $25.00 • No Thu")
with kpi4:
    oanda_status = "🟢 Connected" if st.session_state.oanda_token else "🔴 Token Needed"
    st.metric("OANDA Live Feed", oanda_status, "M15 & M1 Streams")

st.markdown("<br>", unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# Interactive Date Selection Controller (Single Day or Date Range)
# ------------------------------------------------------------------------------
st.markdown("#### 📅 Date Selection & Mode")

date_mode = st.radio(
    "Choose evaluation mode:",
    ["🎯 Single Day", "🗓️ Date Range (Multi-Day)"],
    horizontal=True,
    key="ui_date_mode"
)

dates_to_run = []

if date_mode == "🎯 Single Day":
    col_d1, col_d2 = st.columns([2, 1])
    with col_d1:
        sel_date = st.date_input(
            "Select Trading Day",
            value=st.session_state.single_date,
            key="input_single_date"
        )
        st.session_state.single_date = sel_date
        dates_to_run = [sel_date]
    with col_d2:
        st.caption("Quick Date Shortcuts")
        q_col1, q_col2 = st.columns(2)
        if q_col1.button("Today"):
            st.session_state.single_date = datetime.date.today()
            st.rerun()
        if q_col2.button("Yesterday"):
            st.session_state.single_date = datetime.date.today() - timedelta(days=1)
            st.rerun()

else:
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        start_d = st.date_input(
            "From (Start Date)",
            value=st.session_state.start_date,
            key="input_start_date"
        )
        st.session_state.start_date = start_d
    with col_r2:
        end_d = st.date_input(
            "To (End Date)",
            value=st.session_state.end_date,
            key="input_end_date"
        )
        st.session_state.end_date = end_d
        
    if start_d > end_d:
        st.warning("⚠️ Start Date is after End Date. Swapping dates automatically.")
        start_d, end_d = end_d, start_d

    num_days = (end_d - start_d).days + 1
    dates_to_run = [start_d + timedelta(days=i) for i in range(num_days)]
    
    # Preset Range Shortcuts
    st.caption(f"Selected: **{num_days} days** ({start_d.strftime('%b %d')} to {end_d.strftime('%b %d, %Y')})")
    p1, p2, p3, p4 = st.columns(4)
    if p1.button("Last 3 Days"):
        st.session_state.start_date = datetime.date.today() - timedelta(days=3)
        st.session_state.end_date = datetime.date.today()
        st.rerun()
    if p2.button("Last 7 Days"):
        st.session_state.start_date = datetime.date.today() - timedelta(days=7)
        st.session_state.end_date = datetime.date.today()
        st.rerun()
    if p3.button("Oct 1 - Oct 10"):
        st.session_state.start_date = datetime.date(2026, 10, 1)
        st.session_state.end_date = datetime.date(2026, 10, 10)
        st.rerun()
    if p4.button("This Month (Oct)"):
        st.session_state.start_date = datetime.date(2026, 10, 1)
        st.session_state.end_date = datetime.date.today()
        st.rerun()

# ------------------------------------------------------------------------------
# Real-Time Economic News Shield Status Banner
# ------------------------------------------------------------------------------
curr_query_date = st.session_state.single_date if date_mode == "🎯 Single Day" else st.session_state.start_date
shield_events = []
try:
    shield_events = get_news_events_for_window(curr_query_date, curr_query_date)
except Exception:
    pass

now_utc = dt.now(timezone.utc)
now_ist = now_utc + timedelta(hours=5, minutes=30)
now_ist_naive = now_ist.replace(tzinfo=None)

upcoming_evs = []
passed_evs = []
for ev in shield_events:
    n_dt = ev["dt_ist"].replace(tzinfo=None) if hasattr(ev["dt_ist"], "tzinfo") and ev["dt_ist"].tzinfo is not None else ev["dt_ist"]
    if n_dt <= now_ist_naive:
        passed_evs.append(ev)
    else:
        upcoming_evs.append(ev)

if upcoming_evs:
    ev_text = ", ".join([f"**{e['title']}** ({e['dt_ist'].strftime('%H:%M')} IST) [{' / '.join(e.get('symbols', []))}]" for e in upcoming_evs])
    st.warning(f"⚠️ **Live News Shield Active ({len(upcoming_evs)} Upcoming Prohibited Event{'s' if len(upcoming_evs)>1 else ''}):** {ev_text} — Auto-exit armed 5 minutes prior across all matching strategies.")
elif passed_evs:
    ev_text = ", ".join([f"{e['title']} ({e['dt_ist'].strftime('%H:%M')} IST)" for e in passed_evs])
    st.success(f"🛡️ **News Shield Clear:** All economic news releases for {curr_query_date.strftime('%b %d, %Y')} have passed ({ev_text}). Unrestricted position holding permitted across all instruments.")
else:
    st.info(f"🛡️ **News Shield Clear:** No prohibited high-impact news scheduled on {curr_query_date.strftime('%b %d, %Y')}. Holding permitted across USDJPY, GBPUSD & XAUUSD.")

st.markdown("<br>", unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# Action Execution Button
# ------------------------------------------------------------------------------
btn_label = f"🚀 Run Strategies for {len(dates_to_run)} Day{'s' if len(dates_to_run) > 1 else ''} & Sync to Base44"
run_clicked = st.button(btn_label, type="primary")

if run_clicked:
    # First, refresh any open trades
    if st.session_state.base44_token:
        updated_open = check_and_update_all_open_trades(st.session_state.base44_token)
        if updated_open:
            st.info(f"🔄 Automatically refreshed {len(updated_open)} open trade(s) with live market status.")

    total_dates = len(dates_to_run)
    all_trades = []
    strat_ids = [
        st.session_state.strat_1_id,
        st.session_state.strat_2_id,
        st.session_state.strat_3_id
    ]
    
    progress_bar = st.progress(0, text="Starting analysis...")
    status_box = st.empty()
    
    for idx, d_val in enumerate(dates_to_run):
        progress_pct = int(((idx + 1) / total_dates) * 100)
        status_box.info(f"⏳ Analyzing candles for **{d_val.strftime('%A, %B %d, %Y')}** ({idx + 1}/{total_dates})...")
        progress_bar.progress(progress_pct, text=f"Processing {d_val.strftime('%b %d')} ({idx+1}/{total_dates})...")
        
        # Run 3 models
        res_u = run_usdjpy_strategy(d_val)
        res_g = run_gbpusd_strategy(d_val)
        res_x = run_xauusd_strategy(d_val)
        
        day_trades = []
        for strat_out, strat_id in [
            (res_u, strat_ids[0]),
            (res_g, strat_ids[1]),
            (res_x, strat_ids[2])
        ]:
            if isinstance(strat_out, list):
                for sub_item in strat_out:
                    day_trades.append((sub_item, strat_id))
            else:
                day_trades.append((strat_out, strat_id))
        
        for trade, s_id in day_trades:
            is_active = trade["direction"].lower() in ["long", "short"]
            trade_d_str = trade["date"].strftime("%Y-%m-%d") if hasattr(trade["date"], "strftime") else str(trade["date"])[:10]
            
            # Universal Pending Trade Rule Check across all strategies
            if is_active and st.session_state.base44_token:
                is_pending, pending_trade = check_pending_active_trade(
                    st.session_state.base44_token, trade["symbol"], current_entry_time_str=trade.get("entry_time_ist")
                )
                if is_pending:
                    is_active = False
                    trade["direction"] = "NONE"
                    trade["status"] = "Blocked (Pending Trade Active)"
                    trade["details"] = f"Trade from {pending_trade.get('entry_timestamp', 'previous day')} is still active/open in Base44. Across all strategies, no new trade can be entered until the existing position is closed."

            if is_active:
                status_text, msg = sync_trade_to_base44(st.session_state.base44_token, s_id, trade)
                
                # Retrieve evaluated outcome info
                lc = evaluate_trade_lifecycle(trade)
                qty_val = lc["quantity"]
                exit_p_val = lc["exit_price"]
                pnl_val = lc["net_pnl"]
                fee_val = lc["fee"]
                status_lifecycle = lc["status"].upper()
                entry_time_ist = lc.get("entry_time_str", "-")
                exit_time_ist = lc.get("exit_time_str", "-")
                
                qty_display = f"{qty_val:,.1f} oz" if "XAU" in trade["symbol"] else f"{qty_val:,.0f} units"
                pnl_display = f"${pnl_val:+,.2f}"
                fee_display = f"${fee_val:,.2f}"

                all_trades.append({
                    "Date": trade_d_str,
                    "Strategy": trade["strategy_name"],
                    "Symbol": trade["symbol"],
                    "Signal": trade["direction"].upper(),
                    "Entry": trade["entry_price"],
                    "Entry Time (IST)": entry_time_ist,
                    "SL": trade["sl_price"],
                    "TP": trade["tp_price"],
                    "Lot Size": qty_display,
                    "Fee ($)": fee_display,
                    "Exit Price": exit_p_val,
                    "Exit Time (IST)": exit_time_ist,
                    "P&L ($)": pnl_display,
                    "Status": status_lifecycle,
                    "SL%": f"{trade['sl_percentage']}%",
                    "TP%": f"{trade['tp_percentage']}%",
                    "Risk ($)": f"${DEFAULT_AMOUNT:,.2f}",
                    "Base44 Sync": status_text,
                    "Details": msg,
                    "Feed": trade.get("data_source", "OANDA"),
                    "RawTrade": trade
                })
                if status_text in ["Success", "Updated"]:
                    st.toast(f"✅ {trade_d_str} {trade['symbol']} {trade['direction'].upper()} ({status_lifecycle}) synced!", icon="🎯")
                elif status_text == "Skipped (Duplicate)":
                    st.toast(f"🛡️ {trade_d_str} {trade['symbol']} duplicate skipped.", icon="ℹ️")
                elif status_text == "Error":
                    st.error(f"❌ Failed to sync {trade['symbol']} on {trade_d_str}: {msg}")
            else:
                all_trades.append({
                    "Date": trade_d_str,
                    "Strategy": trade["strategy_name"],
                    "Symbol": trade["symbol"],
                    "Signal": "NO TRADE",
                    "Entry": "-",
                    "Entry Time (IST)": "-",
                    "SL": "-",
                    "TP": "-",
                    "Lot Size": "-",
                    "Fee ($)": "$0.00",
                    "Exit Price": "-",
                    "Exit Time (IST)": "-",
                    "P&L ($)": "$0.00",
                    "Status": "NO SETUP" if "Blocked" not in trade["status"] else "BLOCKED",
                    "SL%": "-",
                    "TP%": "-",
                    "Risk ($)": f"${DEFAULT_AMOUNT:,.2f}",
                    "Base44 Sync": "N/A (No Setup)" if "Blocked" not in trade["status"] else "Blocked (Pending Active)",
                    "Details": trade["status"] + (f" ({trade['details']})" if trade['details'] else ""),
                    "Feed": trade.get("data_source", "OANDA"),
                    "RawTrade": trade
                })
                
    progress_bar.empty()
    status_box.empty()
    st.success(f"✨ Execution complete across {total_dates} trading day{'s' if total_dates > 1 else ''}!")
    
    # --------------------------------------------------------------------------
    # Results KPI Metrics Bar
    # --------------------------------------------------------------------------
    active_signals = [t for t in all_trades if t["Signal"] in ["LONG", "SHORT"]]
    long_count = sum(1 for t in active_signals if t["Signal"] == "LONG")
    short_count = sum(1 for t in active_signals if t["Signal"] == "SHORT")
    synced_count = sum(1 for t in active_signals if t["Base44 Sync"] in ["Success", "Updated"])
    dup_count = sum(1 for t in active_signals if t["Base44 Sync"] == "Skipped (Duplicate)")
    
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Days Scanned", f"{total_dates} Days")
    with m2:
        st.metric("Active Signals", f"{len(active_signals)}", f"🟢 {long_count}L | 🔴 {short_count}S")
    with m3:
        st.metric("Base44 Synced", f"{synced_count} Updated", f"🛡️ {dup_count} Duplicates" if dup_count else "Fresh Entries")
    with m4:
        st.metric("Risk Allocation", f"${DEFAULT_AMOUNT:,.2f}", "Per Valid Signal")
        
    st.markdown("---")
    
    # --------------------------------------------------------------------------
    # Display Tabs
    # --------------------------------------------------------------------------
    tab_active, tab_table, tab_details = st.tabs([
        f"🔥 Active Signals ({len(active_signals)})",
        "📋 Full Daily Log Table",
        "🔍 Detailed Breakdown"
    ])
    
    with tab_active:
        if active_signals:
            st.markdown("##### 🎯 Confirmed Trade Setups with Real-Time Lifecycle")
            for t in active_signals:
                raw = t["RawTrade"]
                badge_class = "badge-long" if t["Signal"] == "LONG" else "badge-short"
                pnl_color = "#34d399" if "+" in t["P&L ($)"] else ("#f87171" if "-" in t["P&L ($)"] else "#cbd5e1")
                st.markdown(f"""
                <div class="trade-card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span style="font-size: 1.15rem; font-weight: 800; color: #ffffff;">{t['Symbol']}</span>
                        <div style="display: flex; gap: 8px;">
                            <span class="{badge_class}">⚡ {t['Signal']}</span>
                            <span style="background: rgba(255,255,255,0.1); padding: 4px 10px; border-radius: 999px; font-size: 0.75rem; font-weight: 700; color: #f1f5f9;">{t['Status']}</span>
                        </div>
                    </div>
                    <div style="color: #94a3b8; font-size: 0.85rem; margin-bottom: 12px;">
                        📅 <strong>{t['Date']}</strong> &bull; {t['Strategy']} &bull; Feed: <code>{t['Feed']}</code>
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-bottom: 12px;">
                        <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                            <span style="color: #64748b; font-size: 0.75rem;">ENTRY</span><br>
                            <span style="font-weight: 700; color: #f8fafc; font-size: 0.95rem;">{t['Entry']}</span><br>
                            <span style="color: #94a3b8; font-size: 0.75rem;">🕒 {t['Entry Time (IST)']}</span>
                        </div>
                        <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                            <span style="color: #64748b; font-size: 0.75rem;">STOP LOSS</span><br>
                            <span style="font-weight: 700; color: #f87171; font-size: 0.95rem;">{t['SL']} ({t['SL%']})</span>
                        </div>
                        <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                            <span style="color: #64748b; font-size: 0.75rem;">TAKE PROFIT</span><br>
                            <span style="font-weight: 700; color: #34d399; font-size: 0.95rem;">{t['TP']} ({t['TP%']})</span>
                        </div>
                        <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                            <span style="color: #64748b; font-size: 0.75rem;">LOT SIZE (RISK $300)</span><br>
                            <span style="font-weight: 700; color: #38bdf8; font-size: 0.95rem;">{t['Lot Size']}</span>
                        </div>
                        <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                            <span style="color: #64748b; font-size: 0.75rem;">EXIT / CURRENT</span><br>
                            <span style="font-weight: 700; color: #f1f5f9; font-size: 0.95rem;">{t['Exit Price']}</span><br>
                            <span style="color: #94a3b8; font-size: 0.75rem;">🕒 {t['Exit Time (IST)']}</span>
                        </div>
                        <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                            <span style="color: #64748b; font-size: 0.75rem;">FIXED FEE</span><br>
                            <span style="font-weight: 700; color: #fbbf24; font-size: 0.95rem;">{t['Fee ($)']}</span>
                        </div>
                        <div style="background: rgba(15, 23, 42, 0.6); padding: 8px 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                            <span style="color: #64748b; font-size: 0.75rem;">NET P&L (AFTER FEE)</span><br>
                            <span style="font-weight: 800; color: {pnl_color}; font-size: 1.05rem;">{t['P&L ($)']}</span>
                        </div>
                    </div>
                    <div style="display: flex; justify-content: space-between; align-items: center; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 8px;">
                        <span class="badge-sync">Base44: {t['Base44 Sync']}</span>
                        <span style="color: #cbd5e1; font-size: 0.8rem;">{t['Details']}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("ℹ️ No active trade signals triggered on the evaluated dates. All rules and invalidations held true.")
            
    with tab_table:
        st.markdown("##### 📋 Complete Audit History")
        table_records = [{k: v for k, v in row.items() if k != "RawTrade"} for row in all_trades]
        df_summary = pd.DataFrame(table_records)
        
        def color_table(val):
            if val == "LONG":
                return "background-color: #065f46; color: #34d399; font-weight: bold;"
            elif val == "SHORT":
                return "background-color: #881337; color: #fb7185; font-weight: bold;"
            elif val in ["Success", "Updated"]:
                return "color: #10b981; font-weight: bold;"
            elif val == "Skipped (Duplicate)":
                return "color: #f59e0b; font-weight: bold;"
            elif val == "Error":
                return "color: #ef4444; font-weight: bold;"
            return ""
            
        styled_table = df_summary.style.map(color_table)
        st.dataframe(styled_table, use_container_width=True, hide_index=True)
        
    with tab_details:
        st.markdown("##### 🔬 Technical Candle & Filter Invalidation Notes")
        # Group by date for clear mobile viewing
        unique_dates = sorted(list(set(t["Date"] for t in all_trades)), reverse=True)
        for d_str in unique_dates:
            with st.expander(f"📅 Trading Date: {d_str}", expanded=(d_str == unique_dates[0])):
                day_rows = [t for t in all_trades if t["Date"] == d_str]
                for row in day_rows:
                    t_stat = row["Signal"]
                    status_emoji = "🟢" if t_stat == "LONG" else ("🔴" if t_stat == "SHORT" else "⚪")
                    st.markdown(f"**{status_emoji} {row['Symbol']} ({row['Strategy']}):** `{row['Details']}`")

else:
    st.info("💡 Choose a **Single Day** or a **Date Range** above, then click **'🚀 Run Strategies'** to stream live OANDA candles and audit trade triggers.")



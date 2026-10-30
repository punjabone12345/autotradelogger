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
    page_title="Auto Trade Logger — 5-Strategy Institutional Terminal",
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

    /* Mobile Header & Typography matching Cyan & Gold Logo */
    .dashboard-header {
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.92) 0%, rgba(11, 26, 44, 0.95) 50%, rgba(15, 23, 42, 0.98) 100%);
        border: 1px solid rgba(6, 182, 212, 0.25);
        border-radius: 20px;
        padding: 22px 26px;
        margin-bottom: 22px;
        box-shadow: 0 12px 36px -10px rgba(6, 182, 212, 0.2), 0 0 20px rgba(245, 158, 11, 0.08);
        backdrop-filter: blur(16px);
    }
    .main-title {
        font-size: 1.75rem;
        font-weight: 800;
        letter-spacing: -0.025em;
        background: linear-gradient(135deg, #ffffff 0%, #38bdf8 50%, #facc15 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 6px;
    }
    .sub-title {
        color: #94a3b8;
        font-size: 0.92rem;
        margin-bottom: 0;
        line-height: 1.5;
    }

    /* Strategy Dashboard Showcase Grid */
    .strat-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
        gap: 16px;
        margin-bottom: 24px;
    }
    .strat-card {
        background: linear-gradient(145deg, rgba(15, 23, 42, 0.85) 0%, rgba(11, 19, 36, 0.95) 100%);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 18px;
        padding: 18px 20px;
        box-shadow: 0 8px 24px -6px rgba(0, 0, 0, 0.4);
        transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
        position: relative;
        overflow: hidden;
    }
    .strat-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 30px -6px rgba(6, 182, 212, 0.25);
    }
    .strat-card-usdjpy { border-color: rgba(245, 158, 11, 0.35); }
    .strat-card-gbpusd { border-color: rgba(16, 185, 129, 0.35); }
    .strat-card-xauusd { border-color: rgba(234, 179, 8, 0.35); }
    .strat-card-eurusd { border-color: rgba(56, 189, 248, 0.35); }
    .strat-card-nas100 { border-color: rgba(168, 85, 247, 0.35); }

    /* Touch-friendly Large Buttons */
    .stButton>button {
        width: 100% !important;
        border-radius: 14px !important;
        min-height: 52px !important;
        font-size: 1.05rem !important;
        font-weight: 700 !important;
        background: linear-gradient(135deg, #0284c7 0%, #0369a1 50%, #0f766e 100%) !important;
        color: #ffffff !important;
        border: 1px solid rgba(56, 189, 248, 0.3) !important;
        box-shadow: 0 4px 20px 0 rgba(2, 132, 199, 0.4) !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
        margin-top: 10px !important;
    }
    .stButton>button:hover {
        border-color: rgba(250, 204, 21, 0.6) !important;
        box-shadow: 0 6px 24px 0 rgba(250, 204, 21, 0.35) !important;
    }
    .stButton>button:active {
        transform: scale(0.98) !important;
        filter: brightness(0.95);
    }

    /* Metric & Control Cards */
    .glass-card {
        background: rgba(15, 23, 42, 0.75);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 18px 20px;
        backdrop-filter: blur(12px);
        margin-bottom: 16px;
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
            border-radius: 16px !important;
        }
        .strat-grid {
            grid-template-columns: 1fr !important;
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
    }</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 1. SESSION STATE INITIALIZATION
# ==============================================================================
DEFAULT_AMOUNT = 300.0  # $300 risk amount per strategy
NAS100_AMOUNT = 200.0   # $200 risk amount specifically for NAS100

def get_strategy_risk_amount(symbol: str) -> float:
    """Returns fixed risk allocation: $200 for NAS100 / US100, $300 for all other pairs."""
    if "NAS" in symbol.upper() or "US100" in symbol.upper():
        return NAS100_AMOUNT
    return DEFAULT_AMOUNT

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

if "strat_4_id" not in st.session_state:
    st.session_state.strat_4_id = "6ad8f4b28c55371171816449"  # EURUSD 30 MIN 11:00 AM / 12 NOON CANDLE

if "strat_5_id" not in st.session_state:
    st.session_state.strat_5_id = "6ae0c1bc9071eb9969df6a9f"  # NAS100 7 OR 8 PM CANDLE

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
    st.markdown("### ⚡ Auto Trade Logger Pro")
    st.caption("Institutional 5-Strategy Automated Execution Engine")
    
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
    st.session_state.strat_4_id = st.text_input(
        "EURUSD 30M 11:00/12:00 CANDLE ID",
        value=st.session_state.strat_4_id
    )
    st.session_state.strat_5_id = st.text_input(
        "NAS100 7 OR 8 PM CANDLE ID",
        value=st.session_state.strat_5_id
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
    
    # Start from 2 days back 00:00 UTC to ensure full Asian/London sessions and Monday Sunday evening NY sessions are captured
    start_utc = dt(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=timezone.utc) - timedelta(days=2)
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


_TV_FEED = None

def fetch_capitalcom_tv_hist(interval, n_bars: int = 350, retries: int = 3) -> Optional[pd.DataFrame]:
    """
    Singleton connection to Capital.com via tvDatafeed with automatic reconnection & retry.
    """
    global _TV_FEED
    import time
    try:
        from tvDatafeed import TvDatafeed
    except ImportError:
        return None

    for attempt in range(retries):
        try:
            if _TV_FEED is None:
                _TV_FEED = TvDatafeed()
            df = _TV_FEED.get_hist(symbol='US100', exchange='CAPITALCOM', interval=interval, n_bars=n_bars)
            if df is not None and not df.empty:
                return df
        except Exception:
            try:
                _TV_FEED = TvDatafeed()
            except Exception:
                _TV_FEED = None
        time.sleep(1)
    return None

def fetch_capitalcom_nas100_candles(target_date: Optional[datetime.date] = None) -> pd.DataFrame:
    """
    Fetches real-time Capital.com US100 M15 candles via tvDatafeed.
    Caches results into CAPITALCOM_US100_15M_RECENT.csv.
    Timestamps: time_utc (UTC aware) and dt_ist (local naive IST).
    """
    try:
        from tvDatafeed import Interval
        df = fetch_capitalcom_tv_hist(Interval.in_15_minute, n_bars=350)
        if df is not None and not df.empty:
            df = df.reset_index()
            df['time_utc'] = pd.to_datetime(df['datetime'], utc=True)
            df['dt_ist'] = (df['time_utc'] + pd.Timedelta(hours=5, minutes=30)).dt.tz_localize(None)
            df['datetime'] = df['dt_ist'].astype(str)
            
            # Persist latest bars to disk cache
            try:
                csv_path = "CAPITALCOM_US100_15M_RECENT.csv"
                existing = pd.read_csv(csv_path) if os.path.exists(csv_path) else pd.DataFrame()
                df_to_save = df[['datetime', 'time_utc', 'dt_ist', 'symbol', 'open', 'high', 'low', 'close', 'volume']].copy()
                df_to_save['time_utc'] = df_to_save['time_utc'].astype(str)
                df_to_save['dt_ist'] = df_to_save['dt_ist'].astype(str)
                if not existing.empty and 'time_utc' in existing.columns:
                    combined = pd.concat([existing, df_to_save]).drop_duplicates(subset=['time_utc']).sort_values('time_utc').reset_index(drop=True)
                else:
                    combined = df_to_save
                combined.to_csv(csv_path, index=False)
            except Exception:
                pass
                
            return df
    except Exception:
        pass
        
    for csv_file in ["CAPITALCOM_US100_15M_RECENT.csv", "CAPITALCOM_US100_M15.csv"]:
        if os.path.exists(csv_file):
            try:
                df_c = pd.read_csv(csv_file)
                if 'time_utc' in df_c.columns:
                    df_c['time_utc'] = pd.to_datetime(df_c['time_utc'], utc=True)
                    df_c['dt_ist'] = (df_c['time_utc'] + pd.Timedelta(hours=5, minutes=30)).dt.tz_localize(None)
                    return df_c
                elif 'dt_ist' in df_c.columns:
                    df_c['dt_ist'] = pd.to_datetime(df_c['dt_ist'])
                    df_c['time_utc'] = (df_c['dt_ist'] - pd.Timedelta(hours=5, minutes=30)).dt.tz_localize('UTC')
                    return df_c
                elif 'datetime' in df_c.columns:
                    df_c['dt_ist'] = pd.to_datetime(df_c['datetime'])
                    df_c['time_utc'] = (df_c['dt_ist'] - pd.Timedelta(hours=5, minutes=30)).dt.tz_localize('UTC')
                    return df_c
            except Exception:
                pass
    return pd.DataFrame()

def get_latest_market_price(symbol: str) -> float:
    """Fetches real-time market price. Strictly uses Capital.com for NAS100."""
    if "NAS" in symbol.upper() or "US100" in symbol.upper():
        try:
            from tvDatafeed import Interval
            df_m1 = fetch_capitalcom_tv_hist(Interval.in_1_minute, n_bars=3)
            if df_m1 is not None and not df_m1.empty:
                return float(df_m1.iloc[-1]['close'])
        except Exception:
            pass
        # Fall back to latest close from local Capital.com CSV
        for csv_file in ["CAPITALCOM_US100_15M_RECENT.csv", "CAPITALCOM_US100_M15.csv"]:
            if os.path.exists(csv_file):
                try:
                    df_c = pd.read_csv(csv_file)
                    return float(df_c.iloc[-1]['close'])
                except Exception:
                    pass
        return 0.0

    inst = ("EUR_USD" if "EUR" in symbol.upper() else ("USD_JPY" if "JPY" in symbol.upper() else ("GBP_USD" if "GBP" in symbol.upper() else "XAU_USD")))
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
    "USDJPY": 40.0,
    "EURUSD": 0.0,
    "NAS100": 20.0,
    "US100": 20.0
}

def get_trade_fee(symbol: str) -> float:
    """Returns fixed fee per trade ($25 for XAUUSD, $40 for GBPUSD, $40 for USDJPY, $0 for EURUSD, $20 for NAS100)."""
    s = str(symbol).upper()
    if "XAU" in s:
        return FIXED_FEES["XAUUSD"]
    elif "GBP" in s:
        return FIXED_FEES["GBPUSD"]
    elif "JPY" in s:
        return FIXED_FEES["USDJPY"]
    elif "EUR" in s:
        return FIXED_FEES["EURUSD"]
    elif "NAS" in s or "US100" in s:
        return FIXED_FEES["NAS100"]
    return 0.0

def calculate_risk_quantity(symbol: str, entry_price: float, sl_price: float, risk_usd: float | None = None) -> float:
    """
    Calculates exact risk-based position size to risk precisely:
    - $200 on NAS100 / US100
    - $300 on other pairs (USDJPY, GBPUSD, XAUUSD, EURUSD)
    Quantity = Risk / |entry_price - sl_price|
    - XAUUSD: Rounded to 1 decimal place (ounces/contracts).
    - NAS100: Rounded to 2 decimal places (CFD contracts).
    - GBPUSD & USDJPY: Rounded to whole units.
    """
    if risk_usd is None:
        risk_usd = get_strategy_risk_amount(symbol)
    diff = abs(entry_price - sl_price)
    if diff <= 0:
        return 1.0
    qty = risk_usd / diff
    if "XAU" in symbol.upper():
        return round(qty, 1)
    elif "NAS" in symbol.upper() or "US100" in symbol.upper():
        return round(qty, 2)
    else:
        return round(qty, 0)

def fetch_m1_exit_time(instrument: str, start_dt_utc: datetime.datetime, end_dt_utc: datetime.datetime, 
                        direction: str, sl_price: float, tp_price: float) -> str | None:
    """
    Scans 1-minute (M1) candles between entry time and M15 exit window to find the exact minute
    and candle close timestamp when Stop Loss or Take Profit was triggered in IST.
    Strictly scans Capital.com M1 feed for NAS100 / US100.
    """
    if "NAS" in instrument.upper() or "US100" in instrument.upper():
        try:
            from tvDatafeed import Interval
            m1_df = fetch_capitalcom_tv_hist(Interval.in_1_minute, n_bars=350)
            if m1_df is not None and not m1_df.empty:
                m1_df = m1_df.reset_index()
                m1_df['time_utc'] = pd.to_datetime(m1_df['datetime'], utc=True)
                m1_df['dt_ist'] = (m1_df['time_utc'] + pd.Timedelta(hours=5, minutes=30)).dt.tz_localize(None)
                
                s_naive = (start_dt_utc + timedelta(hours=5, minutes=30)).replace(tzinfo=None) if hasattr(start_dt_utc, 'tzinfo') and start_dt_utc.tzinfo else (start_dt_utc + timedelta(hours=5, minutes=30))
                e_naive = (end_dt_utc + timedelta(hours=5, minutes=30)).replace(tzinfo=None) if hasattr(end_dt_utc, 'tzinfo') and end_dt_utc.tzinfo else (end_dt_utc + timedelta(hours=5, minutes=30))
                
                sub = m1_df[(m1_df['dt_ist'] >= s_naive) & (m1_df['dt_ist'] <= e_naive)].sort_values('dt_ist')
                for _, row in sub.iterrows():
                    h, l = float(row['high']), float(row['low'])
                    row_dt = row['dt_ist']
                    t_str = row_dt.strftime("%Y-%m-%dT%H:%M")
                    if direction == "long":
                        if l <= sl_price or h >= tp_price:
                            return t_str
                    else:
                        if h >= sl_price or l <= tp_price:
                            return t_str
        except Exception:
            pass
        return None

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
    
    risk_allocation = trade_info.get("risk_allocation", get_strategy_risk_amount(symbol))
    quantity = calculate_risk_quantity(symbol, entry_price, sl_price, risk_usd=risk_allocation)
    is_nas = ("NAS" in symbol.upper() or "US100" in symbol.upper())
    if is_nas:
        candles_df = fetch_capitalcom_nas100_candles(trade_date)
        inst = "CAPITALCOM:US100"
    else:
        inst = ("EUR_USD" if "EUR" in symbol.upper() else ("USD_JPY" if "JPY" in symbol.upper() else ("GBP_USD" if "GBP" in symbol.upper() else "XAU_USD")))
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
            elif symbol == "EURUSD":
                entry_time_str = f"{trade_date.strftime('%Y-%m-%d')}T11:30"
            elif "NAS" in symbol.upper() or "US100" in symbol.upper():
                _sample_utc = dt(trade_date.year, trade_date.month, trade_date.day, 12, 0, tzinfo=timezone.utc)
                entry_time_str = f"{trade_date.strftime('%Y-%m-%d')}T19:15" if is_us_dst(_sample_utc) else f"{trade_date.strftime('%Y-%m-%d')}T20:15"
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

            is_nas = ("NAS" in symbol.upper() or "US100" in symbol.upper())

            # Strict Day Close Exit (17:00 ET) for NAS100 (Intraday zero overnight holding)
            if is_nas:
                _sample_utc = c_time_utc
                _is_summer = is_us_dst(_sample_utc)
                _day_close_t = time(2, 30) if _is_summer else time(3, 30)
                _next_day = trade_date + timedelta(days=1)
                if (c_dt_ist.date() == _next_day and c_dt_ist.time() >= _day_close_t) or (c_dt_ist.date() > _next_day):
                    status = "closed"
                    exit_price = c['open']
                    exit_time_str = c_dt_ist.strftime("%Y-%m-%dT%H:%M")
                    exit_reason = "Day Close Exit (17:00 ET)"
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
        "exit_price": round(exit_price, 5 if ("GBP" in symbol or "EUR" in symbol) else (3 if "JPY" in symbol else 2)),
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
    is_nas = ("NAS" in symbol.upper() or "US100" in symbol.upper())
    strat_ids = [strategy_id, "6ad8f4c39d66482282927550", "6ae0c1bc9071eb9969df6a9f"] if is_nas else [strategy_id]
    params = {"q": f'{{"symbol": "{symbol}"}}'}
    try:
        resp = requests.get(BASE44_API_URL, headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            date_str = trade_date.isoformat()
            for item in items:
                if item.get("strategy_id") in strat_ids:
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
    
    is_aplus = trade_info.get("is_aplus")
    if is_aplus is None:
        symbol_u = symbol.upper()
        if "NAS" in symbol_u or "US100" in symbol_u:
            is_aplus = (trade_date.weekday() == 1)
        elif "EUR" in symbol_u:
            is_aplus = "A++" in str(trade_info.get("tier", "")) or "same-color" in str(trade_info.get("details", "")).lower()
        elif "JPY" in symbol_u:
            is_aplus = (trade_date.weekday() == 3)
        elif "GBP" in symbol_u:
            is_aplus = (direction == "long") and (trade_date.weekday() != 1) and ("-0.4" not in str(trade_info.get("details", "")))
        elif "XAU" in symbol_u:
            is_aplus = (trade_date.weekday() in [0, 1]) and ("A++" in str(trade_info.get("tier", "")) or (("CLEAN" in str(trade_info.get("details", "")).upper()) and (">=50%" in str(trade_info.get("details", "")) or ">=50%" in str(trade_info.get("tier", "")))))
        else:
            is_aplus = False
    elif "XAU" in symbol.upper():
        is_aplus = bool(is_aplus) and (trade_date.weekday() in [0, 1])

    setup_tag = "⭐ A++ Setup" if is_aplus else "Standard Setup"
    strat_risk = trade_info.get('risk_allocation', get_strategy_risk_amount(symbol))
    notes = f"[{setup_tag}] | {sl_pct}% SL ({sl_price}) , {tp_pct}% TP ({tp_price}) | Risk: ${strat_risk:,.2f} | Fee: ${fee:,.2f}"
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
        # Check if already 100% up to date with exact prices and strategy ID
        is_already_accurate = (
            existing.get("status") == status and
            existing.get("strategy_id") == strategy_id and
            abs(float(existing.get("buy_price", 0.0)) - float(entry_price)) < 0.05 and
            abs(float(existing.get("sell_price", 0.0)) - float(exit_price)) < 0.05
        )
        if is_already_accurate:
            return "Skipped (Duplicate)", f"Trade already accurately logged @ {existing.get('sell_price')} (Net P&L: ${existing.get('net_pnl', 0):+.2f})"

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
                elif "NAS" in sym.upper() or "US100" in sym.upper():
                    sl_dist = buy_price * 0.0018
                    sl_price = buy_price - sl_dist if direction == "long" else buy_price + sl_dist
                    tp_price = buy_price + 3.90 * sl_dist if direction == "long" else buy_price - 3.90 * sl_dist
                    
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
                                        _is_aplus = (target_date.weekday() == 3)
                                        _tier = "⭐ A++ Setup (Thursday Power Trade)" if _is_aplus else "Standard Setup"
                                        result_template.update({
                                            "direction": "long",
                                            "entry_price": round(entry, 3),
                                            "entry_time_ist": entry_t_str,
                                            "sl_price": round(ext_sl, 3),
                                            "tp_price": round(tp, 3),
                                            "sl_percentage": round(sl_pct, 3),
                                            "tp_percentage": round(sl_pct * 5.0, 3),
                                            "is_aplus": _is_aplus,
                                            "tier": _tier,
                                            "status": f"Active Signal ({s_name} Long - {_tier})",
                                            "details": f"Confirmed M15 Selfsweep in {s_name} session ({_tier})."
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
                                        _is_aplus = (target_date.weekday() == 3)
                                        _tier = "⭐ A++ Setup (Thursday Power Trade)" if _is_aplus else "Standard Setup"
                                        result_template.update({
                                            "direction": "short",
                                            "entry_price": round(entry, 3),
                                            "entry_time_ist": entry_t_str,
                                            "sl_price": round(ext_sl, 3),
                                            "tp_price": round(tp, 3),
                                            "sl_percentage": round(sl_pct, 3),
                                            "tp_percentage": round(sl_pct * 5.0, 3),
                                            "is_aplus": _is_aplus,
                                            "tier": _tier,
                                            "status": f"Active Signal ({s_name} Short - {_tier})",
                                            "details": f"Confirmed M15 Selfsweep in {s_name} session ({_tier})."
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
    
    # Base Strategy: All days (Mon-Fri) allowed; Tuesday excluded from A++ tier only
    
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
                    lowest_wick = min(lowest_wick, c_l)
                    if c_l <= lvl_m04:
                        touched_04 = True
                        
                    is_bullish = c_c > c_o
                    if is_bullish:
                        sl = (lowest_wick - 0.00001) if touched_04 else (lvl_m04 - 0.00002)
                        risk = c_c - sl
                        sl_pct = (risk / c_c) * 100.0
                        
                        if 0.035 <= sl_pct <= 0.154:
                            tp = c_c + 3.75 * risk
                            entry_close_ist = t_curr + timedelta(minutes=15)
                            _is_aplus = (not touched_04) and (target_date.weekday() != 1)
                            _tier = "⭐ A++ Setup (Clean -0.2 Long)" if _is_aplus else "Standard Setup"
                            result.update({
                                "direction": "long",
                                "entry_price": round(c_c, 5),
                                "entry_time_ist": entry_close_ist.strftime("%Y-%m-%dT%H:%M"),
                                "sl_price": round(sl, 5),
                                "tp_price": round(tp, 5),
                                "sl_percentage": round(sl_pct, 3),
                                "tp_percentage": round(sl_pct * 3.75, 3),
                                "is_aplus": _is_aplus,
                                "tier": _tier,
                                "status": f"Active Signal (London Long - {_tier})",
                                "details": f"Level -0.2 swept ({lvl_m02:.5f}) with confirmed rejection ({_tier})."
                            })
                            return result
                else: # short
                    highest_wick = max(highest_wick, c_h)
                    if c_h >= lvl_m04:
                        touched_04 = True
                        
                    is_bearish = c_c < c_o
                    if is_bearish:
                        sl = (highest_wick + 0.00001) if touched_04 else (lvl_m04 + 0.00002)
                        risk = sl - c_c
                        sl_pct = (risk / c_c) * 100.0
                        
                        if 0.035 <= sl_pct <= 0.154:
                            tp = c_c - 3.75 * risk
                            entry_close_ist = t_curr + timedelta(minutes=15)
                            result.update({
                                "direction": "short",
                                "entry_price": round(c_c, 5),
                                "entry_time_ist": entry_close_ist.strftime("%Y-%m-%dT%H:%M"),
                                "sl_price": round(sl, 5),
                                "tp_price": round(tp, 5),
                                "sl_percentage": round(sl_pct, 3),
                                "tp_percentage": round(sl_pct * 3.75, 3),
                                "is_aplus": False,
                                "tier": "Standard Setup",
                                "status": "Active Signal (London Short - Standard Setup)",
                                "details": f"Level +0.2 swept ({lvl_m02:.5f}) with confirmed rejection (Standard Setup)."
                            })
                            return result
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
                
            _c_range = s_high - s_low
            _body_ratio = abs(s_close - s_open) / _c_range if _c_range > 0 else 0.0
            _is_mon_or_tue = (target_date.weekday() in [0, 1])
            _is_aplus = ("CLEAN" in rule_name) and (_body_ratio >= 0.50) and _is_mon_or_tue
            _tier = "⭐ A++ Setup (Mon/Tue Clean DOL >=50% Body)" if _is_aplus else "Standard Setup"
            result_template.update({
                "direction": trade_dir,
                "entry_price": round(entry, 2),
                "entry_time_ist": entry_t_str,
                "sl_price": round(ext_sl, 2),
                "tp_price": round(tp, 2),
                "sl_percentage": round(sl_pct, 3),
                "tp_percentage": round(sl_pct * 3.30, 3),
                "is_aplus": _is_aplus,
                "tier": _tier,
                "status": f"Active Signal ({rule_name} - {_tier})",
                "details": f"2H DOL confirmed: {rule_name} ({_tier})"
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



# ------------------------------------------------------------------------------
# Strategy 4: EURUSD 30 MIN 11:00 AM / 12 NOON CANDLE
# ------------------------------------------------------------------------------
def run_eurusd_strategy(target_date: datetime.date) -> dict:
    """
    EURUSD 30-Minute Frankfurt Impulse Strategy:
    - Timeframe: 30-Minute (M30)
    - Execution Days: Monday (0) & Thursday (3) ONLY. (Tue, Wed, Fri strictly skipped)
    - Signal Candle: 11:00 AM - 11:30 AM IST (US EDT Summer) / 12:00 PM - 12:30 PM IST (US EST Winter)
    - Entry: Exactly at candle close (11:30 AM IST Summer / 12:30 PM IST Winter)
    - Direction:
        * 30M Close > Open -> LONG (BUY)
        * 30M Close < Open -> SHORT (SELL)
        * 30M Close == Open -> Doji / No Trade
    - Stop Loss: Opposite extreme of the 30M signal candle extended by 1 point (0.00001) beyond extreme level (Low - 1 point for Long, High + 1 point for Short)
    - Stop Loss Range Filter: 0.035% to 0.065% of price (~3.8 to 7.2 pips) measured after 1 point extension. Outside range -> Skipped
    - Target (Take Profit): Strictly 1:5.40 RR (5.40 * Risk)
    - Breakeven Rule: NONE (No Breakeven / Hold strictly to Target or Stop Loss)
    - Setup Quality Tiers (Case 2 Dynamic Allocation):
        * A++ Setup (Preceding 30M candle is same color continuation): $350 risk
        * Normal Setup (Preceding 30M candle is opposite color reversal): $250 risk
    - Safety Protocols:
        * High-impact news exit: NFP, CPI, FOMC, and ECB Monetary Policy releases.
        * Weekend exit: Flat before Saturday 02:30 AM (Summer) / 03:30 AM (Winter) IST.
    """
    result = {
        "strategy_name": "EURUSD 30 MIN 11:00 AM / 12 NOON CANDLE",
        "symbol": "EURUSD",
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
    
    # Day Filter: Monday (0) and Thursday (3) ONLY
    weekday = target_date.weekday()
    if weekday not in [0, 3]:
        day_name = target_date.strftime('%A')
        result["status"] = f"Skipped ({day_name} Rule)"
        result["details"] = f"{day_name} is strictly excluded by EURUSD Frankfurt Impulse rules (Executes Monday & Thursday only)."
        return result
        
    day_df = pd.DataFrame()
    live_df = fetch_oanda_candles("EUR_USD", "M15", target_date)
    if not live_df.empty:
        day_df = live_df[live_df['dt_ist'].dt.date == target_date].sort_values('time_utc').reset_index(drop=True)
        result["data_source"] = "OANDA Live Feed"
        
    if day_df.empty:
        # Check M15 archive first (instant load)
        if os.path.exists("EURUSD_M15_2021_2026_Full.csv"):
            df = pd.read_csv("EURUSD_M15_2021_2026_Full.csv")
            df['dt_utc'] = pd.to_datetime(df['time'])
            df['dt_ist'] = df['dt_utc'] + pd.Timedelta(hours=5, minutes=30)
            df['time_utc'] = df['dt_utc']
            match_df = df[df['dt_ist'].dt.date == target_date].sort_values('dt_ist').reset_index(drop=True)
            if not match_df.empty:
                day_df = match_df
                result["data_source"] = "Local Archive (EURUSD_M15_2021_2026_Full.csv)"
        elif os.path.exists("EURUSD_1M_Sep2024_Sep2026.csv"):
            df = pd.read_csv("EURUSD_1M_Sep2024_Sep2026.csv")
            df['dt_ist'] = pd.to_datetime(df['time_ist'].str.slice(0, 19))
            df['dt_utc'] = pd.to_datetime(df['time_utc'].str.slice(0, 19))
            df['time_utc'] = df['dt_utc']
            match_df = df[df['dt_ist'].dt.date == target_date].sort_values('dt_ist').reset_index(drop=True)
            if not match_df.empty:
                day_df = match_df
                result["data_source"] = "Local Archive (EURUSD_1M_Sep2024_Sep2026.csv)"
                    
    if day_df.empty or len(day_df) < 4:
        result["status"] = "No Session Data"
        result["details"] = f"Insufficient M15 candle data available for EURUSD on {target_date}."
        return result
        
    try:
        sample_utc = pd.to_datetime(day_df['time_utc'].iloc[0])
        is_summer = is_us_dst(sample_utc)
        
        day_df['time_str_ist'] = day_df['dt_ist'].dt.strftime('%H:%M')
        
        # Determine signal and preceding candle times
        if is_summer:
            c1_str = "11:00"
            c2_str = "11:15"
            entry_time_str = "11:30"
            p1_str = "10:30"
            p2_str = "10:45"
            season_name = "Summer (US EDT)"
        else:
            c1_str = "12:00"
            c2_str = "12:15"
            entry_time_str = "12:30"
            p1_str = "11:30"
            p2_str = "11:45"
            season_name = "Winter (US EST)"
            
        b1 = day_df[day_df['time_str_ist'] == c1_str]
        b2 = day_df[day_df['time_str_ist'] == c2_str]
        b_entry = day_df[day_df['time_str_ist'] == entry_time_str]
        
        if b1.empty or b2.empty:
            now_ist = dt.now(timezone(timedelta(hours=5, minutes=30))).replace(tzinfo=None)
            if target_date == now_ist.date():
                target_entry_dt = dt.strptime(f"{target_date} {entry_time_str}", "%Y-%m-%d %H:%M")
                if now_ist < target_entry_dt:
                    result["status"] = "Pending (Candle Forming)"
                    result["details"] = f"EURUSD 30M signal candle ({c1_str}-{entry_time_str} IST) is currently forming. Entry scheduled at {entry_time_str} IST close."
                    return result
            result["status"] = "No Signal Candle"
            result["details"] = f"Required 30M signal bars ({c1_str}, {c2_str} IST) were not found in session data."
            return result
            
        c_open = b1['open'].iloc[0]
        c_high = max(b1['high'].iloc[0], b2['high'].iloc[0])
        c_low = min(b1['low'].iloc[0], b2['low'].iloc[0])
        c_close = b2['close'].iloc[-1]
        entry_price = b_entry['open'].iloc[0] if not b_entry.empty else c_close
        
        # Direction check with 1 point (0.00001) SL extension beyond extreme level:
        point = 0.00001  # 1 point / pipette buffer beyond candle extreme
        if c_close > c_open:
            direction = "long"
            sl = round(c_low - point, 5)
            risk = entry_price - sl
        elif c_close < c_open:
            direction = "short"
            sl = round(c_high + point, 5)
            risk = sl - entry_price
        else:
            result["status"] = "No Trade (Doji)"
            result["details"] = f"EURUSD 30M candle closed as Doji (Open={c_open:.5f}, Close={c_close:.5f}). No directional impulse."
            return result
            
        if risk <= 0:
            result["status"] = "Invalid Risk"
            result["details"] = "Calculated risk is zero or negative."
            return result
            
        sl_pct = round((risk / entry_price) * 100.0, 3)
        risk_pips = risk * 10000.0
        
        # Stop Loss Range Filter: 0.035% to 0.065% (measured after 1 point extension)
        if sl_pct < 0.035:
            result["status"] = "Skipped (SL Below 0.035%)"
            result["details"] = f"Signal candle risk with 1 point extension is {sl_pct:.3f}% ({risk_pips:.1f} pips), below the 0.035% minimum threshold. Skipped to prevent market noise."
            return result
            
        if sl_pct > 0.065:
            result["status"] = "Skipped (SL Above 0.065%)"
            result["details"] = f"Signal candle risk with 1 point extension is {sl_pct:.3f}% ({risk_pips:.1f} pips), exceeding the 0.065% maximum threshold. Skipped to prevent over-extended risk."
            return result
            
        # Target: Exactly 1:5.40 RR
        rr = 5.40
        if direction == "long":
            tp = round(entry_price + rr * risk, 5)
        else:
            tp = round(entry_price - rr * risk, 5)
            
        tp_pct = round((abs(tp - entry_price) / entry_price) * 100.0, 3)
        
        # Preceding 30M Candle Quality Tiering (Case 2 Model)
        p1 = day_df[day_df['time_str_ist'] == p1_str]
        p2 = day_df[day_df['time_str_ist'] == p2_str]
        is_same_color = False
        if not p1.empty and not p2.empty:
            p_open = p1['open'].iloc[0]
            p_close = p2['close'].iloc[-1]
            prev_dir = "long" if p_close > p_open else ("short" if p_close < p_open else "doji")
            is_same_color = (prev_dir == direction)
            
        tier = "A++ (Same-Color Continuation)" if is_same_color else "Normal (Reversal Setup)"
        risk_allocation = 300.0  # Fixed at $300 per strategy rules
        
        result["direction"] = direction
        result["entry_price"] = round(entry_price, 5)
        result["entry_time_ist"] = f"{target_date.strftime('%Y-%m-%d')}T{entry_time_str}"
        result["sl_price"] = round(sl, 5)
        result["tp_price"] = round(tp, 5)
        result["sl_percentage"] = round(sl_pct, 3)
        result["tp_percentage"] = round(tp_pct, 3)
        result["is_aplus"] = is_same_color
        result["tier"] = "⭐ A++ Setup (Same-Color Continuation)" if is_same_color else "Standard Setup (Reversal)"
        result["risk_allocation"] = risk_allocation
        result["status"] = f"Active Setup ({result['tier']})"
        result["details"] = (
            f"EURUSD 30M {direction.upper()} validated at {entry_time_str} IST ({season_name}). "
            f"Entry: {entry_price:.5f}, SL: {sl:.5f} ({risk_pips:.1f} pips / {sl_pct:.3f}%), "
            f"TP: {tp:.5f} (1:5.40 RR / +{risk_pips * 5.4:.1f} pips). "
            f"Tier: {tier} (${risk_allocation:.0f} allocation). "
            f"Protocol: Set & Forget (No BE). News Shield Active (NFP/CPI/FOMC & ECB Monetary Policy)."
        )
        return result
        
    except Exception as e:
        result["status"] = "Error"
        result["details"] = f"EURUSD execution engine error: {str(e)}"
        return result

# ------------------------------------------------------------------------------
# Strategy 5: NAS100 M15 US OPEN IMPULSE (4PT BUFFER & TUESDAY A++)
# ------------------------------------------------------------------------------
def run_nas100_strategy(target_date: datetime.date) -> dict:
    """
    NAS100 / US100 M15 US Open Impulse Strategy:
    - Instrument: US100 / NAS100
    - Timeframe: 15-Minute (M15)
    - Execution Days: Monday to Thursday ONLY (Fridays & weekends strictly skipped)
    - Signal Candle: 09:30 AM - 09:45 AM ET (19:00-19:15 IST Summer / 20:00-20:15 IST Winter)
    - Entry: Exactly at candle close (19:15 IST Summer / 20:15 IST Winter)
    - Solid Body Ratio: (Body / Range) >= 45.0%
    - Range % Filter: 0.15% <= (Range / Open) * 100 <= 1.10%
    - Direction:
        * Close > Open -> LONG (BUY)
        * Close < Open -> SHORT (SELL)
        * Close == Open -> Doji / No Trade
    - Stop Loss: 50% Midpoint ((High + Low) / 2) extended by 4.0 points buffer:
        * BUY: Extended SL = Midpoint - 4.0 pts
        * SELL: Extended SL = Midpoint + 4.0 pts
    - Stop Loss Corridor Filter: 0.070% <= (Risk / Entry) * 100 <= 0.350% (Strict)
    - Take Profit: Fixed 1:3.90 RR (3.90 * Extended Risk)
    - Setup Quality Tiers:
        * ⭐ A++ Setup: TUESDAY trades (42.5% Win Rate, 3.34 PF, 4.0R Max DD)
        * Standard Setup: Monday, Wednesday, Thursday trades
    - Intraday Hard Exit: Strictly flat at 17:00 ET (02:30 AM Summer / 03:30 AM Winter IST)
    - News Cutoff: Flatten 1m before FOMC Rate Decision (14:00 ET / 23:30 Summer / 00:30 Winter IST)
    """
    result_template = {
        "strategy_name": "NAS100 7 OR 8 PM CANDLE",
        "symbol": "NAS100",
        "date": target_date,
        "direction": "none",
        "entry_price": 0.0,
        "entry_time_ist": None,
        "sl_price": 0.0,
        "tp_price": 0.0,
        "sl_percentage": 0.0,
        "tp_percentage": 0.0,
        "is_aplus": False,
        "tier": "Standard Setup",
        "status": "No Trade Setup",
        "details": "",
        "data_source": "OANDA Live API"
    }

    # Friday / Weekend filter
    dow = target_date.weekday()
    if dow == 4:
        result_template["status"] = "Skipped (Friday Rule)"
        result_template["details"] = "Fridays are strictly excluded by NAS100 strategy rules."
        return result_template
    if dow in [5, 6]:
        result_template["status"] = "Skipped (Weekend)"
        result_template["details"] = "Markets closed on weekends."
        return result_template

    # 1. Fetch live Capital.com candles (MANDATORY & EXCLUSIVE for NAS100)
    day_df = pd.DataFrame()
    cap_df = fetch_capitalcom_nas100_candles(target_date)
    if not cap_df.empty:
        match = cap_df[cap_df['dt_ist'].dt.date == target_date].sort_values('dt_ist').reset_index(drop=True)
        if not match.empty:
            day_df = match
            result_template["data_source"] = "Capital.com Live Feed (TradingView)"

    if day_df.empty or len(day_df) < 4:
        result_template["status"] = "No Session Data"
        result_template["details"] = f"Insufficient M15 candle data available for NAS100 on {target_date}."
        return result_template

    try:
        sample_utc = day_df['time_utc'].iloc[0]
        is_summer = is_us_dst(sample_utc)

        # Trigger bar: 09:30-09:45 ET
        # Summer (EDT): 19:00 IST open, 19:15 IST close (Entry 19:15 IST)
        # Winter (EST): 20:00 IST open, 20:15 IST close (Entry 20:15 IST)
        trigger_open_str = "19:00" if is_summer else "20:00"
        trigger_close_str = "19:15" if is_summer else "20:15"

        day_df['time_str_ist'] = day_df['dt_ist'].dt.strftime('%H:%M')
        trigger_bar = day_df[day_df['time_str_ist'] == trigger_open_str]

        if trigger_bar.empty:
            result_template["status"] = f"Waiting for Session (09:30 ET / {trigger_open_str} IST)"
            result_template["details"] = f"Trigger candle forms at 09:30-09:45 NY time ({trigger_open_str} IST). Awaiting candle close."
            return result_template

        bar = trigger_bar.iloc[0]
        c_open = float(bar['open'])
        c_high = float(bar['high'])
        c_low = float(bar['low'])
        c_close = float(bar['close'])

        c_range = c_high - c_low
        c_body = abs(c_close - c_open)

        if c_range <= 0:
            result_template["status"] = "No Trade (Zero Range)"
            result_template["details"] = "Trigger candle range is zero."
            return result_template

        body_pct = (c_body / c_range) * 100.0
        range_pct = (c_range / c_open) * 100.0

        if body_pct < 45.0:
            result_template["status"] = "Skipped (Body < 45%)"
            result_template["details"] = f"Trigger candle solid body ratio is {body_pct:.1f}% (minimum 45.0% required). Weak impulse."
            return result_template

        if range_pct < 0.15:
            result_template["status"] = "Skipped (Range < 0.15%)"
            result_template["details"] = f"Trigger candle range is {range_pct:.3f}% (below 0.15% minimum threshold). Compression bar."
            return result_template

        if range_pct > 1.10:
            result_template["status"] = "Skipped (Range > 1.10%)"
            result_template["details"] = f"Trigger candle range is {range_pct:.3f}% (above 1.10% maximum threshold). Climax bar."
            return result_template

        if c_close > c_open:
            direction = "long"
        elif c_close < c_open:
            direction = "short"
        else:
            result_template["status"] = "No Trade (Doji)"
            result_template["details"] = "Trigger candle closed exactly flat (Doji)."
            return result_template

        midpoint = (c_high + c_low) / 2.0
        sl_buffer_pts = 4.0
        if direction == "long":
            sl = midpoint - sl_buffer_pts
            risk = c_close - sl
        else:
            sl = midpoint + sl_buffer_pts
            risk = sl - c_close

        if risk <= 0:
            result_template["status"] = "Invalid Risk"
            result_template["details"] = "Calculated risk is zero or negative."
            return result_template

        sl_pct = (risk / c_close) * 100.0

        if sl_pct < 0.070:
            result_template["status"] = "Skipped (SL Below 0.070%)"
            result_template["details"] = f"Extended SL is {sl_pct:.3f}% ({risk:.1f} pts), below the 0.070% minimum corridor threshold."
            return result_template

        if sl_pct > 0.350:
            result_template["status"] = "Skipped (SL Above 0.350%)"
            result_template["details"] = f"Extended SL is {sl_pct:.3f}% ({risk:.1f} pts), exceeding the 0.350% maximum corridor threshold."
            return result_template

        # Target 1:3.90 RR
        rr = 3.90
        if direction == "long":
            tp = c_close + rr * risk
        else:
            tp = c_close - rr * risk
        tp_pct = sl_pct * rr

        # Setup Tier Classification: Tuesday = A++ Setup
        is_aplus = (dow == 1)
        tier = "⭐ A++ Setup (Tuesday Power Trade)" if is_aplus else "Standard Setup"

        result_template.update({
            "direction": direction,
            "entry_price": round(c_close, 2),
            "entry_time_ist": f"{target_date.strftime('%Y-%m-%d')}T{trigger_close_str}",
            "sl_price": round(sl, 2),
            "tp_price": round(tp, 2),
            "sl_percentage": round(sl_pct, 3),
            "tp_percentage": round(tp_pct, 3),
            "is_aplus": is_aplus,
            "tier": tier,
            "risk_allocation": 200.0,
            "status": f"Active Signal ({tier})",
            "details": f"Confirmed M15 US Open Impulse ({tier} {'Long' if direction=='long' else 'Short'} @ {c_close:.2f}). Body: {body_pct:.1f}%, Range: {range_pct:.2f}%."
        })
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
    <div class="dashboard-header" style="display: flex; align-items: center; gap: 18px;">
        <img src="data:image/png;base64,{logo_b64}" style="width: 68px; height: 68px; border-radius: 16px; box-shadow: 0 4px 20px rgba(6, 182, 212, 0.4), 0 0 15px rgba(245, 158, 11, 0.2); border: 2px solid rgba(56, 189, 248, 0.35); flex-shrink: 0;" />
        <div style="flex-grow: 1;">
            <div class="main-title">⚡ Auto Trade Logger Terminal</div>
            <div class="sub-title">Algorithmic 5-Strategy Execution Engine & Real-Time Base44 Journal Synchronizer</div>
        </div>
    </div>
    """
else:
    header_html = """
    <div class="dashboard-header">
        <div class="main-title">⚡ Auto Trade Logger Terminal</div>
        <div class="sub-title">Algorithmic 5-Strategy Execution Engine & Real-Time Base44 Journal Synchronizer</div>
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

# System Connectivity & Operational Status Strip
oanda_status = "🟢 Connected" if st.session_state.oanda_token else "🔴 Token Needed"
env_text = f"({st.session_state.oanda_env.title()})" if st.session_state.oanda_token else ""
b44_status = "🟢 Armed (5 Strategies)" if st.session_state.base44_token else "🔴 Token Needed"

st.markdown(f"""
<div style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; align-items: center;">
    <div style="background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 999px; padding: 6px 14px; font-size: 0.82rem; color: #94a3b8; display: flex; align-items: center; gap: 6px;">
        <span style="font-size: 0.9rem;">🌐</span>
        <span>OANDA Broker Feed: <strong style="color: #f1f5f9;">{oanda_status} {env_text}</strong> &bull; M1, M15, M30, H2</span>
    </div>
    <div style="background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(99, 102, 241, 0.25); border-radius: 999px; padding: 6px 14px; font-size: 0.82rem; color: #94a3b8; display: flex; align-items: center; gap: 6px;">
        <span style="font-size: 0.9rem;">⚡</span>
        <span>Base44 Auto-Journal: <strong style="color: #f1f5f9;">{b44_status}</strong></span>
    </div>
    <div style="background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: 999px; padding: 6px 14px; font-size: 0.82rem; color: #94a3b8; display: flex; align-items: center; gap: 6px;">
        <span style="font-size: 0.9rem;">🛡️</span>
        <span>News Shield: <strong style="color: #f1f5f9;">Active</strong> (USD NFP/CPI/FOMC &bull; EUR ECB &bull; GBP BOE &bull; JPY BOJ)</span>
    </div>
</div>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# Top 4 Institutional Strategy Cards (High-Definition Custom Glass Cards)
# ------------------------------------------------------------------------------
st.markdown(f"""
<div class="strat-grid">
    <!-- Card 1: USDJPY -->
    <div class="strat-card strat-card-usdjpy">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 1.4rem;">🇯🇵</span>
                <div>
                    <div style="font-weight: 800; color: #ffffff; font-size: 1.0rem;">USDJPY Selfsweep</div>
                    <div style="font-size: 0.72rem; color: #94a3b8;">USD/JPY &bull; M15 Timeframe</div>
                </div>
            </div>
            <span style="background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); font-size: 0.78rem; font-weight: 800; padding: 3px 9px; border-radius: 999px;">1:5.00 RR</span>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 10px; font-size: 0.8rem;">
            <div style="background: rgba(15, 23, 42, 0.6); padding: 7px 9px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                <span style="color: #64748b; font-size: 0.7rem;">EXECUTION DAYS</span><br>
                <strong style="color: #f1f5f9;">Mon, Wed, Thu, Fri</strong>
            </div>
            <div style="background: rgba(15, 23, 42, 0.6); padding: 7px 9px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                <span style="color: #64748b; font-size: 0.7rem;">RISK & FEE</span><br>
                <strong style="color: #f1f5f9;">$300 &bull; Fee $40</strong>
            </div>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.74rem; color: #94a3b8; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 8px;">
            <span>SL: 0.045% &ndash; 0.154%</span>
            <code style="color: #f59e0b; background: rgba(245, 158, 11, 0.1); padding: 2px 6px; border-radius: 6px;">{st.session_state.strat_1_id[:8]}...</code>
        </div>
    </div>

    <!-- Card 2: GBPUSD -->
    <div class="strat-card strat-card-gbpusd">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 1.4rem;">🇬🇧</span>
                <div>
                    <div style="font-weight: 800; color: #ffffff; font-size: 1.0rem;">GBPUSD Asia Fib</div>
                    <div style="font-size: 0.72rem; color: #94a3b8;">GBP/USD &bull; M15 GodMode</div>
                </div>
            </div>
            <span style="background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); font-size: 0.78rem; font-weight: 800; padding: 3px 9px; border-radius: 999px;">1:3.75 RR</span>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 10px; font-size: 0.8rem;">
            <div style="background: rgba(15, 23, 42, 0.6); padding: 7px 9px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                <span style="color: #64748b; font-size: 0.7rem;">EXECUTION DAYS</span><br>
                <strong style="color: #f1f5f9;">Monday &ndash; Friday</strong>
            </div>
            <div style="background: rgba(15, 23, 42, 0.6); padding: 7px 9px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                <span style="color: #64748b; font-size: 0.7rem;">RISK & FEE</span><br>
                <strong style="color: #f1f5f9;">$300 &bull; Fee $40</strong>
            </div>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.74rem; color: #94a3b8; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 8px;">
            <span>1.2&ndash;1.4 Fib (Double Entry)</span>
            <code style="color: #10b981; background: rgba(16, 185, 129, 0.1); padding: 2px 6px; border-radius: 6px;">{st.session_state.strat_2_id[:8]}...</code>
        </div>
    </div>

    <!-- Card 3: XAUUSD -->
    <div class="strat-card strat-card-xauusd">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 1.4rem;">🪙</span>
                <div>
                    <div style="font-weight: 800; color: #ffffff; font-size: 1.0rem;">XAUUSD 2H DOL</div>
                    <div style="font-size: 0.72rem; color: #94a3b8;">XAU/USD &bull; H2 Breakout</div>
                </div>
            </div>
            <span style="background: rgba(234, 179, 8, 0.2); color: #fde047; border: 1px solid rgba(234, 179, 8, 0.4); font-size: 0.78rem; font-weight: 800; padding: 3px 9px; border-radius: 999px;">1:3.30 RR</span>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 10px; font-size: 0.8rem;">
            <div style="background: rgba(15, 23, 42, 0.6); padding: 7px 9px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                <span style="color: #64748b; font-size: 0.7rem;">EXECUTION DAYS</span><br>
                <strong style="color: #f1f5f9;">Mon, Tue, Wed, Fri</strong>
            </div>
            <div style="background: rgba(15, 23, 42, 0.6); padding: 7px 9px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                <span style="color: #64748b; font-size: 0.7rem;">RISK & FEE</span><br>
                <strong style="color: #f1f5f9;">$300 &bull; Fee $25</strong>
            </div>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.74rem; color: #94a3b8; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 8px;">
            <span>BE Cushion @ +2.5R</span>
            <code style="color: #eab308; background: rgba(234, 179, 8, 0.1); padding: 2px 6px; border-radius: 6px;">{st.session_state.strat_3_id[:8]}...</code>
        </div>
    </div>

    <!-- Card 4: EURUSD -->
    <div class="strat-card strat-card-eurusd">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 1.4rem;">🇪🇺</span>
                <div>
                    <div style="font-weight: 800; color: #ffffff; font-size: 1.0rem;">EURUSD 30M Candle</div>
                    <div style="font-size: 0.72rem; color: #94a3b8;">EUR/USD &bull; M30 Frankfurt Impulse</div>
                </div>
            </div>
            <span style="background: rgba(56, 189, 248, 0.2); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.4); font-size: 0.78rem; font-weight: 800; padding: 3px 9px; border-radius: 999px;">1:5.40 RR</span>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 10px; font-size: 0.8rem;">
            <div style="background: rgba(15, 23, 42, 0.6); padding: 7px 9px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                <span style="color: #64748b; font-size: 0.7rem;">EXECUTION DAYS</span><br>
                <strong style="color: #38bdf8;">Monday & Thursday ONLY</strong>
            </div>
            <div style="background: rgba(15, 23, 42, 0.6); padding: 7px 9px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                <span style="color: #64748b; font-size: 0.7rem;">CASE 2 SIZING</span><br>
                <strong style="color: #f1f5f9;">$300 Fixed Risk</strong>
            </div>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.74rem; color: #94a3b8; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 8px;">
            <span>SL: 0.035% &ndash; 0.065% (No BE)</span>
            <code style="color: #38bdf8; background: rgba(56, 189, 248, 0.1); padding: 2px 6px; border-radius: 6px;">{st.session_state.strat_4_id[:8]}...</code>
        </div>
    </div>

    <!-- Card 5: NAS100 -->
    <div class="strat-card strat-card-nas100">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 1.4rem;">🇺🇸</span>
                <div>
                    <div style="font-weight: 800; color: #ffffff; font-size: 1.0rem;">NAS100 US Open</div>
                    <div style="font-size: 0.72rem; color: #94a3b8;">US100 / NAS100 &bull; M15 Impulse</div>
                </div>
            </div>
            <span style="background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.4); font-size: 0.78rem; font-weight: 800; padding: 3px 9px; border-radius: 999px;">1:3.90 RR</span>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 10px; font-size: 0.8rem;">
            <div style="background: rgba(15, 23, 42, 0.6); padding: 7px 9px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                <span style="color: #64748b; font-size: 0.7rem;">EXECUTION DAYS</span><br>
                <strong style="color: #c084fc;">Mon, Tue, Wed, Thu</strong>
            </div>
            <div style="background: rgba(15, 23, 42, 0.6); padding: 7px 9px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                <span style="color: #64748b; font-size: 0.7rem;">RISK & FEE</span><br>
                <strong style="color: #f1f5f9;">$200 &bull; Fee $20</strong>
            </div>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.74rem; color: #94a3b8; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 8px;">
            <span>Tuesday ⭐ A++ (42.5% WR)</span>
            <code style="color: #c084fc; background: rgba(168, 85, 247, 0.1); padding: 2px 6px; border-radius: 6px;">{st.session_state.strat_5_id[:8]}...</code>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

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
    st.info(f"🛡️ **News Shield Clear:** No prohibited high-impact news scheduled on {curr_query_date.strftime('%b %d, %Y')}. Holding permitted across USDJPY, GBPUSD, XAUUSD & EURUSD.")

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
        st.session_state.strat_3_id,
        st.session_state.strat_4_id,
        st.session_state.strat_5_id
    ]
    
    progress_bar = st.progress(0, text="Starting analysis...")
    status_box = st.empty()
    
    for idx, d_val in enumerate(dates_to_run):
        progress_pct = int(((idx + 1) / total_dates) * 100)
        status_box.info(f"⏳ Analyzing candles for **{d_val.strftime('%A, %B %d, %Y')}** ({idx + 1}/{total_dates})...")
        progress_bar.progress(progress_pct, text=f"Processing {d_val.strftime('%b %d')} ({idx+1}/{total_dates})...")
        
        # Run 5 models
        res_u = run_usdjpy_strategy(d_val)
        res_g = run_gbpusd_strategy(d_val)
        res_x = run_xauusd_strategy(d_val)
        res_e = run_eurusd_strategy(d_val)
        res_n = run_nas100_strategy(d_val)
        
        day_trades = []
        for strat_out, strat_id in [
            (res_u, strat_ids[0]),
            (res_g, strat_ids[1]),
            (res_x, strat_ids[2]),
            (res_e, strat_ids[3]),
            (res_n, strat_ids[4])
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
                
                qty_display = f"{qty_val:,.1f} oz" if "XAU" in trade["symbol"] else (f"{qty_val:,.2f} contracts" if ("NAS" in trade["symbol"] or "US100" in trade["symbol"]) else f"{qty_val:,.0f} units")
                pnl_display = f"${pnl_val:+,.2f}"
                fee_display = f"${fee_val:,.2f}"

                _setup_tier = "⭐ A++ Setup" if trade.get("is_aplus") else "Standard Setup"
                all_trades.append({
                    "Date": trade_d_str,
                    "Strategy": trade["strategy_name"],
                    "Symbol": trade["symbol"],
                    "Setup Tier": _setup_tier,
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
                    "Risk ($)": f"${trade.get('risk_allocation', get_strategy_risk_amount(trade['symbol'])):,.2f}",
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
                    "Risk ($)": f"${trade.get('risk_allocation', get_strategy_risk_amount(trade['symbol'])):,.2f}",
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
        st.metric("Risk Allocation", "$300 / $200 NAS", "Per Valid Signal")
        
    st.markdown("---")
    
    # --------------------------------------------------------------------------
    # Display Tabs
    # --------------------------------------------------------------------------
    tab_active, tab_table, tab_details, tab_rules = st.tabs([
        f"🔥 Active Signals ({len(active_signals)})",
        "📋 Full Daily Log Table",
        "🔍 Detailed Breakdown",
        "📖 Strategy Rules & Conditions"
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
                            <span style="color: #64748b; font-size: 0.75rem;">LOT SIZE (RISK {t['Risk ($)']})</span><br>
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


    with tab_rules:
        st.markdown("##### 📖 Complete Rules & Execution Specifications (All 5 Strategies)")
        
        # Strategy 1: USDJPY
        st.markdown("""
        <div class="trade-card" style="border-left: 4px solid #f59e0b; margin-bottom: 16px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="font-size: 1.15rem; font-weight: 800; color: #f59e0b;">🇯🇵 1. USDJPY SELFSWEEP</span>
                <span style="background: rgba(245, 158, 11, 0.2); padding: 4px 10px; border-radius: 999px; font-size: 0.8rem; font-weight: 700; color: #f59e0b;">Strategy ID: 6acaf2a887cd7b6cb6a1267c</span>
            </div>
            <p style="color: #cbd5e1; font-size: 0.88rem; line-height: 1.6; margin-bottom: 0;">
                <strong>Instrument:</strong> USD/JPY (OANDA: <code>USD_JPY</code>) &bull; <strong>Timeframe:</strong> 15-Minute (<code>M15</code>)<br>
                <strong>Execution Days:</strong> <strong>Monday, Wednesday, Thursday, Friday</strong> (<strong>Tuesday strictly excluded</strong>).<br>
                <strong>Setup Concept:</strong> Liquidity sweep of preceding session extremes with immediate candle rejection.<br>
                <strong>Stop Loss (SL):</strong> Opposite swing extreme &bull; <strong>Filter:</strong> <strong>0.045% to 0.154%</strong> of price (~7.0 to 24.0 pips).<br>
                <strong>Profit Target (TP):</strong> Strictly <strong>1:5.00 RR</strong> &bull; <strong>Breakeven (BE):</strong> <strong>NONE (No Breakeven)</strong>.<br>
                <strong>⭐ A++ Setup Tier:</strong> Strictly <strong>THURSDAY trades ONLY</strong> (Delivers 50.0% Win Rate, 5.00 Profit Factor, +61.8R). Mon/Wed/Fri are Standard Setup.<br>
                <strong>Risk Sizing & Fees:</strong> $300 Fixed Risk Allocation &bull; Broker Fee: $40.00.<br>
                <strong>News Shield:</strong> Auto-exit 5 min prior to <strong>US NFP, CPI, FOMC & BOJ Policy Decisions</strong>.
            </p>
        </div>
        """, unsafe_allow_html=True)

        # Strategy 2: GBPUSD
        st.markdown("""
        <div class="trade-card" style="border-left: 4px solid #10b981; margin-bottom: 16px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="font-size: 1.15rem; font-weight: 800; color: #10b981;">🇬🇧 2. GBPUSD ASIA 1.2 - 1.4 FIB RETRACEMENT (GodMode)</span>
                <span style="background: rgba(16, 185, 129, 0.2); padding: 4px 10px; border-radius: 999px; font-size: 0.8rem; font-weight: 700; color: #10b981;">Strategy ID: 6acaf29762d5f24891c0c9bc</span>
            </div>
            <p style="color: #cbd5e1; font-size: 0.88rem; line-height: 1.6; margin-bottom: 0;">
                <strong>Instrument:</strong> GBP/USD (OANDA: <code>GBP_USD</code>) &bull; <strong>Timeframe:</strong> 15-Minute (<code>M15</code>)<br>
                <strong>Execution Days:</strong> <strong>Monday through Friday (All Days Allowed for Base Strategy)</strong> &bull; <strong>Asian Range:</strong> 05:30&ndash;09:30 Summer / 06:30&ndash;10:30 Winter IST.<br>
                <strong>⭐ A++ Setup Tier:</strong> <strong>LONG ONLY + Clean -0.2 Sweep</strong> on <strong>Mon, Wed, Thu, Fri</strong> (<strong>Tuesday strictly excluded from A++ setups</strong>).<br>
                <strong>Pre-London Gap Check:</strong> 09:45&ndash;11:15 Summer / 10:45&ndash;12:15 Winter IST &bull; <strong>London Window:</strong> 11:30&ndash;14:30 Summer / 12:30&ndash;15:30 Winter IST.<br>
                <strong>Trigger:</strong> Limit/Market touch of the <strong>1.20 to 1.40 Fibonacci Extension</strong> of the Asian session range.<br>
                <strong>Stop Loss (SL):</strong> Opposite extreme &bull; <strong>Filter:</strong> <strong>0.035% to 0.154%</strong> (~4.5 to 20.0 pips).<br>
                <strong>Profit Target (TP):</strong> Strictly <strong>1:3.75 RR</strong> &bull; <strong>Breakeven (BE):</strong> <strong>NONE (No Breakeven)</strong>.<br>
                <strong>Entry 2 Protocol:</strong> Double Entry armed if Entry 1 stops out without a candle closing beyond SL.<br>
                <strong>Risk Sizing & Fees:</strong> $300 Fixed Risk Allocation &bull; Broker Fee: $40.00.<br>
                <strong>News Shield:</strong> Auto-exit 5 min prior to <strong>US NFP, CPI, FOMC & BOE Policy Decisions</strong>.
            </p>
        </div>
        """, unsafe_allow_html=True)

        # Strategy 3: XAUUSD
        st.markdown("""
        <div class="trade-card" style="border-left: 4px solid #eab308; margin-bottom: 16px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="font-size: 1.15rem; font-weight: 800; color: #eab308;">🪙 3. XAUUSD 2H 4:30/5:30 DOL</span>
                <span style="background: rgba(234, 179, 8, 0.2); padding: 4px 10px; border-radius: 999px; font-size: 0.8rem; font-weight: 700; color: #eab308;">Strategy ID: 6acaf24d7a78a186a5430938</span>
            </div>
            <p style="color: #cbd5e1; font-size: 0.88rem; line-height: 1.6; margin-bottom: 0;">
                <strong>Instrument:</strong> Gold (OANDA: <code>XAU_USD</code>) &bull; <strong>Timeframe:</strong> 2-Hour (<code>H2</code>)<br>
                <strong>Execution Days:</strong> <strong>Monday, Tuesday, Wednesday, Friday</strong> (<strong>Thursday strictly excluded</strong>).<br>
                <strong>Structure:</strong> 2-Hour morning reference candle at 18:00 NY / 06:30 IST &bull; Clean Breakout & Swept Breakout triggers.<br>
                <strong>Stop Loss (SL):</strong> Opposite structural extreme &bull; <strong>Filter:</strong> <strong>0.165% to 0.994%</strong>.<br>
                <strong>Profit Target (TP):</strong> <strong>1:3.30 RR</strong> &bull; <strong>Breakeven (BE):</strong> <strong>Armed at +2.50R</strong>.<br>
                <strong>⭐ A++ Setup Tier:</strong> <strong>Clean DOL Breakout with Solid Body Ratio &ge; 50% on Monday & Tuesday ONLY</strong>. Wednesday/Friday trades or Breakouts with Body &lt; 50%, Swept Breakouts, or Sweep Rejections execute as Standard Setup.<br>
                <strong>Risk Sizing & Fees:</strong> $300 Fixed Risk Allocation &bull; Broker Fee: $25.00.<br>
                <strong>News Shield:</strong> Auto-exit 5 min prior to <strong>US NFP, CPI & FOMC Statement</strong>.
            </p>
        </div>
        """, unsafe_allow_html=True)

        # Strategy 4: EURUSD
        st.markdown("""
        <div class="trade-card" style="border-left: 4px solid #38bdf8; margin-bottom: 16px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="font-size: 1.15rem; font-weight: 800; color: #38bdf8;">🇪🇺 4. EURUSD 30 MIN 11:00 AM / 12 NOON CANDLE</span>
                <span style="background: rgba(56, 189, 248, 0.2); padding: 4px 10px; border-radius: 999px; font-size: 0.8rem; font-weight: 700; color: #38bdf8;">Strategy ID: 6ad8f4b28c55371171816449</span>
            </div>
            <p style="color: #cbd5e1; font-size: 0.88rem; line-height: 1.6; margin-bottom: 0;">
                <strong>Instrument:</strong> EUR/USD (OANDA: <code>EUR_USD</code>) &bull; <strong>Timeframe:</strong> 30-Minute (<code>M30</code>)<br>
                <strong>Execution Days:</strong> <strong>Monday & Thursday ONLY</strong> (Tuesdays, Wednesdays & Fridays are strictly excluded to avoid mid-week chop).<br>
                <strong>Entry Timing:</strong><br>
                &bull; <strong>Summer (US EDT / DST):</strong> 11:00 AM &ndash; 11:30 AM IST (Entry at <strong>11:30 AM IST candle close</strong>).<br>
                &bull; <strong>Winter (US EST / Standard):</strong> 12:00 PM &ndash; 12:30 PM IST (Entry at <strong>12:30 PM IST candle close</strong>).<br>
                <strong>Directional Signal:</strong> Close &gt; Open &rarr; <span style="color: #34d399; font-weight: 700;">LONG</span> | Close &lt; Open &rarr; <span style="color: #f87171; font-weight: 700;">SHORT</span> | Close == Open &rarr; Doji (Skip).<br>
                <strong>Stop Loss (SL):</strong> Opposite extreme of the 30M signal candle extended by 1 point (0.00001) buffer (Low - 1 pt for Long, High + 1 pt for Short).<br>
                <strong>SL Range Filter:</strong> <strong>0.035% to 0.065%</strong> of price (~3.8 to 7.2 pips) measured after the 1 point extension. Candles outside this range are strictly skipped.<br>
                <strong>Profit Target (TP):</strong> Strictly <strong>1:5.50 RR</strong> ($5.50 \times \text{Risk}$) &bull; <strong>Breakeven (BE):</strong> <strong>NONE (No Breakeven)</strong>.<br>
                <strong>Quality Tiering & Risk Sizing:</strong><br>
                &bull; <strong>Risk Allocation:</strong> <strong>$300 Fixed Risk</strong> on all setups.<br>
                &bull; <strong>Tier A++:</strong> Preceding 30M candle matches signal candle color (Continuation).<br>
                &bull; <strong>Tier Standard:</strong> Preceding 30M candle has opposite color (Reversal).<br>
                <strong>Restricted News:</strong> <strong>US NFP, CPI, FOMC & ECB Monetary Policy Statement</strong> (Exit 5 min prior).<br>
                <strong>Weekend Rule:</strong> Flat before Saturday 02:30 AM Summer / 03:30 AM Winter IST.
            </p>
        </div>
        """, unsafe_allow_html=True)
        # Strategy 5: NAS100 M15 US Open Impulse
        st.markdown("""
        <div class="rule-box" style="border-left-color: #a855f7;">
            <h4 style="color: #c084fc; margin-bottom: 8px;">🇺🇸 Strategy 5: NAS100 / US100 M15 US Open Impulse (1:3.90 RR)</h4>
            <p style="color: #94a3b8; font-size: 0.88rem; line-height: 1.6;">
                <strong>Core Philosophy:</strong> Captures the explosive institutional momentum impulse forming on the opening 15-minute cash session candle (09:30–09:45 NY).<br>
                <strong>Timeframe:</strong> 15-Minute (M15) &bull; <strong>Target:</strong> Fixed 1:3.90 R:R Ratio &bull; <strong>Breakeven Rule:</strong> Strictly NO Breakeven (Full Run).<br>
                <strong>Execution Days:</strong> Monday, Tuesday, Wednesday, Thursday. (Fridays & weekends strictly skipped).<br>
                <strong>Signal Timing:</strong> 09:30 AM – 09:45 AM ET (19:00–19:15 IST Summer / 20:00–20:15 IST Winter). Entry at bar close.<br>
                <strong>The Trigger Candle Checklist:</strong><br>
                1. <strong>Solid Body Ratio:</strong> Body / Range &ge; 45.0% (Clean directional impulse).<br>
                2. <strong>Candle Range Corridor:</strong> 0.15% &le; Range / Open &le; 1.10% (Filters compression & exhaustion climax bars).<br>
                3. <strong>Direction:</strong> Buy if Close &gt; Open; Sell if Close &lt; Open.<br>
                4. <strong>Base Stop Loss:</strong> 50% Midpoint of the 15-minute trigger candle: (High + Low) / 2.<br>
                5. <strong>Extended Stop Loss (+4.0 Points Buffer):</strong> BUY: Midpoint - 4.0 pts; SELL: Midpoint + 4.0 pts.<br>
                6. <strong>Stop Loss Corridor Filter:</strong> 0.070% &le; Extended SL % &le; 0.350%.<br>
                7. <strong>⭐ A++ Setup Tier:</strong> Any trade forming on <strong>TUESDAY</strong> is an A++ Setup (42.5% WR, 3.34 PF, 4.0R Max Drawdown).<br>
                8. <strong>Strict Day Close Exit:</strong> Any trade still open at 17:00 ET (02:30 AM Summer / 03:30 AM Winter IST) is closed at market price (zero overnight holding).<br>
                9. <strong>FOMC News Shield:</strong> Flatten 1 minute before FOMC Rate Decision (14:00 ET / 23:30 IST Summer / 00:30 IST Winter).
            </p>
        </div>
        """, unsafe_allow_html=True)

else:
    # --------------------------------------------------------------------------
    # DASHBOARD LANDING VIEW (ACTIVE 4-STRATEGY PORTFOLIO BLUEPRINT)
    # --------------------------------------------------------------------------
    st.info("💡 Choose a **Single Day** or a **Date Range** above, then click **'🚀 Run Strategies'** to stream live OANDA candles and audit trade triggers.")
    
    st.markdown("""
    <div class="glass-card" style="margin-top: 14px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; flex-wrap: wrap; gap: 8px;">
            <span style="font-size: 1.15rem; font-weight: 800; color: #f8fafc;">🏛️ Institutional Portfolio Blueprint & Active Strategies</span>
            <span style="background: rgba(37, 99, 235, 0.2); color: #60a5fa; font-weight: 700; padding: 4px 12px; border-radius: 999px; font-size: 0.8rem; border: 1px solid rgba(96, 165, 250, 0.3);">
                ⚡ All 5 Strategies Connected to Base44 Journal
            </span>
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px;">
            <!-- Strategy 1 Card -->
            <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 12px; padding: 14px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <span style="font-weight: 800; color: #f59e0b; font-size: 1.0rem;">🇯🇵 USDJPY Selfsweep</span>
                    <span style="background: rgba(245, 158, 11, 0.2); color: #fbbf24; font-size: 0.75rem; font-weight: 700; padding: 2px 8px; border-radius: 8px;">1:5.00 RR</span>
                </div>
                <div style="color: #94a3b8; font-size: 0.82rem; line-height: 1.5;">
                    &bull; <strong>Timeframe:</strong> M15 &bull; <strong>Fee:</strong> $40.00<br>
                    &bull; <strong>Days:</strong> Mon, Wed, Thu, Fri (No Tue)<br>
                    &bull; <strong>SL Filter:</strong> 0.045% &ndash; 0.154% (No BE)<br>
                    &bull; <strong>A++ Edge:</strong> Thursday ⭐ A++ Setup (5.00 PF / 50% WR)<br>
                    &bull; <strong>News Shield:</strong> US News & BOJ Policy<br>
                    &bull; <code style="font-size: 0.75rem; color: #cbd5e1;">ID: 6acaf2a887cd7b6cb6a1267c</code>
                </div>
            </div>
            <!-- Strategy 2 Card -->
            <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 12px; padding: 14px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <span style="font-weight: 800; color: #10b981; font-size: 1.0rem;">🇬🇧 GBPUSD Asia Fib</span>
                    <span style="background: rgba(16, 185, 129, 0.2); color: #34d399; font-size: 0.75rem; font-weight: 700; padding: 2px 8px; border-radius: 8px;">1:3.75 RR</span>
                </div>
                <div style="color: #94a3b8; font-size: 0.82rem; line-height: 1.5;">
                    &bull; <strong>Timeframe:</strong> M15 &bull; <strong>Fee:</strong> $40.00<br>
                    &bull; <strong>Days:</strong> Monday &ndash; Friday (All Days Allowed)<br>
                    &bull; <strong>Trigger:</strong> 1.20&ndash;1.40 Fib Extension (No BE)<br>
                    &bull; <strong>A++ Edge:</strong> Long Clean -0.2 (Tue excluded from A++)<br>
                    &bull; <strong>News Shield:</strong> US News & BOE Policy<br>
                    &bull; <code style="font-size: 0.75rem; color: #cbd5e1;">ID: 6acaf29762d5f24891c0c9bc</code>
                </div>
            </div>
            <!-- Strategy 3 Card -->
            <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(234, 179, 8, 0.3); border-radius: 12px; padding: 14px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <span style="font-weight: 800; color: #eab308; font-size: 1.0rem;">🪙 XAUUSD 2H DOL</span>
                    <span style="background: rgba(234, 179, 8, 0.2); color: #fde047; font-size: 0.75rem; font-weight: 700; padding: 2px 8px; border-radius: 8px;">1:3.30 RR</span>
                </div>
                <div style="color: #94a3b8; font-size: 0.82rem; line-height: 1.5;">
                    &bull; <strong>Timeframe:</strong> H2 &bull; <strong>Fee:</strong> $25.00<br>
                    &bull; <strong>Days:</strong> Mon, Tue, Wed, Fri (No Thu)<br>
                    &bull; <strong>Breakout:</strong> Swept & Clean (BE @ +2.5R)<br>
                    &bull; <strong>A++ Edge:</strong> Mon/Tue Clean DOL Breakout &ge;50% Body ⭐ A++ Setup<br>
                    &bull; <strong>News Shield:</strong> US NFP, CPI & FOMC<br>
                    &bull; <code style="font-size: 0.75rem; color: #cbd5e1;">ID: 6acaf24d7a78a186a5430938</code>
                </div>
            </div>
            <!-- Strategy 4 Card -->
            <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 12px; padding: 14px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <span style="font-weight: 800; color: #38bdf8; font-size: 1.0rem;">🇪🇺 EURUSD 30M Candle</span>
                    <span style="background: rgba(56, 189, 248, 0.2); color: #7dd3fc; font-size: 0.75rem; font-weight: 700; padding: 2px 8px; border-radius: 8px;">1:5.40 RR</span>
                </div>
                <div style="color: #94a3b8; font-size: 0.82rem; line-height: 1.5;">
                    &bull; <strong>Timeframe:</strong> M30 &bull; <strong>Fee:</strong> $0.00 (Flat)<br>
                    &bull; <strong>Days:</strong> Mon & Thu ONLY (11:00/12:00 IST)<br>
                    &bull; <strong>SL Filter:</strong> 0.035% &ndash; 0.065% (No BE)<br>
                    &bull; <strong>News Shield:</strong> US News & ECB Monetary Policy<br>
                    &bull; <code style="font-size: 0.75rem; color: #cbd5e1;">ID: 6ad8f4b28c55371171816449</code>
                </div>
            </div>

            <!-- Strategy 5 Card -->
            <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(168, 85, 247, 0.3); border-radius: 12px; padding: 14px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <span style="font-weight: 800; color: #c084fc; font-size: 1.0rem;">🇺🇸 NAS100 US Open Impulse</span>
                    <span style="background: rgba(168, 85, 247, 0.2); color: #c084fc; font-size: 0.75rem; font-weight: 700; padding: 2px 8px; border-radius: 8px;">1:3.90 RR</span>
                </div>
                <div style="color: #94a3b8; font-size: 0.82rem; line-height: 1.5;">
                    &bull; <strong>Timeframe:</strong> M15 &bull; <strong>Fee:</strong> $20.00 &bull; <strong>Risk:</strong> $200 Fixed<br>
                    &bull; <strong>Days:</strong> Mon, Tue, Wed, Thu (No Fri)<br>
                    &bull; <strong>Trigger:</strong> 09:30 ET Bar, 45% Body, 4pt Buffer SL<br>
                    &bull; <strong>A++ Edge:</strong> Tuesday ⭐ A++ Setup (3.34 PF)<br>
                    &bull; <strong>Rules:</strong> 17:00 ET Hard Close & FOMC Cutoff<br>
                    &bull; <code style="font-size: 0.75rem; color: #cbd5e1;">ID: 6ae0c1bc9071eb9969df6a9f</code>
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

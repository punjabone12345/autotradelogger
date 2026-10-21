import os
import re
import requests
import datetime
from datetime import datetime as dt, timezone, timedelta, time
import pandas as pd
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ==============================================================================
# HARDCODED SECRET VARIABLES & STRATEGY IDS
# ==============================================================================
BASE44_API_KEY = os.environ.get("BASE44_API_KEY", "b44u_a42da4afa13a09294364b826325610580674a3365e53e3676ba7693e42240d8f")
BASE44_API_URL = "https://trading-journal-2-0.base44.app/api/entities/Trade"

STRAT1_ID = os.environ.get("STRAT1_ID", "6acaf2a887cd7b6cb6a1267c")  # USDJPY SELFSWEEP
STRAT2_ID = os.environ.get("STRAT2_ID", "6acaf29762d5f24891c0c9bc")  # GBPUSD ASIA 1.2 - 1.4 FIB RETRACMENT
STRAT3_ID = os.environ.get("STRAT3_ID", "6acaf24d7a78a186a5430938")  # XAUUSD 2H 4:30/5:30 DOL
STRAT4_ID = os.environ.get("STRAT4_ID", "6ad8f4b28c55371171816449")  # EURUSD 30 MIN 11:00 AM / 12 NOON CANDLE

OANDA_TOKEN = os.environ.get("OANDA_TOKEN", "f2b74d1cee1eb5488ba8b6b067e3ffc6-b6ccbdca86ea9ddb162f03996341ae91")

# Fixed broker & exchange fees per trade:
# XAUUSD: $25.00 per trade
# GBPUSD: $40.00 per trade
# USDJPY: $40.00 per trade
FIXED_FEES = {
    "XAUUSD": 25.0,
    "GBPUSD": 40.0,
    "USDJPY": 40.0,
    "EURUSD": 30.0
}

# ==============================================================================
# FASTAPI APPLICATION SETUP
# ==============================================================================
app = FastAPI(
    title="Base44 Daily Strategy Runner API",
    description="Automated multi-strategy trading engine connected to Base44 Trade Journal",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RunRequest(BaseModel):
    date: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    amount: Optional[float] = 300.0
    fees: Optional[float] = 40.0

# ==============================================================================
# TIMEZONE & DST HELPERS
# ==============================================================================
def is_us_dst(dt_utc: datetime.datetime) -> bool:
    """Checks whether date falls in US Daylight Saving Time (Summer)."""
    year = dt_utc.year
    d_mar = datetime.date(year, 3, 1)
    mar_second_sun = 1 + (6 - d_mar.weekday() + 7) % 7 + 7
    dst_start = datetime.datetime(year, 3, mar_second_sun, 7, 0, tzinfo=timezone.utc)
    d_nov = datetime.date(year, 11, 1)
    nov_first_sun = 1 + (6 - d_nov.weekday()) % 7
    dst_end = datetime.datetime(year, 11, nov_first_sun, 6, 0, tzinfo=timezone.utc)
    return dst_start <= dt_utc < dst_end

# ==============================================================================
# OANDA MARKET DATA PROVIDER & LIVE HELPERS
# ==============================================================================
def fetch_oanda_candles(instrument: str, granularity: str, target_date: datetime.date, end_date: Optional[datetime.date] = None) -> pd.DataFrame:
    """Fetches real-time M15 candlesticks from OANDA API with IST conversion."""
    if not OANDA_TOKEN:
        return pd.DataFrame()
        
    base_urls = ["https://api-fxpractice.oanda.com/v3", "https://api-fxtrade.oanda.com/v3"]
    headers = {"Authorization": f"Bearer {OANDA_TOKEN}"}
    start_utc = dt(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=timezone.utc) - timedelta(days=2)
    now_utc = dt.now(timezone.utc)
    
    params = {
        "granularity": granularity,
        "price": "M",
        "from": start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    eval_end_date = end_date if end_date is not None else target_date
    target_end_utc = dt(eval_end_date.year, eval_end_date.month, eval_end_date.day, 23, 59, 59, tzinfo=timezone.utc)
    if target_end_utc < now_utc:
        params["to"] = target_end_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        
    for base_url in base_urls:
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
        except Exception:
            continue
    return pd.DataFrame()

def get_latest_market_price(symbol: str) -> float:
    """Fetches real-time market price for symbol from OANDA."""
    inst = "EUR_USD" if "EUR" in symbol.upper() else ("USD_JPY" if "JPY" in symbol.upper() else ("GBP_USD" if "GBP" in symbol.upper() else "XAU_USD"))
    if not OANDA_TOKEN:
        return 0.0
    for base_url in ["https://api-fxpractice.oanda.com/v3", "https://api-fxtrade.oanda.com/v3"]:
        try:
            url = f"{base_url}/instruments/{inst}/candles"
            r = requests.get(url, headers={"Authorization": f"Bearer {OANDA_TOKEN}"}, params={"count": 1, "price": "M", "granularity": "M1"}, timeout=5)
            if r.status_code == 200:
                c_list = r.json().get("candles", [])
                if c_list:
                    return float(c_list[-1]["mid"]["c"])
        except Exception:
            pass
    return 0.0

def fetch_m1_exit_time(instrument: str, start_dt_utc: datetime.datetime, end_dt_utc: datetime.datetime, 
                        direction: str, sl_price: float, tp_price: float) -> Optional[str]:
    """
    Scans 1-minute (M1) candles between entry time and exit candle to find the exact minute
    and candle close timestamp when Stop Loss or Take Profit was triggered in IST.
    """
    if not OANDA_TOKEN:
        return None
    headers = {"Authorization": f"Bearer {OANDA_TOKEN}"}
    
    for base_url in ["https://api-fxpractice.oanda.com/v3", "https://api-fxtrade.oanda.com/v3"]:
        cur_from = start_dt_utc
        success = False
        while cur_from < end_dt_utc:
            params = {
                "granularity": "M1",
                "price": "M",
                "from": cur_from.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "count": 500
            }
            try:
                url = f"{base_url}/instruments/{instrument}/candles"
                r = requests.get(url, headers=headers, params=params, timeout=8)
                if r.status_code != 200:
                    break
                raw_candles = r.json().get("candles", [])
                if not raw_candles:
                    break
                success = True
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
                        t_close_utc = t_utc + timedelta(minutes=1)
                        t_close_ist = t_close_utc.astimezone(timezone(timedelta(hours=5, minutes=30)))
                        return t_close_ist.strftime("%Y-%m-%dT%H:%M")
                last_t = dt.strptime(raw_candles[-1]["time"][:19] + "Z", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                if last_t <= cur_from or len(raw_candles) < 500:
                    break
                cur_from = last_t + timedelta(minutes=1)
            except Exception:
                break
        if success:
            break
    return None

# ==============================================================================
# POSITION SIZING & FEES LOGIC
# ==============================================================================
def calculate_risk_quantity(symbol: str, entry_price: float, sl_price: float, risk_usd: float = 300.0) -> float:
    """
    Calculates exact risk-based position size to risk precisely risk_usd on Stop Loss:
    Quantity = Risk ($300 default) / |entry_price - sl_price|
    - XAUUSD: Rounded to 1 decimal place (ounces).
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

def get_trade_fee(symbol: str, user_fee: Optional[float] = None) -> float:
    """Returns fixed fee per trade ($25 for XAUUSD, $40 for GBPUSD, $40 for USDJPY), or custom if explicitly set."""
    if user_fee is not None and user_fee > 0 and user_fee != 40.0:
        return float(user_fee)
    s = str(symbol).upper()
    if "XAU" in s:
        return FIXED_FEES["XAUUSD"]
    elif "GBP" in s:
        return FIXED_FEES["GBPUSD"]
    elif "JPY" in s:
        return FIXED_FEES["USDJPY"]
    elif "EUR" in s:
        return FIXED_FEES["EURUSD"]
    return float(user_fee or 40.0)

# ==============================================================================
# HYBRID HIGH-IMPACT NEWS MONITOR (HISTORICAL ARCHIVE + LIVE REAL-TIME FEED)
# Covers Big 4: NFP, CPI, FOMC, and BOJ Interest Rate Decision
# Evaluates news across ALL dates: historical past dates, today, and future dates!
# ==============================================================================
HISTORICAL_NEWS_SCHEDULE = [
    {"category": "NFP", "title": "NFP (Mar 8, 2024)", "dt_ist": dt(2024, 3, 8, 18, 0), "date_str": "2024-03-08"},
    {"category": "CPI", "title": "CPI (Mar 12, 2024)", "dt_ist": dt(2024, 3, 12, 18, 0), "date_str": "2024-03-12"},
    {"category": "BOJ_RATE", "title": "BOJ_RATE (Mar 19, 2024)", "dt_ist": dt(2024, 3, 19, 8, 30), "date_str": "2024-03-19"},
    {"category": "FOMC", "title": "FOMC (Mar 20, 2024)", "dt_ist": dt(2024, 3, 20, 23, 30), "date_str": "2024-03-20"},
    {"category": "NFP", "title": "NFP (Apr 5, 2024)", "dt_ist": dt(2024, 4, 5, 18, 0), "date_str": "2024-04-05"},
    {"category": "CPI", "title": "CPI (Apr 10, 2024)", "dt_ist": dt(2024, 4, 10, 18, 0), "date_str": "2024-04-10"},
    {"category": "BOJ_RATE", "title": "BOJ_RATE (Apr 26, 2024)", "dt_ist": dt(2024, 4, 26, 8, 30), "date_str": "2024-04-26"},
    {"category": "FOMC", "title": "FOMC (May 1, 2024)", "dt_ist": dt(2024, 5, 1, 23, 30), "date_str": "2024-05-01"},
    {"category": "NFP", "title": "NFP (May 3, 2024)", "dt_ist": dt(2024, 5, 3, 18, 0), "date_str": "2024-05-03"},
    {"category": "CPI", "title": "CPI (May 15, 2024)", "dt_ist": dt(2024, 5, 15, 18, 0), "date_str": "2024-05-15"},
    {"category": "NFP", "title": "NFP (Jun 7, 2024)", "dt_ist": dt(2024, 6, 7, 18, 0), "date_str": "2024-06-07"},
    {"category": "CPI", "title": "CPI (Jun 12, 2024)", "dt_ist": dt(2024, 6, 12, 18, 0), "date_str": "2024-06-12"},
    {"category": "FOMC", "title": "FOMC (Jun 12, 2024)", "dt_ist": dt(2024, 6, 12, 23, 30), "date_str": "2024-06-12"},
    {"category": "BOJ_RATE", "title": "BOJ_RATE (Jun 14, 2024)", "dt_ist": dt(2024, 6, 14, 8, 30), "date_str": "2024-06-14"},
    {"category": "NFP", "title": "NFP (Jul 5, 2024)", "dt_ist": dt(2024, 7, 5, 18, 0), "date_str": "2024-07-05"},
    {"category": "CPI", "title": "CPI (Jul 11, 2024)", "dt_ist": dt(2024, 7, 11, 18, 0), "date_str": "2024-07-11"},
    {"category": "BOJ_RATE", "title": "BOJ_RATE (Jul 31, 2024)", "dt_ist": dt(2024, 7, 31, 8, 30), "date_str": "2024-07-31"},
    {"category": "FOMC", "title": "FOMC (Jul 31, 2024)", "dt_ist": dt(2024, 7, 31, 23, 30), "date_str": "2024-07-31"},
    {"category": "NFP", "title": "NFP (Aug 2, 2024)", "dt_ist": dt(2024, 8, 2, 18, 0), "date_str": "2024-08-02"},
    {"category": "CPI", "title": "CPI (Aug 14, 2024)", "dt_ist": dt(2024, 8, 14, 18, 0), "date_str": "2024-08-14"},
    {"category": "NFP", "title": "NFP (Sep 6, 2024)", "dt_ist": dt(2024, 9, 6, 18, 0), "date_str": "2024-09-06"},
    {"category": "CPI", "title": "CPI (Sep 11, 2024)", "dt_ist": dt(2024, 9, 11, 18, 0), "date_str": "2024-09-11"},
    {"category": "FOMC", "title": "FOMC (Sep 18, 2024)", "dt_ist": dt(2024, 9, 18, 23, 30), "date_str": "2024-09-18"},
    {"category": "BOJ_RATE", "title": "BOJ_RATE (Sep 20, 2024)", "dt_ist": dt(2024, 9, 20, 8, 30), "date_str": "2024-09-20"},
    {"category": "NFP", "title": "NFP (Oct 4, 2024)", "dt_ist": dt(2024, 10, 4, 18, 0), "date_str": "2024-10-04"},
    {"category": "CPI", "title": "CPI (Oct 10, 2024)", "dt_ist": dt(2024, 10, 10, 18, 0), "date_str": "2024-10-10"},
    {"category": "BOJ_RATE", "title": "BOJ_RATE (Oct 31, 2024)", "dt_ist": dt(2024, 10, 31, 8, 30), "date_str": "2024-10-31"},
    {"category": "NFP", "title": "NFP (Nov 1, 2024)", "dt_ist": dt(2024, 11, 1, 18, 0), "date_str": "2024-11-01"},
    {"category": "FOMC", "title": "FOMC (Nov 8, 2024)", "dt_ist": dt(2024, 11, 8, 0, 30), "date_str": "2024-11-08"},
    {"category": "CPI", "title": "CPI (Nov 13, 2024)", "dt_ist": dt(2024, 11, 13, 18, 0), "date_str": "2024-11-13"},
    {"category": "NFP", "title": "NFP (Dec 6, 2024)", "dt_ist": dt(2024, 12, 6, 19, 0), "date_str": "2024-12-06"},
    {"category": "CPI", "title": "CPI (Dec 11, 2024)", "dt_ist": dt(2024, 12, 11, 19, 0), "date_str": "2024-12-11"},
    {"category": "FOMC", "title": "FOMC (Dec 19, 2024)", "dt_ist": dt(2024, 12, 19, 0, 30), "date_str": "2024-12-19"},
    {"category": "BOJ_RATE", "title": "BOJ_RATE (Dec 19, 2024)", "dt_ist": dt(2024, 12, 19, 8, 30), "date_str": "2024-12-19"},
    {"category": "NFP", "title": "NFP (Jan 10, 2025)", "dt_ist": dt(2025, 1, 10, 19, 0), "date_str": "2025-01-10"},
    {"category": "CPI", "title": "CPI (Jan 15, 2025)", "dt_ist": dt(2025, 1, 15, 19, 0), "date_str": "2025-01-15"},
    {"category": "BOJ_RATE", "title": "BOJ_RATE (Jan 24, 2025)", "dt_ist": dt(2025, 1, 24, 8, 30), "date_str": "2025-01-24"},
    {"category": "FOMC", "title": "FOMC (Jan 30, 2025)", "dt_ist": dt(2025, 1, 30, 0, 30), "date_str": "2025-01-30"},
    {"category": "NFP", "title": "NFP (Feb 7, 2025)", "dt_ist": dt(2025, 2, 7, 19, 0), "date_str": "2025-02-07"},
    {"category": "CPI", "title": "CPI (Feb 12, 2025)", "dt_ist": dt(2025, 2, 12, 19, 0), "date_str": "2025-02-12"},
    {"category": "NFP", "title": "NFP (Mar 7, 2025)", "dt_ist": dt(2025, 3, 7, 19, 0), "date_str": "2025-03-07"},
    {"category": "CPI", "title": "CPI (Mar 12, 2025)", "dt_ist": dt(2025, 3, 12, 18, 0), "date_str": "2025-03-12"},
    {"category": "BOJ_RATE", "title": "BOJ_RATE (Mar 19, 2025)", "dt_ist": dt(2025, 3, 19, 8, 30), "date_str": "2025-03-19"},
    {"category": "FOMC", "title": "FOMC (Mar 19, 2025)", "dt_ist": dt(2025, 3, 19, 23, 30), "date_str": "2025-03-19"},
    {"category": "NFP", "title": "NFP (Apr 4, 2025)", "dt_ist": dt(2025, 4, 4, 18, 0), "date_str": "2025-04-04"},
    {"category": "CPI", "title": "CPI (Apr 10, 2025)", "dt_ist": dt(2025, 4, 10, 18, 0), "date_str": "2025-04-10"},
    {"category": "BOJ_RATE", "title": "BOJ_RATE (May 1, 2025)", "dt_ist": dt(2025, 5, 1, 8, 30), "date_str": "2025-05-01"},
    {"category": "NFP", "title": "NFP (May 2, 2025)", "dt_ist": dt(2025, 5, 2, 18, 0), "date_str": "2025-05-02"},
    {"category": "FOMC", "title": "FOMC (May 7, 2025)", "dt_ist": dt(2025, 5, 7, 23, 30), "date_str": "2025-05-07"},
    {"category": "CPI", "title": "CPI (May 13, 2025)", "dt_ist": dt(2025, 5, 13, 18, 0), "date_str": "2025-05-13"},
    {"category": "NFP", "title": "NFP (Jun 6, 2025)", "dt_ist": dt(2025, 6, 6, 18, 0), "date_str": "2025-06-06"},
    {"category": "CPI", "title": "CPI (Jun 11, 2025)", "dt_ist": dt(2025, 6, 11, 18, 0), "date_str": "2025-06-11"},
    {"category": "BOJ_RATE", "title": "BOJ_RATE (Jun 17, 2025)", "dt_ist": dt(2025, 6, 17, 8, 30), "date_str": "2025-06-17"},
    {"category": "FOMC", "title": "FOMC (Jun 18, 2025)", "dt_ist": dt(2025, 6, 18, 23, 30), "date_str": "2025-06-18"},
    {"category": "NFP", "title": "NFP (Jul 3, 2025)", "dt_ist": dt(2025, 7, 3, 18, 0), "date_str": "2025-07-03"},
    {"category": "CPI", "title": "CPI (Jul 15, 2025)", "dt_ist": dt(2025, 7, 15, 18, 0), "date_str": "2025-07-15"},
    {"category": "FOMC", "title": "FOMC (Jul 30, 2025)", "dt_ist": dt(2025, 7, 30, 23, 30), "date_str": "2025-07-30"},
    {"category": "BOJ_RATE", "title": "BOJ_RATE (Jul 31, 2025)", "dt_ist": dt(2025, 7, 31, 8, 30), "date_str": "2025-07-31"},
    {"category": "NFP", "title": "NFP (Aug 1, 2025)", "dt_ist": dt(2025, 8, 1, 18, 0), "date_str": "2025-08-01"},
    {"category": "CPI", "title": "CPI (Aug 12, 2025)", "dt_ist": dt(2025, 8, 12, 18, 0), "date_str": "2025-08-12"},
    {"category": "NFP", "title": "NFP (Sep 5, 2025)", "dt_ist": dt(2025, 9, 5, 18, 0), "date_str": "2025-09-05"},
    {"category": "CPI", "title": "CPI (Sep 11, 2025)", "dt_ist": dt(2025, 9, 11, 18, 0), "date_str": "2025-09-11"},
    {"category": "FOMC", "title": "FOMC (Sep 17, 2025)", "dt_ist": dt(2025, 9, 17, 23, 30), "date_str": "2025-09-17"},
    {"category": "BOJ_RATE", "title": "BOJ_RATE (Sep 19, 2025)", "dt_ist": dt(2025, 9, 19, 8, 30), "date_str": "2025-09-19"},
    {"category": "CPI", "title": "CPI (Oct 24, 2025)", "dt_ist": dt(2025, 10, 24, 18, 0), "date_str": "2025-10-24"},
    {"category": "FOMC", "title": "FOMC (Oct 29, 2025)", "dt_ist": dt(2025, 10, 29, 23, 30), "date_str": "2025-10-29"},
    {"category": "BOJ_RATE", "title": "BOJ_RATE (Oct 30, 2025)", "dt_ist": dt(2025, 10, 30, 8, 30), "date_str": "2025-10-30"},
    {"category": "NFP", "title": "NFP (Nov 20, 2025)", "dt_ist": dt(2025, 11, 20, 19, 0), "date_str": "2025-11-20"},
    {"category": "FOMC", "title": "FOMC (Dec 11, 2025)", "dt_ist": dt(2025, 12, 11, 0, 30), "date_str": "2025-12-11"},
    {"category": "NFP", "title": "NFP (Dec 16, 2025)", "dt_ist": dt(2025, 12, 16, 19, 0), "date_str": "2025-12-16"},
    {"category": "NFP", "title": "NFP (Dec 16, 2025)", "dt_ist": dt(2025, 12, 16, 19, 0), "date_str": "2025-12-16"},
    {"category": "CPI", "title": "CPI (Dec 18, 2025)", "dt_ist": dt(2025, 12, 18, 19, 0), "date_str": "2025-12-18"},
    {"category": "BOJ_RATE", "title": "BOJ_RATE (Dec 19, 2025)", "dt_ist": dt(2025, 12, 19, 8, 30), "date_str": "2025-12-19"},
    {"category": "NFP", "title": "NFP (Jan 9, 2026)", "dt_ist": dt(2026, 1, 9, 19, 0), "date_str": "2026-01-09"},
    {"category": "CPI", "title": "CPI (Jan 13, 2026)", "dt_ist": dt(2026, 1, 13, 19, 0), "date_str": "2026-01-13"},
    {"category": "BOJ_RATE", "title": "BOJ_RATE (Jan 23, 2026)", "dt_ist": dt(2026, 1, 23, 8, 30), "date_str": "2026-01-23"},
    {"category": "FOMC", "title": "FOMC (Jan 29, 2026)", "dt_ist": dt(2026, 1, 29, 0, 30), "date_str": "2026-01-29"},
    {"category": "NFP", "title": "NFP (Feb 11, 2026)", "dt_ist": dt(2026, 2, 11, 19, 0), "date_str": "2026-02-11"},
    {"category": "CPI", "title": "CPI (Feb 13, 2026)", "dt_ist": dt(2026, 2, 13, 19, 0), "date_str": "2026-02-13"},
    {"category": "NFP", "title": "NFP (Mar 6, 2026)", "dt_ist": dt(2026, 3, 6, 19, 0), "date_str": "2026-03-06"},
    {"category": "CPI", "title": "CPI (Mar 11, 2026)", "dt_ist": dt(2026, 3, 11, 18, 0), "date_str": "2026-03-11"},
    {"category": "FOMC", "title": "FOMC (Mar 18, 2026)", "dt_ist": dt(2026, 3, 18, 23, 30), "date_str": "2026-03-18"},
    {"category": "BOJ_RATE", "title": "BOJ_RATE (Mar 19, 2026)", "dt_ist": dt(2026, 3, 19, 8, 30), "date_str": "2026-03-19"},
    {"category": "NFP", "title": "NFP (Apr 3, 2026)", "dt_ist": dt(2026, 4, 3, 18, 0), "date_str": "2026-04-03"},
    {"category": "CPI", "title": "CPI (Apr 10, 2026)", "dt_ist": dt(2026, 4, 10, 18, 0), "date_str": "2026-04-10"},
    {"category": "BOJ_RATE", "title": "BOJ_RATE (Apr 28, 2026)", "dt_ist": dt(2026, 4, 28, 8, 30), "date_str": "2026-04-28"},
    {"category": "FOMC", "title": "FOMC (Apr 29, 2026)", "dt_ist": dt(2026, 4, 29, 23, 30), "date_str": "2026-04-29"},
    {"category": "NFP", "title": "NFP (May 8, 2026)", "dt_ist": dt(2026, 5, 8, 18, 0), "date_str": "2026-05-08"},
    {"category": "CPI", "title": "CPI (May 12, 2026)", "dt_ist": dt(2026, 5, 12, 18, 0), "date_str": "2026-05-12"},
    {"category": "NFP", "title": "NFP (Jun 5, 2026)", "dt_ist": dt(2026, 6, 5, 18, 0), "date_str": "2026-06-05"},
    {"category": "CPI", "title": "CPI (Jun 10, 2026)", "dt_ist": dt(2026, 6, 10, 18, 0), "date_str": "2026-06-10"},
    {"category": "BOJ_RATE", "title": "BOJ_RATE (Jun 16, 2026)", "dt_ist": dt(2026, 6, 16, 8, 30), "date_str": "2026-06-16"},
    {"category": "FOMC", "title": "FOMC (Jun 17, 2026)", "dt_ist": dt(2026, 6, 17, 23, 30), "date_str": "2026-06-17"},
    {"category": "NFP", "title": "NFP (Jul 2, 2026)", "dt_ist": dt(2026, 7, 2, 18, 0), "date_str": "2026-07-02"},
    {"category": "CPI", "title": "CPI (Jul 14, 2026)", "dt_ist": dt(2026, 7, 14, 18, 0), "date_str": "2026-07-14"},
    {"category": "FOMC", "title": "FOMC (Jul 29, 2026)", "dt_ist": dt(2026, 7, 29, 23, 30), "date_str": "2026-07-29"},
    {"category": "BOJ_RATE", "title": "BOJ_RATE (Jul 31, 2026)", "dt_ist": dt(2026, 7, 31, 8, 30), "date_str": "2026-07-31"},
    {"category": "NFP", "title": "NFP (Aug 7, 2026)", "dt_ist": dt(2026, 8, 7, 18, 0), "date_str": "2026-08-07"},
    {"category": "CPI", "title": "CPI (Aug 12, 2026)", "dt_ist": dt(2026, 8, 12, 18, 0), "date_str": "2026-08-12"},
    {"category": "NFP", "title": "NFP (Sep 4, 2026)", "dt_ist": dt(2026, 9, 4, 18, 0), "date_str": "2026-09-04"},
    {"category": "CPI", "title": "CPI (Sep 11, 2026)", "dt_ist": dt(2026, 9, 11, 18, 0), "date_str": "2026-09-11"},
    {"category": "FOMC", "title": "FOMC (Sep 16, 2026)", "dt_ist": dt(2026, 9, 16, 23, 30), "date_str": "2026-09-16"},
    {"category": "NFP", "title": "NFP (Oct 2, 2026)", "dt_ist": dt(2026, 10, 2, 18, 0), "date_str": "2026-10-02"},
    {"category": "CPI", "title": "CPI (Oct 14, 2026)", "dt_ist": dt(2026, 10, 14, 18, 0), "date_str": "2026-10-14"},
    {"category": "FOMC", "title": "FOMC (Oct 28, 2026)", "dt_ist": dt(2026, 10, 28, 23, 30), "date_str": "2026-10-28"},
    {"category": "BOJ_RATE", "title": "BOJ_RATE (Oct 30, 2026)", "dt_ist": dt(2026, 10, 30, 8, 30), "date_str": "2026-10-30"},
    {"category": "BOE_RATE", "title": "BOE Rate Decision (Feb 1, 2024)", "dt_ist": dt(2024, 2, 1, 17, 30), "date_str": "2024-02-01"},
    {"category": "BOE_RATE", "title": "BOE Rate Decision (Mar 21, 2024)", "dt_ist": dt(2024, 3, 21, 17, 30), "date_str": "2024-03-21"},
    {"category": "BOE_RATE", "title": "BOE Rate Decision (May 9, 2024)", "dt_ist": dt(2024, 5, 9, 16, 30), "date_str": "2024-05-09"},
    {"category": "BOE_RATE", "title": "BOE Rate Decision (Jun 20, 2024)", "dt_ist": dt(2024, 6, 20, 16, 30), "date_str": "2024-06-20"},
    {"category": "BOE_RATE", "title": "BOE Rate Decision (Aug 1, 2024)", "dt_ist": dt(2024, 8, 1, 16, 30), "date_str": "2024-08-01"},
    {"category": "BOE_RATE", "title": "BOE Rate Decision (Sep 19, 2024)", "dt_ist": dt(2024, 9, 19, 16, 30), "date_str": "2024-09-19"},
    {"category": "BOE_RATE", "title": "BOE Rate Decision (Nov 7, 2024)", "dt_ist": dt(2024, 11, 7, 17, 30), "date_str": "2024-11-07"},
    {"category": "BOE_RATE", "title": "BOE Rate Decision (Dec 19, 2024)", "dt_ist": dt(2024, 12, 19, 17, 30), "date_str": "2024-12-19"},
    {"category": "BOE_RATE", "title": "BOE Rate Decision (Feb 6, 2025)", "dt_ist": dt(2025, 2, 6, 17, 30), "date_str": "2025-02-06"},
    {"category": "BOE_RATE", "title": "BOE Rate Decision (Mar 20, 2025)", "dt_ist": dt(2025, 3, 20, 17, 30), "date_str": "2025-03-20"},
    {"category": "BOE_RATE", "title": "BOE Rate Decision (May 8, 2025)", "dt_ist": dt(2025, 5, 8, 16, 30), "date_str": "2025-05-08"},
    {"category": "BOE_RATE", "title": "BOE Rate Decision (Jun 19, 2025)", "dt_ist": dt(2025, 6, 19, 16, 30), "date_str": "2025-06-19"},
    {"category": "BOE_RATE", "title": "BOE Rate Decision (Aug 7, 2025)", "dt_ist": dt(2025, 8, 7, 16, 30), "date_str": "2025-08-07"},
    {"category": "BOE_RATE", "title": "BOE Rate Decision (Sep 18, 2025)", "dt_ist": dt(2025, 9, 18, 16, 30), "date_str": "2025-09-18"},
    {"category": "BOE_RATE", "title": "BOE Rate Decision (Nov 6, 2025)", "dt_ist": dt(2025, 11, 6, 17, 30), "date_str": "2025-11-06"},
    {"category": "BOE_RATE", "title": "BOE Rate Decision (Dec 18, 2025)", "dt_ist": dt(2025, 12, 18, 17, 30), "date_str": "2025-12-18"},
    {"category": "BOE_RATE", "title": "BOE Rate Decision (Feb 5, 2026)", "dt_ist": dt(2026, 2, 5, 17, 30), "date_str": "2026-02-05"},
    {"category": "BOE_RATE", "title": "BOE Rate Decision (Mar 19, 2026)", "dt_ist": dt(2026, 3, 19, 17, 30), "date_str": "2026-03-19"},
    {"category": "BOE_RATE", "title": "BOE Rate Decision (May 7, 2026)", "dt_ist": dt(2026, 5, 7, 16, 30), "date_str": "2026-05-07"},
    {"category": "BOE_RATE", "title": "BOE Rate Decision (Jun 18, 2026)", "dt_ist": dt(2026, 6, 18, 16, 30), "date_str": "2026-06-18"},
    {"category": "BOE_RATE", "title": "BOE Rate Decision (Aug 6, 2026)", "dt_ist": dt(2026, 8, 6, 16, 30), "date_str": "2026-08-06"},
    {"category": "BOE_RATE", "title": "BOE Rate Decision (Sep 17, 2026)", "dt_ist": dt(2026, 9, 17, 16, 30), "date_str": "2026-09-17"},
    {"category": "BOE_RATE", "title": "BOE Rate Decision (Nov 5, 2026)", "dt_ist": dt(2026, 11, 5, 17, 30), "date_str": "2026-11-05"},
    {"category": "BOE_RATE", "title": "BOE Rate Decision (Dec 17, 2026)", "dt_ist": dt(2026, 12, 17, 17, 30), "date_str": "2026-12-17"},
    {"category": "UK_CPI", "title": "UK CPI (Oct 21, 2026)", "dt_ist": dt(2026, 10, 21, 11, 30), "date_str": "2026-10-21"},
    {"category": "UK_CPI", "title": "UK CPI (Nov 18, 2026)", "dt_ist": dt(2026, 11, 18, 12, 30), "date_str": "2026-11-18"},
]

def get_event_symbols(category: str, title: str = "") -> list:
    """Returns list of symbols affected by a given news event."""
    c = str(category).upper()
    t = str(title).upper()
    if "BOJ" in c or "BOJ" in t or "BANK OF JAPAN" in t or "JPY" in t:
        return ["USDJPY"]
    elif "BOE" in c or "BOE" in t or "BANK OF ENGLAND" in t or "UK" in c or "UK" in t or "GBP" in t:
        return ["GBPUSD"]
    elif "ECB" in c or "ECB" in t or "EUROPEAN CENTRAL BANK" in t or "ECB_RATE" in c or ("MONETARY POLICY" in t and ("EUR" in t or "ECB" in t or "EURO" in t)):
        return ["EURUSD"]
    elif c in ["NFP", "CPI", "FOMC"]:
        return ["USDJPY", "GBPUSD", "XAUUSD", "EURUSD"]
    return ["USDJPY", "GBPUSD", "XAUUSD", "EURUSD"]

# Attach symbol metadata to all historical events
for ev in HISTORICAL_NEWS_SCHEDULE:
    if "symbols" not in ev:
        ev["symbols"] = get_event_symbols(ev["category"], ev["title"])

_NEWS_CACHE: Dict[str, list] = {}

def get_news_events_for_window(start_date: datetime.date, end_date: datetime.date, symbol: Optional[str] = None) -> list:
    """
    Returns high-impact economic news events (NFP, CPI, FOMC, BOJ Rate, BOE Rate, UK CPI) for any target window.
    Strictly enforces date boundaries [start_date 00:00 to end_date 23:59] so old passed news never leaks into other dates!
    If symbol is specified, filters events to only those relevant to that specific instrument:
    - USDJPY: BOJ_RATE, NFP, CPI, FOMC
    - GBPUSD: BOE_RATE, UK_CPI, UK_GDP, NFP, CPI, FOMC
    - XAUUSD: NFP, CPI, FOMC
    """
    cache_key = f"{start_date}_{end_date}_{symbol or 'ALL'}"
    if cache_key in _NEWS_CACHE:
        return _NEWS_CACHE[cache_key]

    matched_events = []
    seen_keys = set()

    s_dt = dt(start_date.year, start_date.month, start_date.day, 0, 0)
    e_dt = dt(end_date.year, end_date.month, end_date.day, 23, 59, 59)

    # 1. Check Historical Institutional Archive
    for ev in HISTORICAL_NEWS_SCHEDULE:
        ev_dt = ev["dt_ist"]
        if s_dt <= ev_dt <= e_dt:
            ev_symbols = ev.get("symbols", get_event_symbols(ev["category"], ev["title"]))
            if symbol and symbol.upper() not in [s.upper() for s in ev_symbols]:
                continue
            key = f"{ev['category']}_{ev_dt.strftime('%Y%m%d%H%M')}"
            if key not in seen_keys:
                seen_keys.add(key)
                ev_copy = dict(ev)
                ev_copy["symbols"] = ev_symbols
                matched_events.append(ev_copy)

    # 2. Check Real-Time Live Feed if window includes today or future dates
    today = datetime.date.today()
    if end_date >= today:
        live_start = max(start_date, today - timedelta(days=1))
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

        # Primary Live Source: FinanceCalendar API
        try:
            url = f"https://www.financecalendar.com/wp-json/fc/v1/calendar?from={live_start}&to={end_date + timedelta(days=2)}&impact=high"
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code == 200:
                for ev in r.json().get("events", []):
                    name = (ev.get("name") or "").lower()
                    title = (ev.get("title") or "").lower()
                    has_us = bool(re.search(r'\b(us|usa|united states)\b', name) or re.search(r'\b(us|usa|united states)\b', title))
                    is_nfp = ("nfp" in name or "non-farm" in name or "jobs report" in name) and has_us
                    is_cpi = ("cpi" in name or "cpi" in title) and has_us
                    is_fomc = "fomc" in name or "fomc" in title or "federal funds rate" in name
                    is_boj = "bank of japan" in name or "boj" in name or "bank of japan" in title
                    is_boe = "bank of england" in name or "boe" in name or "official bank rate" in name or "monetary policy" in name
                    is_uk_cpi = ("cpi" in name or "cpi" in title) and ("uk" in name or "united kingdom" in name or "britain" in name)
                    is_ecb = ("european central bank" in name or "ecb" in name or "main refinancing" in name or "monetary policy" in name) and ("eur" in name or "euro" in name or "eu" in name or "ecb" in name or "ecb" in title)

                    if is_nfp or is_cpi or is_fomc or is_boj or is_boe or is_uk_cpi or is_ecb:
                        cat = "NFP" if is_nfp else ("CPI" if is_cpi else ("FOMC" if is_fomc else ("BOJ_RATE" if is_boj else ("BOE_RATE" if is_boe else ("ECB_RATE" if is_ecb else "UK_CPI")))))
                        time_utc_str = ev.get("time_utc")
                        if time_utc_str:
                            ev_utc = dt.fromisoformat(time_utc_str)
                            ev_ist = ev_utc.astimezone(timezone(timedelta(hours=5, minutes=30))).replace(tzinfo=None)
                        else:
                            d_val = dt.strptime(ev.get("date"), "%Y-%m-%d").date()
                            ev_ist = dt(d_val.year, d_val.month, d_val.day, 18, 0)

                        # STRICT WINDOW CHECK: Only accept events inside requested window
                        if not (s_dt <= ev_ist <= e_dt):
                            continue

                        ev_symbols = get_event_symbols(cat, ev.get("name", cat))
                        if symbol and symbol.upper() not in [s.upper() for s in ev_symbols]:
                            continue

                        key = f"{cat}_{ev_ist.strftime('%Y%m%d%H%M')}"
                        if key not in seen_keys:
                            seen_keys.add(key)
                            matched_events.append({
                                "category": cat,
                                "title": ev.get("name", cat),
                                "dt_ist": ev_ist,
                                "date_str": ev_ist.strftime("%Y-%m-%d"),
                                "symbols": ev_symbols
                            })
        except Exception:
            pass

        # Secondary Live Fallback: Forex Factory Feed (Strictly bounded)
        if not any(e["dt_ist"].date() >= today for e in matched_events):
            try:
                ff_url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
                r = requests.get(ff_url, headers=headers, timeout=5)
                if r.status_code == 200:
                    for ev in r.json():
                        if ev.get("impact") != "High":
                            continue
                        country = ev.get("country", "")
                        title = (ev.get("title") or "").lower()
                        is_nfp = (country == "USD" and ("non-farm" in title or "nfp" in title))
                        is_cpi = (country == "USD" and "cpi" in title)
                        is_fomc = (country == "USD" and ("fomc" in title or "federal funds rate" in title))
                        is_boj = (country == "JPY" and ("policy rate" in title or "monetary policy" in title or "boj" in title))
                        is_boe = (country == "GBP" and ("rate" in title or "monetary policy" in title or "bank of england" in title or "gdp" in title))
                        is_uk_cpi = (country == "GBP" and "cpi" in title)
                        is_ecb = (country in ["EUR", "EU"] and ("monetary policy" in title or "rate" in title or "ecb" in title or "interest rate" in title or "deposit facility" in title))

                        if is_nfp or is_cpi or is_fomc or is_boj or is_boe or is_uk_cpi or is_ecb:
                            cat = "NFP" if is_nfp else ("CPI" if is_cpi else ("FOMC" if is_fomc else ("BOJ_RATE" if is_boj else ("BOE_RATE" if is_boe else ("ECB_RATE" if is_ecb else "UK_CPI")))))
                            dt_str = ev.get("date")
                            ev_dt = dt.fromisoformat(dt_str)
                            ev_ist = ev_dt.astimezone(timezone(timedelta(hours=5, minutes=30))).replace(tzinfo=None)

                            # STRICT WINDOW CHECK: Only accept events inside requested window
                            if not (s_dt <= ev_ist <= e_dt):
                                continue

                            ev_symbols = get_event_symbols(cat, ev.get("title", cat))
                            if symbol and symbol.upper() not in [s.upper() for s in ev_symbols]:
                                continue

                            key = f"{cat}_{ev_ist.strftime('%Y%m%d%H%M')}"
                            if key not in seen_keys:
                                seen_keys.add(key)
                                matched_events.append({
                                    "category": cat,
                                    "title": ev.get("title", cat),
                                    "dt_ist": ev_ist,
                                    "date_str": ev_ist.strftime("%Y-%m-%d"),
                                    "symbols": ev_symbols
                                })
            except Exception:
                pass

    matched_events.sort(key=lambda x: x["dt_ist"])
    _NEWS_CACHE[cache_key] = matched_events
    return matched_events

# ==============================================================================
# TRADE LIFECYCLE EVALUATOR (M1 PRECISION & LIVE OUTCOMES)
# ==============================================================================
def evaluate_trade_lifecycle(trade_info: dict, risk_usd: float = 300.0, fee_override: Optional[float] = None) -> dict:
    """
    Evaluates whether trade hit TP, SL, or is currently OPEN.
    Uses precise 1-minute (M1) candles for exact exit timing down to the minute in IST.
    Format: YYYY-MM-DDTHH:MM (Exact Indian Standard Time)
    Auto-exits 5 minutes before scheduled high-impact news releases (NFP, CPI, FOMC, BOJ).
    """
    symbol = trade_info["symbol"]
    direction = trade_info["direction"].lower()
    entry_price = float(trade_info["entry_price"])
    sl_price = float(trade_info["sl_price"])
    tp_price = float(trade_info["tp_price"])
    
    trade_date = trade_info.get("date")
    if isinstance(trade_date, str):
        try:
            trade_date = dt.strptime(trade_date[:10], "%Y-%m-%d").date()
        except Exception:
            trade_date = datetime.date.today()
    elif not trade_date:
        trade_date = datetime.date.today()
        
    entry_time_str = trade_info.get("entry_time_ist")
    quantity = calculate_risk_quantity(symbol, entry_price, sl_price, risk_usd=risk_usd)
    inst = "EUR_USD" if "EUR" in symbol.upper() else ("USD_JPY" if "JPY" in symbol.upper() else ("GBP_USD" if "GBP" in symbol.upper() else "XAU_USD"))
    candles_df = fetch_oanda_candles(inst, "M15", trade_date, end_date=trade_date + timedelta(days=2))
    
    status = "open"
    exit_price = get_latest_market_price(symbol)
    exit_time_str = None
    exit_reason = None

    # Fetch live real-time high-impact economic news events tailored to symbol
    realtime_news = get_news_events_for_window(trade_date, trade_date + timedelta(days=2), symbol=symbol)
    
    if not candles_df.empty:
        if not entry_time_str:
            if symbol == "GBPUSD":
                entry_time_str = f"{trade_date.strftime('%Y-%m-%d')}T12:15"
            elif symbol == "XAUUSD":
                entry_time_str = f"{trade_date.strftime('%Y-%m-%d')}T06:30"
            elif symbol == "USDJPY":
                entry_time_str = f"{trade_date.strftime('%Y-%m-%d')}T13:30"
            else:
                entry_time_str = f"{trade_date.strftime('%Y-%m-%d')}T12:00"

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
                    
    # If still open, populate with current live IST timestamp and live market price
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
    fee = get_trade_fee(symbol, fee_override)
    if direction == "long":
        gross_pnl = (exit_price - entry_price) * quantity
    else:
        gross_pnl = (entry_price - exit_price) * quantity
        
    net_pnl = gross_pnl - fee
    decimals = 5 if "GBP" in symbol else (3 if "JPY" in symbol else 2)
        
    return {
        "status": status,
        "entry_time_str": entry_time_str,
        "exit_price": round(exit_price, decimals),
        "exit_time_str": exit_time_str,
        "quantity": quantity,
        "gross_pnl": round(gross_pnl, 2),
        "fee": fee,
        "net_pnl": round(net_pnl, 2),
        "exit_reason": exit_reason
    }

# ==============================================================================
# STRATEGY 1: USDJPY SELFSWEEP
# ==============================================================================
def run_usdjpy_strategy(target_date: datetime.date) -> dict:
    """
    USDJPY Selfsweep Strategy:
    - M15 extremes rejection in Asia & London sessions
    - Strict Champion Rule: Tuesdays excluded with transparent reasoning
    - 1:5.0 RRR Target, No BE
    - SL Range: 0.015% to 0.154%
    """
    result = {
        "strategy_name": "USDJPY SELFSWEEP",
        "strategy_id": STRAT1_ID,
        "symbol": "USDJPY",
        "date": target_date.strftime("%Y-%m-%d"),
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
    
    is_tuesday = (target_date.weekday() == 1)
    day_df = pd.DataFrame()
    live_df = fetch_oanda_candles("USD_JPY", "M15", target_date)
    if not live_df.empty:
        day_df = live_df[live_df['dt_ist'].dt.date == target_date].sort_values('dt_ist').reset_index(drop=True)
        result["data_source"] = "OANDA Live Feed"
        
    if day_df.empty:
        csv_file = "USDJPY_M15_2024-03_to_2026-09.csv"
        if os.path.exists(csv_file):
            df = pd.read_csv(csv_file)
            df['dt_ist'] = pd.to_datetime(df['time_ist'])
            day_df = df[df['dt_ist'].dt.date == target_date].sort_values('dt_ist').reset_index(drop=True)
            result["data_source"] = "Local Archive CSV"
            
    if day_df.empty or len(day_df) < 4:
        if is_tuesday:
            result["status"] = "Skipped (Tuesday Rule)"
            result["details"] = "Tuesday is strictly excluded by USDJPY Champion strategy rules (No Tuesday filter). No live trade logged."
            return result
        result["status"] = "No Session Data"
        result["details"] = f"No M15 candles available for {target_date}."
        return result
        
    try:
        sample_utc = pd.to_datetime(day_df['time_utc'].iloc[0])
        is_summer = is_us_dst(sample_utc)
        t_col = day_df['dt_ist'].dt.time
        
        cond_asia = (t_col >= time(5, 30)) & (t_col <= time(9, 0)) if is_summer else (t_col >= time(6, 30)) & (t_col <= time(10, 0))
        cond_london = (t_col >= time(11, 30)) & (t_col <= time(14, 0)) if is_summer else (t_col >= time(12, 30)) & (t_col <= time(15, 0))
        
        weekday = target_date.weekday()
        is_wed_thu = (weekday in [2, 3])
        is_mon_fri = (weekday in [0, 4])

        def evaluate_entry_candidate(c_c, prev_c, init_sl):
            body = abs(c_c - prev_c)
            risk_points = abs(c_c - init_sl)
            sl_pct = (risk_points / c_c) * 100.0
            sl_pct_rounded = round(sl_pct, 3)
            sl_in_range = (0.045 <= sl_pct_rounded <= 0.154)

            if is_wed_thu:
                if round(body, 3) >= 0.001 and sl_in_range:
                    return 'VALID_ENTER', sl_pct, body
                else:
                    return 'INVALIDATED', sl_pct, body
            elif is_mon_fri:
                if round(body, 3) >= 0.005:
                    if sl_in_range:
                        return 'VALID_ENTER', sl_pct, body
                    else:
                        return 'INVALIDATED', sl_pct, body
                else:
                    if sl_in_range:
                        return 'INVALIDATED', sl_pct, body
                    else:
                        return 'WAIT_NEXT', sl_pct, body
            else:
                if sl_in_range:
                    return 'VALID_ENTER', sl_pct, body
                return 'INVALIDATED', sl_pct, body

        def extend_sl_new(entry, initial_sl, direction):
            risk_points = abs(entry - initial_sl)
            sl_pct = (risk_points / entry) * 100.0
            sl_pct_rounded = round(sl_pct, 3)
            if sl_pct_rounded < 0.045 or sl_pct_rounded > 0.154:
                return None, sl_pct
            ext_sl = initial_sl
            if sl_pct < 0.055:
                ext_sl = entry * (1.0 - 0.00055) if direction == 'long' else entry * (1.0 + 0.00055)
            elif sl_pct < 0.065:
                ext_sl = initial_sl - 0.006 if direction == 'long' else initial_sl + 0.006
            elif sl_pct < 0.075:
                ext_sl = initial_sl - 0.007 if direction == 'long' else initial_sl + 0.007
            elif sl_pct < 0.085:
                ext_sl = initial_sl - 0.014 if direction == 'long' else initial_sl + 0.014
            elif sl_pct < 0.095:
                ext_sl = initial_sl - 0.015 if direction == 'long' else initial_sl + 0.015
            elif sl_pct < 0.105:
                ext_sl = initial_sl - 0.016 if direction == 'long' else initial_sl + 0.016
            elif sl_pct < 0.115:
                ext_sl = initial_sl - 0.017 if direction == 'long' else initial_sl + 0.017
            elif sl_pct < 0.125:
                ext_sl = initial_sl - 0.018 if direction == 'long' else initial_sl + 0.018
            elif sl_pct < 0.135:
                ext_sl = initial_sl - 0.019 if direction == 'long' else initial_sl + 0.019
            elif sl_pct < 0.145:
                ext_sl = initial_sl - 0.020 if direction == 'long' else initial_sl + 0.020
            else:
                ext_sl = initial_sl - 0.021 if direction == 'long' else initial_sl + 0.021
            return ext_sl, sl_pct

        for s_name, cond in [("ASIA", cond_asia), ("LONDON", cond_london)]:
            s_df = day_df[cond].reset_index(drop=True)
            N = len(s_df)
            if N < 4: continue

            opens, highs, lows, closes = s_df['open'].values, s_df['high'].values, s_df['low'].values, s_df['close'].values

            # Long Check
            ext_low, ceiling, state = lows[0], highs[0], 'SEEK_CC'
            sweep_ext = None
            for i in range(1, N):
                c_o, c_h, c_l, c_c = opens[i], highs[i], lows[i], closes[i]
                prev_c = closes[i-1]
                if state == 'SEEK_CC':
                    if c_l <= ext_low:
                        ext_low, ceiling = c_l, c_h
                    else:
                        if c_c > ceiling:
                            state = 'WAIT_OPPOSITE'
                        ceiling = max(ceiling, c_h)
                elif state == 'WAIT_OPPOSITE':
                    if c_l <= ext_low:
                        ext_low, ceiling, state = c_l, c_h, 'SEEK_CC'
                    else:
                        ceiling = max(ceiling, c_h)
                        if c_c < c_o:  # Bearish opposite candle formed before level touch
                            state = 'WAIT_SWEEP'
                elif state == 'WAIT_SWEEP':
                    if c_l <= ext_low - 0.001 + 1e-9:
                        if c_c <= ext_low + 1e-9:
                            ext_low, ceiling, state = c_l, c_h, 'SEEK_CC'
                        else:
                            sweep_ext = c_l
                            if c_c > c_o:
                                decision, sl_pct, body = evaluate_entry_candidate(c_c, prev_c, sweep_ext)
                                if decision == 'VALID_ENTER':
                                    entry = c_c
                                    init_sl = sweep_ext
                                    if is_tuesday:
                                        result.update({
                                            "status": "Skipped (Tuesday Rule)",
                                            "details": f"Setup formed ({s_name} Long @ {entry:.3f}), but Tuesdays are strictly excluded from live execution by strategy rules."
                                        })
                                        return result
                                    ext_sl, _ = extend_sl_new(entry, init_sl, 'long')
                                    risk = abs(entry - ext_sl)
                                    tp = entry + 5.0 * risk
                                    entry_close_ist = s_df.iloc[i]['dt_ist'] + timedelta(minutes=15)
                                    entry_t_str = entry_close_ist.strftime("%Y-%m-%dT%H:%M")
                                    result.update({
                                        "direction": "long",
                                        "entry_price": round(entry, 3),
                                        "entry_time_ist": entry_t_str,
                                        "sl_price": round(ext_sl, 3),
                                        "tp_price": round(tp, 3),
                                        "sl_percentage": round(sl_pct, 3),
                                        "tp_percentage": round(sl_pct * 5.0, 3),
                                        "status": f"Active Signal ({s_name} Long)",
                                        "details": f"Confirmed M15 Selfsweep in {s_name} session (1:5.0 RRR, upgraded SL extension, day-of-week entry engine)."
                                    })
                                    return result
                                elif decision == 'WAIT_NEXT':
                                    state = 'WAIT_BULLISH'
                                else:
                                    ext_low, ceiling, state = c_l, c_h, 'SEEK_CC'
                            else:
                                state = 'WAIT_BULLISH'
                    elif c_l <= ext_low + 1e-9:
                        sweep_ext = c_l
                        state = 'WAIT_SWEEP_AFTER_TAP'
                    else:
                        ceiling = max(ceiling, c_h)
                elif state == 'WAIT_SWEEP_AFTER_TAP':
                    if c_c < ext_low:
                        ext_low, ceiling, state = min(sweep_ext, c_l), c_h, 'SEEK_CC'
                    else:
                        if c_l <= ext_low - 0.001 + 1e-9:
                            if c_c <= ext_low + 1e-9:
                                ext_low, ceiling, state = c_l, c_h, 'SEEK_CC'
                            else:
                                sweep_ext = min(sweep_ext, c_l)
                                if c_c > c_o:
                                    decision, sl_pct, body = evaluate_entry_candidate(c_c, prev_c, sweep_ext)
                                    if decision == 'VALID_ENTER':
                                        entry = c_c
                                        init_sl = sweep_ext
                                        if is_tuesday:
                                            result.update({
                                                "status": "Skipped (Tuesday Rule)",
                                                "details": f"Setup formed ({s_name} Long @ {entry:.3f}), but Tuesdays are strictly excluded from live execution by strategy rules."
                                            })
                                            return result
                                        ext_sl, _ = extend_sl_new(entry, init_sl, 'long')
                                        risk = abs(entry - ext_sl)
                                        tp = entry + 5.0 * risk
                                        entry_close_ist = s_df.iloc[i]['dt_ist'] + timedelta(minutes=15)
                                        entry_t_str = entry_close_ist.strftime("%Y-%m-%dT%H:%M")
                                        result.update({
                                            "direction": "long",
                                            "entry_price": round(entry, 3),
                                            "entry_time_ist": entry_t_str,
                                            "sl_price": round(ext_sl, 3),
                                            "tp_price": round(tp, 3),
                                            "sl_percentage": round(sl_pct, 3),
                                            "tp_percentage": round(sl_pct * 5.0, 3),
                                            "status": f"Active Signal ({s_name} Long)",
                                            "details": f"Confirmed M15 Selfsweep in {s_name} session (1:5.0 RRR, upgraded SL extension, day-of-week entry engine)."
                                        })
                                        return result
                                    elif decision == 'WAIT_NEXT':
                                        state = 'WAIT_BULLISH'
                                    else:
                                        ext_low, ceiling, state = c_l, c_h, 'SEEK_CC'
                                else:
                                    state = 'WAIT_BULLISH'
                        else:
                            sweep_ext = min(sweep_ext, c_l)
                elif state == 'WAIT_BULLISH':
                    if c_c < sweep_ext:
                        ext_low, ceiling, state = min(sweep_ext, c_l), c_h, 'SEEK_CC'
                    else:
                        sweep_ext = min(sweep_ext, c_l)
                        if c_c > c_o:
                            decision, sl_pct, body = evaluate_entry_candidate(c_c, prev_c, sweep_ext)
                            if decision == 'VALID_ENTER':
                                entry = c_c
                                init_sl = sweep_ext
                                if is_tuesday:
                                    result.update({
                                        "status": "Skipped (Tuesday Rule)",
                                        "details": f"Setup formed ({s_name} Long @ {entry:.3f}), but Tuesdays are strictly excluded from live execution by strategy rules."
                                    })
                                    return result
                                ext_sl, _ = extend_sl_new(entry, init_sl, 'long')
                                risk = abs(entry - ext_sl)
                                tp = entry + 5.0 * risk
                                entry_close_ist = s_df.iloc[i]['dt_ist'] + timedelta(minutes=15)
                                entry_t_str = entry_close_ist.strftime("%Y-%m-%dT%H:%M")
                                result.update({
                                    "direction": "long",
                                    "entry_price": round(entry, 3),
                                    "entry_time_ist": entry_t_str,
                                    "sl_price": round(ext_sl, 3),
                                    "tp_price": round(tp, 3),
                                    "sl_percentage": round(sl_pct, 3),
                                    "tp_percentage": round(sl_pct * 5.0, 3),
                                    "status": f"Active Signal ({s_name} Long)",
                                    "details": f"Confirmed M15 Selfsweep in {s_name} session (1:5.0 RRR, upgraded SL extension, day-of-week entry engine)."
                                })
                                return result
                            elif decision == 'WAIT_NEXT':
                                continue
                            else:
                                ext_low, ceiling, state = min(sweep_ext, c_l), c_h, 'SEEK_CC'

            # Short Check
            ext_high, floor, state = highs[0], lows[0], 'SEEK_CC'
            sweep_ext = None
            for i in range(1, N):
                c_o, c_h, c_l, c_c = opens[i], highs[i], lows[i], closes[i]
                prev_c = closes[i-1]
                if state == 'SEEK_CC':
                    if c_h >= ext_high:
                        ext_high, floor = c_h, c_l
                    else:
                        if c_c < floor:
                            state = 'WAIT_OPPOSITE'
                        floor = min(floor, c_l)
                elif state == 'WAIT_OPPOSITE':
                    if c_h >= ext_high:
                        ext_high, floor, state = c_h, c_l, 'SEEK_CC'
                    else:
                        floor = min(floor, c_l)
                        if c_c > c_o:  # Bullish opposite candle formed before level touch
                            state = 'WAIT_SWEEP'
                elif state == 'WAIT_SWEEP':
                    if c_h >= ext_high + 0.001 - 1e-9:
                        if c_c >= ext_high - 1e-9:
                            ext_high, floor, state = c_h, c_l, 'SEEK_CC'
                        else:
                            sweep_ext = c_h
                            if c_c < c_o:
                                decision, sl_pct, body = evaluate_entry_candidate(c_c, prev_c, sweep_ext)
                                if decision == 'VALID_ENTER':
                                    entry = c_c
                                    init_sl = sweep_ext
                                    if is_tuesday:
                                        result.update({
                                            "status": "Skipped (Tuesday Rule)",
                                            "details": f"Setup formed ({s_name} Short @ {entry:.3f}), but Tuesdays are strictly excluded from live execution by strategy rules."
                                        })
                                        return result
                                    ext_sl, _ = extend_sl_new(entry, init_sl, 'short')
                                    risk = abs(ext_sl - entry)
                                    tp = entry - 5.0 * risk
                                    entry_close_ist = s_df.iloc[i]['dt_ist'] + timedelta(minutes=15)
                                    entry_t_str = entry_close_ist.strftime("%Y-%m-%dT%H:%M")
                                    result.update({
                                        "direction": "short",
                                        "entry_price": round(entry, 3),
                                        "entry_time_ist": entry_t_str,
                                        "sl_price": round(ext_sl, 3),
                                        "tp_price": round(tp, 3),
                                        "sl_percentage": round(sl_pct, 3),
                                        "tp_percentage": round(sl_pct * 5.0, 3),
                                        "status": f"Active Signal ({s_name} Short)",
                                        "details": f"Confirmed M15 Selfsweep in {s_name} session (1:5.0 RRR, upgraded SL extension, day-of-week entry engine)."
                                    })
                                    return result
                                elif decision == 'WAIT_NEXT':
                                    state = 'WAIT_BEARISH'
                                else:
                                    ext_high, floor, state = c_h, c_l, 'SEEK_CC'
                            else:
                                state = 'WAIT_BEARISH'
                    elif c_h >= ext_high - 1e-9:
                        sweep_ext = c_h
                        state = 'WAIT_SWEEP_AFTER_TAP'
                    else:
                        floor = min(floor, c_l)
                elif state == 'WAIT_SWEEP_AFTER_TAP':
                    if c_c > ext_high:
                        ext_high, floor, state = max(sweep_ext, c_h), c_l, 'SEEK_CC'
                    else:
                        if c_h >= ext_high + 0.001 - 1e-9:
                            if c_c >= ext_high - 1e-9:
                                ext_high, floor, state = c_h, c_l, 'SEEK_CC'
                            else:
                                sweep_ext = max(sweep_ext, c_h)
                                if c_c < c_o:
                                    decision, sl_pct, body = evaluate_entry_candidate(c_c, prev_c, sweep_ext)
                                    if decision == 'VALID_ENTER':
                                        entry = c_c
                                        init_sl = sweep_ext
                                        if is_tuesday:
                                            result.update({
                                                "status": "Skipped (Tuesday Rule)",
                                                "details": f"Setup formed ({s_name} Short @ {entry:.3f}), but Tuesdays are strictly excluded from live execution by strategy rules."
                                            })
                                            return result
                                        ext_sl, _ = extend_sl_new(entry, init_sl, 'short')
                                        risk = abs(ext_sl - entry)
                                        tp = entry - 5.0 * risk
                                        entry_close_ist = s_df.iloc[i]['dt_ist'] + timedelta(minutes=15)
                                        entry_t_str = entry_close_ist.strftime("%Y-%m-%dT%H:%M")
                                        result.update({
                                            "direction": "short",
                                            "entry_price": round(entry, 3),
                                            "entry_time_ist": entry_t_str,
                                            "sl_price": round(ext_sl, 3),
                                            "tp_price": round(tp, 3),
                                            "sl_percentage": round(sl_pct, 3),
                                            "tp_percentage": round(sl_pct * 5.0, 3),
                                            "status": f"Active Signal ({s_name} Short)",
                                            "details": f"Confirmed M15 Selfsweep in {s_name} session (1:5.0 RRR, upgraded SL extension, day-of-week entry engine)."
                                        })
                                        return result
                                    elif decision == 'WAIT_NEXT':
                                        state = 'WAIT_BEARISH'
                                    else:
                                        ext_high, floor, state = c_h, c_l, 'SEEK_CC'
                                else:
                                    state = 'WAIT_BEARISH'
                        else:
                            sweep_ext = max(sweep_ext, c_h)
                elif state == 'WAIT_BEARISH':
                    if c_c > sweep_ext:
                        ext_high, floor, state = max(sweep_ext, c_h), c_l, 'SEEK_CC'
                    else:
                        sweep_ext = max(sweep_ext, c_h)
                        if c_c < c_o:
                            decision, sl_pct, body = evaluate_entry_candidate(c_c, prev_c, sweep_ext)
                            if decision == 'VALID_ENTER':
                                entry = c_c
                                init_sl = sweep_ext
                                if is_tuesday:
                                    result.update({
                                        "status": "Skipped (Tuesday Rule)",
                                        "details": f"Setup formed ({s_name} Short @ {entry:.3f}), but Tuesdays are strictly excluded from live execution by strategy rules."
                                    })
                                    return result
                                ext_sl, _ = extend_sl_new(entry, init_sl, 'short')
                                risk = abs(ext_sl - entry)
                                tp = entry - 5.0 * risk
                                entry_close_ist = s_df.iloc[i]['dt_ist'] + timedelta(minutes=15)
                                entry_t_str = entry_close_ist.strftime("%Y-%m-%dT%H:%M")
                                result.update({
                                    "direction": "short",
                                    "entry_price": round(entry, 3),
                                    "entry_time_ist": entry_t_str,
                                    "sl_price": round(ext_sl, 3),
                                    "tp_price": round(tp, 3),
                                    "sl_percentage": round(sl_pct, 3),
                                    "tp_percentage": round(sl_pct * 5.0, 3),
                                    "status": f"Active Signal ({s_name} Short)",
                                    "details": f"Confirmed M15 Selfsweep in {s_name} session (1:5.0 RRR, upgraded SL extension, day-of-week entry engine)."
                                })
                                return result
                            elif decision == 'WAIT_NEXT':
                                continue
                            else:
                                ext_high, floor, state = max(sweep_ext, c_h), c_l, 'SEEK_CC'
                                        
        if is_tuesday:
            result["status"] = "Skipped (Tuesday Rule)"
            result["details"] = "Tuesday is strictly excluded by USDJPY Champion strategy rules (No Tuesday filter). No trade logged."
            return result
    except Exception as e:
        result["status"] = "Error"
        result["details"] = str(e)
    return result

# ==============================================================================
# STRATEGY 2: GBPUSD ASIA 1.2 - 1.4 FIB RETRACEMENT (GodMode)
# ==============================================================================
def run_gbpusd_strategy(target_date: datetime.date) -> dict:
    """
    GBPUSD Asian Fib Retracement Strategy (GodMode Engine - 1:3.75 RR, No BE):
    - Asian Session: 05:30-09:30 IST (Summer) / 06:30-10:30 IST (Winter)
    - Pre-London Gap: 09:45-11:15 IST (Summer) / 10:45-12:15 IST (Winter)
      -> Strict Gap Filter: -0.2 sweep or 1.2 runaway before London Open invalidates day.
    - London Entry Window: 11:30-14:30 IST (Summer) / 12:30-15:30 IST (Winter)
    - Level -1.5 Invalidation: Deep runaway invalidates day.
    - Level 1.2 Reached First: Invalidates day if hit before -0.2 touch.
    - Rolling sweep protection & strict rejection criteria.
    - SL Range: 0.035% to 0.154%
    - 1:3.75 RRR Target, Strictly No Breakeven.
    """
    result = {
        "strategy_name": "GBPUSD ASIA 1.2 - 1.4 FIB RETRACMENT",
        "strategy_id": STRAT2_ID,
        "symbol": "GBPUSD",
        "date": target_date.strftime("%Y-%m-%d"),
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
    
    day_df = pd.DataFrame()
    live_df = fetch_oanda_candles("GBP_USD", "M15", target_date)
    if not live_df.empty:
        day_df = live_df[live_df['dt_ist'].dt.date == target_date].sort_values('dt_ist').reset_index(drop=True)
        result["data_source"] = "OANDA Live Feed"
        
    if day_df.empty:
        csv_file = "GBPUSD_2YEARS.csv"
        if os.path.exists(csv_file):
            df = pd.read_csv(csv_file)
            df['dt_ist'] = pd.to_datetime(df['time_ist'])
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
            
        # ----------------------------------------------------------------------
        # RULE 1: PRE-LONDON GAP FILTER (09:45-11:15 IST / 10:45-12:15 IST)
        # Price must NOT touch Level -0.2 (premature liquidity sweep)
        # Price must NOT touch Level 1.2 (premature trend runaway)
        # ----------------------------------------------------------------------
        gap_df = day_df[gap_cond].reset_index(drop=True)
        date_str = target_date.strftime("%Y-%m-%d")
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
                    
        # ----------------------------------------------------------------------
        # RULE 2: LONDON SESSION ENTRY EVALUATION
        # ----------------------------------------------------------------------
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
            
            # Find continuous previous candle in day_df
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
                            result.update({
                                "direction": "long",
                                "entry_price": round(c_c, 5),
                                "entry_time_ist": entry_close_ist.strftime("%Y-%m-%dT%H:%M"),
                                "sl_price": round(sl, 5),
                                "tp_price": round(tp, 5),
                                "sl_percentage": round(sl_pct, 3),
                                "tp_percentage": round(sl_pct * 3.75, 3),
                                "status": "Active Signal (London Long)",
                                "details": f"Level -0.2 swept ({lvl_m02:.5f}) with confirmed rejection."
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
                                "status": "Active Signal (London Short)",
                                "details": f"Level +0.2 swept ({lvl_m02:.5f}) with confirmed rejection."
                            })
                            return result
    except Exception as e:
        result["status"] = "Error"
        result["details"] = str(e)
    return result

# ==============================================================================
# STRATEGY 3: XAUUSD 2H 4:30/5:30 DOL
# ==============================================================================
def run_xauusd_strategy(target_date: datetime.date) -> dict:
    """
    XAUUSD 2H DOL Strategy:
    - 2H morning structure (18:00 NY / 06:30 IST close)
    - Breakout & Sweep rejections
    - 1:3.30 RRR Target, BE @ +2.5R
    - SL Range: 0.165% to 0.994%
    - Strictly skips Thursdays per strategy rule
    """
    result = {
        "strategy_name": "XAUUSD 2H 4:30/5:30 DOL",
        "strategy_id": STRAT3_ID,
        "symbol": "XAUUSD",
        "date": target_date.strftime("%Y-%m-%d"),
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
    
    if target_date.weekday() == 3:
        result["status"] = "Skipped (Thursday Rule)"
        result["details"] = "Thursday is strictly skipped by base strategy rule."
        return result
        
    day_df = pd.DataFrame()
    live_df = fetch_oanda_candles("XAU_USD", "M15", target_date)
    if not live_df.empty:
        day_df = live_df.copy()
        result["data_source"] = "OANDA Live Feed"
        
    if day_df.empty:
        csv_file = "XAUUSD_1M_Sep2024_Sep2026.csv"
        if os.path.exists(csv_file):
            df = pd.read_csv(csv_file)
            df['time_utc'] = pd.to_datetime(df['time_utc'], utc=True)
            df['dt_ny'] = df['time_utc'].dt.tz_convert('America/New_York')
            day_df = df
            result["data_source"] = "Local Archive CSV"
            
    if day_df.empty:
        result["status"] = "No Session Data"
        result["details"] = f"No candle data available for {target_date}."
        return result
        
    try:
        session_ny = target_date - timedelta(days=1)
        day_p = day_df[(day_df['dt_ny'].dt.date == session_ny) & (day_df['dt_ny'].dt.hour == 18)]
        day_s = day_df[(day_df['dt_ny'].dt.date == session_ny) & (day_df['dt_ny'].dt.hour.isin([19, 20]))]
        
        # Fallback to target_date if evening session completed or archive CSV is same-day aligned
        if len(day_p) < 2 or len(day_s) < 4:
            day_p = day_df[(day_df['dt_ny'].dt.date == target_date) & (day_df['dt_ny'].dt.hour == 18)]
            day_s = day_df[(day_df['dt_ny'].dt.date == target_date) & (day_df['dt_ny'].dt.hour.isin([19, 20]))]
            
        if len(day_p) < 2 or len(day_s) < 4:
            result["status"] = "Session Incomplete"
            result["details"] = f"2H DOL session candles not yet complete for {target_date} morning."
            return result
            
        p_high = day_p['high'].max()
        p_low = day_p['low'].min()
        
        s_high = day_s['high'].max()
        s_low = day_s['low'].min()
        s_close = day_s.iloc[-1]['close']
        
        swept_high = s_high > p_high
        swept_low = s_low < p_low
        
        trade_dir = None
        sl_raw = 0.0
        rule_name = ""
        
        if s_close > p_high and not swept_low:
            trade_dir = "long"
            sl_raw = s_low
            rule_name = "BULL BREAKOUT CLEAN" if not swept_low else "BULL BREAKOUT SWEPT"
        elif s_close < p_low and not swept_high:
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
            return result
            
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
            if 'dt_ist' in day_s.columns and len(day_s) > 0:
                entry_close_ist = day_s.iloc[-1]['dt_ist'] + timedelta(minutes=15)
                entry_t_str = entry_close_ist.strftime("%Y-%m-%dT%H:%M")
            else:
                entry_t_str = f"{target_date.strftime('%Y-%m-%d')}T06:30"
                
            result.update({
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
            return result
        else:
            result["status"] = "Skipped (SL Out of Range)"
            result["details"] = f"SL {sl_pct:.3f}% outside 0.165% - 0.994% corridor."
            return result
    except Exception as e:
        result["status"] = "Error"
        result["details"] = str(e)
    return result

# ==============================================================================
# BASE44 API INTEGRATION: SEARCH, SYNC & OPEN TRADES TRACKER
# ==============================================================================
def find_existing_trade(api_key: str, strategy_id: str, symbol: str, trade_date: datetime.date, entry_time_ist: Optional[str] = None) -> Optional[dict]:
    """Finds existing trade entity for strategy_id & symbol on trade_date (or matching exact entry_time_ist), if already logged."""
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

def check_pending_active_trade(api_key: str, symbol: str, current_entry_time_str: Optional[str] = None) -> tuple[bool, Optional[dict]]:
    """
    Checks if there is an active trade for 'symbol' that has not exited yet.
    Rule: Across ALL strategies, if a previous trade is active/pending and has not yet exited,
    no new trade can be entered until the existing trade is closed.
    """
    if not api_key:
        return False, None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    params = {"q": f'{{"symbol": "{symbol}"}}'}
    try:
        resp = requests.get(BASE44_API_URL, headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            items = data if isinstance(data, list) else data.get("items", [])
            for item in items:
                entry_ts = item.get("entry_timestamp")
                exit_ts = item.get("exit_timestamp")
                
                # If this is the exact same trade being evaluated, it does not block itself
                if current_entry_time_str and entry_ts == current_entry_time_str:
                    continue
                    
                if item.get("status") == "open":
                    # Only block if the open trade was entered BEFORE current_entry_time_str
                    if current_entry_time_str and entry_ts and entry_ts >= current_entry_time_str:
                        continue
                    return True, item
                if not exit_ts and item.get("status") != "closed":
                    if current_entry_time_str and entry_ts and entry_ts >= current_entry_time_str:
                        continue
                    return True, item
                if current_entry_time_str and entry_ts and exit_ts:
                    if entry_ts < current_entry_time_str and exit_ts > current_entry_time_str:
                        return True, item
    except Exception as e:
        print(f"Error checking pending trade: {e}")
    return False, None

def sync_trade_to_base44(api_key: str, strategy_id: str, trade_info: dict, amount: float = 300.0, fees: Optional[float] = None) -> tuple[str, str, dict]:
    """
    Logs or updates trade in Base44 Trade Journal:
    - Calculates risk-adjusted quantity ($300 risk / amount).
    - If closed: marks status="closed", sell_price=TP/SL, entry/exit timestamp in IST, and net_pnl.
    - If open: marks status="open", sell_price=current market price, entry/exit timestamp in IST, and unrealized net_pnl.
    - If already exists as open: updates via PUT.
    - If already closed: skips as duplicate.
    """
    if not api_key:
        return "Not Connected", "Base44 Personal Access Token not configured.", {}
        
    symbol = trade_info["symbol"]
    direction = trade_info["direction"]
    entry_price = float(trade_info["entry_price"])
    sl_price = float(trade_info["sl_price"])
    tp_price = float(trade_info["tp_price"])
    sl_pct = trade_info["sl_percentage"]
    tp_pct = trade_info["tp_percentage"]
    
    trade_date = trade_info.get("date")
    if isinstance(trade_date, str):
        try:
            trade_date = dt.strptime(trade_date[:10], "%Y-%m-%d").date()
        except Exception:
            trade_date = datetime.date.today()
    elif not trade_date:
        trade_date = datetime.date.today()

    lifecycle = evaluate_trade_lifecycle(trade_info, risk_usd=amount, fee_override=fees)
    quantity = lifecycle["quantity"]
    status = lifecycle["status"]
    exit_price = lifecycle["exit_price"]
    net_pnl = lifecycle["net_pnl"]
    fee = lifecycle["fee"]
    exit_ts_str = lifecycle["exit_time_str"]
    entry_ts_str = lifecycle["entry_time_str"]
    exit_reason = lifecycle.get("exit_reason")
    notes = f"{sl_pct}% SL ({sl_price}) , {tp_pct}% TP ({tp_price}) | Risk: ${amount:,.2f} | Fee: ${fee:,.2f}"
    if trade_info.get("entry_no") == 2 or trade_info.get("is_double_entry"):
        notes += " | Double Entry"
    if exit_reason:
        notes += f" | {exit_reason}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Duplicate / Existing Trade Check (using exact entry timestamp for Entry 1 vs Entry 2 differentiation)
    existing = find_existing_trade(api_key, strategy_id, symbol, trade_date, entry_time_ist=entry_ts_str)
    if existing:
        t_id = existing.get("id")
        if existing.get("status") == "open":
            put_payload = {
                "strategy_id": strategy_id,
                "symbol": symbol,
                "direction": direction.lower(),
                "buy_price": float(entry_price),
                "sell_price": float(exit_price),
                "quantity": float(quantity),
                "fees": float(fee),
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
                    return "Updated", f"{action_label}: exit @ {exit_price} | Net P&L: ${net_pnl:+.2f} (Fee: ${fee:,.2f})", put_payload
                else:
                    return "Error", f"HTTP {put_r.status_code}: {put_r.text}", put_payload
            except Exception as e:
                return "Error", f"Update failed: {e}", put_payload
        else:
            return "Skipped (Duplicate)", f"Trade already closed @ {existing.get('sell_price')} (Net P&L: ${existing.get('net_pnl', 0):+.2f})", existing

    # Create fresh record (POST)
    payload = {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "direction": direction.lower(),
        "buy_price": float(entry_price),
        "sell_price": float(exit_price),
        "quantity": float(quantity),
        "fees": float(fee),
        "entry_timestamp": entry_ts_str,
        "exit_timestamp": exit_ts_str,
        "status": status,
        "net_pnl": float(net_pnl),
        "notes": notes
    }

    try:
        resp = requests.post(BASE44_API_URL, headers=headers, json=payload, timeout=12)
        if resp.status_code in [200, 201]:
            created = resp.json() if resp.text else payload
            status_desc = "CLOSED (Hit TP/SL)" if status == "closed" else "OPEN (Live Market)"
            return "Success", f"Logged {symbol} {direction.upper()} as {status_desc} @ exit {exit_price} (Net P&L: ${net_pnl:+.2f} after ${fee:,.2f} fee)", created
        else:
            return "Error", f"Base44 API HTTP {resp.status_code}: {resp.text}", payload
    except Exception as e:
        return "Error", f"Request exception: {str(e)}", payload

def check_and_update_all_open_trades(api_key: str, default_risk: float = 300.0) -> list:
    """
    Scans Base44 for any open trades, verifies against live OANDA candles,
    and updates their status, exit price, exit timestamp in IST, and net P&L via PUT.
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
                "date": entry_d,
                "entry_time_ist": entry_ts[:16] if "T" in entry_ts else None
            }
            res = evaluate_trade_lifecycle(trade_dummy, risk_usd=default_risk)
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
                "fees": float(fee),
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
                    "exit_timestamp": exit_ts,
                    "pnl": new_pnl
                })
        return updated_records
    except Exception as e:
        print(f"Error checking open trades: {e}")
        return []


# ==============================================================================
# STRATEGY 4: EURUSD 30 MIN 11:00 AM / 12 NOON CANDLE
# ==============================================================================
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
    - Stop Loss: Opposite extreme of the 30M signal candle (Low for Long, High for Short)
    - Stop Loss Range Filter: 0.035% to 0.065% of price (~3.8 to 7.2 pips). Outside range -> Skipped
    - Target (Take Profit): Strictly 1:5.50 RR (5.50 * Risk)
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
        "strategy_id": STRAT4_ID,
        "symbol": "EURUSD",
        "date": target_date.strftime("%Y-%m-%d"),
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
        day_df = live_df.copy()
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
        
        if b1.empty or b2.empty or b_entry.empty:
            now_ist = dt.now(timezone(timedelta(hours=5, minutes=30))).replace(tzinfo=None)
            if target_date == now_ist.date():
                target_entry_dt = dt.strptime(f"{target_date} {entry_time_str}", "%Y-%m-%d %H:%M")
                if now_ist < target_entry_dt:
                    result["status"] = "Pending (Candle Forming)"
                    result["details"] = f"EURUSD 30M signal candle ({c1_str}-{entry_time_str} IST) is currently forming. Entry scheduled at {entry_time_str} IST close."
                    return result
            result["status"] = "No Signal Candle"
            result["details"] = f"Required 30M signal bars ({c1_str}, {c2_str}, {entry_time_str} IST) were not found in session data."
            return result
            
        c_open = b1['open'].iloc[0]
        c_high = max(b1['high'].iloc[0], b2['high'].iloc[0])
        c_low = min(b1['low'].iloc[0], b2['low'].iloc[0])
        c_close = b2['close'].iloc[-1]
        entry_price = b_entry['open'].iloc[0]
        
        # Direction check
        if c_close > c_open:
            direction = "long"
            sl = c_low
            risk = entry_price - sl
        elif c_close < c_open:
            direction = "short"
            sl = c_high
            risk = sl - entry_price
        else:
            result["status"] = "No Trade (Doji)"
            result["details"] = f"EURUSD 30M candle closed as Doji (Open={c_open:.5f}, Close={c_close:.5f}). No directional impulse."
            return result
            
        if risk <= 0:
            result["status"] = "Invalid Risk"
            result["details"] = "Calculated risk is zero or negative."
            return result
            
        sl_pct = (risk / entry_price) * 100.0
        risk_pips = risk * 10000.0
        
        # Stop Loss Range Filter: 0.035% to 0.065%
        if sl_pct < 0.035:
            result["status"] = "Skipped (SL Below 0.035%)"
            result["details"] = f"Signal candle risk is {sl_pct:.3f}% ({risk_pips:.1f} pips), below the 0.035% minimum threshold. Skipped to prevent market noise."
            return result
            
        if sl_pct > 0.065:
            result["status"] = "Skipped (SL Above 0.065%)"
            result["details"] = f"Signal candle risk is {sl_pct:.3f}% ({risk_pips:.1f} pips), exceeding the 0.065% maximum threshold. Skipped to prevent over-extended risk."
            return result
            
        # Target: Exactly 1:5.50 RR
        rr = 5.50
        if direction == "long":
            tp = entry_price + rr * risk
        else:
            tp = entry_price - rr * risk
            
        tp_pct = (abs(tp - entry_price) / entry_price) * 100.0
        
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
        risk_allocation = 350.0 if is_same_color else 250.0
        
        result["direction"] = direction
        result["entry_price"] = round(entry_price, 5)
        result["entry_time_ist"] = f"{target_date.strftime('%Y-%m-%d')}T{entry_time_str}"
        result["sl_price"] = round(sl, 5)
        result["tp_price"] = round(tp, 5)
        result["sl_percentage"] = round(sl_pct, 3)
        result["tp_percentage"] = round(tp_pct, 3)
        result["status"] = f"Active Setup ({tier})"
        result["details"] = (
            f"EURUSD 30M {direction.upper()} validated at {entry_time_str} IST ({season_name}). "
            f"Entry: {entry_price:.5f}, SL: {sl:.5f} ({risk_pips:.1f} pips / {sl_pct:.3f}%), "
            f"TP: {tp:.5f} (1:5.50 RR / +{risk_pips * 5.5:.1f} pips). "
            f"Tier: {tier} (${risk_allocation:.0f} allocation). "
            f"Protocol: Set & Forget (No BE). News Shield Active (NFP/CPI/FOMC & ECB Monetary Policy)."
        )
        return result
        
    except Exception as e:
        result["status"] = "Error"
        result["details"] = f"EURUSD execution engine error: {str(e)}"
        return result

# ==============================================================================
# FASTAPI ENDPOINTS (VERCEL READY)
# ==============================================================================
@app.get("/")
@app.get("/api")
@app.get("/api/run")
@app.get("/api/health")
@app.get("/health")
async def health_check():
    return {
        "status": "online",
        "service": "Base44 Daily Strategy Runner API",
        "version": "2.0.0",
        "strategies": [
            {"name": "USDJPY SELFSWEEP", "id": STRAT1_ID},
            {"name": "GBPUSD ASIA 1.2 - 1.4 FIB RETRACMENT", "id": STRAT2_ID},
            {"name": "XAUUSD 2H 4:30/5:30 DOL", "id": STRAT3_ID},
            {"name": "EURUSD 30 MIN 11:00 AM / 12 NOON CANDLE", "id": STRAT4_ID}
        ],
        "message": "Send POST /api/run with {'date': 'YYYY-MM-DD', 'amount': 300.0, 'fees': 40.0} to execute strategies."
    }

@app.post("/api/run")
@app.post("/run")
@app.post("/")
async def run_daily_strategies(payload: RunRequest):
    """
    Executes the 3 daily strategies for the requested date,
    performs M1 lifecycle evaluation, duplicate check, and logs setups directly to Base44.
    Also automatically checks and updates any existing OPEN trades in Base44!
    """
    # 1. Resolve evaluation dates
    dates_to_eval = []
    
    # Check if date string contains a range format like "YYYY-MM-DD to YYYY-MM-DD"
    if payload.date and " to " in str(payload.date):
        parts = str(payload.date).split(" to ")
        payload.start_date = parts[0].strip()
        payload.end_date = parts[1].strip()

    if payload.start_date and payload.end_date:
        try:
            s_d = dt.strptime(payload.start_date[:10], "%Y-%m-%d").date()
            e_d = dt.strptime(payload.end_date[:10], "%Y-%m-%d").date()
            if s_d > e_d:
                s_d, e_d = e_d, s_d
            curr = s_d
            while curr <= e_d:
                dates_to_eval.append(curr)
                curr += timedelta(days=1)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid date range format. Use YYYY-MM-DD.")
    elif payload.date:
        try:
            dates_to_eval.append(dt.strptime(payload.date[:10], "%Y-%m-%d").date())
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    else:
        dates_to_eval.append(datetime.date.today())

    amount = float(payload.amount if payload.amount is not None and payload.amount > 0 else 300.0)
    fees = float(payload.fees if payload.fees is not None else 40.0)

    # 2. Check and update existing open trades in Base44 first
    open_updates = check_and_update_all_open_trades(BASE44_API_KEY, default_risk=amount)

    results_list = []
    logged_count = 0
    duplicate_count = 0
    updated_count = 0
    active_count = 0
    total_net_pnl = 0.0

    # 3. Iterate over all dates in requested range
    for target_date in dates_to_eval:
        res_usdjpy = run_usdjpy_strategy(target_date)
        res_gbpusd = run_gbpusd_strategy(target_date)
        res_xauusd = run_xauusd_strategy(target_date)
        res_eurusd = run_eurusd_strategy(target_date)

        day_trades = []
        for strat_out, strat_id in [
            (res_usdjpy, STRAT1_ID),
            (res_gbpusd, STRAT2_ID),
            (res_xauusd, STRAT3_ID),
            (res_eurusd, STRAT4_ID)
        ]:
            if isinstance(strat_out, list):
                for sub_item in strat_out:
                    day_trades.append((sub_item, strat_id))
            else:
                day_trades.append((strat_out, strat_id))

        for strat_result, strat_id in day_trades:
            is_active = strat_result["direction"] in ["long", "short"]
            
            # Universal Pending Trade Rule Check across all strategies
            if is_active:
                is_pending, pending_trade = check_pending_active_trade(
                    BASE44_API_KEY, strat_result["symbol"], current_entry_time_str=strat_result.get("entry_time_ist")
                )
                if is_pending:
                    is_active = False
                    strat_result["direction"] = "NONE"
                    strat_result["status"] = "Blocked (Pending Trade Active)"
                    strat_result["details"] = f"Trade from {pending_trade.get('entry_timestamp', 'previous day')} is still active/open in Base44. Across all strategies, no new trade can be entered until the existing position is closed."

            if is_active:
                active_count += 1
                sync_status, sync_msg, record_data = sync_trade_to_base44(
                    BASE44_API_KEY, strat_id, strat_result, amount=amount, fees=fees
                )
                if sync_status == "Success":
                    logged_count += 1
                elif sync_status == "Updated":
                    updated_count += 1
                elif sync_status == "Skipped (Duplicate)":
                    duplicate_count += 1
                    
                exit_price = record_data.get("sell_price", strat_result.get("tp_price", 0.0))
                entry_time_ist = record_data.get("entry_timestamp", strat_result.get("entry_time_ist"))
                exit_time_ist = record_data.get("exit_timestamp")
                qty = record_data.get("quantity", 1.0)
                net_pnl = record_data.get("net_pnl", 0.0)
                total_net_pnl += net_pnl
                trade_status = record_data.get("status", "open")
                fee_used = record_data.get("fees", fees)
                notes_text = record_data.get("notes", "")
            else:
                sync_status = "N/A (No Setup)"
                sync_msg = "No signal triggered for live execution."
                record_data = {}
                exit_price = 0.0
                entry_time_ist = None
                exit_time_ist = None
                qty = 0.0
                net_pnl = 0.0
                trade_status = "none"
                fee_used = 0.0
                notes_text = ""

            results_list.append({
                "strategy_name": strat_result["strategy_name"],
                "strategy_id": strat_id,
                "symbol": strat_result["symbol"],
                "date": target_date.strftime("%Y-%m-%d"),
                "direction": strat_result["direction"].upper() if is_active else "NONE",
                "entry_price": strat_result["entry_price"],
                "entry_time_ist": entry_time_ist,
                "exit_price": exit_price,
                "exit_time_ist": exit_time_ist,
                "sl_price": strat_result["sl_price"],
                "tp_price": strat_result["tp_price"],
                "sl_percentage": strat_result["sl_percentage"],
                "tp_percentage": strat_result["tp_percentage"],
                "quantity": qty,
                "net_pnl": net_pnl,
                "fees": fee_used,
                "status": strat_result["status"],
                "lifecycle_status": trade_status,
                "notes": notes_text,
                "details": strat_result["details"],
                "data_source": strat_result.get("data_source", "OANDA"),
                "base44_sync": sync_status,
                "base44_message": sync_msg,
                "base44_record": record_data
            })

    total_evals = 3 * len(dates_to_eval)
    date_label = f"{dates_to_eval[0].strftime('%Y-%m-%d')} to {dates_to_eval[-1].strftime('%Y-%m-%d')}" if len(dates_to_eval) > 1 else dates_to_eval[0].strftime('%Y-%m-%d')

    # Gather news events checked across the evaluated window
    news_events_checked = get_news_events_for_window(dates_to_eval[0], dates_to_eval[-1] + timedelta(days=2))
    formatted_news = []
    for ev in news_events_checked:
        formatted_news.append({
            "category": ev["category"],
            "title": ev["title"],
            "dt_ist": ev["dt_ist"].strftime("%Y-%m-%d %H:%M:%S"),
            "date": ev.get("date_str", ev["dt_ist"].strftime("%Y-%m-%d")),
            "auto_exit_time_ist": (ev["dt_ist"] - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        })

    return {
        "status": "success",
        "date": date_label,
        "mode": "date_range" if len(dates_to_eval) > 1 else "single_date",
        "days_evaluated": len(dates_to_eval),
        "amount": amount,
        "fees": fees,
        "summary": {
            "total_strategies": total_evals,
            "days_evaluated": len(dates_to_eval),
            "active_signals": active_count,
            "logged_trades": logged_count,
            "updated_trades": updated_count,
            "duplicates": duplicate_count,
            "open_trades_refreshed": len(open_updates),
            "total_net_pnl": round(total_net_pnl, 2),
            "skipped_or_no_setup": total_evals - active_count,
            "news_events_detected": len(formatted_news)
        },
        "news_events": formatted_news,
        "open_trades_refreshed": open_updates,
        "results": results_list
    }

@app.get("/api/news")
def get_upcoming_news(date: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None, symbol: Optional[str] = None):
    """
    Returns high-impact economic calendar events (NFP, CPI, FOMC, BOJ, BOE) for any requested date or range.
    Supports both historical dates (2024-2026 archive) and live real-time forward calendar!
    Returns is_passed flag and affected symbols so dashboard never displays stale passed news as active warnings.
    """
    today = datetime.date.today()
    now_ist = (dt.now(timezone.utc) + timedelta(hours=5, minutes=30)).replace(tzinfo=None)
    s_d = today
    e_d = today
    
    if start_date and end_date:
        try:
            s_d = dt.strptime(start_date[:10], "%Y-%m-%d").date()
            e_d = dt.strptime(end_date[:10], "%Y-%m-%d").date()
            if s_d > e_d:
                s_d, e_d = e_d, s_d
        except Exception:
            pass
    elif date:
        try:
            s_d = dt.strptime(date[:10], "%Y-%m-%d").date()
            e_d = s_d  # Exact single day
        except Exception:
            pass
            
    events = get_news_events_for_window(s_d, e_d, symbol=symbol)
    res_events = []
    for ev in events:
        ev_dt = ev["dt_ist"]
        ev_dt_naive = ev_dt.replace(tzinfo=None) if hasattr(ev_dt, 'tzinfo') and ev_dt.tzinfo is not None else ev_dt
        is_passed = bool(ev_dt_naive < now_ist)
        res_events.append({
            "category": ev["category"],
            "title": ev["title"],
            "dt_ist": ev_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "date": ev.get("date_str", ev_dt.strftime("%Y-%m-%d")),
            "symbols": ev.get("symbols", ["USDJPY", "GBPUSD", "XAUUSD"]),
            "is_passed": is_passed,
            "auto_exit_time_ist": (ev_dt - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        })
    return {
        "success": True,
        "count": len(res_events),
        "start_date": s_d.strftime("%Y-%m-%d"),
        "end_date": e_d.strftime("%Y-%m-%d"),
        "symbol_filter": symbol or "ALL",
        "monitored_events": ["NFP", "CPI", "FOMC", "BOJ_RATE", "BOE_RATE", "UK_CPI"],
        "events": res_events
    }

# Mount static frontend files for seamless local preview (disabled in Vercel where CDN serves public/)
if not os.environ.get("VERCEL"):
    try:
        from fastapi.staticfiles import StaticFiles
        public_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public")
        if os.path.exists(public_dir):
            app.mount("/", StaticFiles(directory=public_dir, html=True), name="static")
    except Exception:
        pass

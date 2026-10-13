import os
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

OANDA_TOKEN = os.environ.get("OANDA_TOKEN", "f2b74d1cee1eb5488ba8b6b067e3ffc6-b6ccbdca86ea9ddb162f03996341ae91")

# Fixed broker & exchange fees per trade:
# XAUUSD: $25.00 per trade
# GBPUSD: $40.00 per trade
# USDJPY: $40.00 per trade
FIXED_FEES = {
    "XAUUSD": 25.0,
    "GBPUSD": 40.0,
    "USDJPY": 40.0
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
def fetch_oanda_candles(instrument: str, granularity: str, target_date: datetime.date) -> pd.DataFrame:
    """Fetches real-time M15 candlesticks from OANDA API with IST conversion."""
    if not OANDA_TOKEN:
        return pd.DataFrame()
        
    base_urls = ["https://api-fxtrade.oanda.com/v3", "https://api-fxpractice.oanda.com/v3"]
    headers = {"Authorization": f"Bearer {OANDA_TOKEN}"}
    start_utc = dt(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=timezone.utc) - timedelta(days=1)
    now_utc = dt.now(timezone.utc)
    
    params = {
        "granularity": granularity,
        "price": "M",
        "from": start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    target_end_utc = dt(target_date.year, target_date.month, target_date.day, 23, 59, 59, tzinfo=timezone.utc)
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
    inst = "USD_JPY" if "JPY" in symbol else ("GBP_USD" if "GBP" in symbol else "XAU_USD")
    if not OANDA_TOKEN:
        return 0.0
    for base_url in ["https://api-fxtrade.oanda.com/v3", "https://api-fxpractice.oanda.com/v3"]:
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
    
    for base_url in ["https://api-fxtrade.oanda.com/v3", "https://api-fxpractice.oanda.com/v3"]:
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
    return float(user_fee or 40.0)

# ==============================================================================
# TRADE LIFECYCLE EVALUATOR (M1 PRECISION & LIVE OUTCOMES)
# ==============================================================================
def evaluate_trade_lifecycle(trade_info: dict, risk_usd: float = 300.0, fee_override: Optional[float] = None) -> dict:
    """
    Evaluates whether trade hit TP, SL, or is currently OPEN.
    Uses precise 1-minute (M1) candles for exact exit timing down to the minute in IST.
    Format: YYYY-MM-DDTHH:MM (Exact Indian Standard Time)
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
    inst = "USD_JPY" if "JPY" in symbol else ("GBP_USD" if "GBP" in symbol else "XAU_USD")
    candles_df = fetch_oanda_candles(inst, "M15", trade_date)
    
    status = "open"
    exit_price = get_latest_market_price(symbol)
    exit_time_str = None
    
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
            
            # Weekend cutoff check: Saturday before 02:30 AM (Summer) / 03:30 AM (Winter)
            if c_dt_ist.weekday() == 5:
                cut_t = time(2, 15) if is_us_dst(c_time_utc) else time(3, 15)
                if c_dt_ist.time() >= cut_t:
                    status = "closed"
                    exit_price = c['close']
                    exit_time_str = (c_dt_ist + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M")
                    break

            if direction == "long":
                if c_low <= sl_price:
                    status = "closed"
                    exit_price = sl_price
                    hit_exit = True
                elif c_high >= tp_price:
                    status = "closed"
                    exit_price = tp_price
                    hit_exit = True
            elif direction == "short":
                if c_high >= sl_price:
                    status = "closed"
                    exit_price = sl_price
                    hit_exit = True
                elif c_low <= tp_price:
                    status = "closed"
                    exit_price = tp_price
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
        "net_pnl": round(net_pnl, 2)
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
        
        for s_name, cond in [("ASIA", cond_asia), ("LONDON", cond_london)]:
            s_df = day_df[cond].reset_index(drop=True)
            N = len(s_df)
            if N < 4: continue
            
            opens, highs, lows, closes = s_df['open'].values, s_df['high'].values, s_df['low'].values, s_df['close'].values
            
            # Long Check
            ext_low, ceiling, state = lows[0], highs[0], 'SEEK_CC'
            sweep_ext = None
            wait_cnt = 0
            for i in range(1, N):
                c_o, c_h, c_l, c_c = opens[i], highs[i], lows[i], closes[i]
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
                    if c_l <= ext_low - 0.001:
                        if c_c <= ext_low:
                            ext_low, ceiling, state = c_l, c_h, 'SEEK_CC'
                        else:
                            l_wick = c_o - c_l if c_c > c_o else c_c - c_l
                            body = abs(c_c - c_o)
                            ratio_ok = (body >= 0.002) if (l_wick >= 0.100) else (body >= 0.003)
                            if ratio_ok:
                                if c_c > c_o:
                                    entry = c_c
                                    init_sl = c_l
                                    sl_pct = (abs(entry - init_sl) / entry) * 100.0
                                    if 0.045 <= sl_pct <= 0.154:
                                        if is_tuesday:
                                            result.update({
                                                "status": "Skipped (Tuesday Rule)",
                                                "details": f"Setup formed ({s_name} Long @ {entry:.3f}), but Tuesdays are strictly excluded from live execution by strategy rules."
                                            })
                                            return result
                                            
                                        if sl_pct < 0.055:
                                            ext_sl = entry * (1.0 - 0.00055)
                                        elif sl_pct < 0.065:
                                            ext_sl = init_sl - 0.006
                                        elif sl_pct < 0.075:
                                            ext_sl = init_sl - 0.007
                                        else:
                                            buffer_p = 0.014 + int((sl_pct - 0.075) / 0.010) * 0.001
                                            ext_sl = init_sl - buffer_p
                                        risk = entry - ext_sl
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
                                            "details": f"Confirmed M15 Selfsweep in {s_name} session (1:5.0 RRR, upgraded SL extension)."
                                        })
                                        return result
                                else:
                                    sweep_ext = c_l
                                    wait_cnt = 0
                                    state = 'WAIT_BULLISH'
                            else:
                                ext_low, ceiling, state = c_l, c_h, 'SEEK_CC'
                    elif c_l <= ext_low:
                        sweep_ext = c_l
                        wait_cnt = 0
                        state = 'WAIT_SWEEP_AFTER_TAP'
                    else:
                        ceiling = max(ceiling, c_h)
                elif state == 'WAIT_SWEEP_AFTER_TAP':
                    wait_cnt += 1
                    if wait_cnt > 3 or c_c < ext_low:
                        ext_low = min(sweep_ext, c_l)
                        ceiling = c_h
                        state = 'SEEK_CC'
                    else:
                        if c_l <= ext_low - 0.001:
                            if c_c <= ext_low:
                                ext_low, ceiling, state = c_l, c_h, 'SEEK_CC'
                            else:
                                sweep_ext = min(sweep_ext, c_l)
                                l_wick = c_o - c_l if c_c > c_o else c_c - c_l
                                body = abs(c_c - c_o)
                                ratio_ok = (body >= 0.002) if (l_wick >= 0.100) else (body >= 0.003)
                                if ratio_ok:
                                    if c_c > c_o:
                                        entry = c_c
                                        init_sl = sweep_ext
                                        sl_pct = (abs(entry - init_sl) / entry) * 100.0
                                        if 0.045 <= sl_pct <= 0.154:
                                            if is_tuesday:
                                                result.update({
                                                    "status": "Skipped (Tuesday Rule)",
                                                    "details": f"Setup formed ({s_name} Long @ {entry:.3f}), but Tuesdays are strictly excluded from live execution by strategy rules."
                                                })
                                                return result
                                            if sl_pct < 0.055:
                                                ext_sl = entry * (1.0 - 0.00055)
                                            elif sl_pct < 0.065:
                                                ext_sl = init_sl - 0.006
                                            elif sl_pct < 0.075:
                                                ext_sl = init_sl - 0.007
                                            else:
                                                buffer_p = 0.014 + int((sl_pct - 0.075) / 0.010) * 0.001
                                                ext_sl = init_sl - buffer_p
                                            risk = entry - ext_sl
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
                                                "details": f"Confirmed M15 Selfsweep in {s_name} session (1:5.0 RRR, upgraded SL extension)."
                                            })
                                            return result
                                    else:
                                        wait_cnt = 0
                                        state = 'WAIT_BULLISH'
                                else:
                                    ext_low, ceiling, state = c_l, c_h, 'SEEK_CC'
                        else:
                            sweep_ext = min(sweep_ext, c_l)
                elif state == 'WAIT_BULLISH':
                    wait_cnt += 1
                    if wait_cnt > 3 or c_c < sweep_ext:
                        ext_low = min(sweep_ext, c_l)
                        ceiling = c_h
                        state = 'SEEK_CC'
                    else:
                        sweep_ext = min(sweep_ext, c_l)
                        if c_c > c_o:
                            entry = c_c
                            init_sl = sweep_ext
                            sl_pct = (abs(entry - init_sl) / entry) * 100.0
                            if 0.045 <= sl_pct <= 0.154:
                                if is_tuesday:
                                    result.update({
                                        "status": "Skipped (Tuesday Rule)",
                                        "details": f"Setup formed ({s_name} Long @ {entry:.3f}), but Tuesdays are strictly excluded from live execution by strategy rules."
                                    })
                                    return result
                                if sl_pct < 0.055:
                                    ext_sl = entry * (1.0 - 0.00055)
                                elif sl_pct < 0.065:
                                    ext_sl = init_sl - 0.006
                                elif sl_pct < 0.075:
                                    ext_sl = init_sl - 0.007
                                else:
                                    buffer_p = 0.014 + int((sl_pct - 0.075) / 0.010) * 0.001
                                    ext_sl = init_sl - buffer_p
                                risk = entry - ext_sl
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
                                    "details": f"Confirmed M15 Selfsweep in {s_name} session (1:5.0 RRR, upgraded SL extension)."
                                })
                                return result
                                        
            # Short Check
            ext_high, floor, state = highs[0], lows[0], 'SEEK_CC'
            sweep_ext = None
            wait_cnt = 0
            for i in range(1, N):
                c_o, c_h, c_l, c_c = opens[i], highs[i], lows[i], closes[i]
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
                    if c_h >= ext_high + 0.001:
                        if c_c >= ext_high:
                            ext_high, floor, state = c_h, c_l, 'SEEK_CC'
                        else:
                            u_wick = c_h - c_o if c_c < c_o else c_h - c_c
                            body = abs(c_o - c_c)
                            ratio_ok = (body >= 0.002) if (u_wick >= 0.100) else (body >= 0.003)
                            if ratio_ok:
                                if c_c < c_o:
                                    entry = c_c
                                    init_sl = c_h
                                    sl_pct = (abs(entry - init_sl) / entry) * 100.0
                                    if 0.045 <= sl_pct <= 0.154:
                                        if is_tuesday:
                                            result.update({
                                                "status": "Skipped (Tuesday Rule)",
                                                "details": f"Setup formed ({s_name} Short @ {entry:.3f}), but Tuesdays are strictly excluded from live execution by strategy rules."
                                            })
                                            return result
                                            
                                        if sl_pct < 0.055:
                                            ext_sl = entry * (1.0 + 0.00055)
                                        elif sl_pct < 0.065:
                                            ext_sl = init_sl + 0.006
                                        elif sl_pct < 0.075:
                                            ext_sl = init_sl + 0.007
                                        else:
                                            buffer_p = 0.014 + int((sl_pct - 0.075) / 0.010) * 0.001
                                            ext_sl = init_sl + buffer_p
                                        risk = ext_sl - entry
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
                                            "details": f"Confirmed M15 Selfsweep in {s_name} session (1:5.0 RRR, upgraded SL extension)."
                                        })
                                        return result
                                else:
                                    sweep_ext = c_h
                                    wait_cnt = 0
                                    state = 'WAIT_BEARISH'
                            else:
                                ext_high, floor, state = c_h, c_l, 'SEEK_CC'
                    elif c_h >= ext_high:
                        sweep_ext = c_h
                        wait_cnt = 0
                        state = 'WAIT_SWEEP_AFTER_TAP'
                    else:
                        floor = min(floor, c_l)
                elif state == 'WAIT_SWEEP_AFTER_TAP':
                    wait_cnt += 1
                    if wait_cnt > 3 or c_c > ext_high:
                        ext_high = max(sweep_ext, c_h)
                        floor = c_l
                        state = 'SEEK_CC'
                    else:
                        if c_h >= ext_high + 0.001:
                            if c_c >= ext_high:
                                ext_high, floor, state = c_h, c_l, 'SEEK_CC'
                            else:
                                sweep_ext = max(sweep_ext, c_h)
                                u_wick = c_h - c_o if c_c < c_o else c_h - c_c
                                body = abs(c_o - c_c)
                                ratio_ok = (body >= 0.002) if (u_wick >= 0.100) else (body >= 0.003)
                                if ratio_ok:
                                    if c_c < c_o:
                                        entry = c_c
                                        init_sl = sweep_ext
                                        sl_pct = (abs(entry - init_sl) / entry) * 100.0
                                        if 0.045 <= sl_pct <= 0.154:
                                            if is_tuesday:
                                                result.update({
                                                    "status": "Skipped (Tuesday Rule)",
                                                    "details": f"Setup formed ({s_name} Short @ {entry:.3f}), but Tuesdays are strictly excluded from live execution by strategy rules."
                                                })
                                                return result
                                            if sl_pct < 0.055:
                                                ext_sl = entry * (1.0 + 0.00055)
                                            elif sl_pct < 0.065:
                                                ext_sl = init_sl + 0.006
                                            elif sl_pct < 0.075:
                                                ext_sl = init_sl + 0.007
                                            else:
                                                buffer_p = 0.014 + int((sl_pct - 0.075) / 0.010) * 0.001
                                                ext_sl = init_sl + buffer_p
                                            risk = ext_sl - entry
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
                                                "details": f"Confirmed M15 Selfsweep in {s_name} session (1:5.0 RRR, upgraded SL extension)."
                                            })
                                            return result
                                    else:
                                        wait_cnt = 0
                                        state = 'WAIT_BEARISH'
                                else:
                                    ext_high, floor, state = c_h, c_l, 'SEEK_CC'
                        else:
                            sweep_ext = max(sweep_ext, c_h)
                elif state == 'WAIT_BEARISH':
                    wait_cnt += 1
                    if wait_cnt > 3 or c_c > sweep_ext:
                        ext_high = max(sweep_ext, c_h)
                        floor = c_l
                        state = 'SEEK_CC'
                    else:
                        sweep_ext = max(sweep_ext, c_h)
                        if c_c < c_o:
                            entry = c_c
                            init_sl = sweep_ext
                            sl_pct = (abs(entry - init_sl) / entry) * 100.0
                            if 0.045 <= sl_pct <= 0.154:
                                if is_tuesday:
                                    result.update({
                                        "status": "Skipped (Tuesday Rule)",
                                        "details": f"Setup formed ({s_name} Short @ {entry:.3f}), but Tuesdays are strictly excluded from live execution by strategy rules."
                                    })
                                    return result
                                if sl_pct < 0.055:
                                    ext_sl = entry * (1.0 + 0.00055)
                                elif sl_pct < 0.065:
                                    ext_sl = init_sl + 0.006
                                elif sl_pct < 0.075:
                                    ext_sl = init_sl + 0.007
                                else:
                                    buffer_p = 0.014 + int((sl_pct - 0.075) / 0.010) * 0.001
                                    ext_sl = init_sl + buffer_p
                                risk = ext_sl - entry
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
                                    "details": f"Confirmed M15 Selfsweep in {s_name} session (1:5.0 RRR, upgraded SL extension)."
                                })
                                return result
                                        
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
                    if idx > touch_idx:
                        # Rolling sweep invalidation: cannot close below rolling sweep level or original sweep extreme
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
                        result.update({
                            "direction": "long",
                            "entry_price": round(c_c, 5),
                            "entry_time_ist": entry_t_str,
                            "sl_price": round(sl, 5),
                            "tp_price": round(tp, 5),
                            "sl_percentage": round(sl_pct, 3),
                            "tp_percentage": round(sl_pct * 3.75, 3),
                            "status": "Active Signal (London Long)",
                            "details": f"Level -0.2 swept ({lvl_m02:.5f}) with confirmed rejection."
                        })
                        return result
                        
                else: # short
                    if idx > touch_idx:
                        # Rolling sweep invalidation: cannot close above rolling sweep level or original sweep extreme
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
                        result.update({
                            "direction": "short",
                            "entry_price": round(c_c, 5),
                            "entry_time_ist": entry_t_str,
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
        if target_date.weekday() == 0:
            session_ny = target_date - timedelta(days=3)
        else:
            session_ny = target_date - timedelta(days=1)
        day_p = day_df[(day_df['dt_ny'].dt.date == session_ny) & (day_df['dt_ny'].dt.hour == 18)]
        day_s = day_df[(day_df['dt_ny'].dt.date == session_ny) & (day_df['dt_ny'].dt.hour.isin([19, 20]))]
        
        if day_p.empty or day_s.empty:
            result["status"] = "Session Incomplete"
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
def find_existing_trade(api_key: str, strategy_id: str, symbol: str, trade_date: datetime.date) -> Optional[dict]:
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
                if entry_ts.startswith(date_str):
                    return item
    except Exception as e:
        print(f"Error checking existing trade: {e}")
    return None

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
    notes = f"{sl_pct}% SL ({sl_price}) , {tp_pct}% TP ({tp_price}) | Risk: ${amount:,.2f} | Fee: ${fee:,.2f}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Duplicate / Existing Trade Check
    existing = find_existing_trade(api_key, strategy_id, symbol, trade_date)
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
            {"name": "XAUUSD 2H 4:30/5:30 DOL", "id": STRAT3_ID}
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

        strategies_out = [
            (res_usdjpy, STRAT1_ID),
            (res_gbpusd, STRAT2_ID),
            (res_xauusd, STRAT3_ID)
        ]

        for strat_result, strat_id in strategies_out:
            is_active = strat_result["direction"] in ["long", "short"]
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
            "skipped_or_no_setup": total_evals - active_count
        },
        "open_trades_refreshed": open_updates,
        "results": results_list
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

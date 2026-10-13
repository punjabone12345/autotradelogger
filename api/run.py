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
    amount: Optional[float] = 1.0
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
# OANDA MARKET DATA PROVIDER
# ==============================================================================
def fetch_oanda_candles(instrument: str, granularity: str, target_date: datetime.date) -> pd.DataFrame:
    """Fetches real-time M15 candlesticks from OANDA API with IST conversion."""
    if not OANDA_TOKEN:
        return pd.DataFrame()
        
    base_url = "https://api-fxtrade.oanda.com/v3"
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
        
    try:
        url = f"{base_url}/instruments/{instrument}/candles"
        r = requests.get(url, headers=headers, params=params, timeout=12)
        if r.status_code != 200:
            # Fallback to demo practice endpoint if live returns 401/403
            url = f"https://api-fxpractice.oanda.com/v3/instruments/{instrument}/candles"
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
        print(f"OANDA API fetch error for {instrument}: {e}")
    return pd.DataFrame()

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
                                            result.update({
                                                "status": "Skipped (Tuesday Rule)",
                                                "details": f"Setup formed ({s_name} Long @ {entry:.3f}), but Tuesdays are strictly excluded from live execution by strategy rules."
                                            })
                                            return result
                                            
                                        buffer_p = 0.006 + max(0, int((sl_pct - 0.055) / 0.010)) * 0.001
                                        ext_sl = init_sl - buffer_p
                                        risk = entry - ext_sl
                                        tp = entry + 5.0 * risk
                                        result.update({
                                            "direction": "long",
                                            "entry_price": round(entry, 3),
                                            "sl_price": round(ext_sl, 3),
                                            "tp_price": round(tp, 3),
                                            "sl_percentage": round(sl_pct, 3),
                                            "tp_percentage": round(sl_pct * 5.0, 3),
                                            "status": f"Active Signal ({s_name} Long)",
                                            "details": f"Confirmed M15 Selfsweep in {s_name} session."
                                        })
                                        return result
                                        
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
                                            result.update({
                                                "status": "Skipped (Tuesday Rule)",
                                                "details": f"Setup formed ({s_name} Short @ {entry:.3f}), but Tuesdays are strictly excluded from live execution by strategy rules."
                                            })
                                            return result
                                            
                                        buffer_p = 0.006 + max(0, int((sl_pct - 0.055) / 0.010)) * 0.001
                                        ext_sl = init_sl + buffer_p
                                        risk = ext_sl - entry
                                        tp = entry - 5.0 * risk
                                        result.update({
                                            "direction": "short",
                                            "entry_price": round(entry, 3),
                                            "sl_price": round(ext_sl, 3),
                                            "tp_price": round(tp, 3),
                                            "sl_percentage": round(sl_pct, 3),
                                            "tp_percentage": round(sl_pct * 5.0, 3),
                                            "status": f"Active Signal ({s_name} Short)",
                                            "details": f"Confirmed M15 Selfsweep in {s_name} session."
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
    GBPUSD Asian Fib Retracement Strategy (GodMode Engine):
    - Asian Session 05:30-09:30 IST (Summer) / 06:30-10:30 IST (Winter)
    - London Entry Window 11:30-14:30 IST (Summer) / 12:30-15:30 IST (Winter)
    - Rolling sweep protection
    - Stop Loss: Level -0.4 anchor when -0.4 untouched; sweep wick when touched
    - 1:3.75 RRR Target, No BE
    - SL Range: 0.035% to 0.154%
    """
    result = {
        "strategy_name": "GBPUSD ASIA 1.2 - 1.4 FIB RETRACMENT",
        "strategy_id": STRAT2_ID,
        "symbol": "GBPUSD",
        "date": target_date.strftime("%Y-%m-%d"),
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
    
    day_df = pd.DataFrame()
    live_df = fetch_oanda_candles("GBP_USD", "M15", target_date)
    if not live_df.empty:
        day_df = live_df[live_df['dt_ist'].dt.date == target_date].sort_values('dt_ist').reset_index(drop=True)
        result["data_source"] = "OANDA Live Feed"
        
    if day_df.empty:
        csv_file = "GBPUSD_2YEARS.csv"
        if os.path.exists(csv_file):
            df = pd.read_csv(csv_file)
            df.columns = [c.strip().lower() for c in df.columns]
            time_col = 'time' if 'time' in df.columns else ('timestamp' if 'timestamp' in df.columns else df.columns[0])
            df['dt_ist'] = pd.to_datetime(df[time_col])
            day_df = df[df['dt_ist'].dt.date == target_date].sort_values('dt_ist').reset_index(drop=True)
            result["data_source"] = "Local Archive CSV"
            
    if day_df.empty or len(day_df) < 12:
        result["status"] = "No Session Data"
        result["details"] = f"Insufficient M15 candles for {target_date}."
        return result
        
    try:
        sample_utc = pd.to_datetime(day_df['time_utc'].iloc[0])
        is_summer = is_us_dst(sample_utc)
        t_col = day_df['dt_ist'].dt.time
        
        if is_summer:
            asia_cond = (t_col >= time(5, 30)) & (t_col <= time(9, 30))
            lon_cond = (t_col >= time(11, 30)) & (t_col <= time(14, 30))
        else:
            asia_cond = (t_col >= time(6, 30)) & (t_col <= time(10, 30))
            lon_cond = (t_col >= time(12, 30)) & (t_col <= time(15, 30))
            
        asia_df = day_df[asia_cond]
        if len(asia_df) < 4:
            result["status"] = "No Asia Range"
            result["details"] = "Asian range incomplete."
            return result
            
        asia_high = asia_df['high'].max()
        asia_low = asia_df['low'].min()
        asia_open = asia_df.iloc[0]['open']
        asia_close = asia_df.iloc[-1]['close']
        rng = asia_high - asia_low
        
        if rng <= 0.0005:
            result["status"] = "Flat Asian Range"
            result["details"] = f"Asian range too tight: {rng:.5f}"
            return result
            
        is_asia_bearish = asia_close < asia_open
        direction = "long" if is_asia_bearish else "short"
        
        if direction == "long":
            level_sweep = asia_low - 0.20 * rng
            level_m04 = asia_low - 0.40 * rng
        else:
            level_sweep = asia_high + 0.20 * rng
            level_m04 = asia_high + 0.40 * rng
            
        lon_df = day_df[lon_cond].reset_index(drop=True)
        mode = "waiting"
        lowest = 999999.0
        highest = -999999.0
        prev_c, prev_l, prev_h = None, None, None
        touch_idx = None
        
        for idx, row in lon_df.iterrows():
            c_o, c_h, c_l, c_c = row['open'], row['high'], row['low'], row['close']
            
            if mode == "waiting":
                if direction == "long" and c_l <= level_sweep:
                    mode = "entry"
                    lowest = c_l
                    touch_idx = idx
                elif direction == "short" and c_h >= level_sweep:
                    mode = "entry"
                    highest = c_h
                    touch_idx = idx
                    
            if mode == "entry":
                if direction == "long":
                    lowest_prev = lowest
                    lowest = min(lowest, c_l)
                    if idx > touch_idx and (c_c < lowest_prev or abs(c_c - lowest_prev) < 1e-6):
                        result["status"] = "Invalidated (Rolling Low Breach)"
                        result["details"] = f"Candle at {row['dt_ist'].strftime('%H:%M')} closed beyond rolling sweep low."
                        return result
                        
                    bullish = c_c > c_o
                    gap_pct = (abs(c_c - prev_c) / prev_c * 100.0) if prev_c else 0.0
                    sweeps = (c_l <= prev_l) if prev_l else False
                    sweep_ok = (c_c > prev_c) if sweeps else True
                    gap_ok = gap_pct >= 0.01
                    
                    if bullish and sweep_ok and gap_ok:
                        touched04 = (lowest <= level_m04)
                        sl = lowest - 0.00001 if touched04 else level_m04 - 0.00002
                        risk = c_c - sl
                        sl_pct = (risk / c_c) * 100.0
                        if 0.035 <= sl_pct <= 0.154:
                            tp = c_c + 3.75 * risk
                            result.update({
                                "direction": "long",
                                "entry_price": round(c_c, 5),
                                "sl_price": round(sl, 5),
                                "tp_price": round(tp, 5),
                                "sl_percentage": round(sl_pct, 3),
                                "tp_percentage": round(sl_pct * 3.75, 3),
                                "status": "Active Signal (London Long)",
                                "details": f"Level -0.2 swept ({level_sweep:.5f}) with confirmed rejection."
                            })
                            return result
                else: # short
                    highest_prev = highest
                    highest = max(highest, c_h)
                    if idx > touch_idx and (c_c > highest_prev or abs(c_c - highest_prev) < 1e-6):
                        result["status"] = "Invalidated (Rolling High Breach)"
                        result["details"] = f"Candle at {row['dt_ist'].strftime('%H:%M')} closed beyond rolling sweep high."
                        return result
                        
                    bearish = c_c < c_o
                    gap_pct = (abs(c_c - prev_c) / prev_c * 100.0) if prev_c else 0.0
                    sweeps = (c_h >= prev_h) if prev_h else False
                    sweep_ok = (c_c < prev_c) if sweeps else True
                    gap_ok = gap_pct >= 0.01
                    
                    if bearish and sweep_ok and gap_ok:
                        touched04 = (highest >= level_m04)
                        sl = highest + 0.00001 if touched04 else level_m04 + 0.00002
                        risk = sl - c_c
                        sl_pct = (risk / c_c) * 100.0
                        if 0.035 <= sl_pct <= 0.154:
                            tp = c_c - 3.75 * risk
                            result.update({
                                "direction": "short",
                                "entry_price": round(c_c, 5),
                                "sl_price": round(sl, 5),
                                "tp_price": round(tp, 5),
                                "sl_percentage": round(sl_pct, 3),
                                "tp_percentage": round(sl_pct * 3.75, 3),
                                "status": "Active Signal (London Short)",
                                "details": f"Level +0.2 swept ({level_sweep:.5f}) with confirmed rejection."
                            })
                            return result
            prev_c, prev_l, prev_h = c_c, c_l, c_h
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
        
        if len(day_p) < 2 or len(day_s) < 4:
            day_p = day_df[(day_df['dt_ny'].dt.date == target_date) & (day_df['dt_ny'].dt.hour == 18)]
            day_s = day_df[(day_df['dt_ny'].dt.date == target_date) & (day_df['dt_ny'].dt.hour.isin([19, 20]))]
            
        if len(day_p) < 2 or len(day_s) < 4:
            result["status"] = "No Session Data"
            result["details"] = f"2H DOL session candles not yet complete for {target_date}."
            return result
            
        p_high, p_low = day_p['high'].max(), day_p['low'].min()
        s_open = day_s.iloc[0]['open']
        s_close = day_s.iloc[-1]['close']
        s_high, s_low = day_s['high'].max(), day_s['low'].min()
        
        if s_open <= p_low or s_open >= p_high:
            result["status"] = "Skipped (Invalid Open)"
            result["details"] = "S session open was outside P session range."
            return result
            
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
            result.update({
                "direction": trade_dir,
                "entry_price": round(entry, 2),
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
# BASE44 API INTEGRATION: DUPLICATE CHECK & TRADE LOGGER
# ==============================================================================
def find_existing_base44_trade(api_key: str, strategy_id: str, symbol: str, date_str: str) -> dict | None:
    """Requirement A: Verify if trade has already been recorded in Base44."""
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
            for item in items:
                entry_ts = str(item.get("entry_timestamp", ""))
                if entry_ts.startswith(date_str):
                    return item
    except Exception as e:
        print(f"Error checking Base44 trade: {e}")
    return None

def log_trade_to_base44(api_key: str, strategy_id: str, trade_info: dict, amount: float, fees: float) -> tuple[str, str, dict]:
    """
    Requirement B: Log trade into Base44 Trade Journal using exact strict format:
    payload = {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "direction": direction.lower(),
        "buy_price": float(entry_price),
        "quantity": float(amount),
        "fees": float(fees),
        "entry_timestamp": datetime.utcnow().isoformat() + "Z",
        "status": "open",
        "notes": f"{sl_percentage}% SL , {tp_percentage}% TP"
    }
    """
    if not api_key:
        return "Not Connected", "Base44 API Key not provided.", {}

    symbol = trade_info["symbol"]
    direction = trade_info["direction"]
    entry_price = float(trade_info["entry_price"])
    sl_pct = trade_info["sl_percentage"]
    tp_pct = trade_info["tp_percentage"]
    trade_date_str = trade_info.get("date", datetime.date.today().isoformat())

    # Requirement A: Duplicate Check
    existing = find_existing_base44_trade(api_key, strategy_id, symbol, trade_date_str)
    if existing:
        return "Skipped (Duplicate)", f"Trade already logged for {trade_date_str} (ID: {existing.get('id', 'N/A')}).", existing

    # Requirement B: POST Payload
    payload = {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "direction": direction.lower(),
        "buy_price": float(entry_price),
        "quantity": float(amount),
        "fees": float(fees),
        "entry_timestamp": dt.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "open",
        "notes": f"{sl_pct}% SL , {tp_pct}% TP"
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        resp = requests.post(BASE44_API_URL, headers=headers, json=payload, timeout=12)
        if resp.status_code in [200, 201]:
            created = resp.json() if resp.text else payload
            return "Success", f"Logged {symbol} {direction.upper()} to Base44 successfully.", created
        else:
            return "Error", f"Base44 API HTTP {resp.status_code}: {resp.text}", payload
    except Exception as e:
        return "Error", f"Network error sending to Base44: {str(e)}", payload

# ==============================================================================
# FASTAPI ENDPOINTS (VERCEL READY)
# ==============================================================================
@app.get("/")
@app.get("/api")
@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "message": "Base44 Daily Strategy Runner API is running.",
        "strategies": [
            {"id": STRAT1_ID, "name": "USDJPY SELFSWEEP", "symbol": "USDJPY"},
            {"id": STRAT2_ID, "name": "GBPUSD ASIA 1.2 - 1.4 FIB RETRACMENT", "symbol": "GBPUSD"},
            {"id": STRAT3_ID, "name": "XAUUSD 2H 4:30/5:30 DOL", "symbol": "XAUUSD"}
        ]
    }

@app.post("/api/run")
@app.post("/run")
@app.post("/")
async def run_daily_strategies(payload: RunRequest):
    """
    Executes the 3 daily strategies for the requested date,
    performs duplicate check, and logs valid setups directly to Base44 Trade Journal.
    """
    # 1. Resolve date
    if payload.date:
        try:
            target_date = dt.strptime(payload.date[:10], "%Y-%m-%d").date()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    else:
        target_date = datetime.date.today()

    amount = float(payload.amount if payload.amount is not None else 1.0)
    fees = float(payload.fees if payload.fees is not None else 40.0)

    # 2. Execute 3 Strategy Models
    res_usdjpy = run_usdjpy_strategy(target_date)
    res_gbpusd = run_gbpusd_strategy(target_date)
    res_xauusd = run_xauusd_strategy(target_date)

    strategies_out = [
        (res_usdjpy, STRAT1_ID),
        (res_gbpusd, STRAT2_ID),
        (res_xauusd, STRAT3_ID)
    ]

    results_list = []
    logged_count = 0
    duplicate_count = 0
    active_count = 0

    # 3. Base44 Synchronization
    for strat_result, strat_id in strategies_out:
        is_active = strat_result["direction"] in ["long", "short"]
        if is_active:
            active_count += 1
            sync_status, sync_msg, record_data = log_trade_to_base44(
                BASE44_API_KEY, strat_id, strat_result, amount, fees
            )
            if sync_status == "Success":
                logged_count += 1
            elif sync_status == "Skipped (Duplicate)":
                duplicate_count += 1
        else:
            sync_status = "N/A (No Setup)"
            sync_msg = "No signal triggered for live execution."
            record_data = {}

        results_list.append({
            "strategy_name": strat_result["strategy_name"],
            "strategy_id": strat_id,
            "symbol": strat_result["symbol"],
            "date": target_date.strftime("%Y-%m-%d"),
            "direction": strat_result["direction"].upper() if is_active else "NONE",
            "entry_price": strat_result["entry_price"],
            "sl_price": strat_result["sl_price"],
            "tp_price": strat_result["tp_price"],
            "sl_percentage": strat_result["sl_percentage"],
            "tp_percentage": strat_result["tp_percentage"],
            "status": strat_result["status"],
            "details": strat_result["details"],
            "data_source": strat_result.get("data_source", "OANDA"),
            "base44_sync": sync_status,
            "base44_message": sync_msg,
            "base44_record": record_data
        })

    return {
        "status": "success",
        "date": target_date.strftime("%Y-%m-%d"),
        "amount": amount,
        "fees": fees,
        "summary": {
            "total_strategies": 3,
            "active_signals": active_count,
            "logged_trades": logged_count,
            "duplicates": duplicate_count,
            "skipped_or_no_setup": 3 - active_count
        },
        "results": results_list
    }

@app.get("/api/run")
@app.get("/api/health")
@app.get("/health")
async def health_check():
    return {
        "status": "online",
        "service": "Base44 Daily Strategy Runner API",
        "message": "Send a POST request with JSON payload {'date': 'YYYY-MM-DD', 'amount': 1.0, 'fees': 40.0} to execute strategies."
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


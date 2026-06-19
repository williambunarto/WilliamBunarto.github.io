""" 
btc_signal.py — BTC/USDT perpetual trading signal engine for wbagent.
Standalone module: imports nothing from existing screener code.
"""

__version__ = "1.0.7"

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv("/home/ubuntu/.env")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BYBIT_BASE   = "https://api.bybit.com/v5/market"
WIB          = timezone(timedelta(hours=7))
STATE_FILE   = "/home/ubuntu/wbagent/btc_signal_state.json"
LOG_FILE     = "/home/ubuntu/wbagent/logs/btc_signal.log"
WBTRADE_BASE = "http://127.0.0.1:8001"  # wbtrade uvicorn on port 8001

MIN_SCORE                  = 8.5
MAX_DAILY                  = 5
SAME_DIR_COOLDOWN_MINUTES  = 60

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("btc_signal")


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------
def _load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {
            "signals_today":   [],
            "signal_history":  [],
            "last_signal_date": "",
            "account_size":    float(os.getenv("TRADING_ACCOUNT_SIZE", "1000")),
        }


def _save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _reset_daily_if_needed(state: dict) -> dict:
    today_wib = datetime.now(WIB).strftime("%Y-%m-%d")
    if state.get("last_signal_date") != today_wib:
        history = state.get("signal_history", [])
        history.extend(state.get("signals_today", []))
        state["signal_history"] = history[-200:]
        state["signals_today"]   = []
        state["last_signal_date"] = today_wib
    return state


# ---------------------------------------------------------------------------
# Bybit data helpers
# ---------------------------------------------------------------------------
def _klines(interval: str, limit: int = 200, symbol: str = "BTCUSDT") -> list:
    r = requests.get(
        f"{BYBIT_BASE}/kline",
        params={"category": "linear", "symbol": symbol,
                "interval": interval, "limit": limit},
        timeout=12,
    )
    r.raise_for_status()
    raw = r.json()["result"]["list"]
    candles = []
    for d in reversed(raw):
        candles.append({
            "ts":    int(d[0]),
            "open":  float(d[1]),
            "high":  float(d[2]),
            "low":   float(d[3]),
            "close": float(d[4]),
            "vol":   float(d[5]),
        })
    return candles


def _long_short_ratio() -> Optional[float]:
    """Returns buy/sell ratio. >1 = more longs, <1 = more shorts."""
    try:
        r = requests.get(
            f"{BYBIT_BASE}/account-ratio",
            params={"category": "linear", "symbol": "BTCUSDT",
                    "period": "5min", "limit": 1},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()["result"]["list"]
        if data:
            buy  = float(data[0].get("buyRatio",  0.5))
            sell = float(data[0].get("sellRatio", 0.5))
            return buy / max(sell, 0.0001)
    except Exception as e:
        log.warning(f"L/S ratio fetch failed: {e}")
    return None


def _liquidation_clusters() -> dict:
    """Approximate liquidation pressure from recent trades. Returns {'above': price, 'below': price}."""
    try:
        r = requests.get(
            f"{BYBIT_BASE}/liquidation",
            params={"category": "linear", "symbol": "BTCUSDT", "limit": 200},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()["result"]["list"]
        if data:
            prices = [float(d["price"]) for d in data]
            current = prices[0] if prices else 0
            above = [p for p in prices if p > current]
            below = [p for p in prices if p < current]
            return {
                "above": min(above) if above else None,
                "below": max(below) if below else None,
            }
    except Exception:
        pass
    return {"above": None, "below": None}


# ---------------------------------------------------------------------------
# Indicators (pure Python — no pandas-ta required)
# ---------------------------------------------------------------------------
def _ema(values: list, period: int) -> list:
    if not values:
        return []
    k = 2.0 / (period + 1)
    result = [values[0]]
    for v in values[1:]:
        result.append(v * k + result[-1] * (1.0 - k))
    return result


def _rsi(closes: list, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    changes  = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains    = [max(c, 0.0) for c in changes]
    losses   = [max(-c, 0.0) for c in changes]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def _macd(closes: list, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
    """Returns (macd_val, signal_val, histogram) at last candle."""
    if len(closes) < slow + signal:
        return 0.0, 0.0, 0.0
    fast_ema  = _ema(closes, fast)
    slow_ema  = _ema(closes, slow)
    macd_line = [f - s for f, s in zip(fast_ema[slow - 1:], slow_ema[slow - 1:])]
    if len(macd_line) < signal:
        return macd_line[-1], 0.0, macd_line[-1]
    sig_line = _ema(macd_line, signal)
    return macd_line[-1], sig_line[-1], macd_line[-1] - sig_line[-1]


def _vwap_daily(candles_5m: list) -> float:
    """Daily VWAP anchored at 00:00 UTC."""
    now_utc   = datetime.now(timezone.utc)
    midnight  = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    midnight_ms = int(midnight.timestamp() * 1000)
    today = [c for c in candles_5m if c["ts"] >= midnight_ms]
    if not today:
        today = candles_5m[-48:]
    cum_tpv = sum((c["high"] + c["low"] + c["close"]) / 3.0 * c["vol"] for c in today)
    cum_vol  = sum(c["vol"] for c in today)
    return cum_tpv / cum_vol if cum_vol > 0 else candles_5m[-1]["close"]


def _volume_profile(candles_5m: list, buckets: int = 60) -> dict:
    """Returns VAH, VAL, POC from last 24h of 5m candles."""
    data = candles_5m[-288:]
    if not data:
        p = candles_5m[-1]["close"]
        return {"poc": p, "vah": p * 1.01, "val": p * 0.99}
    lo = min(c["low"]  for c in data)
    hi = max(c["high"] for c in data)
    if hi <= lo:
        return {"poc": hi, "vah": hi, "val": lo}
    bucket_size    = (hi - lo) / buckets
    vol_by_bucket  = [0.0] * buckets
    for c in data:
        mid = (c["high"] + c["low"] + c["close"]) / 3.0
        idx = min(int((mid - lo) / bucket_size), buckets - 1)
        vol_by_bucket[idx] += c["vol"]
    poc_idx  = vol_by_bucket.index(max(vol_by_bucket))
    poc      = lo + poc_idx * bucket_size + bucket_size / 2.0
    total    = sum(vol_by_bucket)
    t30, t70 = total * 0.30, total * 0.70
    cum = 0.0
    val_price, vah_price = lo, hi
    val_found, vah_found = False, False
    for i, v in enumerate(vol_by_bucket):
        cum += v
        if not val_found and cum >= t30:
            val_price = lo + i * bucket_size
            val_found = True
        if not vah_found and cum >= t70:
            vah_price = lo + i * bucket_size
            vah_found = True
            break
    return {
        "poc": round(poc, 1),
        "vah": round(vah_price, 1),
        "val": round(val_price, 1),
    }


def _swing_levels(candles: list, lookback: int = 50, wing: int = 3) -> dict:
    """Recent swing highs and lows on given candles."""
    data   = candles[-lookback:]
    highs, lows = [], []
    for i in range(wing, len(data) - wing):
        c = data[i]
        if all(c["high"] >= data[j]["high"] for j in range(i - wing, i + wing + 1) if j != i):
            highs.append(round(c["high"], 1))
        if all(c["low"] <= data[j]["low"] for j in range(i - wing, i + wing + 1) if j != i):
            lows.append(round(c["low"], 1))
    return {
        "highs": sorted(set(highs), reverse=True)[:6],
        "lows":  sorted(set(lows))[:6],
    }


def _volume_delta(candles: list, lookback: int = 10) -> float:
    """Approximate buy-sell balance over last N candles. Range [-1, 1]."""
    recent   = candles[-lookback:]
    buy_vol  = sum(c["vol"] for c in recent if c["close"] >= c["open"])
    sell_vol = sum(c["vol"] for c in recent if c["close"] < c["open"])
    total    = buy_vol + sell_vol
    if total == 0:
        return 0.0
    return (buy_vol - sell_vol) / total


# ---------------------------------------------------------------------------
# Signal scoring
# ---------------------------------------------------------------------------
def _compute_score(data: dict) -> dict:
    c4h  = data["c4h"]
    c1h  = data["c1h"]
    c15m = data["c15m"]
    c5m  = data["c5m"]
    ls_ratio = data["ls_ratio"]
    liq  = data.get("liq", {"above": None, "below": None})

    cl4h  = [c["close"] for c in c4h]
    cl1h  = [c["close"] for c in c1h]
    cl15m = [c["close"] for c in c15m]
    cl5m  = [c["close"] for c in c5m]
    price = cl5m[-1]

    n4h      = len(cl4h)
    ema200_4h = _ema(cl4h, min(200, n4h))[-1]
    ema50_4h  = _ema(cl4h, min(50, n4h))[-1]
    macro_bull = price > ema200_4h and ema50_4h > ema200_4h
    macro_bear = price < ema200_4h and ema50_4h < ema200_4h

    n1h      = len(cl1h)
    ema200_1h = _ema(cl1h, min(200, n1h))[-1]
    ema50_1h  = _ema(cl1h, min(50, n1h))[-1]
    h1_bull = price > ema50_1h and price > ema200_1h
    h1_bear = price < ema50_1h and price < ema200_1h

    rsi_15m          = _rsi(cl15m)
    macd_l, macd_s, macd_h = _macd(cl15m)
    macd_bull = macd_l > macd_s and macd_h > 0
    macd_bear = macd_l < macd_s and macd_h < 0
    rsi_os    = rsi_15m < 35
    rsi_ob    = rsi_15m > 65

    ema9_5m   = _ema(cl5m, 9)
    ema21_5m  = _ema(cl5m, 21)
    ema50_5m  = _ema(cl5m, 50)
    ema9_cur, ema9_prev   = ema9_5m[-1],  ema9_5m[-2]
    ema21_cur, ema21_prev = ema21_5m[-1], ema21_5m[-2]
    ema_bull_cross = ema9_prev < ema21_prev and ema9_cur > ema21_cur
    ema_bear_cross = ema9_prev > ema21_prev and ema9_cur < ema21_cur

    vols_5m  = [c["vol"] for c in c5m]
    vol_ma20 = sum(vols_5m[-21:-1]) / 20 if len(vols_5m) >= 21 else sum(vols_5m) / max(len(vols_5m), 1)
    vol_spike = vols_5m[-1] > vol_ma20 * 1.8

    vwap      = _vwap_daily(c5m)
    vwap_bull = price > vwap
    vwap_bear = price < vwap

    vp    = _volume_profile(c5m)
    delta = _volume_delta(c5m)

    swing = _swing_levels(c1h, lookback=50)

    liq_above = liq.get("above")
    liq_below = liq.get("below")
    liq_tp_bull = liq_above is not None and liq_above > price * 1.02
    liq_tp_bear = liq_below is not None and liq_below < price * 0.98

    ls_bull = ls_ratio is not None and ls_ratio < 0.9
    ls_bear = ls_ratio is not None and ls_ratio > 1.1

    def _score_direction(is_long: bool) -> tuple:
        score  = 0.0
        detail = {}

        if is_long:
            if macro_bull:            pts = 2.0
            elif price > ema50_4h:    pts = 1.0
            else:                     pts = 0.0
        else:
            if macro_bear:            pts = 2.0
            elif price < ema50_4h:    pts = 1.0
            else:                     pts = 0.0
        score += pts; detail["4h_trend"] = pts

        if is_long:
            if h1_bull:               pts = 1.0
            elif price > ema200_1h:   pts = 0.5
            else:                     pts = 0.0
        else:
            if h1_bear:               pts = 1.0
            elif price < ema200_1h:   pts = 0.5
            else:                     pts = 0.0
        score += pts; detail["1h_ema"] = pts

        m = 0.0
        if is_long:
            if macd_bull:      m += 1.0
            if rsi_os:         m += 1.0
            elif rsi_15m < 50: m += 0.5
            if rsi_ob:         m -= 0.5
        else:
            if macd_bear:      m += 1.0
            if rsi_ob:         m += 1.0
            elif rsi_15m > 50: m += 0.5
            if rsi_os:         m -= 0.5
        pts = max(0.0, min(m, 2.0))
        score += pts; detail["15m_momentum"] = pts

        e = 0.0
        if is_long     and ema_bull_cross: e += 0.7
        if not is_long and ema_bear_cross: e += 0.7
        if vol_spike:                      e += 0.3
        pts = min(e, 1.0)
        score += pts; detail["5m_entry"] = pts

        pts = 1.0 if (is_long and vwap_bull) or (not is_long and vwap_bear) else 0.0
        score += pts; detail["vwap"] = pts

        above_sr = [h for h in swing["highs"] if h > price * 1.02]
        below_sr = [l for l in swing["lows"]  if l < price * 0.98]
        if is_long:
            pts = 1.0 if (liq_tp_bull or bool(above_sr)) else 0.0
        else:
            pts = 1.0 if (liq_tp_bear or bool(below_sr)) else 0.0
        score += pts; detail["tp_magnet"] = pts

        if is_long:
            pts = 1.0 if delta > 0.15 else (0.5 if delta > 0 else 0.0)
        else:
            pts = 1.0 if delta < -0.15 else (0.5 if delta < 0 else 0.0)
        score += pts; detail["vol_delta"] = pts

        if is_long:
            pts = 1.0 if ls_bull else (0.5 if ls_ratio is None else 0.0)
        else:
            pts = 1.0 if ls_bear else (0.5 if ls_ratio is None else 0.0)
        score += pts; detail["ls_ratio"] = pts

        return round(score, 2), detail

    long_score,  long_detail  = _score_direction(True)
    short_score, short_detail = _score_direction(False)

    if long_score >= short_score:
        direction, score, detail = "LONG",  long_score,  long_detail
    else:
        direction, score, detail = "SHORT", short_score, short_detail

    tf = 0
    if direction == "LONG":
        tf += int(macro_bull) + int(h1_bull) + int(macd_bull) + int(ema9_cur > ema21_cur)
    else:
        tf += int(macro_bear) + int(h1_bear) + int(macd_bear) + int(ema9_cur < ema21_cur)
    confidence = round(tf / 4.0 * 10, 1)

    return {
        "score":      score,
        "direction":  direction,
        "confidence": confidence,
        "detail":     detail,
        "price":      price,
        "vwap":       round(vwap, 2),
        "vp":         vp,
        "swing":      swing,
        "rsi_15m":    round(rsi_15m, 1),
        "macd_hist":  round(macd_h, 2),
        "vol_delta":  round(delta, 3),
        "ema9_5m":    round(ema9_cur, 2),
        "ema21_5m":   round(ema21_cur, 2),
        "ema50_5m":   round(ema50_5m[-1], 2),
        "ema200_4h":  round(ema200_4h, 2),
        "ls_ratio":   round(ls_ratio, 3) if ls_ratio else None,
        "liq_above":  liq_above,
        "liq_below":  liq_below,
    }


def _trade_params(sig: dict, account_size: float) -> dict:
    price     = sig["price"]
    direction = sig["direction"]
    swing     = sig["swing"]
    vwap      = sig["vwap"]
    ema21     = sig["ema21_5m"]
    vp        = sig["vp"]
    leverage  = 5

    if direction == "LONG":
        candidates = sorted(
            [v for v in [ema21, vwap, vp["val"]] if v < price * 1.003],
            reverse=True
        )
        entry = round(candidates[0] if candidates else price * 0.9990, 1)
        lows = sorted([l for l in swing["lows"] if l < entry * 0.997])
        sl   = round((max(lows) * 0.9975) if lows else entry * (1 - 0.025), 1)
        tp1_cands = [h for h in swing["highs"] if h > entry * 1.02]
        tp1_cands.append(vp["vah"] if vp["vah"] > entry * 1.02 else entry * 1.04)
        tp1 = round(min(tp1_cands), 1)
        tp2_cands = [h for h in swing["highs"] if h > tp1 * 1.015]
        tp2 = round(min(tp2_cands) if tp2_cands else tp1 * 1.065, 1)
    else:
        candidates = sorted(
            [v for v in [ema21, vwap, vp["vah"]] if v > price * 0.997]
        )
        entry = round(candidates[0] if candidates else price * 1.0010, 1)
        highs = sorted([h for h in swing["highs"] if h > entry * 1.003])
        sl    = round((min(highs) * 1.0025) if highs else entry * (1 + 0.025), 1)
        tp1_cands = [l for l in swing["lows"] if l < entry * 0.98]
        tp1_cands.append(vp["val"] if vp["val"] < entry * 0.98 else entry * 0.96)
        tp1 = round(max(tp1_cands), 1)
        tp2_cands = [l for l in swing["lows"] if l < tp1 * 0.985]
        tp2 = round(max(tp2_cands) if tp2_cands else tp1 * 0.935, 1)

    sl_dist    = abs(entry - sl)
    sl_pct     = round(sl_dist / entry * 100, 2)
    risk_amt   = account_size * 0.02
    pos_sz     = round(risk_amt / (sl_pct / 100), 2) if sl_pct > 0 else account_size
    tp1_pct  = round(abs(tp1 - entry) / entry * 100, 2)
    tp2_pct  = round(abs(tp2 - entry) / entry * 100, 2)
    tp1_usd  = round(pos_sz * tp1_pct / 100, 2)
    tp2_usd  = round(pos_sz * tp2_pct / 100, 2)

    return {
        "entry":         entry,
        "sl":            sl,
        "sl_pct":        sl_pct,
        "sl_usd":        round(risk_amt, 2),
        "tp1":           tp1,
        "tp1_pct":       tp1_pct,
        "tp1_usd":       tp1_usd,
        "tp2":           tp2,
        "tp2_pct":       tp2_pct,
        "tp2_usd":       tp2_usd,
        "position_size": pos_sz,
        "leverage":      leverage,
    }


def _commentary(sig: dict) -> str:
    d         = sig["direction"]
    score     = sig["score"]
    detail    = sig["detail"]
    rsi       = sig["rsi_15m"]
    macro_pts = detail.get("4h_trend", 0)
    macd_pts  = detail.get("15m_momentum", 0)
    vwap_pts  = detail.get("vwap", 0)

    if d == "LONG":
        if score >= 9.5 and macro_pts >= 2.0:
            return (
                "This is the kind of setup we wait for. Bitcoin just reclaimed a major level "
                "with real buying pressure behind it. I'd be more afraid of missing this than taking it."
            )
        if score >= 9.0:
            return (
                "Strong long setup — macro trend, momentum, and structure all agree. "
                "Entry near VWAP with defined risk makes this a high-conviction play."
            )
        if score >= 8.5 and macd_pts >= 1.0 and vwap_pts >= 1.0:
            return (
                "Price is holding above VWAP with momentum building on the 15-minute. "
                "Decent setup with good structure — take TP1 and reassess from there."
            )
        return (
            "Conditions are lining up but the setup isn't perfect. "
            "Cautious entry — honor the stop and don't get attached to TP2 yet."
        )
    else:
        if score >= 9.5 and macro_pts >= 2.0:
            return (
                "Smart money is getting out. The move up was weak and volume doesn't support it. "
                "This is a high-probability fade with clear risk management."
            )
        if score >= 9.0:
            return (
                "Structure has broken down on multiple timeframes. "
                "Price below VWAP with negative delta — sellers are clearly in control."
            )
        if rsi > 65:
            return (
                "Overextended rally meeting strong resistance. "
                "RSI is stretched and MACD is rolling over — disciplined short entry."
            )
        return (
            "Market's showing weakness but conviction isn't maximum here. "
            "Take TP1 and reassess before holding toward TP2."
        )


def run_scan(force: bool = False) -> Optional[dict]:
    """
    Full signal scan. Returns signal dict if fired, None if suppressed.
    force=True bypasses score/limit/duplicate guards (for /btcsignal command).
    """
    state = _load_state()
    state = _reset_daily_if_needed(state)

    log.info("Starting scan...")

    try:
        c4h  = _klines("240", 210)
        c1h  = _klines("60",  210)
        c15m = _klines("15",  100)
        c5m  = _klines("5",   300)
        ls_ratio = _long_short_ratio()
        liq      = _liquidation_clusters()
    except Exception as e:
        log.error(f"Data fetch failed: {e}")
        return None

    data   = {"c4h": c4h, "c1h": c1h, "c15m": c15m, "c5m": c5m,
               "ls_ratio": ls_ratio, "liq": liq}
    signal = _compute_score(data)

    direction  = signal["direction"]
    score      = signal["score"]
    account    = state.get("account_size", 1000.0)
    params     = _trade_params(signal, account)
    commentary = _commentary(signal)

    non_force_count = len([s for s in state["signals_today"] if not s.get("force")])
    if not force and non_force_count >= MAX_DAILY:
        log.info(f"Score: {score} | Dir: {direction} | Fired: no | Reason: daily limit reached ({MAX_DAILY})")
        return None

    if not force and score < MIN_SCORE:
        log.info(f"Score: {score:.2f} | Dir: {direction} | Fired: no | Reason: score {score:.2f} < {MIN_SCORE}")
        return None

    if not force:
        now_ts = time.time()
        same_dir_recent = [
            s for s in state["signals_today"]
            if s.get("direction") == direction
            and (now_ts - s.get("ts", 0)) < SAME_DIR_COOLDOWN_MINUTES * 60
        ]
        if same_dir_recent and score < 9.0:
            log.info(f"Score: {score:.2f} | Dir: {direction} | Fired: no | Reason: duplicate within 1h, score < 9.0")
            return None

    signal_id  = hashlib.md5(f"{direction}{int(time.time() * 1000)}".encode()).hexdigest()[:8]
    now_wib    = datetime.now(WIB)
    expiry_min = 120 if score >= 9.0 else 45
    expiry_wib = now_wib + timedelta(minutes=expiry_min)

    result = {
        "signal_id":     signal_id,
        "direction":     direction,
        "score":         score,
        "confidence":    signal["confidence"],
        "entry":         params["entry"],
        "sl":            params["sl"],
        "sl_pct":        params["sl_pct"],
        "sl_usd":        params["sl_usd"],
        "tp1":           params["tp1"],
        "tp1_pct":       params["tp1_pct"],
        "tp1_usd":       params["tp1_usd"],
        "tp2":           params["tp2"],
        "tp2_pct":       params["tp2_pct"],
        "tp2_usd":       params["tp2_usd"],
        "position_size": params["position_size"],
        "leverage":      params["leverage"],
        "account_size":  account,
        "commentary":    commentary,
        "signal_time":   now_wib.strftime("%H:%M WIB"),
        "expiry_time":   expiry_wib.strftime("%H:%M WIB"),
        "date_str":      now_wib.strftime("%d %b %Y"),
        "ts":            time.time(),
        "timeframe":     "5m",
        "vwap":          signal["vwap"],
        "rsi_15m":       signal["rsi_15m"],
        "macd_hist":     signal["macd_hist"],
        "detail":        signal["detail"],
    }

    state["signals_today"].append({**result, "force": force})
    _save_state(state)

    log.info(f"Score: {score:.2f} | Dir: {direction} | Fired: yes | ID: {signal_id}")
    return result


def format_signal_message(sig: dict) -> str:
    return (
        f"\U0001f48e WBAGENT TRADING SIGNAL\n"
        f"━" * 16 + "\n"
        f"BTC/USDT • {sig['direction']} • 5x Isolated\n"
        f"{sig['date_str']} {sig['signal_time']} • Good until {sig['expiry_time']}\n"
        f"━" * 16 + "\n"
        f"\U0001f4b0 Entry  : ${sig['entry']:,.1f}\n"
        f"\U0001f6d1 SL     : ${sig['sl']:,.1f} ({sig['sl_pct']}% | -${sig['sl_usd']:.2f} on ${sig['account_size']:,.0f})\n"
        f"\U0001f3af TP1    : ${sig['tp1']:,.1f} (+{sig['tp1_pct']}% | +${sig['tp1_usd']:.2f})\n"
        f"\U0001f680 TP2    : ${sig['tp2']:,.1f} (+{sig['tp2_pct']}% | +${sig['tp2_usd']:.2f})\n"
        f"━" * 16 + "\n"
        f"\U0001f4ca AI Score     : {sig['score']}/10\n"
        f"\U0001f916 Confidence   : {sig['confidence']}/10\n"
        f"━" * 16 + "\n"
        f"\U0001f4ac {sig['commentary']}\n"
        f"━" * 16 + "\n"
        f"\U0001f4dd /wintrade_{sig['signal_id']} • /losstrade_{sig['signal_id']} • /skiptrade_{sig['signal_id']}"
    )


def log_trade_to_wbtrade(sig: dict, outcome: str, pnl_usdt: float,
                          exit_price: Optional[float] = None) -> bool:
    payload = {
        "direction":          sig["direction"].lower(),
        "entry_price":        str(sig["entry"]),
        "position_size_usdt": str(sig["position_size"]),
        "leverage":           "5",
        "stop_loss":          str(sig["sl"]),
        "take_profit":        str(sig["tp1"]),
        "outcome":            outcome.lower(),
        "setup_tag":          "btcsignal",
        "volume_tag":         f"score_{sig['score']}",
        "notes":              (
            f"Signal ID: {sig['signal_id']} | "
            f"Score: {sig['score']}/10 | "
            f"Confidence: {sig['confidence']}/10 | "
            f"RSI15m: {sig.get('rsi_15m', '?')} | "
            f"MACD hist: {sig.get('macd_hist', '?')}"
        ),
    }
    if exit_price:
        payload["exit_price"] = str(exit_price)
    if pnl_usdt is not None:
        payload["pnl_usdt"] = str(round(pnl_usdt, 4))

    try:
        r = requests.post(f"{WBTRADE_BASE}/api/trades/", data=payload, timeout=15)
        r.raise_for_status()
        log.info(f"wbtrade logged: {outcome} | PnL ${pnl_usdt:.2f}")
        return True
    except Exception as e:
        log.error(f"wbtrade API failed ({e}) — saving locally for retry")
        _save_failed_trade(payload, sig)
        return False


def _save_failed_trade(payload: dict, sig: dict):
    path = "/home/ubuntu/wbagent/failed_trades.json"
    try:
        existing = []
        if os.path.exists(path):
            with open(path) as f:
                existing = json.load(f)
        existing.append({"payload": payload, "ts": time.time()})
        with open(path, "w") as f:
            json.dump(existing[-50:], f, indent=2)
    except Exception:
        pass


if __name__ == "__main__":
    import sys
    force = "--test" in sys.argv
    print(f"{'[TEST MODE] ' if force else ''}Running BTC/USDT signal scan...\n")
    result = run_scan(force=force)
    if result:
        print(format_signal_message(result))
        print(f"\nscore={result['score']} | dir={result['direction']} | confidence={result['confidence']}/10")
        print(f"detail: {result['detail']}")
    else:
        print("No signal fired.")
        print("Use --test to force output regardless of score.")

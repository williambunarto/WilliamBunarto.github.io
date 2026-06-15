import requests
import os
import json
from datetime import datetime

BYBIT_BASE = "https://api.bybit.com/v5/market"
FNG_URL    = "https://api.alternative.me/fng/?limit=1"
GROK_URL   = "https://api.x.ai/v1/chat/completions"

STATE_MAP = {
    "super long":  "super_long",
    "long":        "long",
    "neutral":     "neutral",
    "short":       "short",
    "super short": "super_short",
}

LABEL_MAP = {
    "super_long":  "Super Long",
    "long":        "Long",
    "neutral":     "Neutral",
    "short":       "Short",
    "super_short": "Super Short",
}


def _bybit_klines(symbol="BTCUSDT", interval="240", limit=50):
    r = requests.get(
        f"{BYBIT_BASE}/kline",
        params={"category": "linear", "symbol": symbol,
                "interval": interval, "limit": limit},
        timeout=10
    )
    r.raise_for_status()
    data = r.json()["result"]["list"]
    rows = []
    for d in reversed(data):
        rows.append({
            "ts": int(d[0]),
            "open":  float(d[1]),
            "high":  float(d[2]),
            "low":   float(d[3]),
            "close": float(d[4]),
            "vol":   float(d[5]),
        })
    return rows


def _bybit_funding_rate(symbol="BTCUSDT"):
    r = requests.get(
        f"{BYBIT_BASE}/funding/history",
        params={"category": "linear", "symbol": symbol, "limit": 1},
        timeout=10
    )
    r.raise_for_status()
    lst = r.json()["result"]["list"]
    return float(lst[0]["fundingRate"]) if lst else 0.0


def _bybit_price(symbol="BTCUSDT"):
    r = requests.get(
        f"{BYBIT_BASE}/tickers",
        params={"category": "linear", "symbol": symbol},
        timeout=10
    )
    r.raise_for_status()
    return float(r.json()["result"]["list"][0]["lastPrice"])


def _ema(values, period):
    k = 2 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def signal_ema(candles_4h) -> float:
    closes = [c["close"] for c in candles_4h]
    if len(closes) < 50:
        return 0.0
    ema20  = _ema(closes[-20:], 20)
    ema50  = _ema(closes[-50:], 50)
    ema200 = _ema(closes, 200) if len(closes) >= 200 else _ema(closes, len(closes))
    price  = closes[-1]

    score = 0.0
    if ema20 > ema50:   score += 0.7
    elif ema20 < ema50: score -= 0.7
    if price > ema20:   score += 0.5
    elif price < ema20: score -= 0.5
    if price > ema50:   score += 0.4
    elif price < ema50: score -= 0.4
    if price > ema200:  score += 0.4
    elif price < ema200: score -= 0.4

    return max(-2.0, min(2.0, score))


def signal_volume(candles_1h) -> float:
    if len(candles_1h) < 6:
        return 0.0
    recent = candles_1h[-6:]
    buy_vol  = sum(c["vol"] for c in recent if c["close"] >= c["open"])
    sell_vol = sum(c["vol"] for c in recent if c["close"] < c["open"])
    total    = buy_vol + sell_vol
    if total == 0:
        return 0.0
    ratio = buy_vol / total
    score = (ratio - 0.5) * 8
    return max(-2.0, min(2.0, score))


def signal_funding(rate: float) -> float:
    if rate > 0.015:    return -2.0
    if rate > 0.008:    return -1.0
    if rate > 0.003:    return -0.5
    if rate < -0.005:   return  2.0
    if rate < -0.002:   return  1.0
    return 0.0


def signal_fng(value: int) -> float:
    if value <= 15:   return  2.0
    if value <= 25:   return  1.0
    if value <= 40:   return  0.5
    if value >= 85:   return -2.0
    if value >= 75:   return -1.0
    if value >= 60:   return -0.5
    return 0.0


def fetch_fng():
    try:
        r = requests.get(FNG_URL, timeout=10)
        d = r.json()["data"][0]
        return int(d["value"]), d["value_classification"]
    except Exception:
        return 50, "Neutral"


def grok_classify(ema_s, vol_s, fund_s, fng_s, composite,
                  funding_rate, fng_val, fng_label, btc_price, grok_key):
    if not grok_key:
        if composite >= 1.4:   label = "Super Long"
        elif composite >= 0.5: label = "Long"
        elif composite <= -1.4: label = "Super Short"
        elif composite <= -0.5: label = "Short"
        else:                   label = "Neutral"
        return label, "Signal-based classification (Grok not configured).", ""

    prompt = (
        f"You are a crypto market analyst. Given these real-time BTC signals, classify the current market bias.\n\n"
        f"Signals:\n"
        f"- EMA trend score: {ema_s:+.2f} (range -2 to +2, positive = bullish)\n"
        f"- Volume pressure score: {vol_s:+.2f} (positive = buy pressure dominant)\n"
        f"- Funding rate: {funding_rate:.4f} → score {fund_s:+.2f} (high positive = overleveraged longs = bearish fade)\n"
        f"- Fear & Greed Index: {fng_val}/100 ({fng_label}) → score {fng_s:+.2f} (contrarian)\n"
        f"- Composite weighted score: {composite:+.2f}\n"
        f"- BTC price: ${btc_price:,.0f}\n\n"
        f"Respond in this exact JSON format (no markdown):\n"
        f'{{"classification": "Super Long|Long|Neutral|Short|Super Short", '
        f'"reason": "one sentence explaining the dominant signal", '
        f'"risk": "one sentence on the main risk to this view"}}'
    )

    try:
        r = requests.post(
            GROK_URL,
            headers={"Authorization": f"Bearer {grok_key}", "Content-Type": "application/json"},
            json={"model": "grok-3-mini", "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 200, "temperature": 0.2},
            timeout=20
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()
        parsed  = json.loads(content)
        return parsed["classification"], parsed["reason"], parsed["risk"]
    except Exception as e:
        print(f"[Grok] Error: {e}")
        if composite >= 1.4:    label = "Super Long"
        elif composite >= 0.5:  label = "Long"
        elif composite <= -1.4: label = "Super Short"
        elif composite <= -0.5: label = "Short"
        else:                   label = "Neutral"
        return label, "Fallback classification (Grok error).", ""


def compute_market_state(grok_key: str = "") -> dict:
    print(f"[MarketEngine] Computing state at {datetime.utcnow().isoformat()}Z")

    candles_4h = _bybit_klines(interval="240", limit=50)
    candles_1h = _bybit_klines(interval="60",  limit=24)
    funding    = _bybit_funding_rate()
    price      = _bybit_price()
    fng_val, fng_label = fetch_fng()

    ema_s  = signal_ema(candles_4h)
    vol_s  = signal_volume(candles_1h)
    fund_s = signal_funding(funding)
    fng_s  = signal_fng(fng_val)

    composite = (ema_s * 0.30) + (vol_s * 0.25) + (fund_s * 0.25) + (fng_s * 0.20)

    label, reason, risk = grok_classify(
        ema_s, vol_s, fund_s, fng_s, composite,
        funding, fng_val, fng_label, price, grok_key
    )

    state_key = STATE_MAP.get(label.lower(), "neutral")

    result = {
        "state":         state_key,
        "label":         label,
        "score":         round(composite, 3),
        "ema_score":     round(ema_s, 3),
        "volume_score":  round(vol_s, 3),
        "funding_score": round(fund_s, 3),
        "fng_score":     round(fng_s, 3),
        "funding_rate":  round(funding, 6),
        "fng_value":     fng_val,
        "fng_label":     fng_label,
        "btc_price":     round(price, 2),
        "reason":        reason,
        "risk_note":     risk,
        "timestamp":     datetime.utcnow().isoformat() + "Z",
    }
    print(f"[MarketEngine] → {label} (score {composite:+.2f}) @ ${price:,.0f}")
    return result

import requests
import json
from datetime import datetime, timedelta
from market_engine import _bybit_klines, _bybit_price, _bybit_funding_rate, GROK_URL


def _recent_support_resistance(candles_4h, lookback=20):
    recent = candles_4h[-lookback:]
    highs  = [c["high"]  for c in recent]
    lows   = [c["low"]   for c in recent]
    return min(lows), max(highs)


def _avg_volume(candles_1h, period=20):
    vols = [c["vol"] for c in candles_1h[-period:]]
    return sum(vols) / len(vols) if vols else 1


def _last_volume(candles_1h):
    return candles_1h[-1]["vol"] if candles_1h else 0


def grok_alert_analysis(price, direction, key_level, funding_rate,
                        fng_val, fng_label, market_state_label, grok_key):
    if not grok_key:
        return None

    prompt = (
        f"BTC trade setup detected. Validate and provide levels.\n"
        f"Price: ${price:,.0f} | Direction: {direction.upper()}\n"
        f"Key level nearby: ${key_level:,.0f} | Market bias: {market_state_label}\n"
        f"Funding rate: {funding_rate:.4f} | Fear & Greed: {fng_val}/100 ({fng_label})\n\n"
        f"Respond in this exact JSON format (no markdown):\n"
        f'{{"valid": true, "entry_low": 0, "entry_high": 0, '
        f'"stop_loss": 0, "tp1": 0, "tp2": 0, '
        f'"reason": "one sentence on why this is a good setup"}}'
    )
    try:
        r = requests.post(
            GROK_URL,
            headers={"Authorization": f"Bearer {grok_key}", "Content-Type": "application/json"},
            json={"model": "grok-3-mini", "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 250, "temperature": 0.1},
            timeout=20
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()
        return json.loads(content)
    except Exception as e:
        print(f"[AlertGrok] Error: {e}")
        return None


def check_and_send_alert(db, state_data: dict, bot_token: str, chat_id: str,
                         grok_key: str, max_per_day: int = 3, cooldown_hours: int = 4):
    from database import AlertLog
    if not bot_token or not chat_id:
        print("[Alert] Telegram not configured, skipping.")
        return False

    state = state_data["state"]
    price = state_data["btc_price"]

    if state not in ("long", "super_long", "short", "super_short"):
        return False

    direction = "long" if state in ("long", "super_long") else "short"

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = db.query(AlertLog).filter(
        AlertLog.timestamp >= today_start,
        AlertLog.sent == True
    ).count()
    if today_count >= max_per_day:
        print(f"[Alert] Daily limit ({max_per_day}) reached.")
        return False

    cutoff = datetime.utcnow() - timedelta(hours=cooldown_hours)
    recent = db.query(AlertLog).filter(
        AlertLog.direction == direction,
        AlertLog.timestamp >= cutoff,
        AlertLog.sent == True
    ).first()
    if recent:
        print(f"[Alert] {direction} alert sent {cooldown_hours}h cooldown active.")
        return False

    try:
        candles_4h = _bybit_klines(interval="240", limit=25)
        candles_1h = _bybit_klines(interval="60",  limit=22)
        funding    = _bybit_funding_rate()
    except Exception as e:
        print(f"[Alert] Data fetch error: {e}")
        return False

    support, resistance = _recent_support_resistance(candles_4h)
    avg_vol  = _avg_volume(candles_1h)
    last_vol = _last_volume(candles_1h)

    if last_vol < avg_vol * 1.5:
        print(f"[Alert] Volume not confirmed ({last_vol:.0f} vs avg {avg_vol:.0f})")
        return False

    key_level = support if direction == "long" else resistance
    proximity = abs(price - key_level) / price
    if proximity > 0.012:
        print(f"[Alert] Price not near key level (${price:,.0f} vs ${key_level:,.0f}, {proximity:.2%})")
        return False

    if direction == "long" and funding > 0.01:
        print(f"[Alert] Funding {funding:.4f} too positive for long alert")
        return False
    if direction == "short" and funding < -0.005:
        print(f"[Alert] Funding {funding:.4f} too negative for short alert")
        return False

    analysis = grok_alert_analysis(
        price, direction, key_level, funding,
        state_data["fng_value"], state_data["fng_label"],
        state_data["label"], grok_key
    )

    icon  = "\U0001f7e2" if direction == "long"  else "\U0001f534"
    arrow = "⬆"  if direction == "long"  else "⬇"
    state_label = state_data["label"].upper()
    reason = state_data["reason"]
    fng_val = state_data["fng_value"]
    fng_lbl = state_data.get("fng_label", "")

    if analysis and analysis.get("valid"):
        entry_zone = f"${analysis['entry_low']:,.0f} – ${analysis['entry_high']:,.0f}"
        sl_line    = f"${analysis['stop_loss']:,.0f}"
        tp_line    = f"TP1 ${analysis['tp1']:,.0f}  |  TP2 ${analysis['tp2']:,.0f}"
        ai_reason  = analysis.get("reason", reason)
    else:
        sl_pct   = 0.008
        tp1_pct  = 0.01
        tp2_pct  = 0.02
        sl_price = price * (1 - sl_pct) if direction == "long" else price * (1 + sl_pct)
        tp1      = price * (1 + tp1_pct) if direction == "long" else price * (1 - tp1_pct)
        tp2      = price * (1 + tp2_pct) if direction == "long" else price * (1 - tp2_pct)
        entry_zone = f"~${price:,.0f}"
        sl_line    = f"${sl_price:,.0f}"
        tp_line    = f"TP1 ${tp1:,.0f}  |  TP2 ${tp2:,.0f}"
        ai_reason  = reason

    msg = (
        f"{icon} BTC {direction.upper()} SETUP\n"
        f"{'━' * 24}\n"
        f"Price       : ${price:,.2f}\n"
        f"Bias        : {arrow} {state_label}\n"
        f"\n"
        f"Entry zone  : {entry_zone}\n"
        f"Stop loss   : {sl_line}\n"
        f"{tp_line}\n"
        f"\n"
        f"Funding     : {funding:+.4f}\n"
        f"Fear & Greed: {fng_val}/100 — {fng_lbl}\n"
        f"\n"
        f"\U0001f4ca {ai_reason}\n"
        f"\n"
        f"→ williambunarto.duckdns.org/trade/journal"
    )

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": msg,
            "parse_mode": "HTML"
        }, timeout=10)
        resp.raise_for_status()
        print(f"[Alert] Sent {direction} alert @ ${price:,.0f}")

        log = AlertLog(direction=direction, btc_price=price, reason=ai_reason, sent=True)
        db.add(log)
        db.commit()
        return True
    except Exception as e:
        print(f"[Alert] Send failed: {e}")
        log = AlertLog(direction=direction, btc_price=price, reason=str(e), sent=False)
        db.add(log)
        db.commit()
        return False

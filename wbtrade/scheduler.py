from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime

scheduler = BackgroundScheduler(timezone="UTC")


def _get_setting(db, key, default=""):
    from database import Setting
    row = db.get(Setting, key)
    return row.value if row else default


def run_market_state_job():
    from market_engine import compute_market_state
    from database import MarketState, SessionLocal
    from telegram_alerts import check_and_send_alert

    db = SessionLocal()
    try:
        grok_key = _get_setting(db, "grok_api_key")
        result   = compute_market_state(grok_key=grok_key)

        row = MarketState(
            timestamp     = datetime.utcnow(),
            state         = result["state"],
            score         = result["score"],
            ema_score     = result["ema_score"],
            volume_score  = result["volume_score"],
            funding_score = result["funding_score"],
            fng_score     = result["fng_score"],
            funding_rate  = result["funding_rate"],
            fng_value     = result["fng_value"],
            btc_price     = result["btc_price"],
            reason        = result["reason"],
            risk_note     = result["risk_note"],
        )
        db.add(row)
        db.commit()
        print(f"[Scheduler] Market state saved: {result['state']}")

        bot_token    = _get_setting(db, "telegram_bot_token")
        chat_id      = _get_setting(db, "telegram_chat_id")
        max_per_day  = int(_get_setting(db, "alert_max_per_day", "3"))
        cooldown_hrs = int(_get_setting(db, "alert_cooldown_hours", "4"))

        check_and_send_alert(
            db=db,
            state_data=result,
            bot_token=bot_token,
            chat_id=chat_id,
            grok_key=grok_key,
            max_per_day=max_per_day,
            cooldown_hours=cooldown_hrs,
        )
    except Exception as e:
        print(f"[Scheduler] Job error: {e}")
    finally:
        db.close()


def start_scheduler():
    scheduler.add_job(
        run_market_state_job,
        trigger=IntervalTrigger(hours=1),
        id="market_state",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    print("[Scheduler] Started. Market state job runs every hour.")
    try:
        run_market_state_job()
    except Exception as e:
        print(f"[Scheduler] Initial run failed: {e}")


def stop_scheduler():
    scheduler.shutdown(wait=False)

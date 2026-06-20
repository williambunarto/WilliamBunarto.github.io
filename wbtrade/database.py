from sqlalchemy import (
    create_engine, Column, Integer, Float, String, Boolean,
    DateTime, Date, Text, ForeignKey
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from datetime import datetime
import os

DB_PATH = os.environ.get("WBTRADE_DB", "/home/ubuntu/wbtrade/data/trade.db")
# fallback for local dev
if not os.path.exists(os.path.dirname(DB_PATH)):
    DB_PATH = os.path.join(os.path.dirname(__file__), "data", "trade.db")

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


class MarketState(Base):
    __tablename__ = "market_state"
    id            = Column(Integer, primary_key=True)
    timestamp     = Column(DateTime, default=datetime.utcnow)
    state         = Column(String)
    score         = Column(Float)
    ema_score     = Column(Float)
    volume_score  = Column(Float)
    funding_score = Column(Float)
    fng_score     = Column(Float)
    funding_rate  = Column(Float)
    fng_value     = Column(Integer)
    btc_price     = Column(Float)
    reason        = Column(Text)
    risk_note     = Column(Text)


class Trade(Base):
    __tablename__ = "trades"
    id                  = Column(Integer, primary_key=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    direction           = Column(String)
    entry_price         = Column(Float)
    exit_price          = Column(Float)
    position_size_usdt  = Column(Float)
    leverage            = Column(Integer)
    stop_loss           = Column(Float)
    take_profit         = Column(Float)
    outcome             = Column(String)
    pnl_usdt            = Column(Float)
    r_multiple          = Column(Float)
    setup_tag           = Column(String)
    volume_tag          = Column(String)
    market_state_id     = Column(Integer, ForeignKey("market_state.id"))
    psychology_tag      = Column(String)
    rule_violations     = Column(Text)
    screenshot_path     = Column(String)
    notes               = Column(Text)
    plan_id             = Column(Integer, ForeignKey("trade_plans.id"), nullable=True)
    market              = Column(Text,    nullable=True)
    trade_type          = Column(Text,    nullable=True)
    qty                 = Column(Float,   nullable=True)
    opening_fee         = Column(Float,   nullable=True)
    closing_fee         = Column(Float,   nullable=True)
    funding_fee         = Column(Float,   nullable=True)
    trade_datetime      = Column(DateTime, nullable=True)


class SpotEntry(Base):
    __tablename__ = "spot_entries"
    id           = Column(Integer, primary_key=True)
    date         = Column(Date, default=datetime.utcnow)
    action       = Column(String)
    btc_amount   = Column(Float)
    price_usdt   = Column(Float)
    usdt_spent   = Column(Float)
    thesis_tag   = Column(String)
    notes        = Column(Text)


class SpotTarget(Base):
    __tablename__ = "spot_targets"
    id                  = Column(Integer, primary_key=True)
    label               = Column(String)
    price_usdt          = Column(Float)
    btc_percent_to_sell = Column(Float)
    status              = Column(String, default="active")


class DailyBias(Base):
    __tablename__ = "daily_bias"
    id                      = Column(Integer, primary_key=True)
    date                    = Column(Date, unique=True)
    pre_market_bias         = Column(Text)
    key_levels              = Column(Text)
    macro_notes             = Column(Text)
    system_state_snapshot   = Column(Text)
    post_session_notes      = Column(Text)
    day_rating              = Column(String)


class TradePlan(Base):
    __tablename__ = "trade_plans"
    id                   = Column(Integer, primary_key=True)
    created_at           = Column(DateTime, default=datetime.utcnow)
    direction            = Column(String)
    thesis               = Column(Text)
    entry_zone_low       = Column(Float)
    entry_zone_high      = Column(Float)
    stop_loss            = Column(Float)
    tp1                  = Column(Float)
    tp2                  = Column(Float)
    position_size_usdt   = Column(Float)
    invalidation         = Column(Text)
    market_state_at_plan = Column(String)
    status               = Column(String, default="open")


class Playbook(Base):
    __tablename__ = "playbook"
    id                = Column(Integer, primary_key=True)
    name              = Column(String)
    description       = Column(Text)
    conditions        = Column(Text)
    volume_behavior   = Column(Text)
    funding_context   = Column(Text)
    best_market_state = Column(String)
    screenshot_paths  = Column(Text)


class MonthlyReview(Base):
    __tablename__ = "monthly_reviews"
    id               = Column(Integer, primary_key=True)
    year             = Column(Integer)
    month            = Column(Integer)
    start_balance    = Column(Float)
    end_balance      = Column(Float)
    goals_set        = Column(Text)
    goals_achieved   = Column(Text)
    lessons          = Column(Text)
    next_goals       = Column(Text)
    emotional_pattern = Column(Text)


class AlertLog(Base):
    __tablename__ = "alert_log"
    id        = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    direction = Column(String)
    btc_price = Column(Float)
    reason    = Column(Text)
    sent      = Column(Boolean, default=False)


class Setting(Base):
    __tablename__ = "settings"
    key   = Column(String, primary_key=True)
    value = Column(Text)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    defaults = {
        "account_balance": "10000",
        "risk_percent": "1",
        "telegram_chat_id": "",
        "grok_api_key": "",
        "telegram_bot_token": "",
        "alert_max_per_day": "3",
        "alert_cooldown_hours": "4",
    }
    for k, v in defaults.items():
        if not db.get(Setting, k):
            db.add(Setting(key=k, value=v))
    db.commit()
    db.close()
    print(f"[DB] Initialized at {DB_PATH}")

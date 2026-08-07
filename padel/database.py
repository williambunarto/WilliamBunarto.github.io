"""
Padel Court Payment & Wallet Tracking System — data layer.

SQLAlchemy models mirror the schema in the spec, extended per the owner's
follow-up corrections (see README "Corrections" section): locations are a
first-class managed entity, rate cards belong to a location, packages are
optional per session, and hour slots carry a min/max headcount.
"""
import os
import math
from datetime import datetime, date as date_cls

from sqlalchemy import (
    create_engine, Column, Integer, Float, String, Boolean,
    DateTime, Date, Time, Text, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session as OrmSession

from security import hash_password

DB_PATH = os.environ.get("PADEL_DB", "/home/ubuntu/padel/data/padel.db")
if not os.path.exists(os.path.dirname(DB_PATH)):
    DB_PATH = os.path.join(os.path.dirname(__file__), "data", "padel.db")

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

ROLE_SUPER_ADMIN = "super_admin"
ROLE_ADMIN = "admin"

DAY_WEEKDAY = "weekday"
DAY_WEEKEND = "weekend"

STATUS_ACTIVE = "active"
STATUS_CANCELLED = "cancelled"

PAY_PENDING = "pending"
PAY_CONFIRMED = "confirmed"
PAY_CANCELLED = "cancelled"  # extension beyond spec's pending|confirmed, used when a
                             # session is fully cancelled so a payment never gets collected

MIN_PLAYERS_PER_HOUR = 4   # UI default headcount per hour slot
MAX_PLAYERS_PER_HOUR = 12  # hard cap enforced server-side


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # super_admin | admin
    created_at = Column(DateTime, default=datetime.utcnow)

    def set_password(self, raw):
        self.password_hash = hash_password(raw)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "username": self.username, "role": self.role}


class Location(Base):
    """A court/venue. Registered up front (like players) so sessions,
    packages, and rate cards all reference it instead of a free-text string.
    """
    __tablename__ = "locations"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    rate_cards = relationship("RateCard", backref="location", cascade="all, delete-orphan")

    def to_dict(self):
        return {"id": self.id, "name": self.name, "notes": self.notes}


class CourtPackage(Base):
    __tablename__ = "court_packages"
    id = Column(Integer, primary_key=True)
    purchase_date = Column(Date, nullable=False, default=date_cls.today)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    total_hours = Column(Integer, nullable=False, default=30)
    price_paid = Column(Float, nullable=False)
    hours_remaining = Column(Float, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    location_ref = relationship("Location")

    @property
    def cost_per_hour(self):
        if not self.total_hours:
            return 0
        return self.price_paid / self.total_hours

    def to_dict(self):
        return {
            "id": self.id,
            "purchase_date": self.purchase_date.isoformat() if self.purchase_date else None,
            "location_id": self.location_id,
            "location_name": self.location_ref.name if self.location_ref else None,
            "total_hours": self.total_hours,
            "price_paid": self.price_paid,
            "hours_remaining": self.hours_remaining,
            "is_active": self.is_active,
            "cost_per_hour": round(self.cost_per_hour, 2),
        }


class RateCard(Base):
    """Owned by a Location — "every court has its own rate cards" per the
    owner's correction. Still mutable, still super_admin-only to change;
    sessions snapshot the price so past sessions are unaffected by edits.
    """
    __tablename__ = "rate_cards"
    id = Column(Integer, primary_key=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    day_type = Column(String, nullable=False)  # weekday | weekend
    time_band = Column(String, nullable=False)  # e.g. "Peak" human label
    time_start = Column(String, nullable=False)  # "HH:MM", used for auto-matching
    time_end = Column(String, nullable=False)    # "HH:MM"
    sell_price_per_hour = Column(Float, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "location_id": self.location_id,
            "location_name": self.location.name if self.location else None,
            "day_type": self.day_type,
            "time_band": self.time_band,
            "time_start": self.time_start,
            "time_end": self.time_end,
            "sell_price_per_hour": self.sell_price_per_hour,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PlaySession(Base):
    """A booked play session. Table name kept as `sessions` per spec."""
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    start_time = Column(String, nullable=False)  # "HH:MM"
    end_time = Column(String, nullable=False)    # "HH:MM"
    total_hours = Column(Integer, nullable=False)
    rate_card_id = Column(Integer, ForeignKey("rate_cards.id"), nullable=True)
    sell_price_per_hour_snapshot = Column(Float, nullable=False)
    status = Column(String, nullable=False, default=STATUS_ACTIVE)  # active | cancelled
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    cancelled_at = Column(DateTime, nullable=True)

    location_ref = relationship("Location")
    hour_slots = relationship("SessionHourSlot", backref="session", cascade="all, delete-orphan",
                               order_by="SessionHourSlot.hour_index")
    equipment_charges = relationship("EquipmentCharge", backref="session", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "date": self.date.isoformat() if self.date else None,
            "location_id": self.location_id,
            "location_name": self.location_ref.name if self.location_ref else None,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_hours": self.total_hours,
            "rate_card_id": self.rate_card_id,
            "sell_price_per_hour_snapshot": self.sell_price_per_hour_snapshot,
            "status": self.status,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,
        }


class SessionHourSlot(Base):
    __tablename__ = "session_hour_slots"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    hour_index = Column(Integer, nullable=False)  # 1-based
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    # Nullable: packages are optional (owner's correction) — an hour can be
    # played with no court-hour package backing it, it just costs the owner
    # nothing extra to log (no package cost line for that hour).
    package_id = Column(Integer, ForeignKey("court_packages.id"), nullable=True)

    participants = relationship("SlotParticipant", backref="hour_slot", cascade="all, delete-orphan")
    package = relationship("CourtPackage")

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "hour_index": self.hour_index,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "package_id": self.package_id,
            "participants": [p.to_dict() for p in self.participants],
        }


class Player(Base):
    __tablename__ = "players"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    contact = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "contact": self.contact}


class SlotParticipant(Base):
    __tablename__ = "slot_participants"
    id = Column(Integer, primary_key=True)
    hour_slot_id = Column(Integer, ForeignKey("session_hour_slots.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    cost_share = Column(Float, nullable=False, default=0)  # rounded UP (ceil)
    status = Column(String, nullable=False, default=STATUS_ACTIVE)  # active | cancelled

    player = relationship("Player")

    def to_dict(self):
        return {
            "id": self.id,
            "hour_slot_id": self.hour_slot_id,
            "player_id": self.player_id,
            "player_name": self.player.name if self.player else None,
            "cost_share": self.cost_share,
            "status": self.status,
        }


class EquipmentCharge(Base):
    __tablename__ = "equipment_charges"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    item = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    absorbed_by = Column(String, nullable=False, default="owner")

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "item": self.item,
            "amount": self.amount,
            "absorbed_by": self.absorbed_by,
        }


class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    amount_due = Column(Float, nullable=False, default=0)
    amount_paid = Column(Float, nullable=False, default=0)
    status = Column(String, nullable=False, default=PAY_PENDING)  # pending | confirmed | cancelled
    confirmed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    proof_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    player = relationship("Player")

    __table_args__ = (UniqueConstraint("player_id", "session_id", name="uq_payment_player_session"),)

    def to_dict(self):
        return {
            "id": self.id,
            "player_id": self.player_id,
            "player_name": self.player.name if self.player else None,
            "session_id": self.session_id,
            "amount_due": self.amount_due,
            "amount_paid": self.amount_paid,
            "status": self.status,
            "confirmed_by": self.confirmed_by,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "proof_note": self.proof_note,
        }


def init_db():
    Base.metadata.create_all(engine)
    _seed(SessionLocal())


def _seed(db: OrmSession):
    try:
        if db.query(User).count() == 0:
            superadmin = User(name="Super Admin", username="superadmin", role=ROLE_SUPER_ADMIN)
            superadmin.set_password(os.environ.get("PADEL_SUPERADMIN_PASSWORD", "superadmin"))
            admin = User(name="Admin", username="admin", role=ROLE_ADMIN)
            admin.set_password(os.environ.get("PADEL_ADMIN_PASSWORD", "admin"))
            db.add_all([superadmin, admin])
            db.commit()
    finally:
        db.close()

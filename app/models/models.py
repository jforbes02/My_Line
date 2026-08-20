from app.models.db import Base
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum


class User(Base):
    __tablename__ = 'users'

    firebase_uid = Column(String, primary_key=True)
    name = Column(String, nullable=True)
    phone_number = Column(String, nullable=False, )
    #stripe_account_id = Column(String, nullable=True)
    #completed_handoffs = Column(Integer, default=0, nullable=False)

    listings = relationship('Listing', back_populates='seller', foreign_keys='Listing.seller_uid')


class Location(Base):
    __tablename__ = 'locations'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    state = Column(String, nullable=False)
    country = Column(String, nullable=False)
    address = Column(String, nullable=False)

    listings = relationship('Listing', back_populates='location')


class ListingStatus(enum.Enum):
    available = 'available'
    sold = 'sold'
    cancelled = 'cancelled'


class Listing(Base):
    __tablename__ = 'listings'

    id = Column(Integer, primary_key=True, index=True)
    seller_uid = Column(String, ForeignKey('users.firebase_uid'), nullable=False)
    buyer_uid = Column(String, ForeignKey('users.firebase_uid'), nullable=True)
    location_id = Column(Integer, ForeignKey('locations.id'), nullable=False)
    spot_in_queue = Column(Integer, nullable=False)

    price = Column(Float, nullable=False)
    status = Column(Enum(ListingStatus), default=ListingStatus.available, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    seller = relationship('User', back_populates='listings', foreign_keys=[seller_uid])
    buyer = relationship('User', foreign_keys=[buyer_uid])
    location = relationship('Location', back_populates='listings')
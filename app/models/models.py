from app.models.db import Base
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum


class User(Base):
    __tablename__ = 'users'

    firebase_uid = Column(String, primary_key=True)
    name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone_number = Column(String, nullable=False)

    stripe_account_id = Column(String, nullable=True)
    stripe_onboarded = Column(Boolean, default=False, nullable=False, server_default='false')

    completed_transactions = Column(Integer, default=0, nullable=False)

    listings = relationship('Listing', back_populates='seller', foreign_keys='Listing.seller_uid')


"""class Location(Base):
    __tablename__ = 'locations'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    state = Column(String, nullable=False)
    country = Column(String, nullable=False)
    address = Column(String, nullable=False)

    #listings = relationship('Listing', back_populates='location')
"""

class ListingStatus(enum.Enum):
    available = 'available'
    sold = 'sold'
    cancelled = 'cancelled'


class Listing(Base):
    __tablename__ = 'listings'

    id = Column(Integer, primary_key=True, index=True)
    seller_uid = Column(String, ForeignKey('users.firebase_uid'), nullable=False)
    #location_id = Column(Integer, ForeignKey('locations.id'), nullable=False)
    spot_in_queue = Column(Integer, nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)

    price = Column(Float, nullable=False)
    #status = Column(Enum(ListingStatus), default=ListingStatus.available, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    seller = relationship('User', back_populates='listings', foreign_keys=[seller_uid])
    #location = relationship('Location', back_populates='listings')

class TransactionStatus(enum.Enum):
    pending = 'pending'
    completed = 'completed'
    cancelled = 'cancelled'
    refunded = 'refunded'


class Transaction(Base):
    __tablename__ = 'transactions'

    id = Column(Integer, primary_key=True, index=True)
    listing_id = Column(Integer, ForeignKey('listings.id'), nullable=False)
    buyer_uid = Column(String, ForeignKey('users.firebase_uid'), nullable=False)
    seller_uid = Column(String, ForeignKey('users.firebase_uid'), nullable=False)
    price = Column(Float, nullable=False)
    status = Column(Enum(TransactionStatus), default=TransactionStatus.pending, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    stripe_payment_intent_id = Column(String, nullable=False)

    listing = relationship('Listing')
    buyer = relationship('User', foreign_keys='Transaction.buyer_uid')
    seller = relationship('User', foreign_keys='Transaction.seller_uid')

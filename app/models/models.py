from app.models.db import Base
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum


class User(Base):
    __tablename__ = 'users'

    #firebase auth
    firebase_uid = Column(String, primary_key=True)

    #optional name
    name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    #phone number
    phone_number = Column(String, nullable=False)

    #stripe account for sellers
    stripe_account_id = Column(String, nullable=True)
    stripe_onboarded = Column(Boolean, default=False, nullable=False, server_default='false')

    completed_transactions = Column(Integer, default=0, nullable=False)

    listings = relationship('Listing', back_populates='seller', foreign_keys='Listing.seller_uid')


class Listing(Base):
    __tablename__ = 'listings'

    id = Column(Integer, primary_key=True, index=True)
    seller_uid = Column(String, ForeignKey('users.firebase_uid'), nullable=False)
    spot_in_queue = Column(Integer, nullable=False)

    #location of where the listing is
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)

    #price of listing along with when made and if its sold
    price = Column(Float, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    sold = Column(Boolean, nullable=False, server_default='false')
    seller = relationship('User', back_populates='listings', foreign_keys=[seller_uid])

class TransactionStatus(enum.Enum):
    pending = 'pending'
    completed = 'completed'
    cancelled = 'cancelled'
    refunded = 'refunded'
    paid = 'paid'


class Transaction(Base):
    __tablename__ = 'transactions'

    #identification of users and listing
    id = Column(Integer, primary_key=True, index=True)
    listing_id = Column(Integer, ForeignKey('listings.id'), nullable=False)
    buyer_uid = Column(String, ForeignKey('users.firebase_uid'), nullable=False)
    seller_uid = Column(String, ForeignKey('users.firebase_uid'), nullable=False)

    #price of transaction
    price = Column(Float, nullable=False)

    #payment life cycle
    status = Column(Enum(TransactionStatus), default=TransactionStatus.pending, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    stripe_payment_intent_id = Column(String, nullable=False)
    qr_expires_at = Column(DateTime, nullable=True)

    listing = relationship('Listing')
    buyer = relationship('User', foreign_keys='Transaction.buyer_uid')
    seller = relationship('User', foreign_keys='Transaction.seller_uid')
from datetime import datetime

import phonenumbers
from pydantic import BaseModel, field_validator


def validate_phone(phone: str) -> str:
    try:
        parsed = phonenumbers.parse(phone, "US")
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError
    except Exception:
        raise ValueError("Invalid phone number")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


# --- Requests ---

class SignupRequest(BaseModel):
    email: str
    password: str
    phone: str

    @field_validator('phone')
    @classmethod
    def phone_must_be_valid(cls, v):
        return validate_phone(v)


class UpdateNameRequest(BaseModel):
    name: str

class ListingRequest(BaseModel):
    price: float
    lat: float
    lng: float
    spot_in_queue: int

class AccountCreate(BaseModel):
    business_type : str = 'company'
    country: str = 'US'

class TransactionRequest(BaseModel):
    listing_id: int

# --- Responses ---

class UserResponse(BaseModel):
    name: str | None
    phone_number: str

    model_config = {"from_attributes": True}


class ListingResponse(BaseModel):
    id: int
    price: float
    spot_in_queue: int
    lat: float
    lng: float

    model_config = {"from_attributes": True}

class OnboardSellerResponse(BaseModel):
    url: str

class TransactionResponse(BaseModel):
    listing_id: int
    buyer_uid: str
    seller_uid: str
    price: float
    created_at: datetime
    stripe_payment_intent_id: str
    client_secret: str | None = None
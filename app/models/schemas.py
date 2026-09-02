from datetime import datetime

import phonenumbers
from pydantic import BaseModel, field_validator, SecretStr


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
    email: str | None
    password: SecretStr | None
    phone: str

    @field_validator('phone')
    @classmethod
    def phone_must_be_valid(cls, v):
        return validate_phone(v)


class RegisterRequest(BaseModel):
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
    business_type: str = 'individual'
    country: str = 'US'


class TransactionRequest(BaseModel):
    listing_id: int


class UpdateEmailRequest(BaseModel):
    email: str

# --- Responses ---

class UserResponse(BaseModel):
    name: str | None
    phone_number: str
    email: str | None

    model_config = {"from_attributes": True}


class ListingResponse(BaseModel):
    id: int
    price: float
    spot_in_queue: int
    lat: float
    lng: float
    sold: bool = False
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


class AbandonTransactionResponse(BaseModel):
    listing_id: int
    seller_uid: str
    buyer_uid: str
    created_at: datetime
    stripe_payment_intent_id: str


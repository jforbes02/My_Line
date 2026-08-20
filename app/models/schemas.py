import phonenumbers
from pydantic import BaseModel, field_validator


def validate_phone(phone: str) -> str:
    try:
        parsed = phonenumbers.parse(phone)
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
    location_id: int
    spot_in_queue: int

# --- Responses ---

class UserResponse(BaseModel):
    name: str | None
    phone_number: str

    model_config = {"from_attributes": True}


class ListingResponse(BaseModel):
    id: int
    price: float
    status: str
    location_id: int

    model_config = {"from_attributes": True}
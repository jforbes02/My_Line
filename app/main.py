from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
from app.models.db import mySession, engine, Base
from app.models.models import User, Listing
from app.models.auth import signup as firebase_signup, CurrentUser
from app.models.schemas import SignupRequest, UpdateNameRequest, UserResponse, ListingRequest, ListingResponse
from firebase_admin import auth as firebase_auth
from firebase_admin import exceptions as firebase_exc
from app.data.payments import router as payment_router
from app.data.users import router as users_router
load_dotenv()

Base.metadata.create_all(bind=engine)

app = FastAPI()
app.include_router(payment_router)
app.include_router(users_router)

@app.get("/")
async def root():
    return {"message": "Kirk..."}



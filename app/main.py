from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
from app.models.db import mySession, engine, Base
from app.models.models import User, Listing
from app.models.auth import signup as firebase_signup, CurrentUser
from app.models.schemas import SignupRequest, UpdateNameRequest, UserResponse, ListingRequest, ListingResponse
from firebase_admin import auth as firebase_auth
from firebase_admin import exceptions as firebase_exc
from app.data.payments import router as payment_router
load_dotenv()

Base.metadata.create_all(bind=engine)

app = FastAPI()
app.include_router(payment_router)


@app.get("/")
async def root():
    return {"message": "Kirk..."}


@app.post("/signup", response_model=UserResponse)
async def signup(db: mySession, body: SignupRequest):
    x = firebase_signup(body.email, body.password)

    db_user = User(firebase_uid=x.uid, phone_number=body.phone)
    try:
        db.add(db_user)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return db_user


@app.post("/login", response_model=UserResponse)
async def login(db: mySession, token: str):
    decoded = firebase_auth.verify_id_token(token)
    uid = decoded["uid"]
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.delete("/delete_user")
async def delete_user(db: mySession, user: CurrentUser):
    try:
        firebase_auth.delete_user(user.firebase_uid)
        db.delete(user)
        db.commit()
    except firebase_exc.NotFoundError:
        raise HTTPException(status_code=404, detail="User not found in Firebase")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return {'user': 'DELETED'}


@app.post("/update_name", response_model=UserResponse)
async def update_name(db: mySession, body: UpdateNameRequest, user: CurrentUser):
    try:
        user.name = body.name
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return user

@app.post('/create_listing', response_model=ListingResponse)
async def create_listing(db: mySession, user: CurrentUser, listing: ListingRequest):
    listing = Listing(
        seller_uid=user.firebase_uid,
        price=listing.price,
        lat=listing.lat,
        lng=listing.lng,
        spot_in_queue=listing.spot_in_queue,
    )

    try:
        db.add(listing)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return listing

@app.post('/start_transaction')
async def create_location(db: mySession, user: CurrentUser):
    pass
from fastapi import APIRouter, HTTPException
from app.models.schemas import UserResponse, UpdateNameRequest, SignupRequest
from app.models.auth import signup as firebase_signup, CurrentUser
from firebase_admin import auth as firebase_auth
from firebase_admin import exceptions as firebase_exc
from app.models.db import mySession
from app.models.models import User

router = APIRouter()

@router.post("/signup", response_model=UserResponse)
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


@router.post("/login", response_model=UserResponse)
async def login(db: mySession, token: str):
    decoded = firebase_auth.verify_id_token(token)
    uid = decoded["uid"]
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.delete("/delete_user")
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


@router.post("/update_name", response_model=UserResponse)
async def update_name(db: mySession, body: UpdateNameRequest, user: CurrentUser):
    try:
        user.name = body.name
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return user
from fastapi import APIRouter, HTTPException
from app.models.schemas import UserResponse, UpdateNameRequest, SignupRequest, RegisterRequest, UpdateEmailRequest
from app.models.auth import signup as firebase_signup, CurrentUser
from firebase_admin import auth as firebase_auth
from firebase_admin import exceptions as firebase_exc
from app.models.db import mySession
from app.models.models import User

router = APIRouter()


@router.post("/signup", response_model=UserResponse)
def signup(db: mySession, body: SignupRequest):
    """Email/password flow — backend creates the Firebase account and DB record together."""
    if not body.email or not body.password:
        raise HTTPException(status_code=400, detail="Email and password required for this flow")

    x = firebase_signup(body.email, body.password)

    db_user = User(firebase_uid=x.uid, email=body.email, phone_number=body.phone)
    try:
        db.add(db_user)
        db.commit()
    except Exception as e:
        db.rollback()
        firebase_auth.delete_user(x.uid)
        raise HTTPException(status_code=500, detail=str(e))

    return db_user


@router.post("/register", response_model=UserResponse)
def register(db: mySession, user: CurrentUser, body: RegisterRequest):
    """Phone auth flow — Firebase account already exists on client, just create the DB record."""
    existing = db.query(User).filter(User.firebase_uid == user.firebase_uid).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already registered")

    db_user = User(firebase_uid=user.firebase_uid, phone_number=body.phone)
    try:
        db.add(db_user)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return db_user


@router.post("/login", response_model=UserResponse)
def login(db: mySession, token: str):
    decoded = firebase_auth.verify_id_token(token)
    uid = decoded["uid"]
    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.delete("/delete_user")
def delete_user(db: mySession, user: CurrentUser):
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
def update_name(db: mySession, body: UpdateNameRequest, user: CurrentUser):
    try:
        user.name = body.name
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return user

@router.post("/update_email", response_model=UserResponse)
def update_email(db: mySession, user: CurrentUser, body: UpdateEmailRequest):
    try:
        firebase_auth.update_user(user.firebase_uid, email=body.email)
        user.email = body.email
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return user
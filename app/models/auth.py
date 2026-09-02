from typing import Annotated

import firebase_admin
from fastapi import HTTPException, Depends, Request
from firebase_admin import credentials, auth as firebase_auth
import os
from dotenv import load_dotenv

from app.models.db import mySession
from app.models.models import User

load_dotenv()

_cred_path = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
if not _cred_path:
    raise ValueError("FIREBASE_SERVICE_ACCOUNT env var not set (path to service account JSON)")

cred = credentials.Certificate(_cred_path)
firebase_admin.initialize_app(cred)


def signup(email: str, password: str):
    """Firebase signup function"""
    user = firebase_auth.create_user(email=email, password=password)
    return user

def get_current_user(request: Request, db: mySession, token: str) -> type[User]:
    """Uses firebase auth to get and verify the current user
    :param request: used to store the auth users ID so waygate reads it when rate-limiting
    :param db: session
    :param token: firebase token
    :return: User
    """
    decoded = firebase_auth.verify_id_token(token)
    uid = decoded["uid"]
    user = db.query(User).filter(User.firebase_uid == uid).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    request.state.user_id = uid
    return user

CurrentUser = Annotated[User, Depends(get_current_user)]

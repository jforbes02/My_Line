from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm.session import sessionmaker, Session
load_dotenv()
DATABASE_URL = os.environ.get('DATABASE')
if not DATABASE_URL:
    raise ValueError('DATABASE_URL environment variable not set')
engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

#reusable session made by get_db
mySession = Annotated[Session, Depends(get_db)]
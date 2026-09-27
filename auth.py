import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from passlib.context import CryptContext
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from database import get_db, User
from config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

COOKIE_NAME = "admin_session"
TOKEN_EXPIRE_HOURS = 24 * 7


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    user = db.query(User).filter_by(username=username).first()
    if not user or not verify_password(password, user.password_hash):
        return None
    if user.is_active is False:
        return None
    return user


def password_version(user: User) -> str:
    """ลายนิ้วมือสั้น ๆ ของรหัสผ่านปัจจุบัน — เปลี่ยนรหัสเมื่อไหร่ ค่านี้เปลี่ยน session เก่าทุกเครื่องหลุด

    ได้จาก HMAC(SECRET_KEY, hash รหัสผ่าน) จึงไม่เปิดเผย hash จริงใน cookie
    """
    return hmac.new(settings.SECRET_KEY.encode(), (user.password_hash or "").encode(),
                    hashlib.sha256).hexdigest()[:16]


def create_session_token(user: User) -> str:
    expire = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {"sub": str(user.id), "pv": password_version(user), "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        return None
    user = db.query(User).filter_by(id=user_id).first()
    # บัญชีที่ถูกปิด → cookie เดิมใช้ไม่ได้ทันที ไม่ต้องรอหมดอายุ 7 วัน
    if not user or user.is_active is False:
        return None
    # รหัสผ่านถูกเปลี่ยนหลังออก cookie นี้ (หรือ cookie รุ่นเก่าที่ไม่มี pv) → ต้องล็อกอินใหม่
    if not hmac.compare_digest(str(payload.get("pv") or ""), password_version(user)):
        return None
    return user


def require_admin(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(
            status_code=303,
            detail="Login required",
            headers={"Location": "/admin/login"},
        )
    return user


def require_owner(request: Request, db: Session = Depends(get_db)) -> User:
    """หน้าที่เฉพาะเจ้าของ — ทีมงานที่ล็อกอินแล้วถูกส่งกลับ Dashboard พร้อมแจ้งเหตุผล"""
    user = require_admin(request, db)
    if not user.is_owner:
        raise HTTPException(status_code=303, detail="Owner only",
                            headers={"Location": "/admin?denied=owner"})
    return user

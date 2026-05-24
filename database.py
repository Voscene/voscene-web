from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, Float
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
from config import get_settings

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Content(Base):
    """เนื้อหาหน้าเว็บที่แก้ไขได้จาก Admin Panel"""
    __tablename__ = "content"
    id = Column(Integer, primary_key=True)
    key = Column(String(128), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=False, default="")
    label = Column(String(255), nullable=False, default="")
    section = Column(String(64), nullable=False, default="general")
    field_type = Column(String(32), nullable=False, default="text")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Package(Base):
    """ราคา/Package สำหรับเสนอลูกค้า"""
    __tablename__ = "packages"
    id = Column(Integer, primary_key=True)
    code = Column(String(64), unique=True, nullable=False)
    name = Column(String(128), nullable=False)
    price = Column(String(64), nullable=False)
    price_unit = Column(String(32), default="")
    description = Column(Text, default="")
    features = Column(Text, default="")
    category = Column(String(32), default="purchase")
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    is_featured = Column(Boolean, default=False)


class Lead(Base):
    """รายการลูกค้าที่กรอกฟอร์มความต้องการ"""
    __tablename__ = "leads"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    company = Column(String(128), default="")
    phone = Column(String(64), default="")
    email = Column(String(128), default="")
    room_size = Column(String(64), default="")
    budget = Column(String(64), default="")
    requirement = Column(Text, nullable=False)
    ai_analysis = Column(Text, default="")
    ai_in_scope = Column(Boolean, default=False)
    ai_confidence = Column(Float, default=0.0)
    ai_recommended_package = Column(String(64), default="")
    status = Column(String(32), default="new")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class BlogPost(Base):
    __tablename__ = "blog_posts"
    id = Column(Integer, primary_key=True)
    slug = Column(String(128), unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    excerpt = Column(Text, default="")
    content = Column(Text, default="")
    cover_image = Column(String(255), default="")
    tags = Column(String(255), default="")
    is_published = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)

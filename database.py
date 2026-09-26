from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Date, Boolean, Float
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
    # owner = ทำได้ทุกอย่าง + จัดการบัญชี · staff = Lead / การตลาด / บทความ
    # ค่าเริ่มต้น staff (ปลอดภัยกว่า) — migration 002 ตั้งบัญชีที่มีอยู่เดิมเป็น owner
    display_name = Column(String(100), default="")
    role = Column(String(16), default="staff")
    is_active = Column(Boolean, default=True)

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"

    @property
    def label(self) -> str:
        return self.display_name or self.username


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

    # ===== การตลาด (เพิ่ม 2026-09 · migrations.py เติมคอลัมน์ให้ DB เดิม) =====
    # `status` ข้างบนคงไว้ตามเดิมเพื่อไม่ทำลายข้อมูล ส่วนงานขายใช้ 2 ช่องที่แยกกันชัด:
    # sales_stage = ขั้นการขาย · qualification = ผลคัดกรอง (คนตัดสิน ไม่ใช่ AI)
    sales_stage = Column(String(16), default="new")
    qualification = Column(String(16), default="pending")
    spam_reason = Column(String(64), default="")
    request_type = Column(String(16), default="")       # consult / demo / quote
    service_interest = Column(String(32), default="")
    quote_value = Column(Float, nullable=True)
    won_value = Column(Float, nullable=True)
    next_follow_up = Column(Date, nullable=True)
    # แหล่งที่มา — ค่าว่างทั้งหมด = "ไม่ทราบแหล่งที่มา" (ไม่เดา)
    channel = Column(String(32), default="")
    utm_source = Column(String(128), default="")
    utm_medium = Column(String(128), default="")
    utm_campaign = Column(String(128), default="")
    utm_content = Column(String(128), default="")
    utm_term = Column(String(128), default="")
    landing_page = Column(String(512), default="")
    referrer = Column(String(512), default="")
    campaign_id = Column(Integer, nullable=True)
    content_item_id = Column(Integer, nullable=True)
    group_post_id = Column(Integer, nullable=True)
    # รายการซ้ำ — ชี้ไป Lead แรกของคนเดียวกัน ไม่ลบ ไม่รวม
    phone_norm = Column(String(32), default="")
    email_norm = Column(String(128), default="")
    duplicate_of = Column(Integer, nullable=True)
    not_duplicate = Column(Boolean, default=False)
    updated_at = Column(DateTime, nullable=True)
    assigned_to = Column(Integer, nullable=True)  # users.id ของผู้รับผิดชอบ


class LeadNote(Base):
    """บันทึกติดตาม Lead ทีละรายการ (เดิมมีแค่ช่อง notes ช่องเดียว)"""
    __tablename__ = "lead_notes"
    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, nullable=False, index=True)
    text = Column(Text, nullable=False, default="")
    next_follow_up = Column(Date, nullable=True)
    created_by = Column(String(64), default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    """ประวัติการแก้ไขที่สำคัญ — สถานะขาย · ค่าโฆษณา · งบแคมเปญ · การเผยแพร่"""
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    username = Column(String(64), default="")
    action = Column(String(64), nullable=False)
    entity = Column(String(32), nullable=False)
    entity_id = Column(Integer, nullable=True)
    detail = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class Campaign(Base):
    __tablename__ = "mk_campaigns"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    code = Column(String(80), unique=True, nullable=False)  # = utm_campaign
    service = Column(String(32), default="")
    audience = Column(Text, default="")
    channels = Column(String(255), default="")  # คีย์ช่องทางคั่นด้วย ,
    budget = Column(Float, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    goal = Column(String(16), default="")
    landing_url = Column(String(512), default="")
    status = Column(String(16), default="draft")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TrackingLink(Base):
    __tablename__ = "mk_tracking_links"
    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, nullable=False, index=True)
    channel = Column(String(32), nullable=False)
    utm_source = Column(String(128), nullable=False)
    utm_medium = Column(String(128), nullable=False)
    utm_campaign = Column(String(128), nullable=False)
    utm_content = Column(String(128), default="")
    utm_term = Column(String(128), default="")
    destination = Column(String(512), nullable=False)
    url = Column(String(1024), unique=True, nullable=False)
    label = Column(String(200), default="")
    content_item_id = Column(Integer, nullable=True)
    group_post_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ContentItem(Base):
    __tablename__ = "mk_content"
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    body = Column(Text, default="")
    channel = Column(String(32), default="")
    campaign_id = Column(Integer, nullable=True)
    media = Column(Text, default="[]")  # JSON: [{stored, name, size}]
    destination = Column(String(512), default="")
    tracking_link_id = Column(Integer, nullable=True)
    planned_at = Column(DateTime, nullable=True)  # เวลาไทย (naive)
    owner = Column(String(100), default="")
    status = Column(String(16), default="draft")
    published_url = Column(String(512), default="")
    published_at = Column(DateTime, nullable=True)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FbGroup(Base):
    __tablename__ = "mk_fb_groups"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    url = Column(String(512), default="")
    audience = Column(Text, default="")
    relevance = Column(String(16), default="")
    rules = Column(Text, default="")
    allowed_frequency = Column(String(200), default="")
    min_days_between = Column(Integer, nullable=True)
    notes = Column(Text, default="")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class FbGroupPost(Base):
    __tablename__ = "mk_fb_group_posts"
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, nullable=False, index=True)
    content_item_id = Column(Integer, nullable=True)
    campaign_id = Column(Integer, nullable=True)
    tracking_link_id = Column(Integer, nullable=True)
    message = Column(Text, default="")
    status = Column(String(24), default="queued")
    planned_date = Column(Date, nullable=True)
    posted_at = Column(Date, nullable=True)
    post_url = Column(String(512), default="")
    next_post_date = Column(Date, nullable=True)
    note = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class AdSpend(Base):
    """ค่าโฆษณารายวัน — กรอกเอง / นำเข้า CSV (ระยะ 2: ดึงจากแพลตฟอร์ม)"""
    __tablename__ = "mk_ad_spend"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, index=True)
    channel = Column(String(32), nullable=False)
    campaign_id = Column(Integer, nullable=True)
    campaign_label = Column(String(200), default="")
    spend = Column(Float, nullable=False)
    impressions = Column(Integer, nullable=True)
    clicks = Column(Integer, nullable=True)
    currency = Column(String(8), default="THB")
    source = Column(String(16), default="manual")  # manual / csv / api
    batch_id = Column(Integer, nullable=True)
    dedupe_key = Column(String(300), unique=True, nullable=False)
    note = Column(Text, default="")
    created_by = Column(String(64), default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class ImportBatch(Base):
    __tablename__ = "mk_import_batches"
    id = Column(Integer, primary_key=True)
    filename = Column(String(255), default="")
    file_hash = Column(String(64), nullable=False, index=True)
    status = Column(String(16), default="preview")  # preview / imported / cancelled
    rows_json = Column(Text, default="[]")
    total_rows = Column(Integer, default=0)
    imported_rows = Column(Integer, default=0)
    skipped_rows = Column(Integer, default=0)
    created_by = Column(String(64), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    imported_at = Column(DateTime, nullable=True)


class WebEvent(Base):
    """คลิก LINE / โทร จากหน้าเว็บ — นับครั้งเดียวต่อ session ต่อประเภท

    ไม่ใช่ Lead และไม่ใช่ผู้เข้าเว็บ · ส่งฟอร์มสำเร็จนับจากตาราง leads โดยตรง
    """
    __tablename__ = "mk_web_events"
    id = Column(Integer, primary_key=True)
    event = Column(String(32), nullable=False)
    dedupe_key = Column(String(120), unique=True, nullable=False)
    path = Column(String(512), default="")
    channel = Column(String(32), default="")
    utm_source = Column(String(128), default="")
    utm_medium = Column(String(128), default="")
    utm_campaign = Column(String(128), default="")
    utm_content = Column(String(128), default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


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
    # migrations สำรองไฟล์ DB ก่อน แล้วค่อยสร้างตารางใหม่ + เติมคอลัมน์ให้ตารางเดิม
    from migrations import run_migrations
    run_migrations(engine, Base)

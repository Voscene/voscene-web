"""AV Control System — Marketing Website + Admin CMS"""
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional
from markupsafe import Markup, escape

# ===== File Uploads =====
# Use persistent disk on Render, local folder for dev
UPLOAD_DIR = Path("/var/data/uploads") if os.path.exists("/var/data") else Path("./uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_UPLOAD_EXT = {".pdf", ".doc", ".docx", ".ppt", ".pptx"}
MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20 MB

from config import get_settings
from database import get_db, Content, Package, Lead, BlogPost, User, LeadNote, AuditLog, Campaign, ContentItem, FbGroupPost
import marketing
import marketing_core as mc
from auth import (
    authenticate_user, create_session_token, get_current_user, require_admin,
    pwd_context, COOKIE_NAME, TOKEN_EXPIRE_HOURS,
)
from ai_service import analyze_requirement, consult_disabled, _unavailable as ai_unavailable
from seed import run_seed
from security import (
    SecurityHeadersMiddleware, client_ip, rate_limited, honeypot_tripped,
    contact_format_error, login_lock_remaining, record_login_failure,
    clear_login_failures, ANALYZE_RULES, LEAD_RULES, LOGIN_RULES,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_seed()
    yield


settings = get_settings()
app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# App version shown in the footer. Override without a code change by setting
# the APP_VERSION env var (e.g. in Render); defaults to the baseline below.
APP_VERSION = os.getenv("APP_VERSION", "2.0.0")
templates.env.globals["APP_VERSION"] = APP_VERSION


# Contact numbers are free text from the CMS (may hold a name and several lines),
# so linkify the number runs instead of wrapping the whole field.
_PHONE_RE = re.compile(r"0\d[\d\s\-]{7,12}\d")


def linkify_phone(value) -> Markup:
    """ทำเบอร์โทรในข้อความให้กดโทรได้บนมือถือ (tel:) โดยคงข้อความรอบ ๆ ไว้"""
    if not value:
        return Markup("")
    text, out, last = str(value), [], 0
    for m in _PHONE_RE.finditer(text):
        out.append(escape(text[last:m.start()]))
        raw = m.group(0)
        digits = re.sub(r"\D", "", raw)
        out.append(Markup('<a href="tel:{}" class="hover:text-electric">{}</a>').format(digits, raw))
        last = m.end()
    out.append(escape(text[last:]))
    return Markup("").join(out)


templates.env.filters["linkify_phone"] = linkify_phone


def _money(value) -> str:
    """ตัวเลขเงินบาท · None = "—" (ยังไม่มีข้อมูล ต่างจาก 0)"""
    if value is None:
        return "—"
    return f"฿{value:,.0f}" if abs(value - round(value)) < 0.005 else f"฿{value:,.2f}"


def _bkk(dt, fmt: str = "%d/%m/%y %H:%M") -> str:
    """created_at ในฐานข้อมูลเป็น UTC → แสดงเป็นเวลาไทย"""
    return mc.utc_to_bkk(dt).strftime(fmt) if dt else "—"


templates.env.filters["money"] = _money
templates.env.filters["bkk"] = _bkk

# เมนูการตลาด (/admin/marketing/*) + endpoint คลิก LINE/โทร (/api/event)
marketing.bind(templates, UPLOAD_DIR)
app.include_router(marketing.router)
app.include_router(marketing.public_router)


# ===== โค้ดติดตามโฆษณา =====
# เก็บในตาราง Content เหมือนเนื้อหาอื่น แอดมินจึงแก้เองได้จากหลังบ้าน
# โดยไม่ต้องแก้ env ใน Render และไม่ต้อง deploy ใหม่
TRACKING_KEYS = ("gtm_id", "ga4_id", "meta_pixel_id")
TRACKING_LABELS = {
    "gtm_id": "Google Tag Manager ID",
    "ga4_id": "Google Analytics 4 ID",
    "meta_pixel_id": "Meta (Facebook) Pixel ID",
}
_TRACKING_PATTERNS = {
    "gtm_id": re.compile(r"GTM-[A-Z0-9]{4,12}", re.I),
    "ga4_id": re.compile(r"G-[A-Z0-9]{6,12}", re.I),
    "meta_pixel_id": re.compile(r"\d{10,20}"),
}


def clean_tracking_id(key: str, raw: str) -> tuple:
    """ดึงเฉพาะ ID ออกจากสิ่งที่แอดมินวางมา — คืน (id, รูปแบบถูกไหม)

    รับได้ทั้ง ID เปล่า ๆ และสคริปต์เต็ม ๆ ที่ก๊อปมาจากหน้า Google/Meta
    เพราะคนส่วนใหญ่กดคัดลอกทั้งก้อนมามากกว่าจะไล่หาเฉพาะ ID · หาไม่เจอคืน ("", False)
    เพื่อให้หน้าเว็บไม่มีทางฝังค่ามั่ว ๆ ลงใน <script> ได้เลย
    """
    raw = (raw or "").strip()
    if not raw:
        return "", True  # ล้างค่า = ตั้งใจปิด ไม่ใช่กรอกผิด
    found = _TRACKING_PATTERNS[key].search(raw)
    if not found:
        return "", False
    value = found.group(0)
    return (value if key == "meta_pixel_id" else value.upper()), True


def load_content(db: Session) -> dict:
    """โหลดเนื้อหาทั้งหมดเป็น dict { key: value }"""
    rows = db.query(Content).all()
    return {row.key: row.value for row in rows}


def get_packages(db: Session, category: Optional[str] = None) -> list:
    q = db.query(Package).filter_by(is_active=True)
    if category:
        q = q.filter_by(category=category)
    return q.order_by(Package.sort_order).all()


# ============ PUBLIC ROUTES ============

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    content = load_content(db)
    purchase = get_packages(db, "purchase")
    rental = get_packages(db, "rental")
    posts = db.query(BlogPost).filter_by(is_published=True).order_by(BlogPost.created_at.desc()).limit(3).all()
    return templates.TemplateResponse("public/index.html", {
        "request": request,
        "c": content,
        "purchase_packages": purchase,
        "rental_packages": rental,
        "posts": posts,
        "settings": settings,
    })


@app.get("/why", response_class=HTMLResponse)
async def why_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("public/why.html", {
        "request": request,
        "c": load_content(db),
        "settings": settings,
    })


@app.get("/features", response_class=HTMLResponse)
async def features_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("public/features.html", {
        "request": request,
        "c": load_content(db),
        "settings": settings,
    })


@app.get("/pricing", response_class=HTMLResponse)
async def pricing_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("public/pricing.html", {
        "request": request,
        "c": load_content(db),
        "purchase_packages": get_packages(db, "purchase"),
        "addon_packages": get_packages(db, "addon"),
        "rental_packages": get_packages(db, "rental"),  # legacy, may be empty
        "settings": settings,
    })


@app.get("/blog", response_class=HTMLResponse)
async def blog_list(request: Request, db: Session = Depends(get_db)):
    posts = db.query(BlogPost).filter_by(is_published=True).order_by(BlogPost.created_at.desc()).all()
    return templates.TemplateResponse("public/blog_list.html", {
        "request": request,
        "c": load_content(db),
        "posts": posts,
        "settings": settings,
    })


@app.get("/blog/{slug}", response_class=HTMLResponse)
async def blog_detail(slug: str, request: Request, db: Session = Depends(get_db)):
    post = db.query(BlogPost).filter_by(slug=slug, is_published=True).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return templates.TemplateResponse("public/blog_detail.html", {
        "request": request,
        "c": load_content(db),
        "post": post,
        "settings": settings,
    })


@app.get("/contact", response_class=HTMLResponse)
async def contact_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("public/contact.html", {
        "request": request,
        "c": load_content(db),
        "settings": settings,
    })


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    base = (settings.APP_URL or "").rstrip("/")
    lines = ["User-agent: *", "Allow: /", "Disallow: /admin", ""]
    if base:
        lines.append(f"Sitemap: {base}/sitemap.xml")
    return "\n".join(lines) + "\n"


@app.get("/sitemap.xml")
async def sitemap_xml(db: Session = Depends(get_db)):
    base = (settings.APP_URL or "").rstrip("/")
    urls = [(f"{base}/", "1.0"), (f"{base}/why", "0.8"), (f"{base}/features", "0.8"),
            (f"{base}/pricing", "0.8"), (f"{base}/blog", "0.6"), (f"{base}/contact", "0.6")]
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, pri in urls:
        parts.append(f"  <url><loc>{loc}</loc><priority>{pri}</priority></url>")
    for post in db.query(BlogPost).filter_by(is_published=True).all():
        lastmod = (post.updated_at or post.created_at)
        mod = f"<lastmod>{lastmod.date().isoformat()}</lastmod>" if lastmod else ""
        parts.append(f"  <url><loc>{base}/blog/{post.slug}</loc>{mod}<priority>0.5</priority></url>")
    parts.append("</urlset>")
    return Response("\n".join(parts), media_type="application/xml")


@app.post("/api/analyze", response_class=JSONResponse)
async def analyze_only(
    request: Request,
    requirement: str = Form(...),
    room_size: str = Form(""),
    budget: str = Form(""),
    fax_number: str = Form(""),  # honeypot — คนจริงมองไม่เห็นช่องนี้
    db: Session = Depends(get_db),
):
    """วิเคราะห์อย่างเดียว ยังไม่บันทึก Lead — บันทึกเป็น anonymous lead เพื่อเก็บสถิติ"""
    if not requirement.strip():
        return JSONResponse({"ok": False, "error": "กรุณากรอกความต้องการ"}, status_code=400)

    ip = client_ip(request)
    if rate_limited("analyze", ip, ANALYZE_RULES):
        return JSONResponse({
            "ok": False,
            "error": "คุณส่งคำขอถี่เกินไป กรุณารอสักครู่แล้วลองอีกครั้ง "
                     "หรือติดต่อทีมงานโดยตรงจากเบอร์โทรที่หน้าติดต่อเรา",
        }, status_code=429)

    # บอทกรอกช่องล่อ → ไม่เรียก AI (ไม่เผาโควตา) แต่ยังเก็บลง DB เป็นสถานะ spam
    # เผื่อเป็นคนจริงที่ระบบเดาผิด ข้อมูลจะได้ไม่หายไปเฉย ๆ แอดมินยังตามเจอ
    if honeypot_tripped(fax_number):
        analysis, lead_status = ai_unavailable("honeypot", detail=f"ip={ip}"), "spam"
    elif not settings.AI_CONSULT_ENABLED:
        # ที่ปรึกษา AI ปิดอยู่ — หน้าเว็บไม่เรียก endpoint นี้แล้ว แต่กันหน้าเก่าที่ค้าง
        # ในแคชผู้ใช้ยิงเข้ามา ยังต้องเก็บ lead ไว้ ไม่ทิ้งข้อมูลลูกค้า
        analysis, lead_status = consult_disabled(), "anonymous"
    else:
        analysis = await analyze_requirement(
            requirement=requirement, room_size=room_size, budget=budget, company="",
        )
        lead_status = "anonymous"

    # บันทึก anonymous lead (ยังไม่มีข้อมูลติดต่อ) เพื่อให้ admin เห็น
    lead = Lead(
        name="(ยังไม่ระบุชื่อ)",
        company="",
        phone="",
        email="",
        room_size=room_size.strip(),
        budget=budget.strip(),
        requirement=requirement.strip(),
        ai_analysis=analysis.get("raw", ""),
        ai_in_scope=bool(analysis.get("in_scope", False)),
        ai_confidence=float(analysis.get("confidence", 0.0)),
        ai_recommended_package=str(analysis.get("recommended_package", "")),
        status=lead_status,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)

    return {
        "ok": True,
        "lead_id": lead.id,
        "ai_ok": analysis.get("ai_ok", True),
        "in_scope": analysis.get("in_scope", False),
        "summary": analysis.get("summary", ""),
        "recommended_package": analysis.get("recommended_package", ""),
        "fit_reason": analysis.get("fit_reason", ""),
        "next_action": analysis.get("next_action", ""),
    }


@app.post("/api/lead", response_class=JSONResponse)
async def submit_lead(
    request: Request,
    name: str = Form(...),
    company: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    room_size: str = Form(""),
    budget: str = Form(""),
    requirement: str = Form(...),
    lead_id: str = Form(""),
    fax_number: str = Form(""),  # honeypot — คนจริงมองไม่เห็นช่องนี้
    db: Session = Depends(get_db),
):
    """บันทึก/อัปเดต Lead เมื่อมีข้อมูลติดต่อแล้ว — รองรับทั้ง flow ใหม่ (อัปเดต anonymous lead) และ flow เดิม (สร้างใหม่)"""
    if not name.strip() or not requirement.strip():
        return JSONResponse({"ok": False, "error": "กรุณากรอกชื่อและความต้องการ"}, status_code=400)

    ip = client_ip(request)
    if rate_limited("lead", ip, LEAD_RULES):
        return JSONResponse({
            "ok": False,
            "error": "คุณส่งข้อมูลถี่เกินไป กรุณารอสักครู่แล้วลองอีกครั้ง "
                     "หรือติดต่อทีมงานโดยตรงจากเบอร์โทรที่หน้าติดต่อเรา",
        }, status_code=429)

    format_error = contact_format_error(phone, email)
    if format_error:
        return JSONResponse({"ok": False, "error": format_error}, status_code=400)

    is_spam = honeypot_tripped(fax_number)
    # ช่องแหล่งที่มา/ประเภทคำขอ ที่สคริปต์หน้าเว็บแนบมา (vs-track.js) — ไม่มีก็ไม่เป็นไร
    form = await request.form()

    # ถ้ามี lead_id แปลว่า analyze มาแล้ว ให้ update lead เดิม
    lead = None
    if lead_id:
        try:
            lead = db.query(Lead).filter_by(id=int(lead_id)).first()
        except (TypeError, ValueError):
            lead = None

    if lead and lead.status == "anonymous":
        lead.name = name.strip()
        lead.company = company.strip()
        lead.phone = phone.strip()
        lead.email = email.strip()
        if is_spam:
            lead.status = "spam"
        elif not settings.AI_CONSULT_ENABLED:
            lead.status = "new"
        else:
            lead.status = "new_in_scope" if lead.ai_in_scope else "new_out_scope"
        marketing.apply_attribution(db, lead, form)
        marketing.screen_lead(db, lead, form, honeypot=is_spam)
        db.commit()
        return {
            "ok": True,
            "in_scope": lead.ai_in_scope,
            "summary": "บันทึกข้อมูลของคุณเรียบร้อย ทีมขายจะติดต่อกลับเร็วๆ นี้",
            "recommended_package": lead.ai_recommended_package,
            "fit_reason": "",
            "next_action": "รอทีมขายติดต่อกลับ",
        }

    # Flow เดิม: ไม่มี lead_id → วิเคราะห์ + สร้าง lead ใหม่
    if is_spam:
        analysis, lead_status = ai_unavailable("honeypot", detail=f"ip={ip}"), "spam"
    elif not settings.AI_CONSULT_ENABLED:
        # ปิดที่ปรึกษา AI ไว้ → ไม่เรียก Groq เลย เก็บเป็น lead ธรรมดารอทีมงานประเมิน
        # ใช้สถานะ "new" ไม่ใช่ new_out_scope เพราะยังไม่มีใครตัดสินขอบเขตให้
        analysis, lead_status = consult_disabled(), "new"
    else:
        analysis = await analyze_requirement(
            requirement=requirement, room_size=room_size, budget=budget, company=company,
        )
        lead_status = "new_in_scope" if analysis.get("in_scope") else "new_out_scope"

    lead = Lead(
        name=name.strip(),
        company=company.strip(),
        phone=phone.strip(),
        email=email.strip(),
        room_size=room_size.strip(),
        budget=budget.strip(),
        requirement=requirement.strip(),
        ai_analysis=analysis.get("raw", ""),
        ai_in_scope=bool(analysis.get("in_scope", False)),
        ai_confidence=float(analysis.get("confidence", 0.0)),
        ai_recommended_package=str(analysis.get("recommended_package", "")),
        status=lead_status,
    )
    marketing.apply_attribution(db, lead, form)
    marketing.screen_lead(db, lead, form, honeypot=is_spam)
    db.add(lead)
    db.commit()

    return {
        "ok": True,
        "in_scope": analysis.get("in_scope", False),
        "summary": analysis.get("summary", ""),
        "recommended_package": analysis.get("recommended_package", ""),
        "fit_reason": analysis.get("fit_reason", ""),
        "next_action": analysis.get("next_action", ""),
    }


# ============ ADMIN AUTH ============

@app.get("/admin/login", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None, wait: int = 0):
    return templates.TemplateResponse("admin/login.html", {
        "request": request, "error": error, "wait": wait, "settings": settings,
    })


@app.post("/admin/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    # ล็อกตาม IP หลังเดารหัสผิดติดกันหลายครั้ง — username เป็น "admin" ตายตัว
    # ช่องนี้จึงเป็นทางเดียวที่คนนอกใช้ยิงเดารหัสได้
    ip = client_ip(request)
    locked_for = login_lock_remaining(ip)
    if locked_for:
        return RedirectResponse(
            f"/admin/login?error=locked&wait={(locked_for + 59) // 60}", status_code=303
        )
    if rate_limited("login", ip, LOGIN_RULES):
        return RedirectResponse("/admin/login?error=too_many", status_code=303)

    user = authenticate_user(db, username, password)
    if not user:
        record_login_failure(ip)
        return RedirectResponse("/admin/login?error=invalid", status_code=303)

    clear_login_failures(ip)
    token = create_session_token(user.id)
    resp = RedirectResponse("/admin", status_code=303)
    resp.set_cookie(
        COOKIE_NAME, token,
        max_age=TOKEN_EXPIRE_HOURS * 3600,
        httponly=True,
        samesite="lax",
        secure=not settings.DEBUG,  # dev รันบน http ล้วน จึงปิดเฉพาะตอน DEBUG
    )
    return resp


@app.get("/admin/logout")
async def logout():
    resp = RedirectResponse("/admin/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp


# ============ ADMIN PAGES ============

def _check_admin(request: Request, db: Session):
    user = get_current_user(request, db)
    if not user:
        return None
    return user


@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    user = _check_admin(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=303)

    real = db.query(Lead).filter(Lead.status != "anonymous")
    total_leads = real.count()
    in_scope = db.query(Lead).filter_by(ai_in_scope=True).count()
    # รอติดต่อ = ขั้น "ใหม่" ที่ไม่ใช่รายการซ้ำและไม่สงสัยสแปม
    new_leads = real.filter(Lead.sales_stage == "new", Lead.duplicate_of.is_(None),
                            Lead.qualification != "spam").count()
    recent_leads = real.order_by(Lead.created_at.desc()).limit(5).all()
    total_posts = db.query(BlogPost).count()
    published_posts = db.query(BlogPost).filter_by(is_published=True).count()

    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "user": user,
        "total_leads": total_leads,
        "in_scope_leads": in_scope,
        "new_leads": new_leads,
        "recent_leads": recent_leads,
        "total_posts": total_posts,
        "published_posts": published_posts,
        "settings": settings,
    })


@app.get("/admin/content", response_class=HTMLResponse)
async def admin_content(request: Request, db: Session = Depends(get_db)):
    user = _check_admin(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=303)

    # tracking มีหน้าของตัวเองที่ /admin/tracking (มีตัวตรวจรูปแบบ ID ให้)
    # จึงกันออกจากหน้านี้ ไม่งั้นจะมีสองที่แก้ค่าเดียวกัน
    rows = (
        db.query(Content)
        .filter(Content.section != "tracking")
        .order_by(Content.section, Content.id)
        .all()
    )
    grouped: dict = {}
    for row in rows:
        grouped.setdefault(row.section, []).append(row)
    return templates.TemplateResponse("admin/content.html", {
        "request": request, "user": user, "grouped": grouped, "settings": settings,
    })


@app.post("/admin/content/update")
async def admin_content_update(
    request: Request, db: Session = Depends(get_db),
):
    user = _check_admin(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=303)
    form = await request.form()
    for key, value in form.items():
        if key.startswith("content_"):
            content_key = key[8:]
            row = db.query(Content).filter_by(key=content_key).first()
            if row:
                row.value = str(value)
    db.commit()
    return RedirectResponse("/admin/content?saved=1", status_code=303)


@app.get("/admin/tracking", response_class=HTMLResponse)
async def admin_tracking(
    request: Request, saved: int = 0, invalid: str = "", db: Session = Depends(get_db),
):
    user = _check_admin(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=303)

    content = load_content(db)
    return templates.TemplateResponse("admin/tracking.html", {
        "request": request, "user": user, "settings": settings,
        "values": {key: content.get(key, "") for key in TRACKING_KEYS},
        "env_values": {
            "gtm_id": settings.GTM_ID,
            "ga4_id": settings.GA4_ID,
            "meta_pixel_id": settings.META_PIXEL_ID,
        },
        "labels": TRACKING_LABELS,
        "saved": saved,
        "invalid": [k for k in invalid.split(",") if k in TRACKING_KEYS],
    })


@app.post("/admin/tracking")
async def admin_tracking_update(request: Request, db: Session = Depends(get_db)):
    user = _check_admin(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=303)

    form = await request.form()
    invalid = []
    for key in TRACKING_KEYS:
        value, ok = clean_tracking_id(key, str(form.get(key, "")))
        if not ok:
            # กรอกมาแต่หา ID ไม่เจอ — เก็บค่าเดิมไว้ อย่าล้างของที่ทำงานอยู่ทิ้ง
            invalid.append(key)
            continue
        row = db.query(Content).filter_by(key=key).first()
        if row:
            row.value = value
        else:
            db.add(Content(
                key=key, value=value, label=TRACKING_LABELS[key],
                section="tracking", field_type="text",
            ))
    db.commit()

    if invalid:
        return RedirectResponse(f"/admin/tracking?invalid={','.join(invalid)}", status_code=303)
    return RedirectResponse("/admin/tracking?saved=1", status_code=303)


@app.get("/admin/packages", response_class=HTMLResponse)
async def admin_packages(request: Request, db: Session = Depends(get_db)):
    user = _check_admin(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=303)
    packages = db.query(Package).order_by(Package.category, Package.sort_order).all()
    return templates.TemplateResponse("admin/packages.html", {
        "request": request, "user": user, "packages": packages, "settings": settings,
    })


@app.post("/admin/packages/{pkg_id}/update")
async def admin_package_update(
    pkg_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _check_admin(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=303)
    form = await request.form()
    pkg = db.query(Package).filter_by(id=pkg_id).first()
    if pkg:
        pkg.name = form.get("name", pkg.name)
        pkg.price = form.get("price", pkg.price)
        pkg.price_unit = form.get("price_unit", pkg.price_unit)
        pkg.description = form.get("description", pkg.description)
        pkg.features = form.get("features", pkg.features)
        pkg.is_active = form.get("is_active") == "on"
        pkg.is_featured = form.get("is_featured") == "on"
        try:
            pkg.sort_order = int(form.get("sort_order", pkg.sort_order))
        except (TypeError, ValueError):
            pass
        db.commit()
    return RedirectResponse("/admin/packages?saved=1", status_code=303)


def _lead_ctx() -> dict:
    return {
        "SALES_STAGES": mc.SALES_STAGES, "SALES_STAGE_LABELS": mc.SALES_STAGE_LABELS,
        "QUALIFICATIONS": mc.QUALIFICATIONS, "QUALIFICATION_LABELS": mc.QUALIFICATION_LABELS,
        "SERVICES": mc.SERVICES, "SERVICE_MAP": mc.SERVICE_MAP,
        "REQUEST_TYPE_LABELS": mc.REQUEST_TYPE_LABELS, "SPAM_REASON_LABELS": mc.SPAM_REASON_LABELS,
        "channel_label": mc.channel_label, "CHANNELS": mc.CHANNELS + mc.DERIVED_CHANNELS,
        "UNKNOWN_SOURCE": mc.UNKNOWN_SOURCE,
    }


@app.get("/admin/leads", response_class=HTMLResponse)
async def admin_leads(request: Request, db: Session = Depends(get_db), filter: str = "all",
                      stage: str = "", qual: str = "", channel: str = "", dup: str = ""):
    user = _check_admin(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=303)
    q = db.query(Lead)
    if filter == "anonymous":
        q = q.filter(Lead.status == "anonymous")
    else:
        q = q.filter(Lead.status != "anonymous")
    if filter == "in_scope":
        q = q.filter_by(ai_in_scope=True)
    elif filter == "out_scope":
        q = q.filter_by(ai_in_scope=False)
    elif filter == "new":
        q = q.filter(Lead.sales_stage == "new", Lead.qualification != "spam",
                     Lead.duplicate_of.is_(None))
    elif filter == "followup":
        q = q.filter(Lead.next_follow_up.isnot(None), Lead.sales_stage.notin_(("won", "lost")))
    if stage in mc.SALES_STAGE_LABELS:
        q = q.filter(Lead.sales_stage == stage)
    if qual in mc.QUALIFICATION_LABELS:
        q = q.filter(Lead.qualification == qual)
    if channel == "unknown":
        q = q.filter((Lead.channel == "unknown") | (Lead.channel == "") | (Lead.channel.is_(None)))
    elif channel in mc.CHANNEL_MAP:
        q = q.filter(Lead.channel == channel)
    if dup == "only":
        q = q.filter(Lead.duplicate_of.isnot(None))
    elif dup != "all":
        q = q.filter(Lead.duplicate_of.is_(None))
    order = Lead.next_follow_up if filter == "followup" else Lead.created_at.desc()
    leads = q.order_by(order).limit(500).all()
    campaigns = {c.id: c for c in db.query(Campaign).all()}
    return templates.TemplateResponse("admin/leads.html", {
        "request": request, "user": user, "leads": leads, "filter": filter, "settings": settings,
        "f": {"stage": stage, "qual": qual, "channel": channel, "dup": dup},
        "campaigns": campaigns, **_lead_ctx(),
    })


@app.get("/admin/leads/{lead_id}", response_class=HTMLResponse)
async def admin_lead_detail(lead_id: int, request: Request, db: Session = Depends(get_db)):
    user = _check_admin(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=303)
    lead = db.query(Lead).filter_by(id=lead_id).first()
    if not lead:
        raise HTTPException(status_code=404)
    notes = db.query(LeadNote).filter_by(lead_id=lead.id).order_by(LeadNote.created_at.desc()).all()
    history = (db.query(AuditLog).filter_by(entity="lead", entity_id=lead.id)
               .order_by(AuditLog.created_at.desc()).limit(30).all())
    dup_first = db.get(Lead, lead.duplicate_of) if lead.duplicate_of else None
    dup_others = db.query(Lead).filter(Lead.duplicate_of == lead.id).order_by(Lead.created_at).all()
    return templates.TemplateResponse("admin/lead_detail.html", {
        "request": request, "user": user, "lead": lead, "settings": settings,
        "notes": notes, "history": history, "dup_first": dup_first, "dup_others": dup_others,
        "campaign": db.get(Campaign, lead.campaign_id) if lead.campaign_id else None,
        "content_item": db.get(ContentItem, lead.content_item_id) if lead.content_item_id else None,
        "group_post": db.get(FbGroupPost, lead.group_post_id) if lead.group_post_id else None,
        "error": request.query_params.get("error", ""),
        **_lead_ctx(),
    })


def _lead_audit(db: Session, user: User, action: str, lead_id: int, detail: dict) -> None:
    import json as _json
    db.add(AuditLog(username=user.username, action=action, entity="lead", entity_id=lead_id,
                    detail=_json.dumps(detail, ensure_ascii=False, default=str)))


@app.post("/admin/leads/{lead_id}/update")
async def admin_lead_update(
    lead_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _check_admin(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=303)
    form = await request.form()
    lead = db.query(Lead).filter_by(id=lead_id).first()
    if not lead:
        raise HTTPException(status_code=404)

    errors = []
    stage = str(form.get("sales_stage") or lead.sales_stage or "new")
    qual = str(form.get("qualification") or lead.qualification or "pending")
    service = str(form.get("service_interest") or "")
    if stage not in mc.SALES_STAGE_LABELS or qual not in mc.QUALIFICATION_LABELS:
        errors.append("สถานะไม่ถูกต้อง")
    if service and service not in mc.SERVICE_MAP:
        service = ""
    values = {}
    for key in ("quote_value", "won_value"):
        raw = str(form.get(key) or "").strip()
        values[key] = mc.parse_money(raw)
        if raw and values[key] is None:
            errors.append("มูลค่าต้องเป็นตัวเลข ≥ 0")
    if stage == "won" and values["won_value"] is None:
        errors.append("ปิดงานแล้ว — กรุณาใส่มูลค่างานที่ปิดได้")
    next_raw = str(form.get("next_follow_up") or "").strip()
    next_date = mc.parse_date(next_raw)
    if next_raw and not next_date:
        errors.append("วันนัดถัดไปไม่ถูกต้อง")
    if errors:
        from urllib.parse import quote
        return RedirectResponse(f"/admin/leads/{lead_id}?error={quote(' · '.join(errors))}",
                                status_code=303)

    before = {"sales_stage": lead.sales_stage, "qualification": lead.qualification,
              "quote_value": lead.quote_value, "won_value": lead.won_value,
              "service_interest": lead.service_interest, "next_follow_up": lead.next_follow_up}
    lead.sales_stage, lead.qualification, lead.service_interest = stage, qual, service
    lead.quote_value, lead.won_value = values["quote_value"], values["won_value"]
    lead.next_follow_up = next_date
    if qual == "spam" and not lead.spam_reason:
        lead.spam_reason = "manual"
    # คงช่อง status เดิมให้สอดคล้อง (ระบบเก่าบางจุดยังอ่านค่านี้)
    lead.status = "spam" if qual == "spam" else stage
    lead.notes = form.get("notes", lead.notes)
    lead.updated_at = datetime.utcnow()
    after = {"sales_stage": lead.sales_stage, "qualification": lead.qualification,
             "quote_value": lead.quote_value, "won_value": lead.won_value,
             "service_interest": lead.service_interest, "next_follow_up": lead.next_follow_up}
    changed = {k: {"from": before[k], "to": after[k]} for k in after if before[k] != after[k]}
    if changed:
        _lead_audit(db, user, "lead_update", lead.id, changed)
    db.commit()
    return RedirectResponse(f"/admin/leads/{lead_id}?saved=1", status_code=303)


@app.post("/admin/leads/{lead_id}/notes")
async def admin_lead_note(lead_id: int, request: Request, db: Session = Depends(get_db)):
    user = _check_admin(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=303)
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404)
    form = await request.form()
    text = str(form.get("text") or "").strip()[:4000]
    next_date = mc.parse_date(str(form.get("next_follow_up") or ""))
    if not text and not next_date:
        return RedirectResponse(f"/admin/leads/{lead_id}", status_code=303)
    db.add(LeadNote(lead_id=lead.id, text=text, next_follow_up=next_date,
                    created_by=user.username))
    if next_date:
        lead.next_follow_up = next_date
    if lead.sales_stage == "new" and form.get("mark_contacted") == "on":
        _lead_audit(db, user, "lead_update", lead.id,
                    {"sales_stage": {"from": "new", "to": "contacted"}})
        lead.sales_stage = lead.status = "contacted"
    lead.updated_at = datetime.utcnow()
    db.commit()
    return RedirectResponse(f"/admin/leads/{lead_id}?saved=1", status_code=303)


@app.post("/admin/leads/{lead_id}/not-duplicate")
async def admin_lead_not_duplicate(lead_id: int, request: Request, db: Session = Depends(get_db)):
    """ยืนยันว่าไม่ใช่รายการซ้ำ (เช่น คนละคนใช้เบอร์สำนักงานเดียวกัน)"""
    user = _check_admin(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=303)
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404)
    if lead.duplicate_of:
        _lead_audit(db, user, "lead_not_duplicate", lead.id, {"was_duplicate_of": lead.duplicate_of})
        lead.duplicate_of = None
        lead.not_duplicate = True
        db.commit()
    return RedirectResponse(f"/admin/leads/{lead_id}?saved=1", status_code=303)


@app.get("/admin/blog", response_class=HTMLResponse)
async def admin_blog(request: Request, db: Session = Depends(get_db)):
    user = _check_admin(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=303)
    posts = db.query(BlogPost).order_by(BlogPost.created_at.desc()).all()
    return templates.TemplateResponse("admin/blog_list.html", {
        "request": request, "user": user, "posts": posts, "settings": settings,
    })


@app.get("/admin/blog/new", response_class=HTMLResponse)
async def admin_blog_new(request: Request, db: Session = Depends(get_db)):
    user = _check_admin(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=303)
    return templates.TemplateResponse("admin/blog_edit.html", {
        "request": request, "user": user, "post": None, "settings": settings,
    })


@app.get("/admin/blog/{post_id}", response_class=HTMLResponse)
async def admin_blog_edit(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = _check_admin(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=303)
    post = db.query(BlogPost).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("admin/blog_edit.html", {
        "request": request, "user": user, "post": post, "settings": settings,
    })


@app.post("/admin/blog/save")
async def admin_blog_save(request: Request, db: Session = Depends(get_db)):
    user = _check_admin(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=303)
    form = await request.form()
    post_id = form.get("id")
    if post_id:
        post = db.query(BlogPost).filter_by(id=int(post_id)).first()
        if not post:
            raise HTTPException(status_code=404)
    else:
        post = BlogPost()
        db.add(post)

    post.slug = form.get("slug", "").strip()
    post.title = form.get("title", "").strip()
    post.excerpt = form.get("excerpt", "")
    post.content = form.get("content", "")
    post.cover_image = form.get("cover_image", "")
    post.tags = form.get("tags", "")
    post.is_published = form.get("is_published") == "on"
    db.commit()
    return RedirectResponse("/admin/blog?saved=1", status_code=303)


@app.post("/admin/blog/{post_id}/delete")
async def admin_blog_delete(post_id: int, request: Request, db: Session = Depends(get_db)):
    user = _check_admin(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=303)
    post = db.query(BlogPost).filter_by(id=post_id).first()
    if post:
        db.delete(post)
        db.commit()
    return RedirectResponse("/admin/blog", status_code=303)


@app.get("/uploads/{filename}")
async def serve_upload(filename: str):
    """Serve uploaded file (public download)"""
    safe_name = Path(filename).name  # prevent path traversal
    file_path = UPLOAD_DIR / safe_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, filename=safe_name)


@app.get("/admin/files", response_class=HTMLResponse)
async def admin_files(request: Request, db: Session = Depends(get_db)):
    user = _check_admin(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=303)

    # Get current file info for each slot
    files_info = {}
    for slot in ("brochure", "catalog"):
        content = db.query(Content).filter_by(key=f"{slot}_file").first()
        filename = content.value if content else ""
        info = {"filename": filename, "exists": False, "size": 0}
        if filename:
            fpath = UPLOAD_DIR / filename
            if fpath.exists():
                info["exists"] = True
                info["size"] = fpath.stat().st_size
        files_info[slot] = info

    return templates.TemplateResponse("admin/files.html", {
        "request": request, "user": user, "files": files_info, "settings": settings,
    })


@app.post("/admin/files/upload")
async def admin_files_upload(
    request: Request,
    slot: str = Form(...),  # "brochure" or "catalog"
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user = _check_admin(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=303)

    if slot not in ("brochure", "catalog"):
        return RedirectResponse("/admin/files?error=invalid_slot", status_code=303)

    # Validate extension
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXT:
        return RedirectResponse("/admin/files?error=invalid_type", status_code=303)

    # Save with predictable filename (slot.ext) so we can serve consistently
    safe_filename = f"{slot}{ext}"
    file_path = UPLOAD_DIR / safe_filename

    # Remove old file with different extension if exists
    for old_ext in ALLOWED_UPLOAD_EXT:
        old_path = UPLOAD_DIR / f"{slot}{old_ext}"
        if old_path.exists() and old_ext != ext:
            old_path.unlink()

    # Save new file
    size = 0
    try:
        with file_path.open("wb") as buffer:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                size += len(chunk)
                if size > MAX_UPLOAD_SIZE:
                    file_path.unlink(missing_ok=True)
                    return RedirectResponse("/admin/files?error=too_large", status_code=303)
                buffer.write(chunk)
    except Exception:
        return RedirectResponse("/admin/files?error=upload_failed", status_code=303)

    # Update content
    content = db.query(Content).filter_by(key=f"{slot}_file").first()
    if content:
        content.value = safe_filename
    else:
        db.add(Content(
            key=f"{slot}_file",
            value=safe_filename,
            label=f"{slot.title()} filename (auto)",
            section="files",
            field_type="text",
        ))
    db.commit()
    return RedirectResponse("/admin/files?saved=1", status_code=303)


@app.post("/admin/files/delete")
async def admin_files_delete(
    request: Request,
    slot: str = Form(...),
    db: Session = Depends(get_db),
):
    user = _check_admin(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=303)

    if slot not in ("brochure", "catalog"):
        return RedirectResponse("/admin/files", status_code=303)

    # Remove any file matching slot.* extension
    for ext in ALLOWED_UPLOAD_EXT:
        fpath = UPLOAD_DIR / f"{slot}{ext}"
        if fpath.exists():
            fpath.unlink()

    # Clear content reference
    content = db.query(Content).filter_by(key=f"{slot}_file").first()
    if content:
        content.value = ""
        db.commit()

    return RedirectResponse("/admin/files?deleted=1", status_code=303)


@app.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings(request: Request, db: Session = Depends(get_db)):
    user = _check_admin(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=303)
    return templates.TemplateResponse("admin/settings.html", {
        "request": request, "user": user, "settings": settings,
    })


@app.post("/admin/settings/password")
async def admin_change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = _check_admin(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=303)
    if not pwd_context.verify(current_password, user.password_hash):
        return RedirectResponse("/admin/settings?error=wrong_password", status_code=303)
    if len(new_password) < 6:
        return RedirectResponse("/admin/settings?error=too_short", status_code=303)
    user.password_hash = pwd_context.hash(new_password)
    db.commit()
    return RedirectResponse("/admin/settings?saved=1", status_code=303)


if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=settings.DEBUG)

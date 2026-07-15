"""AV Control System — Marketing Website + Admin CMS"""
import os
import shutil
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional

# ===== File Uploads =====
# Use persistent disk on Render, local folder for dev
UPLOAD_DIR = Path("/var/data/uploads") if os.path.exists("/var/data") else Path("./uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_UPLOAD_EXT = {".pdf", ".doc", ".docx", ".ppt", ".pptx"}
MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20 MB

from config import get_settings
from database import get_db, Content, Package, Lead, BlogPost, User
from auth import (
    authenticate_user, create_session_token, get_current_user, require_admin,
    pwd_context, COOKIE_NAME, TOKEN_EXPIRE_HOURS,
)
from ai_service import analyze_requirement
from seed import run_seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_seed()
    yield


settings = get_settings()
app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# App version shown in the footer. Override without a code change by setting
# the APP_VERSION env var (e.g. in Render); defaults to the baseline below.
APP_VERSION = os.getenv("APP_VERSION", "2.0.0")
templates.env.globals["APP_VERSION"] = APP_VERSION


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


@app.post("/api/analyze", response_class=JSONResponse)
async def analyze_only(
    requirement: str = Form(...),
    room_size: str = Form(""),
    budget: str = Form(""),
    db: Session = Depends(get_db),
):
    """วิเคราะห์อย่างเดียว ยังไม่บันทึก Lead — บันทึกเป็น anonymous lead เพื่อเก็บสถิติ"""
    if not requirement.strip():
        return JSONResponse({"ok": False, "error": "กรุณากรอกความต้องการ"}, status_code=400)

    analysis = await analyze_requirement(
        requirement=requirement, room_size=room_size, budget=budget, company="",
    )

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
        status="anonymous",
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)

    return {
        "ok": True,
        "lead_id": lead.id,
        "in_scope": analysis.get("in_scope", False),
        "summary": analysis.get("summary", ""),
        "recommended_package": analysis.get("recommended_package", ""),
        "fit_reason": analysis.get("fit_reason", ""),
        "next_action": analysis.get("next_action", ""),
    }


@app.post("/api/lead", response_class=JSONResponse)
async def submit_lead(
    name: str = Form(...),
    company: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    room_size: str = Form(""),
    budget: str = Form(""),
    requirement: str = Form(...),
    lead_id: str = Form(""),
    db: Session = Depends(get_db),
):
    """บันทึก/อัปเดต Lead เมื่อมีข้อมูลติดต่อแล้ว — รองรับทั้ง flow ใหม่ (อัปเดต anonymous lead) และ flow เดิม (สร้างใหม่)"""
    if not name.strip() or not requirement.strip():
        return JSONResponse({"ok": False, "error": "กรุณากรอกชื่อและความต้องการ"}, status_code=400)

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
        lead.status = "new_in_scope" if lead.ai_in_scope else "new_out_scope"
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
    analysis = await analyze_requirement(
        requirement=requirement, room_size=room_size, budget=budget, company=company,
    )

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
        status="new_in_scope" if analysis.get("in_scope") else "new_out_scope",
    )
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
async def login_page(request: Request, error: Optional[str] = None):
    return templates.TemplateResponse("admin/login.html", {
        "request": request, "error": error, "settings": settings,
    })


@app.post("/admin/login")
async def login_submit(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, username, password)
    if not user:
        return RedirectResponse("/admin/login?error=invalid", status_code=303)
    token = create_session_token(user.id)
    resp = RedirectResponse("/admin", status_code=303)
    resp.set_cookie(
        COOKIE_NAME, token,
        max_age=TOKEN_EXPIRE_HOURS * 3600,
        httponly=True,
        samesite="lax",
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

    total_leads = db.query(Lead).count()
    in_scope = db.query(Lead).filter_by(ai_in_scope=True).count()
    new_leads = db.query(Lead).filter(Lead.status.like("new%")).count()
    recent_leads = db.query(Lead).order_by(Lead.created_at.desc()).limit(5).all()
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

    rows = db.query(Content).order_by(Content.section, Content.id).all()
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


@app.get("/admin/leads", response_class=HTMLResponse)
async def admin_leads(request: Request, db: Session = Depends(get_db), filter: str = "all"):
    user = _check_admin(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=303)
    q = db.query(Lead)
    if filter == "in_scope":
        q = q.filter_by(ai_in_scope=True)
    elif filter == "out_scope":
        q = q.filter_by(ai_in_scope=False)
    elif filter == "new":
        q = q.filter(Lead.status.like("new%"))
    leads = q.order_by(Lead.created_at.desc()).all()
    return templates.TemplateResponse("admin/leads.html", {
        "request": request, "user": user, "leads": leads, "filter": filter, "settings": settings,
    })


@app.get("/admin/leads/{lead_id}", response_class=HTMLResponse)
async def admin_lead_detail(lead_id: int, request: Request, db: Session = Depends(get_db)):
    user = _check_admin(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=303)
    lead = db.query(Lead).filter_by(id=lead_id).first()
    if not lead:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("admin/lead_detail.html", {
        "request": request, "user": user, "lead": lead, "settings": settings,
    })


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
    if lead:
        lead.status = form.get("status", lead.status)
        lead.notes = form.get("notes", lead.notes)
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

"""เมนู "การตลาด" ใน Admin — แคมเปญ · ลิงก์ติดตาม · เนื้อหา/ปฏิทิน · กลุ่ม Facebook
· ค่าโฆษณา · รายงาน และ endpoint เก็บคลิก LINE/โทรจากหน้าเว็บ

สิทธิ์: ทุก route ใต้ /admin/marketing ผ่าน require_admin ที่ระดับ router (ตรวจฝั่ง
เซิร์ฟเวอร์ทุกคำขอ ไม่พึ่งการซ่อนเมนู) — ใช้บัญชีและ cookie เดียวกับ Admin เดิม

ตรรกะที่ไม่เกี่ยวกับ HTTP อยู่ใน marketing_core.py · นิยามตัวชี้วัดอยู่ใน
docs/MARKETING-GUIDE.md
"""
import calendar
import hashlib
import json
import mimetypes
import re
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import marketing_core as mc
from auth import require_admin
from config import get_settings
from database import (
    AdSpend, AuditLog, Campaign, ContentItem, FbGroup, FbGroupPost, ImportBatch, Lead,
    TrackingLink, User, WebEvent, get_db,
)
from marketing_integrations import CONNECTORS, connector_for_channel
from security import client_ip, rate_limited

settings = get_settings()

router = APIRouter(prefix="/admin/marketing", dependencies=[Depends(require_admin)])
public_router = APIRouter()

_templates = None
MEDIA_DIR: Path = Path("./uploads/marketing")

MEDIA_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov", ".webm", ".pdf"}
MAX_MEDIA_SIZE = 50 * 1024 * 1024  # 50 MB ต่อไฟล์ — คลิปยาวให้เก็บเป็นลิงก์ Drive/YouTube
_STORED_RE = re.compile(r"^[0-9a-f]{32}\.[a-z0-9]{2,5}$")


def bind(templates, upload_dir: Path) -> None:
    """main.py ส่ง Jinja env (มี filter/global ครบ) และที่เก็บไฟล์เดิมมาให้"""
    global _templates, MEDIA_DIR
    _templates = templates
    MEDIA_DIR = Path(upload_dir) / "marketing"
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)


# ============ ตัวช่วย ============

def _catalog() -> dict:
    return {
        "SERVICES": mc.SERVICES, "SERVICE_MAP": mc.SERVICE_MAP, "CLAIM_LABELS": mc.CLAIM_LABELS,
        "CHANNELS": mc.CHANNELS, "CHANNEL_MAP": mc.CHANNEL_MAP, "SPEND_CHANNELS": mc.SPEND_CHANNELS,
        "channel_label": mc.channel_label,
        "SALES_STAGES": mc.SALES_STAGES, "SALES_STAGE_LABELS": mc.SALES_STAGE_LABELS,
        "QUALIFICATIONS": mc.QUALIFICATIONS, "QUALIFICATION_LABELS": mc.QUALIFICATION_LABELS,
        "CAMPAIGN_GOALS": mc.CAMPAIGN_GOALS, "CAMPAIGN_GOAL_LABELS": mc.CAMPAIGN_GOAL_LABELS,
        "CAMPAIGN_STATUSES": mc.CAMPAIGN_STATUSES,
        "CAMPAIGN_STATUS_LABELS": mc.CAMPAIGN_STATUS_LABELS,
        "CONTENT_STATUSES": mc.CONTENT_STATUSES, "CONTENT_STATUS_LABELS": mc.CONTENT_STATUS_LABELS,
        "GROUP_POST_STATUSES": mc.GROUP_POST_STATUSES,
        "GROUP_POST_STATUS_LABELS": mc.GROUP_POST_STATUS_LABELS,
        "RELEVANCE": mc.RELEVANCE, "RELEVANCE_LABELS": mc.RELEVANCE_LABELS,
        "UNKNOWN_SOURCE": mc.UNKNOWN_SOURCE,
    }


def _render(request: Request, name: str, user: User, **ctx) -> HTMLResponse:
    return _templates.TemplateResponse(f"admin/marketing/{name}", {
        "request": request, "user": user, "settings": settings, "mk": _catalog(), **ctx,
    })


def _back(url: str, **params) -> RedirectResponse:
    q = "&".join(f"{k}={v}" for k, v in params.items() if v not in (None, ""))
    return RedirectResponse(f"{url}{'?' + q if q else ''}", status_code=303)


def _s(form, key: str, limit: int = 200) -> str:
    return str(form.get(key) or "").strip()[:limit]


def _audit(db: Session, user: User, action: str, entity: str, entity_id, detail) -> None:
    db.add(AuditLog(
        username=user.username if user else "", action=action, entity=entity,
        entity_id=entity_id,
        detail=detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False, default=str),
    ))


def _parse_dt_local(value: str) -> Optional[datetime]:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _date_range(request: Request) -> tuple:
    """ช่วงวันที่จาก query (เวลาไทย) · ค่าเริ่มต้น 30 วันล่าสุด"""
    today = mc.bkk_today()
    qp = request.query_params
    preset = qp.get("range", "")
    start = mc.parse_date(qp.get("start", ""))
    end = mc.parse_date(qp.get("end", ""))
    if preset == "7d":
        start, end = today - timedelta(days=6), today
    elif preset == "90d":
        start, end = today - timedelta(days=89), today
    elif preset == "month":
        start, end = today.replace(day=1), today
    if not end:
        end = today
    if not start:
        start = end - timedelta(days=29)
    if start > end:
        start, end = end, start
    return start, end


def _safe_url(value: str, hosts: tuple = ()) -> str:
    """ลิงก์ที่ผู้ใช้กรอก (ลิงก์โพสต์จริง / ลิงก์กลุ่ม) — https เท่านั้น"""
    value = (value or "").strip()
    if not value:
        return ""
    if not value.startswith("https://") or any(c in value for c in " <>\"'"):
        return ""
    if hosts:
        from urllib.parse import urlsplit
        host = (urlsplit(value).hostname or "").lower()
        if not any(host == h or host.endswith("." + h) for h in hosts):
            return ""
    return value[:512]


# ============ ลิงก์ติดตาม ============

def ensure_link(db: Session, campaign: Campaign, channel: str, destination: str, *,
                content: str = "", term: str = "", label: str = "",
                source: str = "", medium: str = "",
                content_item_id: Optional[int] = None,
                group_post_id: Optional[int] = None) -> tuple:
    """สร้าง (หรือคืนของเดิมถ้า URL ตรงกัน) ลิงก์ UTM ตามมาตรฐาน → (link, error)"""
    ch = mc.CHANNEL_MAP.get(channel)
    if not ch or channel not in [c["key"] for c in mc.CHANNELS]:
        return None, "เลือกช่องทาง"
    src = ch["source"] or mc.slugify(source, 40)
    med = ch["medium"] or mc.slugify(medium, 40)
    if not src or not med:
        return None, "ช่องทางอื่นต้องระบุ source และ medium (a-z 0-9 -)"
    dest, err = mc.normalize_destination(destination or campaign.landing_url, settings.APP_URL)
    if err:
        return None, err
    content = mc.slugify(content, 80) if content else ""
    term = mc.slugify(term, 80) if term else ""
    url = mc.build_utm_url(dest, src, med, campaign.code, content, term)
    existing = db.query(TrackingLink).filter_by(url=url).first()
    if existing:
        return existing, ""
    link = TrackingLink(
        campaign_id=campaign.id, channel=channel, utm_source=src, utm_medium=med,
        utm_campaign=campaign.code, utm_content=content, utm_term=term,
        destination=dest, url=url, label=label[:200],
        content_item_id=content_item_id, group_post_id=group_post_id,
    )
    db.add(link)
    db.flush()
    return link, ""


# ============ Lead: แหล่งที่มา / ซ้ำ / สแปม (เรียกจาก main.submit_lead) ============

ATTRIBUTION_FIELDS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
                      "landing_page", "referrer")


def apply_attribution(db: Session, lead: Lead, form) -> None:
    """เติมแหล่งที่มาจากค่าที่สคริปต์หน้าเว็บแนบมากับฟอร์ม · ไม่มีค่า = ไม่ทราบแหล่งที่มา"""
    get = lambda k: str(form.get(k) or "")  # noqa: E731
    lead.utm_source = mc.clean_utm_value(get("utm_source"))
    lead.utm_medium = mc.clean_utm_value(get("utm_medium"))
    lead.utm_campaign = mc.clean_utm_value(get("utm_campaign"))
    lead.utm_content = mc.clean_utm_value(get("utm_content"))
    lead.utm_term = mc.clean_utm_value(get("utm_term"))
    lead.landing_page = mc.clean_page_url(get("landing_page"))
    lead.referrer = mc.clean_page_url(get("referrer"))
    lead.channel = mc.classify_channel(
        lead.utm_source, lead.utm_medium, lead.referrer, mc.site_host(settings.APP_URL),
    )
    rt = get("request_type").strip()
    lead.request_type = rt if rt in mc.REQUEST_TYPE_LABELS else ""

    lead.campaign_id = None
    if lead.utm_campaign:
        camp = db.query(Campaign).filter_by(code=lead.utm_campaign.strip().lower()).first()
        if camp:
            lead.campaign_id = camp.id
            if not lead.service_interest and camp.service:
                lead.service_interest = camp.service
    ci, gp = mc.parse_content_ref(lead.utm_content)
    lead.content_item_id = ci if ci and db.get(ContentItem, ci) else None
    lead.group_post_id = gp if gp and db.get(FbGroupPost, gp) else None


def screen_lead(db: Session, lead: Lead, form, honeypot: bool) -> None:
    """ผลคัดกรองเบื้องต้น + ตรวจซ้ำ — ติดป้ายเท่านั้น ไม่ลบ ไม่ปฏิเสธการบันทึก"""
    lead.phone_norm = mc.normalize_phone(lead.phone)
    lead.email_norm = mc.normalize_email(lead.email)
    if not lead.sales_stage:
        lead.sales_stage = "new"
    fill_ms = mc.parse_int(form.get("form_ms"))
    reason = "honeypot" if honeypot else mc.spam_signals(lead.requirement, fill_ms)
    if reason:
        lead.qualification, lead.spam_reason = "spam", reason
    elif not lead.qualification:
        lead.qualification = "pending"

    lead.duplicate_of = None
    conds = []
    if lead.phone_norm:
        conds.append(Lead.phone_norm == lead.phone_norm)
    if lead.email_norm:
        conds.append(Lead.email_norm == lead.email_norm)
    if conds:
        from sqlalchemy import or_
        q = db.query(Lead).filter(or_(*conds), Lead.status != "anonymous",
                                  Lead.duplicate_of.is_(None))
        if lead.id:
            q = q.filter(Lead.id != lead.id)
        first = q.order_by(Lead.created_at, Lead.id).first()
        if first:
            lead.duplicate_of = first.id


# ============ endpoint สาธารณะ: คลิก LINE / โทร ============

EVENT_TYPES = {"line_click", "phone_click"}
EVENT_RULES = ((30, 60), (300, 3600))
_SID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")


@public_router.post("/api/event")
async def record_event(request: Request, db: Session = Depends(get_db)):
    """นับครั้งเดียวต่อ session ต่อประเภท (unique dedupe_key) — ส่งซ้ำก็ไม่เพิ่ม

    sid สุ่มจาก sessionStorage ของแท็บ ไม่ใช่คุกกี้ และไม่ผูกกับตัวบุคคล
    """
    if rate_limited("event", client_ip(request), EVENT_RULES):
        return Response(status_code=429)
    try:
        data = await request.json()
    except Exception:
        return Response(status_code=400)
    if not isinstance(data, dict):
        return Response(status_code=400)
    event = str(data.get("event") or "")
    sid = str(data.get("sid") or "")
    if event not in EVENT_TYPES or not _SID_RE.match(sid):
        return Response(status_code=400)
    src = mc.clean_utm_value(str(data.get("utm_source") or ""))
    med = mc.clean_utm_value(str(data.get("utm_medium") or ""))
    ref = mc.clean_page_url(str(data.get("referrer") or ""))
    db.add(WebEvent(
        event=event, dedupe_key=f"{event}:{sid}",
        path=mc.clean_page_url(str(data.get("path") or ""), 512) or str(data.get("path") or "")[:200],
        channel=mc.classify_channel(src, med, ref, mc.site_host(settings.APP_URL)),
        utm_source=src, utm_medium=med,
        utm_campaign=mc.clean_utm_value(str(data.get("utm_campaign") or "")),
        utm_content=mc.clean_utm_value(str(data.get("utm_content") or "")),
    ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # นับไปแล้วใน session นี้
    return Response(status_code=204)


# ============ รายงาน ============

def _lead_scope(db: Session, start: date, end: date, channel: str = ""):
    s, e = mc.bkk_range_to_utc(start, end)
    q = db.query(Lead).filter(Lead.created_at >= s, Lead.created_at < e,
                              Lead.status != "anonymous")
    if channel:
        if channel == "unknown":
            q = q.filter((Lead.channel == "unknown") | (Lead.channel == "") | (Lead.channel.is_(None)))
        else:
            q = q.filter(Lead.channel == channel)
    return q


def _unique(lead: Lead) -> bool:
    return not lead.duplicate_of and lead.qualification != "spam"


def _lead_stats(leads: list) -> dict:
    uniq = [l for l in leads if _unique(l)]
    fit = [l for l in uniq if l.qualification == "fit"]
    stage = {k: 0 for k, _ in mc.SALES_STAGES}
    for l in uniq:
        stage[l.sales_stage or "new"] = stage.get(l.sales_stage or "new", 0) + 1
    quoted = [l for l in uniq if l.sales_stage in ("quoted", "won") or l.quote_value is not None]
    won = [l for l in uniq if l.sales_stage == "won"]
    return {
        "submitted": len(leads),
        "unique": len(uniq),
        "duplicates": sum(1 for l in leads if l.duplicate_of),
        "spam": sum(1 for l in leads if l.qualification == "spam"),
        "fit": len(fit),
        "pending": sum(1 for l in uniq if l.qualification == "pending"),
        "stage": stage,
        "quoted": len(quoted),
        "won": len(won),
        "demo_requests": sum(1 for l in uniq if l.request_type == "demo"),
        "quote_requests": sum(1 for l in uniq if l.request_type == "quote"),
        "quote_value": sum(l.quote_value or 0 for l in uniq if l.quote_value is not None),
        "won_value": sum(l.won_value or 0 for l in won if l.won_value is not None),
    }


def _spend_rows(db: Session, start: date, end: date, channel: str = ""):
    q = db.query(AdSpend).filter(AdSpend.date >= start, AdSpend.date <= end)
    if channel:
        q = q.filter(AdSpend.channel == channel)
    return q.all()


def _sum_spend(rows: list) -> Optional[float]:
    """ไม่มีแถวเลย = None (ยังไม่มีข้อมูล) ต่างจาก 0 (มีข้อมูลและใช้ 0 บาท)"""
    return sum(r.spend for r in rows) if rows else None


SOURCE_LABELS = {"manual": "กรอกเอง", "csv": "นำเข้าไฟล์", "api": "เชื่อมต่อ"}


def compute_report(db: Session, start: date, end: date, channel: str = "") -> dict:
    leads = _lead_scope(db, start, end, channel).all()
    spend_rows = _spend_rows(db, start, end, channel)
    s_utc, e_utc = mc.bkk_range_to_utc(start, end)
    ev_q = db.query(WebEvent).filter(WebEvent.created_at >= s_utc, WebEvent.created_at < e_utc)
    if channel:
        ev_q = ev_q.filter(WebEvent.channel == channel)
    events = ev_q.all()

    stats = _lead_stats(leads)
    total_spend = _sum_spend(spend_rows)

    # ---- ตามช่องทาง ----
    last_spend = dict(db.query(AdSpend.channel, func.max(AdSpend.created_at))
                      .group_by(AdSpend.channel).all())
    by_channel = []
    keys = [channel] if channel else mc.REPORT_CHANNELS
    for key in keys:
        cl = [l for l in leads if (l.channel or "unknown") == key]
        cs = [r for r in spend_rows if r.channel == key]
        st = _lead_stats(cl)
        conn = connector_for_channel(key)
        conn_code, conn_label = conn.status() if conn else ("manual", "ไม่มีการเชื่อมต่อ (กรอกเอง)")
        always = key in ("google_ads", "facebook_ads", "facebook_page", "facebook_group",
                         "tiktok", "other", "unknown")
        if not always and not cl and not cs:
            continue
        spend = _sum_spend(cs)
        by_channel.append({
            "key": key, "label": mc.channel_label(key),
            "spend": spend, "spend_applicable": key in mc.SPEND_CHANNELS,
            "spend_sources": sorted({SOURCE_LABELS.get(r.source, r.source) for r in cs}),
            "last_update": mc.utc_to_bkk(last_spend.get(key)),
            "connection": conn_label, "connection_code": conn_code,
            "cpl_fit": mc.cost_per(spend, st["fit"]),
            **st,
        })

    # ---- ตามแคมเปญ ----
    camp_ids = {l.campaign_id for l in leads if l.campaign_id} | \
               {r.campaign_id for r in spend_rows if r.campaign_id}
    campaigns = {c.id: c for c in db.query(Campaign).all()}
    active_ids = {c.id for c in campaigns.values() if c.status == "active"}
    by_campaign = []
    for cid in sorted(camp_ids | active_ids, key=lambda i: campaigns[i].name if i in campaigns else ""):
        camp = campaigns.get(cid)
        if not camp:
            continue
        cl = [l for l in leads if l.campaign_id == cid]
        cs = [r for r in spend_rows if r.campaign_id == cid]
        st = _lead_stats(cl)
        spend = _sum_spend(cs)
        by_campaign.append({"id": cid, "label": camp.name, "code": camp.code,
                            "service": camp.service, "budget": camp.budget,
                            "spend": spend, "cpl_fit": mc.cost_per(spend, st["fit"]), **st})
    no_camp_leads = [l for l in leads if not l.campaign_id]
    no_camp_spend = [r for r in spend_rows if not r.campaign_id]
    if no_camp_leads or no_camp_spend:
        st = _lead_stats(no_camp_leads)
        spend = _sum_spend(no_camp_spend)
        by_campaign.append({"id": None, "label": "ไม่ผูกแคมเปญ / ไม่ทราบ", "code": "",
                            "service": "", "budget": None, "spend": spend,
                            "cpl_fit": mc.cost_per(spend, st["fit"]), **st})

    # ---- ตามเนื้อหา / โพสต์ (ไม่มีค่าโฆษณาระดับโพสต์ในรุ่นนี้) ----
    by_content = []
    items = {c.id: c for c in db.query(ContentItem).filter(
        ContentItem.id.in_({l.content_item_id for l in leads if l.content_item_id} or {0})).all()}
    for iid, item in items.items():
        st = _lead_stats([l for l in leads if l.content_item_id == iid])
        by_content.append({"kind": "content", "id": iid, "label": item.title,
                           "channel": item.channel, **st})
    gposts = db.query(FbGroupPost).filter(
        FbGroupPost.id.in_({l.group_post_id for l in leads if l.group_post_id} or {0})).all()
    groups = {g.id: g for g in db.query(FbGroup).all()}
    for p in gposts:
        st = _lead_stats([l for l in leads if l.group_post_id == p.id])
        g = groups.get(p.group_id)
        by_content.append({"kind": "group_post", "id": p.id, "group_id": p.group_id,
                           "label": f"โพสต์กลุ่ม: {g.name if g else '#' + str(p.group_id)}",
                           "channel": "facebook_group", **st})
    by_content.sort(key=lambda r: (-r["fit"], -r["unique"]))

    last_lead = db.query(func.max(Lead.created_at)).filter(Lead.status != "anonymous").scalar()
    last_event = db.query(func.max(WebEvent.created_at)).scalar()
    last_any_spend = db.query(func.max(AdSpend.created_at)).scalar()
    return {
        "start": start, "end": end, "channel": channel,
        "stats": stats,
        "spend": total_spend,
        "spend_rows": len(spend_rows),
        "cpl_fit": mc.cost_per(total_spend, stats["fit"]),
        "cpl_unique": mc.cost_per(total_spend, stats["unique"]),
        "line_clicks": sum(1 for e in events if e.event == "line_click"),
        "phone_clicks": sum(1 for e in events if e.event == "phone_click"),
        "by_channel": by_channel, "by_campaign": by_campaign, "by_content": by_content,
        "sources": [
            {"label": "Lead / ฟอร์มบนเว็บ", "how": "ฐานข้อมูลเว็บไซต์ (บันทึกทันทีที่ส่งฟอร์ม)",
             "last": mc.utc_to_bkk(last_lead)},
            {"label": "ค่าโฆษณา", "how": "กรอกเอง / นำเข้า CSV",
             "last": mc.utc_to_bkk(last_any_spend)},
            {"label": "คลิก LINE / โทร", "how": "ตัวนับบนเว็บของเราเอง (ครั้งเดียวต่อ session)",
             "last": mc.utc_to_bkk(last_event)},
            {"label": "ผู้เข้าเว็บไซต์", "how": "ยังไม่เชื่อมข้อมูล (รอ GA4 — ระยะ 2)", "last": None},
        ],
        "connectors": [(c, *c.status()) for c in CONNECTORS],
    }


def _report_ctx(request: Request, db: Session) -> dict:
    start, end = _date_range(request)
    channel = request.query_params.get("channel", "")
    if channel and channel not in mc.CHANNEL_MAP:
        channel = ""
    return {"r": compute_report(db, start, end, channel),
            "filters": {"start": start.isoformat(), "end": end.isoformat(), "channel": channel}}


# ============ หน้า: ภาพรวม ============

@router.get("", response_class=HTMLResponse)
async def overview(request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_admin)):
    today = mc.bkk_today()
    upcoming = (db.query(ContentItem)
                .filter(ContentItem.status != "published", ContentItem.planned_at.isnot(None),
                        ContentItem.planned_at >= datetime(today.year, today.month, today.day))
                .order_by(ContentItem.planned_at).limit(5).all())
    followups = (db.query(Lead)
                 .filter(Lead.next_follow_up.isnot(None), Lead.next_follow_up <= today + timedelta(days=7),
                         Lead.sales_stage.notin_(("won", "lost")), Lead.status != "anonymous")
                 .order_by(Lead.next_follow_up).limit(8).all())
    return _render(request, "overview.html", user, tab="overview",
                   upcoming=upcoming, followups=followups, today=today,
                   **_report_ctx(request, db))


# ============ หน้า: แคมเปญ ============

@router.get("/campaigns", response_class=HTMLResponse)
async def campaigns_list(request: Request, show: str = "", db: Session = Depends(get_db),
                         user: User = Depends(require_admin)):
    q = db.query(Campaign)
    if show != "archived":
        q = q.filter(Campaign.status != "archived")
    camps = q.order_by(Campaign.created_at.desc()).all()
    lead_counts = dict(db.query(Lead.campaign_id, func.count(Lead.id))
                       .filter(Lead.campaign_id.isnot(None), Lead.status != "anonymous",
                               Lead.duplicate_of.is_(None), Lead.qualification != "spam")
                       .group_by(Lead.campaign_id).all())
    fit_counts = dict(db.query(Lead.campaign_id, func.count(Lead.id))
                      .filter(Lead.campaign_id.isnot(None), Lead.qualification == "fit",
                              Lead.duplicate_of.is_(None))
                      .group_by(Lead.campaign_id).all())
    spend = dict(db.query(AdSpend.campaign_id, func.sum(AdSpend.spend))
                 .filter(AdSpend.campaign_id.isnot(None)).group_by(AdSpend.campaign_id).all())
    return _render(request, "campaigns.html", user, tab="campaigns", campaigns=camps,
                   show=show, lead_counts=lead_counts, fit_counts=fit_counts, spend=spend)


@router.get("/campaigns/new", response_class=HTMLResponse)
async def campaign_new(request: Request, user: User = Depends(require_admin)):
    return _render(request, "campaign_edit.html", user, tab="campaigns", c=None, errors=[], form={})


@router.get("/campaigns/{cid}/edit", response_class=HTMLResponse)
async def campaign_edit(cid: int, request: Request, db: Session = Depends(get_db),
                        user: User = Depends(require_admin)):
    c = db.get(Campaign, cid) or _404()
    return _render(request, "campaign_edit.html", user, tab="campaigns", c=c, errors=[], form={})


def _404():
    raise HTTPException(status_code=404)


@router.post("/campaigns/save")
async def campaign_save(request: Request, db: Session = Depends(get_db),
                        user: User = Depends(require_admin)):
    form = await request.form()
    cid = mc.parse_int(form.get("id"))
    c = db.get(Campaign, cid) if cid else None
    if cid and not c:
        _404()
    errors = []
    name = _s(form, "name")
    code = mc.slugify(_s(form, "code", 80) or name, 80)
    if not name:
        errors.append("กรุณาใส่ชื่อแคมเปญ")
    if not mc.valid_code(code):
        errors.append("รหัสแคมเปญ (utm_campaign) ใช้ได้เฉพาะ a-z 0-9 และขีด เช่น one-touch-gov-q4")
    elif db.query(Campaign).filter(Campaign.code == code, Campaign.id != (cid or 0)).first():
        errors.append(f"รหัส '{code}' ถูกใช้แล้ว")
    elif c and c.code != code and db.query(TrackingLink).filter_by(campaign_id=c.id).first():
        errors.append("แคมเปญนี้มีลิงก์ติดตามแล้ว เปลี่ยนรหัสไม่ได้ (ลิงก์ที่แจกไปจะไม่ผูกกับแคมเปญ)")
    service = _s(form, "service", 32)
    if service not in mc.SERVICE_MAP:
        errors.append("เลือกบริการที่โปรโมต")
    channels = [k for k in form.getlist("channels") if k in mc.CHANNEL_MAP]
    budget_raw = _s(form, "budget", 30)
    budget = mc.parse_money(budget_raw)
    if budget_raw and budget is None:
        errors.append("งบประมาณต้องเป็นตัวเลข")
    start = mc.parse_date(_s(form, "start_date", 20))
    end = mc.parse_date(_s(form, "end_date", 20))
    if start and end and end < start:
        errors.append("วันสิ้นสุดต้องไม่ก่อนวันเริ่ม")
    goal = _s(form, "goal", 16)
    if goal not in mc.CAMPAIGN_GOAL_LABELS:
        errors.append("เลือกเป้าหมาย")
    landing, lerr = ("", "")
    if _s(form, "landing_url", 512):
        landing, lerr = mc.normalize_destination(_s(form, "landing_url", 512), settings.APP_URL)
        if lerr:
            errors.append(lerr)
    else:
        errors.append("ระบุหน้าเว็บปลายทาง")
    status = _s(form, "status", 16)
    if status not in mc.CAMPAIGN_STATUS_LABELS:
        status = "draft"
    if errors:
        return _render(request, "campaign_edit.html", user, tab="campaigns", c=c,
                       errors=errors, form=dict(form) | {"channels": channels})

    is_new = c is None
    before = {} if is_new else {"budget": c.budget, "status": c.status, "code": c.code}
    if is_new:
        c = Campaign()
        db.add(c)
    c.name, c.code, c.service = name, code, service
    c.audience = _s(form, "audience", 2000)
    c.channels = ",".join(channels)
    c.budget, c.start_date, c.end_date = budget, start, end
    c.goal, c.landing_url, c.status = goal, landing, status
    c.notes = _s(form, "notes", 4000)
    db.flush()
    after = {"budget": c.budget, "status": c.status, "code": c.code}
    if is_new:
        _audit(db, user, "campaign_create", "campaign", c.id, after)
    elif before != after:
        _audit(db, user, "campaign_update", "campaign", c.id, {"from": before, "to": after})
    db.commit()
    return _back(f"/admin/marketing/campaigns/{c.id}", saved=1)


@router.get("/campaigns/{cid}", response_class=HTMLResponse)
async def campaign_detail(cid: int, request: Request, db: Session = Depends(get_db),
                          user: User = Depends(require_admin)):
    c = db.get(Campaign, cid) or _404()
    links = db.query(TrackingLink).filter_by(campaign_id=cid).order_by(TrackingLink.id.desc()).all()
    items = db.query(ContentItem).filter_by(campaign_id=cid).order_by(ContentItem.planned_at).all()
    leads = (db.query(Lead).filter(Lead.campaign_id == cid, Lead.status != "anonymous")
             .order_by(Lead.created_at.desc()).all())
    spend_rows = db.query(AdSpend).filter_by(campaign_id=cid).all()
    history = (db.query(AuditLog).filter_by(entity="campaign", entity_id=cid)
               .order_by(AuditLog.created_at.desc()).limit(20).all())
    link_leads = {}
    for l in leads:
        key = (l.utm_source, l.utm_medium, l.utm_content)
        link_leads[key] = link_leads.get(key, 0) + (1 if _unique(l) else 0)
    stats = _lead_stats(leads)
    spend = _sum_spend(spend_rows)
    return _render(request, "campaign_detail.html", user, tab="campaigns", c=c, links=links,
                   items=items, leads=leads[:20], stats=stats, spend=spend,
                   cpl_fit=mc.cost_per(spend, stats["fit"]), history=history,
                   link_leads=link_leads, error=request.query_params.get("error", ""),
                   new_link=mc.parse_int(request.query_params.get("link")))


@router.post("/campaigns/{cid}/links")
async def campaign_link_create(cid: int, request: Request, db: Session = Depends(get_db),
                               user: User = Depends(require_admin)):
    c = db.get(Campaign, cid) or _404()
    form = await request.form()
    ci = mc.parse_int(form.get("content_item_id"))
    item = db.get(ContentItem, ci) if ci else None
    content = mc.content_utm(item.id, item.title) if item else _s(form, "content", 80)
    link, err = ensure_link(
        db, c, _s(form, "channel", 32), _s(form, "destination", 512),
        content=content, term=_s(form, "term", 80), label=_s(form, "label"),
        source=_s(form, "source", 40), medium=_s(form, "medium", 40),
        content_item_id=item.id if item else None,
    )
    if err:
        return _back(f"/admin/marketing/campaigns/{cid}", error=err)
    db.commit()
    return _back(f"/admin/marketing/campaigns/{cid}", link=link.id)


# ============ หน้า: เนื้อหาและปฏิทิน ============

def _media(item: ContentItem) -> list:
    try:
        data = json.loads(item.media or "[]")
        return data if isinstance(data, list) else []
    except ValueError:
        return []


@router.get("/content", response_class=HTMLResponse)
async def content_list(request: Request, db: Session = Depends(get_db),
                       user: User = Depends(require_admin)):
    qp = request.query_params
    view = qp.get("view", "list")
    q = db.query(ContentItem)
    status = qp.get("status", "")
    if status in mc.CONTENT_STATUS_LABELS:
        q = q.filter(ContentItem.status == status)
    channel = qp.get("channel", "")
    if channel in mc.CHANNEL_MAP:
        q = q.filter(ContentItem.channel == channel)
    campaign_id = mc.parse_int(qp.get("campaign"))
    if campaign_id:
        q = q.filter(ContentItem.campaign_id == campaign_id)

    today = mc.bkk_today()
    month = qp.get("month", "")
    try:
        y, m = (int(x) for x in month.split("-"))
        date(y, m, 1)
    except (ValueError, TypeError):
        y, m = today.year, today.month
    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(y, m)
    items = q.order_by(ContentItem.planned_at.is_(None), ContentItem.planned_at,
                       ContentItem.id.desc()).all()
    by_day = {}
    for it in items:
        if it.planned_at:
            by_day.setdefault(it.planned_at.date(), []).append(it)
    prev_m = (date(y, m, 1) - timedelta(days=1))
    next_m = (date(y, m, 28) + timedelta(days=7)).replace(day=1)
    camps = {c.id: c for c in db.query(Campaign).all()}
    return _render(request, "content.html", user, tab="content", items=items, view=view,
                   weeks=weeks, by_day=by_day, year=y, month=m, today=today,
                   prev_month=f"{prev_m.year}-{prev_m.month:02d}",
                   next_month=f"{next_m.year}-{next_m.month:02d}",
                   campaigns=camps, f={"status": status, "channel": channel,
                                       "campaign": campaign_id or ""})


@router.get("/content/new", response_class=HTMLResponse)
async def content_new(request: Request, db: Session = Depends(get_db),
                      user: User = Depends(require_admin)):
    camps = db.query(Campaign).filter(Campaign.status != "archived").order_by(Campaign.name).all()
    pre = {"campaign_id": mc.parse_int(request.query_params.get("campaign"))}
    return _render(request, "content_edit.html", user, tab="content", item=None, media=[],
                   campaigns=camps, link=None, errors=[], pre=pre)


@router.get("/content/{iid}", response_class=HTMLResponse)
async def content_edit(iid: int, request: Request, db: Session = Depends(get_db),
                       user: User = Depends(require_admin)):
    item = db.get(ContentItem, iid) or _404()
    camps = db.query(Campaign).filter(
        (Campaign.status != "archived") | (Campaign.id == item.campaign_id)).order_by(Campaign.name).all()
    link = db.get(TrackingLink, item.tracking_link_id) if item.tracking_link_id else None
    leads = db.query(Lead).filter(Lead.content_item_id == iid, Lead.status != "anonymous").count()
    history = (db.query(AuditLog).filter_by(entity="content", entity_id=iid)
               .order_by(AuditLog.created_at.desc()).limit(20).all())
    return _render(request, "content_edit.html", user, tab="content", item=item,
                   media=_media(item), campaigns=camps, link=link, errors=[], pre={},
                   lead_count=leads, history=history,
                   error=request.query_params.get("error", ""))


async def _save_upload(upload) -> tuple:
    """เก็บไฟล์สื่อด้วยชื่อสุ่ม → (meta, error) · รูปแบบเดียวกับ /admin/files เดิม"""
    name = Path(upload.filename or "").name
    ext = Path(name).suffix.lower()
    if ext not in MEDIA_EXT:
        return None, f"{name}: ชนิดไฟล์ไม่รองรับ ({', '.join(sorted(MEDIA_EXT))})"
    stored = f"{uuid.uuid4().hex}{ext}"
    path = MEDIA_DIR / stored
    size = 0
    with path.open("wb") as buf:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_MEDIA_SIZE:
                buf.close()
                path.unlink(missing_ok=True)
                return None, f"{name}: ใหญ่เกิน 50 MB — คลิปยาวให้ใส่เป็นลิงก์ในหมายเหตุ"
            buf.write(chunk)
    if size == 0:
        path.unlink(missing_ok=True)
        return None, ""
    return {"stored": stored, "name": name[:150], "size": size}, ""


@router.post("/content/save")
async def content_save(request: Request, db: Session = Depends(get_db),
                       user: User = Depends(require_admin)):
    form = await request.form()
    iid = mc.parse_int(form.get("id"))
    item = db.get(ContentItem, iid) if iid else None
    if iid and not item:
        _404()
    title = _s(form, "title")
    errors = []
    if not title:
        errors.append("กรุณาใส่หัวข้อ")
    channel = _s(form, "channel", 32)
    if channel and channel not in [c["key"] for c in mc.CHANNELS]:
        channel = ""
    campaign_id = mc.parse_int(form.get("campaign_id"))
    camp = db.get(Campaign, campaign_id) if campaign_id else None
    status = _s(form, "status", 16)
    if status not in mc.CONTENT_STATUS_LABELS:
        status = "draft"
    if status == "published" and not (item and item.status == "published"):
        errors.append("การเปลี่ยนเป็น 'เผยแพร่แล้ว' ต้องใส่ลิงก์โพสต์จริงในช่องบันทึกการเผยแพร่")
        status = item.status if item else "draft"
    destination = _s(form, "destination", 512)
    dest_ok = True
    if destination:
        _, derr = mc.normalize_destination(destination, settings.APP_URL)
        if derr:
            errors.append("หน้าปลายทาง: " + derr)
            dest_ok = False
    if not title:
        camps = db.query(Campaign).filter(Campaign.status != "archived").all()
        return _render(request, "content_edit.html", user, tab="content", item=item,
                       media=_media(item) if item else [], campaigns=camps, link=None,
                       errors=errors, pre=dict(form))

    is_new = item is None
    if is_new:
        item = ContentItem(media="[]")
        db.add(item)
    old_status = item.status
    item.title, item.body = title, _s(form, "body", 20000)
    item.channel, item.campaign_id = channel, camp.id if camp else None
    if dest_ok:
        item.destination = destination  # ผิดรูปแบบ = คงค่าเดิมไว้ + แจ้งเตือน
    item.planned_at = _parse_dt_local(_s(form, "planned_at", 20))
    item.owner = _s(form, "owner", 100)
    item.notes = _s(form, "notes", 4000)
    item.status = status
    db.flush()

    media = _media(item)
    for up in form.getlist("files"):
        if not getattr(up, "filename", ""):
            continue
        meta, err = await _save_upload(up)
        if meta:
            media.append(meta)
        elif err:
            errors.append(err)
    item.media = json.dumps(media, ensure_ascii=False)

    # ลิงก์ติดตามของโพสต์นี้ — สร้างใหม่เมื่อแคมเปญ/ช่องทาง/ปลายทางเปลี่ยน ของเดิมคงไว้
    if camp and channel:
        link, lerr = ensure_link(db, camp, channel, item.destination or camp.landing_url,
                                 content=mc.content_utm(item.id, item.title),
                                 label=f"เนื้อหา: {item.title}", content_item_id=item.id)
        if link:
            item.tracking_link_id = link.id
        elif lerr:
            errors.append("ลิงก์ติดตาม: " + lerr)
    if old_status != item.status or is_new:
        _audit(db, user, "content_status", "content", item.id,
               {"from": None if is_new else old_status, "to": item.status})
    db.commit()
    return _back(f"/admin/marketing/content/{item.id}", saved=1,
                 error="; ".join(errors) if errors else "")


@router.post("/content/{iid}/publish")
async def content_publish(iid: int, request: Request, db: Session = Depends(get_db),
                          user: User = Depends(require_admin)):
    """บันทึกว่าผู้ใช้ลงโพสต์เองแล้ว — ระบบไม่ได้โพสต์แทน"""
    item = db.get(ContentItem, iid) or _404()
    form = await request.form()
    url = _safe_url(_s(form, "published_url", 512))
    when = _parse_dt_local(_s(form, "published_at", 20))
    if not url:
        return _back(f"/admin/marketing/content/{iid}", error="ลิงก์โพสต์จริงต้องขึ้นต้นด้วย https://")
    if not when:
        return _back(f"/admin/marketing/content/{iid}", error="ระบุวันเวลาที่เผยแพร่จริง")
    old = item.status
    item.published_url, item.published_at, item.status = url, when, "published"
    _audit(db, user, "content_published", "content", iid,
           {"from": old, "url": url, "at": when.isoformat()})
    db.commit()
    return _back(f"/admin/marketing/content/{iid}", saved=1)


@router.post("/content/{iid}/media/remove")
async def content_media_remove(iid: int, request: Request, db: Session = Depends(get_db),
                               user: User = Depends(require_admin)):
    item = db.get(ContentItem, iid) or _404()
    form = await request.form()
    stored = _s(form, "stored", 64)
    media = _media(item)
    keep = [m for m in media if m.get("stored") != stored]
    if len(keep) != len(media) and _STORED_RE.match(stored):
        (MEDIA_DIR / stored).unlink(missing_ok=True)
        item.media = json.dumps(keep, ensure_ascii=False)
        _audit(db, user, "content_media_remove", "content", iid, {"file": stored})
        db.commit()
    return _back(f"/admin/marketing/content/{iid}")


@router.get("/media/{stored}")
async def media_file(stored: str, download: int = 0):
    if not _STORED_RE.match(stored):
        _404()
    path = MEDIA_DIR / stored
    if not path.is_file():
        _404()
    mime = mimetypes.guess_type(stored)[0] or "application/octet-stream"
    if download:
        return FileResponse(path, media_type=mime, filename=stored)
    return FileResponse(path, media_type=mime)


# ============ ผู้ช่วย AI ร่างข้อความ ============

AI_DRAFT_RULES = ((6, 60), (60, 86400))  # ต่อบัญชี — กันกดรัวเผาโควตา Groq ที่แชร์กันทั้งระบบ


@router.post("/ai/draft")
async def ai_draft(request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_admin)):
    """ร่างข้อความ — คืน JSON ให้หน้าเว็บแสดง ไม่บันทึกลงเนื้อหาเอง (คนต้องกดใส่และบันทึกเอง)"""
    import marketing_ai
    from fastapi.responses import JSONResponse
    if rate_limited("ai_draft", f"user:{user.id}", AI_DRAFT_RULES):
        return JSONResponse({"ok": False, "error": "ขอร่างถี่เกินไป รอสักครู่แล้วลองใหม่"}, status_code=429)
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "คำขอไม่ถูกต้อง"}, status_code=400)
    service = str(data.get("service") or "")
    channel = str(data.get("channel") or "other")
    if channel not in mc.CHANNEL_MAP:
        channel = "other"
    goal = str(data.get("goal") or "lead")
    item_id = mc.parse_int(data.get("item_id"))
    result = await marketing_ai.draft(service, channel, goal,
                                      audience=str(data.get("audience") or ""),
                                      notes=str(data.get("notes") or ""))
    # บันทึกว่ามีการใช้ AI (ไม่เก็บข้อความ — ข้อความจริงอยู่ในเนื้อหาถ้าคนกดใช้)
    _audit(db, user, "ai_draft", "content", item_id,
           {"service": service, "channel": channel, "goal": goal, "ok": result.get("ok"),
            "warnings": len(result.get("warnings") or []), "error": result.get("error", "")})
    db.commit()
    return JSONResponse(result, status_code=200 if result.get("ok") else 400)


# ============ หน้า: กลุ่ม Facebook ============

FB_HOSTS = ("facebook.com", "fb.com")


def _group_summary(db: Session, groups: list) -> dict:
    out = {}
    today = mc.bkk_today()
    for g in groups:
        posts = db.query(FbGroupPost).filter_by(group_id=g.id).all()
        posted = [p.posted_at for p in posts if p.posted_at and p.status in ("published", "awaiting_approval")]
        last = max(posted) if posted else None
        planned = [p.next_post_date for p in posts if p.next_post_date and p.next_post_date >= today] + \
                  [p.planned_date for p in posts if p.status == "queued" and p.planned_date]
        nxt = min(planned) if planned else None
        wait = None
        if last and g.min_days_between:
            wait = (last + timedelta(days=g.min_days_between) - today).days
        out[g.id] = {"last": last, "next": nxt, "count": len(posts),
                     "published": sum(1 for p in posts if p.status == "published"),
                     "rejected": sum(1 for p in posts if p.status == "rejected"),
                     "wait_days": wait if wait and wait > 0 else 0}
    return out


@router.get("/groups", response_class=HTMLResponse)
async def groups_list(request: Request, show: str = "", db: Session = Depends(get_db),
                      user: User = Depends(require_admin)):
    q = db.query(FbGroup)
    if show != "all":
        q = q.filter(FbGroup.is_active.is_(True))
    groups = q.order_by(FbGroup.name).all()
    return _render(request, "groups.html", user, tab="groups", groups=groups,
                   summary=_group_summary(db, groups), show=show)


@router.get("/groups/new", response_class=HTMLResponse)
async def group_new(request: Request, user: User = Depends(require_admin)):
    return _render(request, "group_edit.html", user, tab="groups", g=None, errors=[], form={})


@router.get("/groups/{gid}/edit", response_class=HTMLResponse)
async def group_edit(gid: int, request: Request, db: Session = Depends(get_db),
                     user: User = Depends(require_admin)):
    g = db.get(FbGroup, gid) or _404()
    return _render(request, "group_edit.html", user, tab="groups", g=g, errors=[], form={})


@router.post("/groups/save")
async def group_save(request: Request, db: Session = Depends(get_db),
                     user: User = Depends(require_admin)):
    form = await request.form()
    gid = mc.parse_int(form.get("id"))
    g = db.get(FbGroup, gid) if gid else None
    if gid and not g:
        _404()
    errors = []
    name = _s(form, "name")
    if not name:
        errors.append("กรุณาใส่ชื่อกลุ่ม")
    raw_url = _s(form, "url", 512)
    url = _safe_url(raw_url, FB_HOSTS)
    if raw_url and not url:
        errors.append("ลิงก์กลุ่มต้องเป็น https://www.facebook.com/groups/...")
    min_days_raw = _s(form, "min_days_between", 5)
    min_days = mc.parse_int(min_days_raw)
    if min_days_raw and min_days is None:
        errors.append("ระยะห่างขั้นต่ำต้องเป็นจำนวนวัน")
    if errors:
        return _render(request, "group_edit.html", user, tab="groups", g=g, errors=errors,
                       form=dict(form))
    if not g:
        g = FbGroup()
        db.add(g)
    g.name, g.url = name, url
    g.audience = _s(form, "audience", 2000)
    rel = _s(form, "relevance", 16)
    g.relevance = rel if rel in mc.RELEVANCE_LABELS else ""
    g.rules = _s(form, "rules", 4000)
    g.allowed_frequency = _s(form, "allowed_frequency", 200)
    g.min_days_between = min_days
    g.notes = _s(form, "notes", 4000)
    g.is_active = form.get("is_active") == "on" if gid else True
    db.commit()
    return _back(f"/admin/marketing/groups/{g.id}", saved=1)


@router.get("/groups/{gid}", response_class=HTMLResponse)
async def group_detail(gid: int, request: Request, db: Session = Depends(get_db),
                       user: User = Depends(require_admin)):
    g = db.get(FbGroup, gid) or _404()
    posts = db.query(FbGroupPost).filter_by(group_id=gid).order_by(FbGroupPost.id.desc()).all()
    links = {l.id: l for l in db.query(TrackingLink).filter(
        TrackingLink.id.in_({p.tracking_link_id for p in posts if p.tracking_link_id} or {0})).all()}
    items = db.query(ContentItem).filter(ContentItem.status != "published").order_by(
        ContentItem.id.desc()).limit(100).all()
    all_items = {i.id: i for i in db.query(ContentItem).filter(
        ContentItem.id.in_({p.content_item_id for p in posts if p.content_item_id} or {0})).all()}
    camps = db.query(Campaign).filter(Campaign.status != "archived").order_by(Campaign.name).all()
    lead_counts = dict(db.query(Lead.group_post_id, func.count(Lead.id))
                       .filter(Lead.group_post_id.isnot(None), Lead.duplicate_of.is_(None),
                               Lead.qualification != "spam", Lead.status != "anonymous")
                       .group_by(Lead.group_post_id).all())
    return _render(request, "group_detail.html", user, tab="groups", g=g, posts=posts,
                   links=links, items=items, all_items=all_items, campaigns=camps,
                   summary=_group_summary(db, [g])[g.id], lead_counts=lead_counts,
                   error=request.query_params.get("error", ""))


@router.post("/groups/{gid}/posts")
async def group_post_create(gid: int, request: Request, db: Session = Depends(get_db),
                            user: User = Depends(require_admin)):
    g = db.get(FbGroup, gid) or _404()
    form = await request.form()
    ci = mc.parse_int(form.get("content_item_id"))
    item = db.get(ContentItem, ci) if ci else None
    cid = mc.parse_int(form.get("campaign_id")) or (item.campaign_id if item else None)
    camp = db.get(Campaign, cid) if cid else None
    message = _s(form, "message", 20000) or (item.body if item else "")
    if not message and not item:
        return _back(f"/admin/marketing/groups/{gid}", error="ใส่ข้อความ หรือเลือกเนื้อหาจากคลัง")
    p = FbGroupPost(group_id=g.id, content_item_id=item.id if item else None,
                    campaign_id=camp.id if camp else None, message=message,
                    status="queued", planned_date=mc.parse_date(_s(form, "planned_date", 20)),
                    note=_s(form, "note", 2000))
    db.add(p)
    db.flush()
    err = ""
    if camp:
        dest = _s(form, "destination", 512) or (item.destination if item else "") or camp.landing_url
        link, err = ensure_link(db, camp, "facebook_group", dest, content=mc.group_post_utm(p.id),
                                label=f"กลุ่ม: {g.name}", group_post_id=p.id,
                                content_item_id=item.id if item else None)
        if link:
            p.tracking_link_id = link.id
    else:
        err = "ยังไม่ได้เลือกแคมเปญ — โพสต์นี้จะไม่มีลิงก์ติดตาม"
    _audit(db, user, "group_post_create", "group", g.id, {"post": p.id})
    db.commit()
    return _back(f"/admin/marketing/groups/{gid}", saved=1, error=err)


@router.post("/groups/posts/{pid}/update")
async def group_post_update(pid: int, request: Request, db: Session = Depends(get_db),
                            user: User = Depends(require_admin)):
    p = db.get(FbGroupPost, pid) or _404()
    form = await request.form()
    status = _s(form, "status", 24)
    if status not in mc.GROUP_POST_STATUS_LABELS:
        status = p.status
    raw_url = _s(form, "post_url", 512)
    url = _safe_url(raw_url, FB_HOSTS)
    if raw_url and not url:
        return _back(f"/admin/marketing/groups/{p.group_id}",
                     error="ลิงก์โพสต์จริงต้องเป็นลิงก์ facebook.com แบบ https://")
    posted = mc.parse_date(_s(form, "posted_at", 20))
    if status in ("published", "awaiting_approval") and not posted:
        posted = mc.bkk_today()
    old = p.status
    p.status, p.post_url = status, url or p.post_url
    p.posted_at = posted or p.posted_at
    p.next_post_date = mc.parse_date(_s(form, "next_post_date", 20))
    p.note = _s(form, "note", 2000)
    if old != status:
        _audit(db, user, "group_post_status", "group", p.group_id,
               {"post": p.id, "from": old, "to": status, "url": p.post_url})
    db.commit()
    return _back(f"/admin/marketing/groups/{p.group_id}", saved=1)


# ============ หน้า: รายงาน + ค่าโฆษณา ============

@router.get("/reports", response_class=HTMLResponse)
async def reports(request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_admin)):
    return _render(request, "reports.html", user, tab="reports", **_report_ctx(request, db))


def _fmt(v) -> str:
    return "" if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v))


@router.get("/reports/export.csv")
async def reports_export(request: Request, kind: str = "channel", db: Session = Depends(get_db),
                         user: User = Depends(require_admin)):
    ctx = _report_ctx(request, db)
    r = ctx["r"]
    common = ["lead_unique", "lead_fit", "cost_per_fit_lead", "quoted", "won", "won_value"]
    if kind == "campaign":
        header = ["campaign", "utm_campaign", "service", "budget", "spend"] + common
        rows = [[x["label"], x["code"], mc.SERVICE_MAP.get(x["service"], {}).get("label", ""),
                 _fmt(x["budget"]), _fmt(x["spend"]), x["unique"], x["fit"], _fmt(x["cpl_fit"]),
                 x["quoted"], x["won"], _fmt(x["won_value"])] for x in r["by_campaign"]]
    elif kind == "content":
        header = ["type", "id", "label", "channel", "lead_unique", "lead_fit", "quoted", "won"]
        rows = [[x["kind"], x["id"], x["label"], mc.channel_label(x["channel"]), x["unique"],
                 x["fit"], x["quoted"], x["won"]] for x in r["by_content"]]
    elif kind == "leads":
        leads = _lead_scope(db, r["start"], r["end"], r["channel"]).order_by(Lead.created_at).all()
        header = ["id", "created_at_bkk", "name", "company", "phone", "email", "channel",
                  "utm_source", "utm_medium", "utm_campaign", "utm_content", "landing_page",
                  "request_type", "service_interest", "sales_stage", "qualification",
                  "duplicate_of", "quote_value", "won_value", "next_follow_up"]
        rows = [[l.id, mc.utc_to_bkk(l.created_at).strftime("%Y-%m-%d %H:%M"), l.name, l.company,
                 l.phone, l.email, mc.channel_label(l.channel), l.utm_source, l.utm_medium,
                 l.utm_campaign, l.utm_content, l.landing_page,
                 mc.REQUEST_TYPE_LABELS.get(l.request_type, ""),
                 mc.SERVICE_MAP.get(l.service_interest, {}).get("label", ""),
                 mc.SALES_STAGE_LABELS.get(l.sales_stage, l.sales_stage),
                 mc.QUALIFICATION_LABELS.get(l.qualification, l.qualification),
                 l.duplicate_of or "", _fmt(l.quote_value), _fmt(l.won_value),
                 l.next_follow_up or ""] for l in leads]
    else:
        kind = "channel"
        header = ["channel", "connection", "spend_source", "spend"] + common
        rows = [[x["label"], x["connection"], "/".join(x["spend_sources"]), _fmt(x["spend"]),
                 x["unique"], x["fit"], _fmt(x["cpl_fit"]), x["quoted"], x["won"],
                 _fmt(x["won_value"])] for x in r["by_channel"]]
    name = f"voscene-{kind}-{r['start']}_{r['end']}.csv"
    _audit(db, user, "report_export", "report", None, {"kind": kind, "start": r["start"],
                                                        "end": r["end"], "rows": len(rows)})
    db.commit()
    return Response(mc.to_csv(header, rows), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/spend", response_class=HTMLResponse)
async def spend_page(request: Request, db: Session = Depends(get_db),
                     user: User = Depends(require_admin)):
    rows = db.query(AdSpend).order_by(AdSpend.date.desc(), AdSpend.id.desc()).limit(200).all()
    batches = db.query(ImportBatch).order_by(ImportBatch.id.desc()).limit(10).all()
    camps = db.query(Campaign).filter(Campaign.status != "archived").order_by(Campaign.name).all()
    all_camps = {c.id: c for c in db.query(Campaign).all()}
    return _render(request, "spend.html", user, tab="reports", rows=rows, batches=batches,
                   campaigns=camps, all_campaigns=all_camps, today=mc.bkk_today(),
                   error=request.query_params.get("error", ""))


@router.post("/spend/add")
async def spend_add(request: Request, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    form = await request.form()
    d = mc.parse_date(_s(form, "date", 20))
    channel = _s(form, "channel", 32)
    spend = mc.parse_money(_s(form, "spend", 30))
    cid = mc.parse_int(form.get("campaign_id"))
    camp = db.get(Campaign, cid) if cid else None
    if not d or channel not in mc.SPEND_CHANNELS or spend is None:
        return _back("/admin/marketing/spend", error="กรอกวันที่ ช่องทาง และค่าโฆษณา (ตัวเลข ≥ 0) ให้ครบ")
    if d > mc.bkk_today():
        return _back("/admin/marketing/spend", error="บันทึกค่าโฆษณาล่วงหน้าไม่ได้")
    key = mc.spend_dedupe_key(d, channel, camp.code if camp else "")
    if db.query(AdSpend).filter_by(dedupe_key=key).first():
        return _back("/admin/marketing/spend",
                     error="มีค่าโฆษณาของวัน/ช่องทาง/แคมเปญนี้แล้ว — ลบรายการเดิมก่อนถ้าต้องการแก้")
    row = AdSpend(date=d, channel=channel, campaign_id=camp.id if camp else None,
                  campaign_label=camp.code if camp else "", spend=spend,
                  impressions=mc.parse_int(form.get("impressions")),
                  clicks=mc.parse_int(form.get("clicks")), source="manual", dedupe_key=key,
                  note=_s(form, "note", 500), created_by=user.username)
    db.add(row)
    db.flush()
    _audit(db, user, "spend_add", "spend", row.id,
           {"date": d, "channel": channel, "campaign": row.campaign_label, "spend": spend})
    db.commit()
    return _back("/admin/marketing/spend", saved=1)


@router.post("/spend/{sid}/delete")
async def spend_delete(sid: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    row = db.get(AdSpend, sid) or _404()
    _audit(db, user, "spend_delete", "spend", sid,
           {"date": row.date, "channel": row.channel, "campaign": row.campaign_label,
            "spend": row.spend, "source": row.source})
    db.delete(row)
    db.commit()
    return _back("/admin/marketing/spend", saved=1)


@router.get("/spend/sample.csv")
async def spend_sample():
    return Response("﻿" + mc.sample_spend_csv(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="voscene-ad-spend-sample.csv"'})


MAX_CSV_SIZE = 2 * 1024 * 1024


@router.post("/spend/import")
async def spend_import(request: Request, db: Session = Depends(get_db),
                       user: User = Depends(require_admin)):
    form = await request.form()
    up = form.get("file")
    if not getattr(up, "filename", ""):
        return _back("/admin/marketing/spend", error="เลือกไฟล์ CSV")
    raw = await up.read(MAX_CSV_SIZE + 1)
    if len(raw) > MAX_CSV_SIZE:
        return _back("/admin/marketing/spend", error="ไฟล์ใหญ่เกิน 2 MB")
    digest = hashlib.sha256(raw).hexdigest()
    if db.query(ImportBatch).filter_by(file_hash=digest, status="imported").first():
        return _back("/admin/marketing/spend", error="ไฟล์นี้เคยนำเข้าแล้ว (เนื้อหาไฟล์ตรงกันทุกไบต์)")
    try:
        text_data = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return _back("/admin/marketing/spend", error="อ่านไฟล์ไม่ได้ — บันทึกเป็น CSV UTF-8")
    codes = {c.code: c.id for c in db.query(Campaign).all()}
    rows = mc.parse_spend_csv(text_data, codes)
    existing = {k for (k,) in db.query(AdSpend.dedupe_key).filter(
        AdSpend.dedupe_key.in_([r.get("key") for r in rows if r.get("key")] or [""])).all()}
    for r in rows:
        r["exists"] = bool(r.get("key") and r["key"] in existing)
    batch = ImportBatch(filename=Path(up.filename).name[:255], file_hash=digest,
                        rows_json=json.dumps(rows, ensure_ascii=False), total_rows=len(rows),
                        created_by=user.username)
    db.add(batch)
    db.commit()
    return _back(f"/admin/marketing/spend/import/{batch.id}")


@router.get("/spend/import/{bid}", response_class=HTMLResponse)
async def spend_import_preview(bid: int, request: Request, db: Session = Depends(get_db),
                               user: User = Depends(require_admin)):
    batch = db.get(ImportBatch, bid) or _404()
    rows = json.loads(batch.rows_json or "[]")
    camps = {c.id: c for c in db.query(Campaign).all()}
    return _render(request, "spend_import.html", user, tab="reports", batch=batch, rows=rows,
                   campaigns=camps,
                   ok_count=sum(1 for r in rows if r.get("ok") and not r.get("exists")),
                   bad_count=sum(1 for r in rows if not r.get("ok")),
                   dup_count=sum(1 for r in rows if r.get("ok") and r.get("exists")))


@router.post("/spend/import/{bid}/confirm")
async def spend_import_confirm(bid: int, db: Session = Depends(get_db),
                               user: User = Depends(require_admin)):
    batch = db.get(ImportBatch, bid) or _404()
    if batch.status != "preview":
        return _back(f"/admin/marketing/spend/import/{bid}")
    if db.query(ImportBatch).filter(ImportBatch.file_hash == batch.file_hash,
                                    ImportBatch.status == "imported").first():
        batch.status = "cancelled"
        db.commit()
        return _back("/admin/marketing/spend", error="ไฟล์นี้เคยนำเข้าแล้ว")
    rows = json.loads(batch.rows_json or "[]")
    imported = skipped = 0
    for r in rows:
        if not r.get("ok"):
            skipped += 1
            continue
        if db.query(AdSpend).filter_by(dedupe_key=r["key"]).first():
            skipped += 1
            continue
        db.add(AdSpend(date=mc.parse_date(r["date"]), channel=r["channel"],
                       campaign_id=r.get("campaign_id"), campaign_label=r.get("campaign_label", ""),
                       spend=r["spend"], impressions=r.get("impressions"), clicks=r.get("clicks"),
                       source="csv", batch_id=batch.id, dedupe_key=r["key"],
                       created_by=user.username))
        imported += 1
    batch.status, batch.imported_rows, batch.skipped_rows = "imported", imported, skipped
    batch.imported_at = datetime.utcnow()
    _audit(db, user, "spend_import", "spend", batch.id,
           {"file": batch.filename, "imported": imported, "skipped": skipped})
    db.commit()
    return _back("/admin/marketing/spend", saved=1)


@router.post("/spend/import/{bid}/cancel")
async def spend_import_cancel(bid: int, db: Session = Depends(get_db),
                              user: User = Depends(require_admin)):
    batch = db.get(ImportBatch, bid) or _404()
    if batch.status == "preview":
        batch.status = "cancelled"
        db.commit()
    return _back("/admin/marketing/spend")

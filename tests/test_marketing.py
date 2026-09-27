"""ทดสอบระบบการตลาดรุ่นแรก — รันจากโฟลเดอร์โปรเจกต์: python -m pytest tests -q

ใช้ฐานข้อมูล SQLite ชั่วคราวแยกต่างหาก ไม่แตะ data.db จริง
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # templates/ และ static/ อ้างแบบ relative

_TMP = Path(tempfile.mkdtemp(prefix="voscene-test-"))
os.environ.update({
    "DATABASE_URL": f"sqlite:///{(_TMP / 'app.db').as_posix()}",
    "ADMIN_USERNAME": "admin",
    "ADMIN_PASSWORD": "test-password-123",
    "SECRET_KEY": "test-secret-key-for-pytest-only-0123456789",
    "DEBUG": "True",
    "AI_CONSULT_ENABLED": "False",
    "APP_URL": "https://www.voscene.com",
})

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, inspect  # noqa: E402

import main  # noqa: E402
import marketing_core as mc  # noqa: E402
import security  # noqa: E402
from database import (  # noqa: E402
    AdSpend, AuditLog, Base, Campaign, ContentItem, FbGroupPost, Lead, SessionLocal,
    TrackingLink, WebEvent,
)
from migrations import run_migrations  # noqa: E402

main.marketing.bind(main.templates, _TMP)  # ไฟล์สื่อที่ทดสอบอัปโหลดไปลงโฟลเดอร์ชั่วคราว
# เทสเดิมใช้ /api/lead จำลองลูกค้าส่งฟอร์ม (ทดสอบตรรกะแหล่งที่มา/ซ้ำ/สแปม) — เปิดสวิตช์ไว้
# ส่วนพฤติกรรมจริงตอนปิด (ค่าเริ่มต้น) ทดสอบใน test_web_forms_closed_by_default
main.settings.WEB_FORMS_ENABLED = True


def new_client() -> TestClient:
    """เหมือนเบราว์เซอร์จริง: ฟอร์มในหลังบ้านส่ง Origin ของเว็บตัวเองมาด้วยเสมอ"""
    return TestClient(main.app, headers={"Origin": "http://testserver"})


@pytest.fixture(scope="module")
def client():
    with new_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_limits():
    security._HITS.clear()
    security._LOGIN_FAILS.clear()
    security._LOCKED_UNTIL.clear()
    yield


@pytest.fixture(scope="module")
def admin(client):
    r = client.post("/admin/login", data={"username": "admin", "password": "test-password-123"},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/admin"
    return client


def db():
    return SessionLocal()


def submit_lead(client, **fields):
    data = {"name": "ทดสอบ", "requirement": "ห้องประชุม 3 ห้อง ต้องการคุมจากจอเดียว",
            "phone": "", "email": "", "fax_number": "", "form_ms": "15000"}
    data.update(fields)
    r = client.post("/api/lead", data=data)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    s = db()
    lead = s.query(Lead).order_by(Lead.id.desc()).first()
    s.close()
    return lead


# ================= migration =================

OLD_SCHEMA = """
CREATE TABLE leads (id INTEGER PRIMARY KEY, name VARCHAR(128) NOT NULL, company VARCHAR(128),
  phone VARCHAR(64), email VARCHAR(128), room_size VARCHAR(64), budget VARCHAR(64),
  requirement TEXT NOT NULL, ai_analysis TEXT, ai_in_scope BOOLEAN, ai_confidence FLOAT,
  ai_recommended_package VARCHAR(64), status VARCHAR(32), notes TEXT, created_at DATETIME);
CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(64) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL, created_at DATETIME);
"""


def test_migration_keeps_legacy_data_and_is_idempotent():
    path = _TMP / "legacy.db"
    con = sqlite3.connect(path)
    con.executescript(OLD_SCHEMA)
    rows = [
        (1, "เก่า1", "081-111-2222", "a@x.com", "new_in_scope", "โน้ตเดิม", "2026-08-01 10:00:00"),
        (2, "เก่า2", "+66 81 111 2222", "", "contacted", "", "2026-08-02 10:00:00"),
        (3, "บอท", "", "", "spam", "", "2026-08-03 10:00:00"),
        (4, "(ยังไม่ระบุชื่อ)", "", "", "anonymous", "", "2026-08-04 10:00:00"),
        (5, "ลูกค้าจริง", "", "A@X.COM", "won", "", "2026-08-05 10:00:00"),
        (6, "แปลก", "", "", "custom_status", "", "2026-08-06 10:00:00"),
    ]
    for r in rows:
        con.execute("INSERT INTO leads (id,name,phone,email,status,notes,created_at,requirement,"
                    "ai_in_scope,ai_confidence) VALUES (?,?,?,?,?,?,?,'x',1,0.9)", r)
    con.execute("INSERT INTO users (id, username, password_hash) VALUES (1, 'admin', 'x')")
    con.commit()
    con.close()

    engine = create_engine(f"sqlite:///{path.as_posix()}")
    first = run_migrations(engine, Base)
    assert first and first[0].startswith("001_marketing")
    assert list(_TMP.glob("legacy.db.pre-001_marketing-*.bak")), "ต้องสำรองไฟล์ก่อนย้าย"

    cols = {c["name"] for c in inspect(engine).get_columns("leads")}
    assert {"sales_stage", "qualification", "utm_campaign", "duplicate_of", "won_value"} <= cols
    assert "mk_campaigns" in inspect(engine).get_table_names()

    con = sqlite3.connect(path)
    got = {r[0]: r[1:] for r in con.execute(
        "SELECT id, name, status, notes, sales_stage, qualification, duplicate_of, phone_norm "
        "FROM leads ORDER BY id")}
    con.close()
    # ข้อมูลเดิมไม่ถูกแตะ
    assert got[1][:3] == ("เก่า1", "new_in_scope", "โน้ตเดิม")
    # แปลงสถานะ — ผลของ AI ไม่ถูกนับเป็น "ตรงกลุ่ม"
    assert got[1][3:5] == ("new", "pending")
    assert got[2][3] == "contacted"
    assert got[3][3:5] == ("new", "spam")
    assert got[5][3] == "won"
    assert got[6][3:5] == ("new", "pending")
    # รายการซ้ำ: เบอร์เดียวกันคนละรูปแบบ / อีเมลต่างตัวพิมพ์
    assert got[2][5] == 1 and got[2][6] == "0811112222"
    assert got[5][5] == 1
    assert got[4][5] is None  # anonymous ไม่ถูกจับคู่
    con = sqlite3.connect(path)
    methods = dict(con.execute("SELECT id, contact_method FROM leads"))
    con.close()
    assert methods[1] == "web_form" and methods[4] in ("", None)  # Lead เก่า = ฟอร์มเว็บ

    con = sqlite3.connect(path)
    assert con.execute("SELECT role, is_active FROM users WHERE id=1").fetchone() == ("owner", 1),         "บัญชีเดิมต้องเป็นเจ้าของ ไม่งั้นล็อกตัวเองออกหลัง deploy"
    con.close()
    assert run_migrations(engine, Base) == []  # รันซ้ำไม่ทำอะไร


# ================= สิทธิ์ =================

PROTECTED_GET = [
    "/admin/marketing", "/admin/marketing/campaigns", "/admin/marketing/campaigns/new",
    "/admin/marketing/content", "/admin/marketing/content/new", "/admin/marketing/groups",
    "/admin/marketing/reports", "/admin/marketing/spend", "/admin/marketing/spend/sample.csv",
    "/admin/marketing/reports/export.csv?kind=leads", "/admin/marketing/media/" + "a" * 32 + ".png",
]
PROTECTED_POST = [
    "/admin/marketing/campaigns/save", "/admin/marketing/content/save", "/admin/marketing/groups/save",
    "/admin/marketing/spend/add", "/admin/marketing/spend/import", "/admin/marketing/spend/1/delete",
]


def test_marketing_requires_login():
    with new_client() as anon:
        for url in PROTECTED_GET:
            r = anon.get(url, follow_redirects=False)
            assert r.status_code == 303 and r.headers["location"] == "/admin/login", url
        for url in PROTECTED_POST:
            r = anon.post(url, data={}, follow_redirects=False)
            assert r.status_code == 303, url
        anon.cookies.set("admin_session", "forged.token.value")
        r = anon.get("/admin/marketing", follow_redirects=False)
        assert r.status_code == 303


# ================= เส้นทางตรวจรับ =================

def test_acceptance_path(admin):
    # 1) สร้างแคมเปญ
    r = admin.post("/admin/marketing/campaigns/save", data={
        "name": "เปิดห้องปุ่มเดียว ราชการ Q4", "code": "one-touch-gov-q4", "service": "one_touch",
        "audience": "ฝ่ายอาคาร", "channels": ["facebook_page", "facebook_group", "google_ads"],
        "budget": "20,000", "start_date": "2026-10-01", "end_date": "2026-12-31",
        "goal": "demo", "landing_url": "/features", "status": "active",
    }, follow_redirects=False)
    assert r.status_code == 303, r.text
    s = db()
    camp = s.query(Campaign).filter_by(code="one-touch-gov-q4").one()
    assert camp.budget == 20000 and camp.landing_url == "https://www.voscene.com/features"

    # 2) สร้างลิงก์ติดตาม (ปลายทางนอกเว็บต้องถูกปฏิเสธ)
    r = admin.post(f"/admin/marketing/campaigns/{camp.id}/links",
                   data={"channel": "google_ads", "destination": "https://evil.example.com/"},
                   follow_redirects=False)
    assert "error=" in r.headers["location"]
    r = admin.post(f"/admin/marketing/campaigns/{camp.id}/links",
                   data={"channel": "google_ads", "destination": ""}, follow_redirects=False)
    assert "link=" in r.headers["location"]
    s.expire_all()
    gl = s.query(TrackingLink).filter_by(campaign_id=camp.id, channel="google_ads").one()
    assert gl.url == ("https://www.voscene.com/features?utm_source=google&utm_medium=cpc"
                      "&utm_campaign=one-touch-gov-q4")

    # 3) เตรียมโพสต์ในคลังเนื้อหา + ไฟล์สื่อ
    r = admin.post("/admin/marketing/content/save", data={
        "title": "โพสต์ Page: เปิดห้องประชุมปุ่มเดียว", "body": "ข้อความโพสต์",
        "channel": "facebook_page", "campaign_id": str(camp.id), "status": "ready",
        "planned_at": "2026-10-05T10:00", "owner": "แอดมินเพจ",
    }, files={"files": ("pic.png", b"\x89PNG fake", "image/png")}, follow_redirects=False)
    assert r.status_code == 303
    s.expire_all()
    item = s.query(ContentItem).filter_by(campaign_id=camp.id).one()
    link = s.get(TrackingLink, item.tracking_link_id)
    assert link.utm_content.startswith(f"ci{item.id}") and link.utm_medium == "social"
    stored = main.marketing._media(item)[0]["stored"]
    assert admin.get(f"/admin/marketing/media/{stored}").status_code == 200
    # เผยแพร่: ต้องมีลิงก์ https
    r = admin.post(f"/admin/marketing/content/{item.id}/publish",
                   data={"published_url": "javascript:alert(1)", "published_at": "2026-10-05T10:05"},
                   follow_redirects=False)
    assert "error=" in r.headers["location"]
    r = admin.post(f"/admin/marketing/content/{item.id}/publish",
                   data={"published_url": "https://www.facebook.com/voscene/posts/1",
                         "published_at": "2026-10-05T10:05"}, follow_redirects=False)
    s.expire_all()
    assert s.get(ContentItem, item.id).status == "published"

    # 4) ลูกค้าเข้าเว็บผ่านลิงก์ → ส่งฟอร์ม (ค่าที่ vs-track.js แนบมา)
    lead = submit_lead(admin, name="คุณสมชาย", phone="089-000-1111", company="กรมตัวอย่าง",
                       request_type="demo", utm_source=link.utm_source, utm_medium=link.utm_medium,
                       utm_campaign=link.utm_campaign, utm_content=link.utm_content,
                       landing_page=link.url, referrer="https://m.facebook.com/")
    # 5) Lead มีแหล่งที่มา
    assert lead.channel == "facebook_page"
    assert lead.campaign_id == camp.id and lead.content_item_id == item.id
    assert lead.request_type == "demo" and lead.service_interest == "one_touch"
    assert lead.sales_stage == "new" and lead.qualification == "pending"
    page = admin.get(f"/admin/leads/{lead.id}").text
    assert "เปิดห้องปุ่มเดียว ราชการ Q4" in page and "Facebook Page" in page

    # Lead ที่ไม่มีข้อมูลแหล่งที่มา
    unknown = submit_lead(admin, name="เข้าตรง", email="direct@example.com")
    assert unknown.channel == "unknown"
    assert mc.UNKNOWN_SOURCE in admin.get(f"/admin/leads/{unknown.id}").text

    # 6) อัปเดตสถานะการขาย (ปิดงานต้องมีมูลค่า)
    r = admin.post(f"/admin/leads/{lead.id}/update", data={
        "sales_stage": "won", "qualification": "fit", "service_interest": "one_touch",
        "quote_value": "180000", "won_value": ""}, follow_redirects=False)
    assert "error=" in r.headers["location"]
    r = admin.post(f"/admin/leads/{lead.id}/update", data={
        "sales_stage": "quoted", "qualification": "fit", "service_interest": "one_touch",
        "quote_value": "180000", "won_value": "", "next_follow_up": "2026-10-10"},
        follow_redirects=False)
    assert r.headers["location"].endswith("saved=1")
    admin.post(f"/admin/leads/{lead.id}/notes", data={"text": "ส่งใบเสนอราคาแล้ว"})
    s.expire_all()
    fresh = s.get(Lead, lead.id)
    assert fresh.sales_stage == "quoted" and fresh.quote_value == 180000
    assert s.query(AuditLog).filter_by(entity="lead", entity_id=lead.id).count() >= 1

    # ค่าโฆษณาของแคมเปญนี้ (วันที่ = วันนี้ ให้อยู่ในช่วงรายงาน)
    today = mc.bkk_today().isoformat()
    r = admin.post("/admin/marketing/spend/add", data={
        "date": today, "channel": "facebook_ads", "campaign_id": str(camp.id), "spend": "1500"},
        follow_redirects=False)
    assert r.headers["location"].endswith("saved=1")
    r = admin.post("/admin/marketing/spend/add", data={
        "date": today, "channel": "facebook_ads", "campaign_id": str(camp.id), "spend": "99"},
        follow_redirects=False)
    assert "error=" in r.headers["location"], "วัน/ช่องทาง/แคมเปญเดียวกันต้องบันทึกซ้ำไม่ได้"

    # 7) รายงานสะท้อนข้อมูลถูกต้อง
    start, end = mc.bkk_today(), mc.bkk_today()
    rep = main.marketing.compute_report(s, start, end)
    assert rep["spend"] == 1500
    assert rep["stats"]["fit"] == 1
    assert rep["cpl_fit"] == 1500
    camp_row = next(x for x in rep["by_campaign"] if x["id"] == camp.id)
    assert camp_row["fit"] == 1 and camp_row["quoted"] == 1 and camp_row["spend"] == 1500
    page_row = next(x for x in rep["by_channel"] if x["key"] == "facebook_page")
    assert page_row["fit"] == 1 and page_row["spend"] is None  # Page ไม่มีค่าโฆษณา ≠ 0
    content_row = next(x for x in rep["by_content"] if x["kind"] == "content")
    assert content_row["id"] == item.id and content_row["fit"] == 1
    html = admin.get(f"/admin/marketing?start={today}&end={today}").text
    assert "฿1,500" in html
    rep_html = admin.get(f"/admin/marketing/reports?start={today}&end={today}").text
    assert "one-touch-gov-q4" in rep_html
    csv_text = admin.get(f"/admin/marketing/reports/export.csv?kind=campaign&start={today}&end={today}").text
    assert "one-touch-gov-q4" in csv_text and csv_text.startswith("﻿")
    s.close()


def test_facebook_group_post_attribution(admin):
    s = db()
    camp = s.query(Campaign).filter_by(code="one-touch-gov-q4").one()
    r = admin.post("/admin/marketing/groups/save", data={
        "name": "ช่าง AV ประเทศไทย", "url": "https://www.facebook.com/groups/avthai",
        "relevance": "high", "min_days_between": "7", "rules": "ลงได้วันศุกร์"},
        follow_redirects=False)
    gid = int(r.headers["location"].split("/")[-1].split("?")[0])
    r = admin.post("/admin/marketing/groups/save", data={"name": "x", "url": "https://evil.com/g"},
                   follow_redirects=False)
    assert r.status_code == 200 and "facebook.com" in r.text  # ฟอร์มแจ้งผิด ไม่บันทึก
    admin.post(f"/admin/marketing/groups/{gid}/posts",
               data={"campaign_id": str(camp.id), "message": "สวัสดีช่างทุกท่าน"})
    post = s.query(FbGroupPost).filter_by(group_id=gid).one()
    link = s.get(TrackingLink, post.tracking_link_id)
    assert link.utm_medium == "group" and link.utm_content == f"fg{post.id}"
    admin.post(f"/admin/marketing/groups/posts/{post.id}/update", data={
        "status": "published", "post_url": "https://www.facebook.com/groups/avthai/posts/9",
        "posted_at": mc.bkk_today().isoformat(), "next_post_date": ""})
    s.expire_all()
    assert s.get(FbGroupPost, post.id).status == "published"
    page = admin.get(f"/admin/marketing/groups/{gid}").text
    assert "ได้อีกใน 7 วัน" in page  # เตือนตามกติกาความถี่

    lead = submit_lead(admin, name="ช่างเอ", phone="0822223333", utm_source="facebook",
                       utm_medium="group", utm_campaign=camp.code, utm_content=link.utm_content)
    assert lead.channel == "facebook_group" and lead.group_post_id == post.id
    s.close()


def test_duplicate_and_spam_are_flagged_not_deleted(admin):
    a = submit_lead(admin, name="ซ้ำ A", phone="0955556666")
    b = submit_lead(admin, name="ซ้ำ B", phone="095-555-6666")
    assert b.duplicate_of == a.id and a.duplicate_of is None
    bot = submit_lead(admin, name="bot", fax_number="12345")
    assert bot.qualification == "spam" and bot.spam_reason == "honeypot"
    fast = submit_lead(admin, name="เร็ว", form_ms="300")
    assert fast.qualification == "spam" and fast.spam_reason == "too_fast"
    s = db()
    assert s.get(Lead, bot.id) is not None  # ยังอยู่ ไม่ถูกลบ
    s.close()
    r = admin.post(f"/admin/leads/{b.id}/not-duplicate", follow_redirects=False)
    assert r.status_code == 303
    s = db()
    assert s.get(Lead, b.id).duplicate_of is None
    s.close()
    # รายการเริ่มต้นซ่อนรายการซ้ำ แต่ดูได้
    assert "ซ้ำ B" in admin.get("/admin/leads?dup=all").text


def test_csv_import_preview_and_duplicate_protection(admin):
    today = mc.bkk_today().isoformat()
    csv1 = ("date,channel,campaign,spend,impressions,clicks,currency\n"
            f"{today},google_ads,one-touch-gov-q4,1000,500,20,THB\n"
            f"{today},tiktok,,300,,,THB\n"
            f"{today},myspace,,10,,,THB\n"
            f"bad-date,google_ads,,10,,,THB\n").encode("utf-8")
    r = admin.post("/admin/marketing/spend/import", files={"file": ("a.csv", csv1, "text/csv")},
                   follow_redirects=False)
    preview = r.headers["location"]
    bid = int(preview.rsplit("/", 1)[1])
    s = db()
    before = s.query(AdSpend).count()
    page = admin.get(preview).text
    assert "myspace" in page and "ไม่รู้จัก" in page and "วันที่ไม่ถูกต้อง" in page
    assert s.query(AdSpend).count() == before, "ตรวจตัวอย่างต้องยังไม่บันทึก"
    admin.post(f"/admin/marketing/spend/import/{bid}/confirm")
    s.expire_all()
    assert s.query(AdSpend).count() == before + 2
    g = s.query(AdSpend).filter_by(channel="google_ads").one()
    assert g.source == "csv" and g.campaign_id is not None

    # ไฟล์เดิมซ้ำ → ปฏิเสธตั้งแต่อัปโหลด
    r = admin.post("/admin/marketing/spend/import", files={"file": ("a-copy.csv", csv1, "text/csv")},
                   follow_redirects=False)
    assert "error=" in r.headers["location"]
    # ไฟล์ใหม่ที่มีแถวซ้ำ → แถวนั้นถูกข้าม
    csv2 = ("date,channel,campaign,spend\n"
            f"{today},google_ads,one-touch-gov-q4,1000\n"
            f"{today},line_oa,,50\n").encode("utf-8")
    r = admin.post("/admin/marketing/spend/import", files={"file": ("b.csv", csv2, "text/csv")},
                   follow_redirects=False)
    bid2 = int(r.headers["location"].rsplit("/", 1)[1])
    assert "มีอยู่แล้ว" in admin.get(r.headers["location"]).text
    admin.post(f"/admin/marketing/spend/import/{bid2}/confirm")
    s.expire_all()
    assert s.query(AdSpend).count() == before + 3
    s.close()
    assert admin.get("/admin/marketing/spend/sample.csv").text.lstrip("﻿").startswith("date,channel")


def test_web_events_counted_once_per_session(client):
    body = {"event": "line_click", "sid": "abcd1234-test", "path": "/contact"}
    assert client.post("/api/event", json=body).status_code == 204
    assert client.post("/api/event", json=body).status_code == 204
    assert client.post("/api/event", json={**body, "event": "phone_click"}).status_code == 204
    assert client.post("/api/event", json={**body, "event": "form_submit"}).status_code == 400
    assert client.post("/api/event", json={**body, "sid": "x"}).status_code == 400
    s = db()
    assert s.query(WebEvent).filter(WebEvent.dedupe_key.like("%abcd1234-test")).count() == 2
    s.close()


def test_cost_and_csv_safety():
    assert mc.cost_per(None, 5) is None
    assert mc.cost_per(1000.0, 0) is None
    assert mc.cost_per(0.0, 2) == 0
    assert mc.cost_per(1000.0, 4) == 250
    assert mc.csv_safe("=HYPERLINK(\"x\")") == "'=HYPERLINK(\"x\")"
    assert mc.csv_safe("@SUM(A1)").startswith("'")
    assert mc.csv_safe("ปกติ") == "ปกติ"
    out = mc.to_csv(["name"], [["=1+1"], ["+66"]])
    assert "'=1+1" in out and "'+66" in out


def test_empty_range_shows_no_data_not_zero(admin):
    s = db()
    rep = main.marketing.compute_report(s, mc.parse_date("2020-01-01"), mc.parse_date("2020-01-31"))
    s.close()
    assert rep["spend"] is None and rep["cpl_fit"] is None
    html = admin.get("/admin/marketing?start=2020-01-01&end=2020-01-31").text
    assert "ยังไม่เชื่อมข้อมูล" in html  # ผู้เข้าเว็บ


def test_utm_helpers():
    assert mc.slugify("One Touch — ราชการ Q4!") == "one-touch-q4"
    dest, err = mc.normalize_destination("/features?x=1", "https://www.voscene.com")
    assert not err and dest == "https://www.voscene.com/features?x=1"
    assert mc.normalize_destination("https://voscene.com/why", "https://www.voscene.com")[1] == ""
    assert mc.normalize_destination("https://evil.com/", "https://www.voscene.com")[1]
    assert mc.normalize_destination("javascript:alert(1)", "https://www.voscene.com")[1]
    url = mc.build_utm_url("https://www.voscene.com/?utm_source=old&a=1", "google", "cpc", "c1")
    assert url == "https://www.voscene.com/?a=1&utm_source=google&utm_medium=cpc&utm_campaign=c1"
    assert mc.classify_channel("", "", "https://www.google.com/", "www.voscene.com") == "organic_search"
    assert mc.classify_channel("", "", "https://voscene.com/features", "www.voscene.com") == "unknown"
    assert mc.parse_content_ref("ci12-hello") == (12, None)
    assert mc.parse_content_ref("fg7") == (None, 7)


def test_existing_pages_still_work(admin):
    for url in ["/", "/why", "/features", "/pricing", "/blog", "/contact", "/robots.txt",
                "/sitemap.xml"]:
        assert admin.get(url).status_code == 200, url
    for url in ["/admin", "/admin/leads", "/admin/leads?filter=new", "/admin/content",
                "/admin/packages", "/admin/blog", "/admin/files", "/admin/tracking",
                "/admin/settings", "/admin/marketing/campaigns", "/admin/marketing/content?view=calendar",
                "/admin/marketing/groups", "/admin/marketing/spend", "/admin/marketing/content/new",
                "/admin/marketing/campaigns/new", "/admin/marketing/groups/new"]:
        r = admin.get(url)
        assert r.status_code == 200, (url, r.text[:300])
    home = admin.get("/").text
    assert "/static/js/vs-track.js" in home
    assert admin.get("/static/js/vs-track.js").status_code == 200


def test_ad_tags_wait_for_consent(client):
    """ไม่มี ID = ไม่มีแบนเนอร์ · มี ID = แท็กอยู่ในฟังก์ชันที่รอกดยอมรับ ไม่ยิงเอง ไม่มี noscript"""
    from database import Content
    html = client.get("/").text
    assert "consent-banner" not in html and "googletagmanager.com" not in html

    s = db()
    for key, value in (("ga4_id", "G-TEST123456"), ("meta_pixel_id", "1234567890123456"),
                       ("gtm_id", "GTM-TEST123")):
        row = s.query(Content).filter_by(key=key).first()
        if row:
            row.value = value
        else:
            s.add(Content(key=key, value=value, label=key, section="tracking", field_type="text"))
    s.commit()
    try:
        html = client.get("/contact").text
        assert 'id="consent-banner"' in html and "ตั้งค่าคุกกี้" in html
        head = html.split("</head>")[0]
        # โหลดแท็กได้ทางเดียวคือ loadTags() ซึ่งเรียกเมื่อ state === 'granted' เท่านั้น
        assert head.count("function loadTags()") == 1
        assert "if (window.vsConsent.state === 'granted') loadTags();" in head
        assert '<script async src="https://www.googletagmanager.com' not in html
        assert "ns.html?id=" not in html and "noscript=1" not in html
        assert '"G-TEST123456"' in head  # ID ผ่าน tojson
    finally:
        for key in ("ga4_id", "meta_pixel_id", "gtm_id"):
            s.query(Content).filter_by(key=key).update({"value": ""})
        s.commit()
        s.close()


def _login(username, password):
    c = new_client()
    r = c.post("/admin/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.headers["location"] == "/admin", (username, r.headers["location"])
    return c


def test_roles_accounts_and_assignment(admin):
    from database import User
    # เจ้าของสร้างบัญชีทีมงาน
    r = admin.post("/admin/users/create", data={"username": "rotjana", "display_name": "รจนา (ขาย)",
                                                 "role": "staff", "password": "short"}, follow_redirects=False)
    assert "error=" in r.headers["location"]
    r = admin.post("/admin/users/create", data={"username": "rotjana", "display_name": "รจนา (ขาย)",
                                                 "role": "staff", "password": "staff-pass-123"},
                   follow_redirects=False)
    assert r.headers["location"].endswith("saved=1")
    s = db()
    staff = s.query(User).filter_by(username="rotjana").one()
    owner = s.query(User).filter_by(username="admin").one()
    assert staff.role == "staff" and owner.role == "owner"

    sc = _login("rotjana", "staff-pass-123")
    # ทีมงาน: หน้าเจ้าของถูกปฏิเสธที่เซิร์ฟเวอร์ ทั้ง GET และ POST
    for url in ["/admin/content", "/admin/tracking", "/admin/packages", "/admin/files", "/admin/users"]:
        r = sc.get(url, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/admin?denied=owner", url
    for url in ["/admin/content/update", "/admin/tracking", "/admin/packages/1/update",
                "/admin/files/delete", "/admin/users/create", f"/admin/users/{owner.id}/update"]:
        r = sc.post(url, data={"slot": "brochure", "role": "staff"}, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/admin?denied=owner", url
    s.expire_all()
    assert s.get(User, owner.id).role == "owner"
    # ทีมงาน: ใช้ Lead / การตลาด / บทความได้ · ไม่เห็นเมนูเจ้าของ · ไม่เห็น DATABASE_URL
    for url in ["/admin", "/admin/leads", "/admin/marketing", "/admin/marketing/campaigns", "/admin/blog",
                "/admin/settings"]:
        assert sc.get(url).status_code == 200, url
    page = sc.get("/admin/settings").text
    assert "sqlite" not in page and 'href="/admin/tracking"' not in page
    assert "การเก็บข้อมูลถาวร" in admin.get("/admin/settings").text

    # กันล็อกตัวเองออก: ลดสิทธิ์ตัวเอง / เจ้าของคนสุดท้าย
    r = admin.post(f"/admin/users/{owner.id}/update", data={"role": "staff", "is_active": "on"},
                   follow_redirects=False)
    assert "error=" in r.headers["location"]
    s.expire_all()
    assert s.get(User, owner.id).role == "owner"

    # มอบหมาย Lead + กรอง "ของฉัน"
    lead = submit_lead(admin, name="มอบหมายทดสอบ", phone="0861112222")
    admin.post(f"/admin/leads/{lead.id}/update", data={"sales_stage": "contacted", "qualification": "pending",
                                                       "assigned_to": str(staff.id)})
    s.expire_all()
    assert s.get(Lead, lead.id).assigned_to == staff.id
    assert "มอบหมายทดสอบ" in sc.get("/admin/leads?owner=me").text
    assert "มอบหมายทดสอบ" not in admin.get("/admin/leads?owner=me").text
    assert s.query(AuditLog).filter_by(entity="lead", entity_id=lead.id).count() >= 1

    # ปิดบัญชี → cookie เดิมใช้ไม่ได้ทันที และล็อกอินใหม่ไม่ได้
    r = admin.post(f"/admin/users/{staff.id}/update", data={"role": "staff", "display_name": "รจนา"},
                   follow_redirects=False)
    assert r.headers["location"].endswith("saved=1")
    r = sc.get("/admin/leads", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/admin/login"
    r = new_client().post("/admin/login", data={"username": "rotjana", "password": "staff-pass-123"},
                                  follow_redirects=False)
    assert r.headers["location"].startswith("/admin/login?error")
    s.close()


def test_privacy_page_hidden_until_filled(admin):
    from database import Content
    s = db()
    draft = s.query(Content).filter_by(key="privacy_policy_draft").one()
    assert "พระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล" in draft.value  # ร่างอยู่ในหลังบ้าน
    assert "แบบฟอร์ม" not in draft.value  # ฉบับไม่มีฟอร์ม
    assert admin.get("/privacy").status_code == 404  # ช่องจริงว่าง = ไม่มีหน้า
    home = admin.get("/").text
    assert 'href="/privacy"' not in home and "/privacy" not in admin.get("/sitemap.xml").text
    assert "นโยบายความเป็นส่วนตัว (/privacy)" in admin.get("/admin/content").text

    real = s.query(Content).filter_by(key="privacy_policy").one()
    real.value = "บทนำ\n## ข้อมูลที่เก็บ\n- ชื่อ\n- <script>alert(1)</script>"
    s.commit()
    try:
        page = admin.get("/privacy")
        assert page.status_code == 200
        assert "<h2>ข้อมูลที่เก็บ</h2>" in page.text and "<li>ชื่อ</li>" in page.text
        assert "<script>alert(1)</script>" not in page.text and "&lt;script&gt;" in page.text
        for url in ["/", "/contact"]:
            assert 'href="/privacy"' in admin.get(url).text, url  # ท้ายเว็บ + หน้าติดต่อ
        assert "/privacy" in admin.get("/sitemap.xml").text
    finally:
        real.value = ""
        s.commit()
        s.close()


def test_ai_draft_grounded_and_checked(admin, monkeypatch):
    import marketing_ai
    sent = {}

    async def fake_llm(messages):
        sent["messages"] = messages
        return "ควบคุมห้องประชุมได้ทุกยี่ห้อ พร้อมระบบไฟและประกาศเสียงตามสาย ดูที่ https://x.com"

    monkeypatch.setattr(marketing_ai, "call_llm", fake_llm)
    r = admin.post("/admin/marketing/ai/draft", json={"service": "multi_room", "channel": "facebook_page",
                                                      "goal": "demo", "notes": "เน้นผู้บริหาร"})
    j = r.json()
    assert r.status_code == 200 and j["ok"]
    system = sent["messages"][0]["content"]
    assert "สูงสุด 20 ห้อง" in system and "PA" in system  # ข้อเท็จจริง + ข้อห้ามอยู่ในพรอมต์
    assert "20 ห้อง" in sent["messages"][1]["content"]     # เงื่อนไขของบริการถูกบังคับใส่
    joined = " ".join(j["warnings"])
    for expect in ("เกินจริง", "ระบบไฟ", "PA", "ลิงก์", "20 ห้อง"):
        assert expect in joined, expect

    # บริการที่ยังไม่ยืนยัน → ไม่ร่าง และไม่เรียก AI
    sent.clear()
    r = admin.post("/admin/marketing/ai/draft", json={"service": "integrator", "channel": "facebook_page"})
    assert r.status_code == 400 and "ยังไม่ได้รับการยืนยัน" in r.json()["error"] and not sent

    # ข้อความสะอาด → ไม่มีคำเตือน
    async def clean_llm(messages):
        return "เข้าห้องแล้วแตะปุ่มเดียว จอ ไมค์ เสียง พร้อมประชุม — ขอนัดสาธิตได้เลย"
    monkeypatch.setattr(marketing_ai, "call_llm", clean_llm)
    r = admin.post("/admin/marketing/ai/draft", json={"service": "one_touch", "channel": "line_oa"})
    assert r.json()["ok"] and r.json()["warnings"] == []

    with new_client() as anon:
        r = anon.post("/admin/marketing/ai/draft", json={"service": "one_touch"}, follow_redirects=False)
        assert r.status_code == 303


def test_admin_posts_need_same_origin(admin):
    from database import Content
    s = db()
    before = s.query(Content).filter_by(key="contact_email").one().value
    # เว็บอื่นหลอกส่งฟอร์ม (cookie แอดมินติดไปด้วย แต่ Origin เป็นของเว็บอื่น)
    r = admin.post("/admin/content/update", data={"content_contact_email": "evil@x.com"},
                   headers={"Origin": "https://evil.example"}, follow_redirects=False)
    assert r.status_code == 403
    # ไม่มีทั้ง Origin และ Referer → ปฏิเสธ
    bare = TestClient(main.app)
    bare.cookies = admin.cookies
    assert bare.post("/admin/content/update", data={"content_contact_email": "evil@x.com"},
                     follow_redirects=False).status_code == 403
    s.expire_all()
    assert s.query(Content).filter_by(key="contact_email").one().value == before
    # Referer จากหน้าเว็บเดียวกันผ่าน · หน้า GET ไม่ถูกตรวจ · API สาธารณะไม่ถูกตรวจ
    r = bare.post("/admin/marketing/spend/add", data={}, headers={"Referer": "http://testserver/admin/marketing/spend"},
                  follow_redirects=False)
    assert r.status_code == 303
    assert bare.get("/admin/marketing").status_code == 200
    r = TestClient(main.app).post("/api/event", json={"event": "line_click", "sid": "origin-free-001"})
    assert r.status_code == 204
    s.close()


def test_password_change_logs_out_other_sessions(admin):
    from auth import COOKIE_NAME
    from jose import jwt
    admin.post("/admin/users/create", data={"username": "benz", "display_name": "เบนซ์",
                                            "role": "staff", "password": "benz-pass-111"})
    phone = _login("benz", "benz-pass-111")      # เครื่องที่ 1
    laptop = _login("benz", "benz-pass-111")     # เครื่องที่ 2
    r = laptop.post("/admin/settings/password", data={"current_password": "benz-pass-111",
                                                       "new_password": "short"}, follow_redirects=False)
    assert "too_short" in r.headers["location"]
    r = laptop.post("/admin/settings/password", data={"current_password": "benz-pass-111",
                                                       "new_password": "benz-pass-222"}, follow_redirects=False)
    assert r.headers["location"].endswith("saved=1")
    assert laptop.get("/admin/leads", follow_redirects=False).status_code == 200  # เครื่องที่เปลี่ยนใช้ต่อได้
    r = phone.get("/admin/leads", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/admin/login"      # เครื่องอื่นหลุด
    # cookie รุ่นเก่า (ไม่มี pv) ใช้ไม่ได้
    old = jwt.encode({"sub": "1", "exp": 4102444800}, os.environ["SECRET_KEY"], algorithm="HS256")
    legacy = new_client()
    legacy.cookies.set(COOKIE_NAME, old)
    assert legacy.get("/admin", follow_redirects=False).status_code == 303
    # เจ้าของรีเซ็ตรหัสให้ → session ของคนนั้นหลุดเหมือนกัน
    from database import User
    s = db()
    uid = s.query(User).filter_by(username="benz").one().id
    s.close()
    admin.post(f"/admin/users/{uid}/update", data={"role": "staff", "is_active": "on",
                                                   "display_name": "เบนซ์", "new_password": "reset-pass-333"})
    assert laptop.get("/admin/leads", follow_redirects=False).status_code == 303
    assert "เบนซ์" in admin.get("/admin/marketing/content/new").text  # ตัวเลือกผู้รับผิดชอบ


def test_no_forms_line_button_and_manual_leads(admin):
    from database import Content
    s = db()
    line = s.query(Content).filter_by(key="contact_line").one()
    old_line = line.value
    line.value = "@CSIPROAV"
    s.commit()
    try:
        for url in ["/", "/contact", "/why", "/features", "/pricing", "/blog"]:
            html = admin.get(url).text
            assert "<form" not in html, url                       # ลูกค้าไม่ต้องกรอกอะไร
            assert "Book Demo" not in html and "Book a Demo" not in html, url
            assert 'href="https://line.me/R/ti/p/@CSIPROAV"' in html, url  # ปุ่ม LINE ลอย
            assert "LINE @CSIPROAV" in html, url
        assert "ให้ AI วิเคราะห์" not in admin.get("/why").text
        assert "กรอก" not in admin.get("/contact").text.split("<main")[1].split("</main>")[0]
    finally:
        line.value = old_line
        s.commit()

    # ทีมงานบันทึก Lead ที่ทัก LINE เข้ามา + ผูกแคมเปญ
    camp = s.query(Campaign).filter_by(code="one-touch-gov-q4").one()
    r = admin.post("/admin/leads/create", data={"name": "", "contact_method": "line"}, follow_redirects=False)
    assert "error=" in r.headers["location"]
    r = admin.post("/admin/leads/create", data={
        "name": "คุณวิภา (LINE)", "company": "เทศบาลตัวอย่าง", "phone": "0877776666",
        "contact_method": "line", "channel": "facebook_ads", "campaign_id": str(camp.id),
        "request_type": "quote", "qualification": "fit", "note": "ขอรูปห้องเพิ่ม"}, follow_redirects=False)
    lid = int(r.headers["location"].split("/")[-1].split("?")[0])
    s.expire_all()
    lead = s.get(Lead, lid)
    assert (lead.contact_method, lead.channel, lead.campaign_id, lead.service_interest) ==         ("line", "facebook_ads", camp.id, "one_touch")
    assert lead.qualification == "fit" and lead.duplicate_of is None
    # คนเดิมโทรมาอีกรอบ → ถูกจับเป็นรายการซ้ำ
    r = admin.post("/admin/leads/create", data={"name": "คุณวิภา", "phone": "087-777-6666",
                                                "contact_method": "phone"}, follow_redirects=False)
    dup = s.get(Lead, int(r.headers["location"].split("/")[-1].split("?")[0]))
    assert dup.duplicate_of == lid
    rep = main.marketing.compute_report(s, mc.bkk_today(), mc.bkk_today())
    assert rep["stats"]["by_method"]["line"] >= 1
    page = admin.get(f"/admin/leads/{lid}").text
    assert "ติดต่อเข้ามาทาง" in page and "LINE" in page
    s.close()


def test_migration_003_and_seed_retire_form_text():
    import seed
    from database import Content
    s = db()
    # คำโปรยที่ยังชวน "กรอก" ถูกเปลี่ยนตอนบูต · ร่างนโยบายฉบับแรกที่ไม่มีใครแก้ถูกอัปเดต
    s.query(Content).filter_by(key="contact_subtitle").update({"value": "กรอกความต้องการของคุณ"})
    draft = s.query(Content).filter_by(key="privacy_policy_draft").one()
    draft.value = "ร่างที่เจ้าของแก้เองแล้ว"
    s.commit()
    seed.run_seed()
    s.expire_all()
    assert "กรอก" not in s.query(Content).filter_by(key="contact_subtitle").one().value
    assert s.query(Content).filter_by(key="privacy_policy_draft").one().value == "ร่างที่เจ้าของแก้เองแล้ว"
    assert "แบบฟอร์ม" not in seed.PRIVACY_POLICY_DRAFT
    s.close()


def test_web_forms_closed_by_default(client):
    from config import Settings
    assert Settings.model_fields["WEB_FORMS_ENABLED"].default is False
    s = db()
    before = s.query(Lead).count()
    main.settings.WEB_FORMS_ENABLED = False
    try:
        for url in ("/api/lead", "/api/analyze"):
            r = client.post(url, data={"name": "หน้าเก่าในแคช", "requirement": "x", "phone": "0811111111"})
            assert r.status_code == 410 and "LINE" in r.json()["error"], url
    finally:
        main.settings.WEB_FORMS_ENABLED = True
    s.expire_all()
    assert s.query(Lead).count() == before  # ไม่มีอะไรถูกบันทึก
    s.close()


def test_chat_ref_from_line_message(admin):
    # ตัวอ่านรหัส: ทั้งข้อความแชตทั้งก้อน / เฉพาะรหัส / เข้าเว็บตรง / อ่านไม่ออก
    full = "สวัสดีครับ สนใจระบบ Voscene\n(รหัสอ้างอิง: one-touch-gov-q4/facebook.group/fg7)"
    assert mc.parse_chat_ref(full) == {"utm_source": "facebook", "utm_medium": "group",
                                       "utm_campaign": "one-touch-gov-q4", "utm_content": "fg7",
                                       "referrer": ""}
    assert mc.parse_chat_ref("-/google.cpc")["utm_campaign"] == ""
    assert mc.parse_chat_ref("web") == {"utm_source": "", "utm_medium": "", "utm_campaign": "",
                                        "utm_content": "", "referrer": ""}
    assert mc.parse_chat_ref("web/google.com")["referrer"] == "https://google.com/"
    assert mc.parse_chat_ref("สวัสดีครับ อยากได้ราคา") is None
    assert mc.parse_chat_ref("abc/def") is None  # ไม่มี source.medium

    s = db()
    camp = s.query(Campaign).filter_by(code="one-touch-gov-q4").one()
    item = s.query(ContentItem).filter_by(campaign_id=camp.id).first()
    # รหัสชนะช่องที่เลือกเอง (เลือก unknown ไว้ แต่รหัสบอก Facebook Page + โพสต์ในคลัง)
    r = admin.post("/admin/leads/create", data={
        "name": "ลูกค้าจากแชต", "contact_method": "line", "channel": "unknown",
        "chat_ref": f"(รหัสอ้างอิง: one-touch-gov-q4/facebook.social/ci{item.id}-page)"},
        follow_redirects=False)
    lead = s.get(Lead, int(r.headers["location"].split("/")[-1].split("?")[0]))
    assert (lead.channel, lead.campaign_id, lead.content_item_id) == ("facebook_page", camp.id, item.id)
    assert lead.utm_source == "facebook" and lead.service_interest == "one_touch"
    # เข้าเว็บจาก Google (ไม่มี UTM) → ค้นหาทั่วไป
    r = admin.post("/admin/leads/create", data={"name": "จาก Google", "contact_method": "line",
                                                "chat_ref": "web/google.co.th"}, follow_redirects=False)
    assert s.get(Lead, int(r.headers["location"].split("/")[-1].split("?")[0])).channel == "organic_search"
    # รหัสเสีย → แจ้ง ไม่บันทึก
    r = admin.post("/admin/leads/create", data={"name": "x", "contact_method": "line",
                                                "chat_ref": "อะไรก็ไม่รู้"}, follow_redirects=False)
    assert "error=" in r.headers["location"]
    s.close()


def test_dashboard_is_daily_work_view(admin):
    s = db()
    r = admin.post("/admin/leads/create", data={"name": "นัดวันนี้ทดสอบ", "contact_method": "phone",
                                                "phone": "0845550000"}, follow_redirects=False)
    lid = int(r.headers["location"].split("/")[-1].split("?")[0])
    admin.post(f"/admin/leads/{lid}/update", data={
        "sales_stage": "contacted", "qualification": "pending",
        "next_follow_up": (mc.bkk_today()).isoformat(), "assigned_to": "1"})
    html = admin.get("/admin").text
    assert "นัดติดตามของฉัน" in html and "นัดวันนี้ทดสอบ" in html and "นัดวันนี้" in html
    assert "+ เพิ่ม Lead" in html
    assert "(AI)" not in html and "ใน Scope" not in html  # การ์ด/คอลัมน์ AI เก่าไม่อยู่แล้ว
    s.close()


def test_seed_splits_sales_and_tech_phone_once():
    import seed
    from database import Content
    s = db()
    row = s.query(Content).filter_by(key="contact_phone").one()
    row.value = "\r\n".join(["รจนา 088-886 4660", "LINE : @CSIPROAV"])  # ค่าบน production ก่อนแก้
    s.commit()
    seed.run_seed()
    s.expire_all()
    value = s.query(Content).filter_by(key="contact_phone").one().value
    assert "ฝ่ายเทคนิค : เบนซ์ 099-345 1998" in value and "ฝ่ายขาย : รจนา" in value
    # แอดมินแก้เป็นแบบอื่นแล้ว → บูตรอบหลังไม่ทับ
    s.query(Content).filter_by(key="contact_phone").update({"value": "ติดต่อ 02-000-0000"})
    s.commit()
    seed.run_seed()
    s.expire_all()
    assert s.query(Content).filter_by(key="contact_phone").one().value == "ติดต่อ 02-000-0000"
    s.close()


def test_privacy_patch_keeps_owner_edits():
    import seed
    old_lines = [
        "นโยบายนี้อธิบายว่า ...",
        "## ข้อมูลที่เราเก็บ",
        "- ข้อมูลที่คุณกรอกในแบบฟอร์มติดต่อ: ชื่อ-นามสกุล บริษัท/หน่วยงาน เบอร์โทรศัพท์ อีเมล ขนาดห้องประชุม งบประมาณ ความต้องการ และประเภทคำขอ (ปรึกษา / ขอนัด Demo / ขอใบเสนอราคา)",
        "- หมายเลข IP ในกรณีที่ระบบตรวจพบว่าการส่งแบบฟอร์มอาจเป็นสแปมหรือบอท",
        "- ผู้ให้บริการระบบที่เว็บไซต์ใช้ ได้แก่ ผู้ให้บริการเซิร์ฟเวอร์ (Render — ศูนย์ข้อมูลในสิงคโปร์) และ Cloudflare ซึ่งอาจประมวลผลข้อมูลนอกประเทศไทย ภายใต้มาตรการคุ้มครองที่เหมาะสม",
        "- เก็บข้อมูลไว้ 2 ปี",                       # เจ้าของเติมเอง
        "อีเมล: privacy@csi.example",                 # เจ้าของเติมเอง
    ]
    owner_draft = "\r\n".join(old_lines)             # textarea บันทึกเป็น CRLF
    patched = seed.patch_privacy_text(owner_draft)
    assert "แบบฟอร์ม" not in patched and "หมายเลข IP" not in patched
    assert "ติดต่อเราทาง LINE โทรศัพท์ หรืออีเมล" in patched
    assert "- LINE ในฐานะผู้ให้บริการช่องทางแชต" in patched
    assert "- เก็บข้อมูลไว้ 2 ปี" in patched and "อีเมล: privacy@csi.example" in patched
    assert seed.patch_privacy_text(patched) == patched           # รันซ้ำไม่เปลี่ยน
    assert seed.patch_privacy_text("ข้อความเจ้าของล้วน") == "ข้อความเจ้าของล้วน"
    assert "รหัสอ้างอิง" in seed.PRIVACY_POLICY_DRAFT               # ฉบับใหม่พูดถึงรหัสในข้อความ LINE


def test_settings_security_panel(admin):
    html = admin.get("/admin/settings").text
    assert "ความปลอดภัยของระบบ" in html and "SECRET_KEY" in html
    assert "✓ ปิดอยู่" not in html  # เทสรันด้วย DEBUG=True → ต้องขึ้นเตือน ไม่ใช่ผ่าน
    assert "ตั้งแล้ว" in html          # คีย์เทสยาวพอ ไม่ใช่ค่าตัวอย่าง
    assert os.environ["SECRET_KEY"] not in html  # ไม่แสดงค่าจริง

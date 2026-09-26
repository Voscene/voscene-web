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


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
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
    with TestClient(main.app) as anon:
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
    assert "/static/js/vs-track.js" in home and 'name="request_type"' in home
    assert admin.get("/static/js/vs-track.js").status_code == 200

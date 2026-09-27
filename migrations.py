"""ย้ายโครงสร้าง DB แบบไม่ทำลายข้อมูล — เพิ่มได้อย่างเดียว ไม่ลบ ไม่เปลี่ยนชนิดคอลัมน์

ทำไมไม่ใช้ create_all อย่างเดียว: create_all สร้าง *ตารางใหม่* ได้ แต่ไม่เติมคอลัมน์
ให้ตารางที่มีอยู่แล้ว (เช่น leads บน production) — ถ้าไม่มีไฟล์นี้ แอปจะพังทันทีที่
ORM เลือกคอลัมน์ใหม่

ลำดับทุกครั้งที่บูต:
1. ดูว่ามีขั้นตอนไหนยังไม่เคยรัน (ตาราง schema_migrations)
2. ถ้ามีและเป็น SQLite → คัดลอกไฟล์ DB เก็บไว้ก่อน (`data.db.pre-<ขั้น>-<เวลา>.bak`)
3. create_all → สร้างตารางใหม่ที่ยังไม่มี (ตารางเดิมไม่ถูกแตะ)
4. ADD COLUMN ที่ขาด → เติมข้อมูลย้อนหลัง → บันทึกว่ารันแล้ว

แต่ละขั้นเขียนให้รันซ้ำได้ปลอดภัย (เช็คก่อนเพิ่มทุกคอลัมน์) และไม่แตะค่าที่มีอยู่
ยกเว้นคอลัมน์ใหม่ที่เพิ่งเพิ่มในขั้นนั้นเอง
"""
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import inspect, text


def _sqlite_file(engine) -> Path | None:
    if engine.dialect.name != "sqlite":
        return None
    db = engine.url.database
    if not db or db == ":memory:":
        return None
    return Path(db)


def _backup(engine, label: str) -> str:
    path = _sqlite_file(engine)
    if not path or not path.exists() or path.stat().st_size == 0:
        return ""
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    dest = path.with_name(f"{path.name}.pre-{label}-{stamp}.bak")
    shutil.copy2(path, dest)
    return str(dest)


def _add_columns(conn, table: str, table_obj) -> list:
    """เพิ่มคอลัมน์ที่ model มีแต่ตารางจริงยังไม่มี — คืนชื่อคอลัมน์ที่เพิ่ม"""
    existing = {c["name"] for c in inspect(conn).get_columns(table)}
    added = []
    for col in table_obj.columns:
        if col.name in existing:
            continue
        coltype = col.type.compile(dialect=conn.dialect)
        default = ""
        # ใส่ DEFAULT ให้คอลัมน์ที่มีค่าเริ่มต้นแบบค่าคงที่ แถวเดิมจะได้ไม่เป็น NULL
        if col.default is not None and getattr(col.default, "is_scalar", False):
            val = col.default.arg
            if isinstance(val, bool):
                default = f" DEFAULT {1 if val else 0}" if conn.dialect.name == "sqlite" \
                    else f" DEFAULT {'TRUE' if val else 'FALSE'}"
            elif isinstance(val, (int, float)):
                default = f" DEFAULT {val}"
            elif isinstance(val, str):
                default = " DEFAULT '" + val.replace("'", "''") + "'"
        conn.execute(text(f'ALTER TABLE {table} ADD COLUMN "{col.name}" {coltype}{default}'))
        added.append(col.name)
    return added


def _m001_marketing(conn, Base) -> str:
    """Lead: แหล่งที่มา · ขั้นการขาย · ผลคัดกรอง · มูลค่า · รายการซ้ำ"""
    from marketing_core import legacy_status_to_new, normalize_email, normalize_phone

    added = _add_columns(conn, "leads", Base.metadata.tables["leads"])
    rows = conn.execute(text(
        "SELECT id, status, phone, email FROM leads ORDER BY created_at, id"
    )).fetchall()
    first_seen: dict = {}
    dupes = 0
    for lead_id, status, phone, email in rows:
        stage, qual = legacy_status_to_new(status)
        pn, en = normalize_phone(phone), normalize_email(email)
        dup_of = None
        if (status or "") != "anonymous":
            for key in (("p", pn), ("e", en)):
                if key[1] and key in first_seen:
                    dup_of = first_seen[key]
                    break
            for key in (("p", pn), ("e", en)):
                if key[1]:
                    first_seen.setdefault(key, lead_id)
        dupes += 1 if dup_of else 0
        conn.execute(text(
            "UPDATE leads SET sales_stage=:s, qualification=:q, phone_norm=:p, email_norm=:e, "
            "duplicate_of=:d, spam_reason=:r WHERE id=:id"
        ), {"s": stage, "q": qual, "p": pn, "e": en, "d": dup_of,
            "r": "honeypot" if status == "spam" else "", "id": lead_id})
    # ASCII ล้วน — print ภาษาไทยบนคอนโซล Windows (cp1252) ทำให้แอปบูตไม่ขึ้น
    return f"leads +{len(added)} columns, {len(rows)} rows mapped, {dupes} duplicates flagged"


def _m002_users_roles(conn, Base) -> str:
    """บัญชีรายคน + สิทธิ์ · ผู้รับผิดชอบ Lead

    บัญชีที่มีอยู่ก่อนขั้นนี้ (admin เดิม) ต้องเป็น owner ไม่งั้นเจ้าของจะล็อกตัวเอง
    ออกจากหน้าตั้งค่าทันทีหลัง deploy
    """
    added = _add_columns(conn, "users", Base.metadata.tables["users"])
    added += _add_columns(conn, "leads", Base.metadata.tables["leads"])
    owners = conn.execute(text("UPDATE users SET role='owner', is_active=:t"), {"t": True}).rowcount
    return f"+{len(added)} columns, {owners} existing users set to owner"


def _m003_contact_method(conn, Base) -> str:
    """เลิกใช้ฟอร์ม (2026-09-27) — Lead ใหม่ทีมงานบันทึกเองจาก LINE/โทร จึงต้องรู้ว่าติดต่อทางไหน

    Lead เดิมที่มีข้อมูลติดต่อมาจากฟอร์มเว็บทั้งหมด → web_form · anonymous คงว่างไว้
    """
    added = _add_columns(conn, "leads", Base.metadata.tables["leads"])
    n = conn.execute(text(
        "UPDATE leads SET contact_method='web_form' "
        "WHERE (contact_method IS NULL OR contact_method='') AND status != 'anonymous'"
    )).rowcount
    return f"leads +{len(added)} columns, {n} existing leads marked web_form"


def _m004_content_tags(conn, Base) -> str:
    """เนื้อหาจัดหมวดตามบริการ + กลุ่มเป้าหมาย (2026-09-27) · เนื้อหาเดิมเว้นว่าง = ยังไม่จัดหมวด"""
    added = _add_columns(conn, "mk_content", Base.metadata.tables["mk_content"])
    return f"mk_content +{len(added)} columns"


MIGRATIONS = [
    ("001_marketing", _m001_marketing),
    ("002_users_roles", _m002_users_roles),
    ("003_contact_method", _m003_contact_method),
    # หมายเหตุ: branch shelved/line-webhook มี 004 ของตัวเอง — ถ้าเอากลับมาใช้ให้เปลี่ยนเป็น 005
    ("004_content_tags", _m004_content_tags),
]


def run_migrations(engine, Base) -> list:
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version VARCHAR(64) PRIMARY KEY, applied_at VARCHAR(32), note TEXT)"
        ))
        done = {r[0] for r in conn.execute(text("SELECT version FROM schema_migrations"))}
    pending = [(v, fn) for v, fn in MIGRATIONS if v not in done]

    had_tables = bool(inspect(engine).get_table_names())
    backup = _backup(engine, pending[0][0]) if pending and had_tables else ""

    Base.metadata.create_all(bind=engine)  # ตารางใหม่เท่านั้น ของเดิมไม่ถูกแตะ

    results = []
    for version, fn in pending:
        with engine.begin() as conn:  # ขั้นละ transaction — พลาดกลางทางย้อนทั้งขั้น
            note = fn(conn, Base)
            conn.execute(text(
                "INSERT INTO schema_migrations (version, applied_at, note) VALUES (:v, :t, :n)"
            ), {"v": version, "t": datetime.utcnow().isoformat(timespec="seconds"), "n": note})
        results.append(f"{version}: {note}")
        print(f"[migrate] {version}: {note}")
    if backup:
        print(f"[migrate] backup before migrating: {backup}")
    return results

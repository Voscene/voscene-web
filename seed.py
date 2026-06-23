"""สร้างข้อมูลเริ่มต้น: admin user, default content, default packages
Aligned with Voscene Product Catalog V2 (2026 Edition · Volume 2.0)
"""
from passlib.context import CryptContext
from database import SessionLocal, init_db, User, Content, Package
from config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
settings = get_settings()


DEFAULT_CONTENT = [
    # ===== Hero Section =====
    ("hero_badge", "AI-Powered AV Control · Now in Thailand", "Badge ใต้ navbar", "hero", "text"),
    ("hero_title_line1", "The voice of", "บรรทัดที่ 1 ของ Headline", "hero", "text"),
    ("hero_title_line2", "smart spaces.", "บรรทัดที่ 2 (สี gradient)", "hero", "text"),
    ("hero_subtitle_th", "ระบบควบคุม AV ขับเคลื่อนด้วย AI ออกแบบเพื่อองค์กรไทย", "บรรทัดภาษาไทย", "hero", "text"),
    ("hero_tagline", "Voice on SCENE · Speak. Control. Transform.", "Slogan", "hero", "text"),
    ("hero_description", "Voscene เปลี่ยนห้องประชุม โรงแรม ห้องเรียน และพื้นที่ event ให้กลายเป็น smart space ที่ควบคุมด้วยภาษาธรรมชาติ ผ่าน AI Thai/English — ติดตั้งใน 24 ชั่วโมง ราคาประหยัดกว่าระบบ AV ระดับโลก 60-80% รองรับอุปกรณ์ AV หลากหลายยี่ห้อ — 48 ยี่ห้อ · 1,000+ รุ่น ผ่านโปรโตคอลมาตรฐาน (PJLink · VISCA · webOS/Tizen · DMX ฯลฯ)", "คำอธิบาย Hero", "hero", "textarea"),
    ("hero_cta_primary", "Book a Demo", "ปุ่มหลัก", "hero", "text"),
    ("hero_cta_secondary", "ดูฟีเจอร์", "ปุ่มรอง", "hero", "text"),
    ("hero_mission", "\"พูดสิ่งที่อยากทำ\" — Voscene จัดการที่เหลือให้", "Mission Statement (quote-style)", "hero", "textarea"),

    # ===== Downloads (labels — files managed via /admin/files) =====
    ("brochure_label", "Download Brochure", "ป้ายปุ่ม Download Brochure", "files", "text"),
    ("catalog_label", "Download Catalog", "ป้ายปุ่ม Download Catalog", "files", "text"),

    # ===== Brand meaning =====
    ("brand_meaning_title", "VOSCENE คืออะไร", "หัวข้อความหมายแบรนด์", "brand", "text"),
    ("brand_meaning_text", "VOSCENE ออกเสียงว่า \"VO-seen\" — มาจาก Voice on SCENE หมายถึง \"เสียงพร้อมแล้ว ในทุกพื้นที่\"", "ความหมายแบรนด์", "brand", "textarea"),

    # ===== USP Stats =====
    ("stat_1_value", "60-80%", "ตัวเลขสถิติ 1", "stats", "text"),
    ("stat_1_label", "ประหยัดกว่าระบบ AV แบรนด์ใหญ่", "คำอธิบายสถิติ 1", "stats", "text"),
    ("stat_2_value", "<24h", "ตัวเลขสถิติ 2", "stats", "text"),
    ("stat_2_label", "ติดตั้งห้องเดียว Plug & Play", "คำอธิบายสถิติ 2", "stats", "text"),
    ("stat_3_value", "48", "ตัวเลขสถิติ 3", "stats", "text"),
    ("stat_3_label", "ยี่ห้อที่รองรับ · 1,000+ รุ่น", "คำอธิบายสถิติ 3", "stats", "text"),
    ("stat_4_value", "0", "ตัวเลขสถิติ 4 (มี * เล็ก)", "stats", "text"),
    ("stat_4_label", "App ที่ต้องติดตั้ง · Browser-based UI", "คำอธิบายสถิติ 4", "stats", "text"),

    # ===== About / Why =====
    ("about_title", "ทำไมต้องเลือก Voscene", "หัวข้อ About", "about", "text"),
    ("about_description", "ออกแบบมาเทียบชั้นระบบ AV ระดับโลก แต่ราคาประหยัดกว่า 60-80% — ใช้ AI สั่งงานด้วยภาษาธรรมชาติ ลดความซับซ้อน รองรับอุปกรณ์ที่ลูกค้ามีอยู่แล้วผ่านโปรโตคอลมาตรฐาน", "คำอธิบาย About", "about", "textarea"),

    # ===== Brand Note =====
    ("brand_note", "ระบบรองรับอุปกรณ์แทบทุกยี่ห้อที่ใช้โปรโตคอลมาตรฐาน — ไม่ต้องมีรุ่นในลิสต์ก็คุมได้ถ้าพูดโปรโตคอลที่รองรับ · ปรับแต่งเพื่อรองรับอุปกรณ์ที่ลูกค้ามีอยู่แล้วได้", "หมายเหตุเรื่อง Brand", "about", "textarea"),

    # ===== LINE Integration =====
    ("line_title", "Text to control. Alerts in real-time.", "หัวข้อ LINE section", "line", "text"),
    ("line_subtitle", "Voscene meets your team where they already are — in LINE.", "คำอธิบาย LINE", "line", "text"),

    # ===== Contact =====
    ("contact_title", "Let's talk.", "หัวข้อ Contact", "contact", "text"),
    ("contact_subtitle", "Ready to transform your AV experience? — กรอกความต้องการของคุณ AI จะวิเคราะห์และแนะนำ Edition ที่เหมาะสมให้ทันที", "คำอธิบาย Contact", "contact", "textarea"),
    ("contact_phone", "088-886-4660", "เบอร์โทร (ใส่หลายเบอร์ได้ ขึ้นบรรทัดใหม่)", "contact", "textarea"),
    ("contact_email", "hello@voscene.com", "อีเมล", "contact", "text"),
    ("contact_address", "Bangkok, Thailand · Serving Southeast Asia", "ที่อยู่ (รองรับ 2-3 บรรทัด)", "contact", "textarea"),
    ("contact_hours", "จันทร์-ศุกร์ 09:00-18:00", "เวลาทำการ", "contact", "text"),
    ("contact_facebook", "", "Facebook URL (เช่น https://facebook.com/voscene)", "contact", "text"),
    ("contact_line", "", "LINE Official Account URL หรือ ID (เช่น https://lin.ee/xxxxx หรือ @voscene)", "contact", "text"),

    # ===== Footer =====
    ("footer_company", "Central System Integration Co., Ltd.", "ชื่อบริษัท", "footer", "text"),
    ("footer_tagline", "The voice of smart spaces. · Voice on SCENE — Speak. Control. Transform.", "คำขวัญ", "footer", "text"),
    ("footer_copyright", "© 2026 Voscene by Central System Integration. All rights reserved.", "Copyright", "footer", "text"),

    # ===== SEO / Meta =====
    ("seo_title", "Voscene — The voice of smart spaces. AI-Powered AV Control for Thai Enterprise", "Title สำหรับ Search Engine", "seo", "text"),
    ("seo_description", "Voscene — ระบบควบคุม AV เพื่อองค์กรไทย ขับเคลื่อนด้วย AI · ควบคุมด้วยเสียง/ข้อความภาษาไทยและอังกฤษ · ติดตั้งใน 24 ชั่วโมง · ประหยัด 60-80% · 15 ฟีเจอร์: AI Agent, Scene, Matrix, Audio, Projector, TV, DMX Lighting, PTZ, Auto Tracking, Conference, Calendar, Schedule, Multi-Room (สูงสุด 20 ห้อง), Video Conferencing · OAuth + LINE + OTA + AES-128 Backup · รองรับอุปกรณ์ 48 ยี่ห้อ 1,000+ รุ่น", "Meta Description", "seo", "textarea"),
]


# Aligned with Catalog V2 (Volume 2.0) — Editions section (Contact for pricing, no fixed numbers)
DEFAULT_PACKAGES = [
    {
        "code": "starter", "name": "Voscene Starter",
        "price": "Contact for pricing", "price_unit": "",
        "description": "For single meeting rooms · Best for small offices",
        "features": "1 control unit\nUp to 8 connected devices\n4 configurable scenes (tech-tunable)\nBrowser-based UI (no app install)\nTwo-tier PIN security\nIn-browser settings\nDevice health monitor\nOffline-capable\nEmail support\n1-year warranty",
        "category": "purchase", "sort_order": 1, "is_featured": False,
    },
    {
        "code": "pro", "name": "Voscene Pro",
        "price": "Contact for pricing", "price_unit": "",
        "description": "For multi-room deployments · Best for hotels, universities, enterprises",
        "features": "Everything in Starter\n1 control unit per room\nUnlimited connected devices\nAI command module (BYOL — customer brings own LLM key)\nLINE integration (send commands + alerts)\nUp to 4 PTZ camera control (VISCA over IP)\nAuto video tracking (mic-driven)\nCalendar integration (auto-trigger scenes)\nSchedule rules engine\nVideo conferencing room control\nMulti-room dashboard (up to 20 rooms)\nAPI Keys (X-API-Key) for integrations\nOTA software updates + auto-rollback\nEncrypted auto-backup (AES-128, 30-day)\nSecure remote support (encrypted, on-demand)\nPriority phone support\n3-year warranty\nOn-site installation",
        "category": "purchase", "sort_order": 2, "is_featured": True,
    },
    {
        "code": "enterprise", "name": "Voscene Enterprise",
        "price": "Custom quote", "price_unit": "",
        "description": "For large-scale operations · Best for government, large enterprises",
        "features": "Everything in Pro\nUnlimited control units\nCustom protocol integration\nAD / LDAP authentication (Roadmap)\nCustom DSP integration (Roadmap)\nWhite-label option\nOn-premises LLM (optional)\nCentral management\nSLA 24/7\nDedicated account manager\n5-year warranty\nCustom training program\nSource code escrow (opt.)",
        "category": "purchase", "sort_order": 3, "is_featured": False,
    },

    # ===== Add-on Kits (Catalog v1.4) =====
    {
        "code": "addon_base", "name": "Base Kit",
        "price": "Included", "price_unit": "in-box",
        "description": "มาในกล่อง · สำหรับห้องประชุมขนาดเล็ก",
        "features": "Voscene 2U Controller\nIR emitter cable มาตรฐาน 1.8 เมตร\nสำหรับ: ห้องประชุมขนาดเล็ก · อุปกรณ์อยู่ใน AV cabinet เดียวกัน",
        "category": "addon", "sort_order": 10, "is_featured": False,
    },
    {
        "code": "addon_ir_extension", "name": "IR Extension Kit",
        "price": "Contact for pricing", "price_unit": "",
        "description": "เดินสาย IR ระยะไกล · สำหรับห้องประชุมใหญ่",
        "features": "IR Extender (Transmitter + Receiver pair)\nCAT5 cable 15-30 เมตร\nIR emitter cable 3 เส้น\nสำหรับ: ห้องประชุมใหญ่ · เดินสายผ่านฝ้าเพดาน",
        "category": "addon", "sort_order": 11, "is_featured": True,
    },
    {
        "code": "addon_multi_device", "name": "Multi-device Kit",
        "price": "Contact for pricing", "price_unit": "",
        "description": "คุมหลายอุปกรณ์ผ่าน IR พร้อมกัน",
        "features": "IR Y-splitter (1-to-4)\nIR emitter cable 4 เส้น\nสำหรับ: คุมหลายอุปกรณ์พร้อมกัน (TV + Audio + Player)",
        "category": "addon", "sort_order": 12, "is_featured": False,
    },
]


def run_seed():
    init_db()
    db = SessionLocal()
    try:
        # Admin user
        if not db.query(User).filter_by(username=settings.ADMIN_USERNAME).first():
            user = User(
                username=settings.ADMIN_USERNAME,
                password_hash=pwd_context.hash(settings.ADMIN_PASSWORD),
            )
            db.add(user)
            print(f"[seed] created admin user: {settings.ADMIN_USERNAME}")

        # Default content — adds new keys + migrates field_type/label/section of existing.
        # Legal-risk values (competitor names, "10-15 เท่า", absolutes/superlatives) are
        # force-updated to the safe default; if the operator has already replaced the value
        # with something that no longer contains any risky phrase, their edit is preserved.
        LEGAL_RISK_PHRASES = (
            "Crestron", "AMX", "QSC",
            "10-15 เท่า", "10-15เท่า",
            "อัจฉริยะ ตัวแรก", "ตัวแรกที่ออกแบบ",
            "ทุก Brand", "ทุกยี่ห้อ", "ทุกยีห้อ",
        )
        LEGAL_CRITICAL_KEYS = {
            "hero_subtitle_th", "hero_description",
            "about_description", "brand_note",
            "seo_description",
            "stat_3_value", "stat_3_label",
        }
        added = 0
        migrated = 0
        legal_forced = 0
        for key, value, label, section, field_type in DEFAULT_CONTENT:
            existing = db.query(Content).filter_by(key=key).first()
            if existing:
                # Migrate metadata (preserves user-edited value)
                changed = False
                if existing.field_type != field_type:
                    existing.field_type = field_type
                    changed = True
                if existing.label != label:
                    existing.label = label
                    changed = True
                if existing.section != section:
                    existing.section = section
                    changed = True
                # Force legal fixes if the stored value still carries a risky phrase,
                # OR if a critical stat key still reads "100%" (superlative).
                if key in LEGAL_CRITICAL_KEYS:
                    current = existing.value or ""
                    has_risk = any(p in current for p in LEGAL_RISK_PHRASES)
                    is_100_pct_stat = (key == "stat_3_value" and current.strip() in {"100%", "100"})
                    if has_risk or is_100_pct_stat:
                        existing.value = value
                        legal_forced += 1
                        changed = True
                if changed:
                    migrated += 1
            else:
                db.add(Content(key=key, value=value, label=label, section=section, field_type=field_type))
                added += 1
        print(f"[seed] content: +{added} new · ~{migrated} migrated · {legal_forced} legal-forced ({len(DEFAULT_CONTENT)} total defined)")

        # Default packages — add new, and migrate features of core editions (starter/pro/enterprise)
        # to keep them aligned with the latest catalog. Add-on kits are NOT auto-migrated
        # (admin may have customized pricing).
        pkg_added = 0
        pkg_migrated = 0
        CORE_EDITIONS = {"starter", "pro", "enterprise"}
        for pkg_data in DEFAULT_PACKAGES:
            existing = db.query(Package).filter_by(code=pkg_data["code"]).first()
            if not existing:
                db.add(Package(**pkg_data))
                pkg_added += 1
            elif pkg_data["code"] in CORE_EDITIONS:
                # Migrate features + description for core editions if they differ from defaults
                changed = False
                if existing.features != pkg_data["features"]:
                    existing.features = pkg_data["features"]
                    changed = True
                if existing.description != pkg_data["description"]:
                    existing.description = pkg_data["description"]
                    changed = True
                if changed:
                    pkg_migrated += 1
        print(f"[seed] packages: +{pkg_added} new · ~{pkg_migrated} migrated ({len(DEFAULT_PACKAGES)} total defined)")

        db.commit()
        print("[seed] done")
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()

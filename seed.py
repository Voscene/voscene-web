"""สร้างข้อมูลเริ่มต้น: admin user, default content, default packages
Aligned with Voscene Product Catalog V2 (2026 Edition · Volume 2.0)
"""
from passlib.context import CryptContext
from database import SessionLocal, init_db, User, Content, Package
from config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
settings = get_settings()


# ร่างโดยทีมเว็บ — อธิบายสิ่งที่ระบบเก็บ "จริง" ตามโค้ด ณ 2026-09-27 (ไม่มีฟอร์มแล้ว · vs-track.js ·
# แบนเนอร์คุกกี้ · Render/Cloudflare) · ข้อความใน [วงเล็บเหลี่ยม] ต้องให้เจ้าของ/ที่ปรึกษากฎหมาย
# กำหนดก่อนเผยแพร่ · ถ้าระบบเปลี่ยนวิธีเก็บข้อมูล ต้องแก้ร่างนี้และหน้าจริงด้วย
PRIVACY_POLICY_DRAFT = """นโยบายนี้อธิบายว่า บริษัท เซ็นทรัล ซิสเท็ม อินทิเกรชั่น จำกัด ("บริษัท") ผู้ให้บริการเว็บไซต์ voscene.com เก็บ ใช้ และดูแลข้อมูลส่วนบุคคลของคุณอย่างไร ตามพระราชบัญญัติคุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562

## ข้อมูลที่เราเก็บ
- ข้อมูลที่คุณให้เมื่อติดต่อเราทาง LINE โทรศัพท์ หรืออีเมล: ชื่อหรือชื่อบัญชี LINE บริษัท/หน่วยงาน เบอร์โทรศัพท์ อีเมล และรายละเอียดความต้องการ ซึ่งทีมงานบันทึกไว้เพื่อติดตามการให้บริการ
- ช่องทางที่คุณรู้จักเรา เช่น โฆษณาหรือโพสต์ที่เห็น — จากที่คุณแจ้ง หรือจากรหัสอ้างอิงที่ปุ่ม LINE บนเว็บไซต์ใส่ไว้ในข้อความแรก (คุณลบรหัสออกก่อนส่งได้)
- จำนวนครั้งที่มีการกดปุ่ม LINE หรือปุ่มโทรบนเว็บไซต์ พร้อมหน้าที่เข้าชมและลิงก์ที่พาเข้ามา โดยใช้รหัสสุ่มที่หมดอายุเมื่อปิดหน้าต่าง ไม่ผูกกับตัวตนของคุณ

## วัตถุประสงค์และฐานทางกฎหมาย
- ตอบคำถาม ให้คำปรึกษา นัดสาธิต และจัดทำใบเสนอราคาตามที่คุณร้องขอ (ขั้นตอนก่อนเข้าทำสัญญา)
- ติดตามผลการขายและปรับปรุงบริการ และวัดผลว่าช่องทางการตลาดใดเข้าถึงผู้ที่สนใจบริการ (ประโยชน์โดยชอบด้วยกฎหมาย)
- วัดผลและปรับปรุงโฆษณาด้วยคุกกี้ของ Google และ Meta — เฉพาะเมื่อคุณกด "ยอมรับ" ในแบนเนอร์คุกกี้ (ความยินยอม)

## คุกกี้
- เว็บไซต์ไม่ใช้คุกกี้โฆษณาจนกว่าคุณจะกด "ยอมรับ" ถ้าปฏิเสธ ยังใช้งานเว็บไซต์ได้ตามปกติ
- เมื่อยอมรับ Google Analytics / Google Tag Manager และ Meta Pixel จะตั้งคุกกี้เพื่อวัดผลการเข้าชมและโฆษณา
- คุณเปลี่ยนการตั้งค่าได้ทุกเมื่อที่ลิงก์ "ตั้งค่าคุกกี้" ท้ายเว็บไซต์ เมื่อเปลี่ยนเป็นปฏิเสธ ระบบจะลบคุกกี้ดังกล่าวออก
- เว็บไซต์เก็บการตั้งค่าคุกกี้ของคุณไว้ในเบราว์เซอร์เป็นเวลา 12 เดือน

## การเปิดเผยข้อมูล
- ทีมขายและทีมเทคนิคของบริษัท เท่าที่จำเป็นต่อการให้บริการ
- ผู้ให้บริการระบบที่เว็บไซต์ใช้ ได้แก่ ผู้ให้บริการเซิร์ฟเวอร์ (Render — ศูนย์ข้อมูลในสิงคโปร์) และ Cloudflare ซึ่งอาจประมวลผลข้อมูลนอกประเทศไทย ภายใต้มาตรการคุ้มครองที่เหมาะสม
- LINE ในฐานะผู้ให้บริการช่องทางแชต เมื่อคุณติดต่อผ่าน LINE (อยู่ภายใต้นโยบายความเป็นส่วนตัวของ LINE ด้วย)
- Google และ Meta เฉพาะกรณีที่คุณยินยอมให้ใช้คุกกี้
- บริษัทไม่ขายข้อมูลส่วนบุคคลของคุณให้ผู้ใดทั้งสิ้น

## ระยะเวลาการเก็บรักษา
- [ระบุระยะเวลา เช่น เก็บข้อมูลการติดต่อไว้ไม่เกิน 2 ปีนับจากการติดต่อครั้งล่าสุด หรือตามที่กฎหมายกำหนดหากมีการทำสัญญา]

## สิทธิของคุณ
- ขอเข้าถึง ขอรับสำเนา หรือขอให้แก้ไขข้อมูลของคุณให้ถูกต้อง
- ขอให้ลบ ระงับการใช้ หรือคัดค้านการประมวลผลข้อมูล
- ถอนความยินยอมเรื่องคุกกี้ได้ทุกเมื่อ โดยไม่กระทบการใช้งานเว็บไซต์
- ร้องเรียนต่อสำนักงานคณะกรรมการคุ้มครองข้อมูลส่วนบุคคล (สคส.)

## ติดต่อเรา
บริษัท เซ็นทรัล ซิสเท็ม อินทิเกรชั่น จำกัด
[ที่อยู่บริษัท]
อีเมล: [อีเมลสำหรับเรื่องข้อมูลส่วนบุคคล เช่น info@voscene.com]
[ชื่อหรือตำแหน่งผู้ดูแลข้อมูลส่วนบุคคล / DPO ถ้ามี]

ปรับปรุงล่าสุด: [วันที่เผยแพร่]"""

# ร่างฉบับก่อน ๆ ที่ยังไม่มีใครแก้ — seed เปลี่ยนเป็นฉบับปัจจุบันให้เอง (ฉบับแรกยังพูดถึงฟอร์มบนเว็บ)
OLD_PRIVACY_DRAFTS = {"fe2750b3606323a3"}


def _fingerprint(value) -> str:
    import hashlib
    return hashlib.sha256((value or "").encode()).hexdigest()[:16]


# ร่างที่เจ้าของเติมข้อมูลไปแล้ว (fingerprint ไม่ตรง) ยังมีบรรทัดเก่าของทีมเว็บที่ไม่จริงแล้วหลังเลิกใช้ฟอร์ม
# แก้ "ทีละบรรทัด" เฉพาะบรรทัดที่ตรงกับข้อความเดิมของเราทุกตัวอักษร — บรรทัดที่เจ้าของเขียน/แก้เองไม่ถูกแตะ
# (เก่า → ใหม่ · ใหม่ = None คือลบบรรทัดนั้น) · ใช้กับทั้งร่างและช่องจริง
PRIVACY_LINE_FIXES = [
    ("- ข้อมูลที่คุณกรอกในแบบฟอร์มติดต่อ: ชื่อ-นามสกุล บริษัท/หน่วยงาน เบอร์โทรศัพท์ อีเมล ขนาดห้องประชุม งบประมาณ ความต้องการ และประเภทคำขอ (ปรึกษา / ขอนัด Demo / ขอใบเสนอราคา)",
     "- ข้อมูลที่คุณให้เมื่อติดต่อเราทาง LINE โทรศัพท์ หรืออีเมล: ชื่อหรือชื่อบัญชี LINE บริษัท/หน่วยงาน เบอร์โทรศัพท์ อีเมล และรายละเอียดความต้องการ ซึ่งทีมงานบันทึกไว้เพื่อติดตามการให้บริการ"),
    ("- ข้อมูลว่าคุณเข้ามาที่เว็บไซต์จากช่องทางใด เช่น ลิงก์โฆษณาหรือโพสต์ที่คลิก (ค่า UTM) หน้าแรกที่เข้าชม และเว็บไซต์ที่พาคุณมา — บันทึกพร้อมแบบฟอร์มเมื่อคุณกดส่งเท่านั้น",
     "- ช่องทางที่คุณรู้จักเรา เช่น โฆษณาหรือโพสต์ที่เห็น — จากที่คุณแจ้ง หรือจากรหัสอ้างอิงที่ปุ่ม LINE บนเว็บไซต์ใส่ไว้ในข้อความแรก (คุณลบรหัสออกก่อนส่งได้)"),
    ("- ช่องทางที่คุณรู้จักเรา เช่น โฆษณาหรือโพสต์ที่เห็น (ถ้าคุณแจ้ง)",
     "- ช่องทางที่คุณรู้จักเรา เช่น โฆษณาหรือโพสต์ที่เห็น — จากที่คุณแจ้ง หรือจากรหัสอ้างอิงที่ปุ่ม LINE บนเว็บไซต์ใส่ไว้ในข้อความแรก (คุณลบรหัสออกก่อนส่งได้)"),
    ("- จำนวนครั้งที่มีการกดปุ่ม LINE หรือปุ่มโทรบนเว็บไซต์ โดยใช้รหัสสุ่มที่หมดอายุเมื่อปิดหน้าต่าง ไม่ผูกกับตัวตนของคุณ",
     "- จำนวนครั้งที่มีการกดปุ่ม LINE หรือปุ่มโทรบนเว็บไซต์ พร้อมหน้าที่เข้าชมและลิงก์ที่พาเข้ามา โดยใช้รหัสสุ่มที่หมดอายุเมื่อปิดหน้าต่าง ไม่ผูกกับตัวตนของคุณ"),
    ("- หมายเลข IP ในกรณีที่ระบบตรวจพบว่าการส่งแบบฟอร์มอาจเป็นสแปมหรือบอท", None),
    ("- ติดต่อกลับ ให้คำปรึกษา นัดสาธิต และจัดทำใบเสนอราคาตามที่คุณร้องขอ (ขั้นตอนก่อนเข้าทำสัญญา)",
     "- ตอบคำถาม ให้คำปรึกษา นัดสาธิต และจัดทำใบเสนอราคาตามที่คุณร้องขอ (ขั้นตอนก่อนเข้าทำสัญญา)"),
    ("- ป้องกันสแปมและการใช้งานเว็บไซต์ในทางที่ผิด (ประโยชน์โดยชอบด้วยกฎหมาย)", None),
    ('- เว็บไซต์ไม่ใช้คุกกี้โฆษณาจนกว่าคุณจะกด "ยอมรับ" ถ้าปฏิเสธ ยังใช้งานเว็บและส่งแบบฟอร์มได้ตามปกติ',
     '- เว็บไซต์ไม่ใช้คุกกี้โฆษณาจนกว่าคุณจะกด "ยอมรับ" ถ้าปฏิเสธ ยังใช้งานเว็บไซต์ได้ตามปกติ'),
]
# บรรทัดที่ต้องเพิ่ม (ถ้ายังไม่มี) ต่อท้ายบรรทัดหลักที่ระบุ
PRIVACY_LINE_INSERTS = [
    ("Cloudflare ซึ่งอาจประมวลผลข้อมูลนอกประเทศไทย",
     "- LINE ในฐานะผู้ให้บริการช่องทางแชต เมื่อคุณติดต่อผ่าน LINE (อยู่ภายใต้นโยบายความเป็นส่วนตัวของ LINE ด้วย)"),
]


def patch_privacy_text(value: str) -> str:
    """แก้บรรทัดเก่าของเราในนโยบาย โดยคงทุกบรรทัดที่เจ้าของเขียนเอง · ไม่มีอะไรต้องแก้ = คืนค่าเดิมทุกตัวอักษร"""
    if not value:
        return value
    fixes = {old: new for old, new in PRIVACY_LINE_FIXES}
    lines, out, changed = value.splitlines(), [], False
    for line in lines:
        key = line.strip()
        if key in fixes:
            changed = True
            if fixes[key] is not None:
                out.append(fixes[key])
            continue
        out.append(line)
        for anchor, extra in PRIVACY_LINE_INSERTS:
            if anchor in line and not any(extra == l.strip() for l in lines):
                out.append(extra)
                changed = True
    return "\n".join(out) if changed else value


# เจ้าของขอ 2026-09-26 ให้แยกฝ่ายขาย/ฝ่ายเทคนิค — ค่าบน production ยังเป็นแบบเดิม (ยังไม่ได้แก้ในหลังบ้าน)
# seed จึงเปลี่ยนให้ตอนบูต เฉพาะเมื่อค่ายังตรงกับของเดิมทุกบรรทัด ถ้าแอดมินแก้เป็นอย่างอื่นแล้วไม่แตะ
CONTACT_PHONE_DEFAULT = "\n".join([
    "ฝ่ายขาย : รจนา 088-886 4660",
    "ฝ่ายเทคนิค : เบนซ์ 099-345 1998",
    "LINE : @CSIPROAV",
])
OLD_CONTACT_PHONES = {
    ("รจนา 088-886 4660", "LINE : @CSIPROAV"),
    ("088-886-4660",),
}


def _lines(value) -> tuple:
    return tuple(l.strip() for l in (value or "").splitlines() if l.strip())


DEFAULT_CONTENT = [
    # ===== Hero Section =====
    ("hero_badge", "AI-Powered AV Control · Now in Thailand", "Badge ใต้ navbar", "hero", "text"),
    ("hero_title_line1", "The voice of", "บรรทัดที่ 1 ของ Headline", "hero", "text"),
    ("hero_title_line2", "smart spaces.", "บรรทัดที่ 2 (สี gradient)", "hero", "text"),
    ("hero_subtitle_th", "ระบบควบคุม AV ขับเคลื่อนด้วย AI ออกแบบเพื่อองค์กรไทย", "บรรทัดภาษาไทย", "hero", "text"),
    ("hero_tagline", "Voice on SCENE · Speak. Control. Transform.", "Slogan", "hero", "text"),
    ("hero_description", "Voscene เปลี่ยนห้องประชุม โรงแรม ห้องเรียน และพื้นที่ event ให้กลายเป็น smart space ที่ควบคุมด้วยภาษาธรรมชาติ ผ่าน AI Thai/English — ราคาประหยัดกว่าระบบควบคุม AV ต่างประเทศ รองรับอุปกรณ์ AV หลากหลายยี่ห้อ — 48 ยี่ห้อ · 1,000+ รุ่น ผ่านโปรโตคอลมาตรฐาน (PJLink · VISCA · webOS/Tizen · DMX ฯลฯ)", "คำอธิบาย Hero", "hero", "textarea"),
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
    ("stat_1_value", "ประหยัดกว่า", "ตัวเลขสถิติ 1", "stats", "text"),
    ("stat_1_label", "ระบบควบคุม AV ต่างประเทศ", "คำอธิบายสถิติ 1", "stats", "text"),
    ("stat_2_value", "<24h", "ตัวเลขสถิติ 2", "stats", "text"),
    ("stat_2_label", "ติดตั้งห้องเดียว Plug & Play", "คำอธิบายสถิติ 2", "stats", "text"),
    ("stat_3_value", "48", "ตัวเลขสถิติ 3", "stats", "text"),
    ("stat_3_label", "ยี่ห้อที่รองรับ · 1,000+ รุ่น", "คำอธิบายสถิติ 3", "stats", "text"),
    ("stat_4_value", "0", "ตัวเลขสถิติ 4 (มี * เล็ก)", "stats", "text"),
    ("stat_4_label", "App ที่ต้องติดตั้ง · Browser-based UI", "คำอธิบายสถิติ 4", "stats", "text"),

    # ===== About / Why =====
    ("about_title", "ทำไมต้องเลือก Voscene", "หัวข้อ About", "about", "text"),
    ("about_description", "ออกแบบมาเทียบชั้นระบบ AV ระดับโลก แต่ราคาประหยัดกว่าระบบควบคุม AV ต่างประเทศ — ใช้ AI สั่งงานด้วยภาษาธรรมชาติ ลดความซับซ้อน รองรับอุปกรณ์ที่ลูกค้ามีอยู่แล้วผ่านโปรโตคอลมาตรฐาน", "คำอธิบาย About", "about", "textarea"),

    # ===== Brand Note =====
    ("brand_note", "ระบบรองรับอุปกรณ์แทบทุกยี่ห้อที่ใช้โปรโตคอลมาตรฐาน — ไม่ต้องมีรุ่นในลิสต์ก็คุมได้ถ้าพูดโปรโตคอลที่รองรับ · ปรับแต่งเพื่อรองรับอุปกรณ์ที่ลูกค้ามีอยู่แล้วได้", "หมายเหตุเรื่อง Brand", "about", "textarea"),

    # ===== LINE Integration =====
    ("line_title", "Text to control. Alerts in real-time.", "หัวข้อ LINE section", "line", "text"),
    ("line_subtitle", "Voscene meets your team where they already are — in LINE.", "คำอธิบาย LINE", "line", "text"),

    # ===== Contact =====
    ("contact_title", "Let's talk.", "หัวข้อ Contact", "contact", "text"),
    # โค้ดติดตามโฆษณา — แก้ที่หน้า /admin/tracking ไม่ใช่หน้าเนื้อหา (ถูกกรองออกจาก /admin/content)
    ("gtm_id", "", "Google Tag Manager ID", "tracking", "text"),
    ("ga4_id", "", "Google Analytics 4 ID", "tracking", "text"),
    ("meta_pixel_id", "", "Meta (Facebook) Pixel ID", "tracking", "text"),
    ("contact_subtitle", "Ready to transform your AV experience? — ทัก LINE หรือโทรหาทีมงานได้โดยตรง ปรึกษาฟรี ไม่มีข้อผูกมัด", "คำอธิบาย Contact", "contact", "textarea"),
    ("contact_phone", CONTACT_PHONE_DEFAULT, "เบอร์โทร (ใส่หลายเบอร์ได้ ขึ้นบรรทัดใหม่)", "contact", "textarea"),
    ("contact_email", "hello@voscene.com", "อีเมล", "contact", "text"),
    ("contact_address", "Bangkok, Thailand · Serving Southeast Asia", "ที่อยู่ (รองรับ 2-3 บรรทัด)", "contact", "textarea"),
    ("contact_hours", "จันทร์-ศุกร์ 09:00-18:00", "เวลาทำการ", "contact", "text"),
    ("contact_facebook", "", "Facebook URL (เช่น https://facebook.com/voscene)", "contact", "text"),
    ("contact_line", "", "LINE Official Account URL หรือ ID (เช่น https://lin.ee/xxxxx หรือ @voscene)", "contact", "text"),

    # ===== Footer =====
    ("footer_company", "Central System Integration Co., Ltd.", "ชื่อบริษัท", "footer", "text"),
    ("footer_tagline", "One touch. Total control. · ซอฟต์แวร์ควบคุม AV สำหรับองค์กร", "คำขวัญ", "footer", "text"),
    ("footer_copyright", "© 2026 Voscene by Central System Integration. All rights reserved.", "Copyright", "footer", "text"),

    # ===== นโยบายความเป็นส่วนตัว (/privacy) =====
    # ช่องจริงเริ่มต้นว่าง = หน้า /privacy และลิงก์ทั้งหมดซ่อนอยู่ · ร่างอยู่อีกช่อง ไม่แสดงบนเว็บ
    ("privacy_policy", "", "นโยบายความเป็นส่วนตัว — ข้อความที่แสดงบนเว็บ (เว้นว่าง = ซ่อนหน้าและลิงก์) · ขึ้นหัวข้อด้วย ## · รายการด้วย -", "privacy", "textarea"),
    ("privacy_policy_draft", PRIVACY_POLICY_DRAFT, "ร่าง (ไม่แสดงบนเว็บ) — ตรวจ/แก้ แล้วคัดลอกไปช่องด้านบนเมื่อพร้อม", "privacy", "textarea"),

    # ===== SEO / Meta =====
    ("seo_title", "Voscene — ซอฟต์แวร์ควบคุม AV สำหรับองค์กร · Enterprise AV Control Software", "Title สำหรับ Search Engine", "seo", "text"),
    ("seo_description", "Voscene — ซอฟต์แวร์ควบคุม AV สำหรับองค์กรและงานราชการ · เปิดเบราว์เซอร์ใช้งานได้ทันที ไม่ต้องติดตั้งแอป ไม่ต้องใช้ Touch Panel ราคาแพง · ตั้งค่าผ่านเบราว์เซอร์ · ราคาประหยัดกว่าระบบควบคุม AV ต่างประเทศ · 18 โมดูลควบคุม: Scene, Video Matrix, Audio, Projector, Smart TV, DMX Lighting, Multi-Room (20 ห้อง/controller · รองรับการขยายได้ 200 ห้อง), PTZ, Auto Tracking, IR, Conference, Calendar, Schedule, Booking (Coming soon · ปฏิทิน พ.ศ.), Video Conferencing, PA + Graphic Paging (กำลังพัฒนา) + AI Assist สั่งงานภาษาไทย/อังกฤษ (นำร่อง) · OAuth + LINE + OTA · รองรับอุปกรณ์ 48 ยี่ห้อ 1,000+ รุ่น · เหมาะกับงานราชการ (ขายขาด · ผ่านเกณฑ์จัดซื้อ)", "Meta Description", "seo", "textarea"),
]


# Aligned with Catalog V2 (Volume 2.0) — Editions section (Contact for pricing, no fixed numbers)
DEFAULT_PACKAGES = [
    {
        "code": "starter", "name": "Voscene Starter",
        "price": "Contact for pricing", "price_unit": "",
        "description": "For single meeting rooms · Best for small offices",
        "features": "1 control unit\nUp to 8 connected devices\n4 configurable scenes (tech-tunable)\nBrowser-based UI (no app install)\n3-level access (Engineer / Admin / User)\nIn-browser settings\nDevice health monitor\nOffline-capable\nEmail support\n1-year warranty",
        "category": "purchase", "sort_order": 1, "is_featured": False,
    },
    {
        "code": "pro", "name": "Voscene Pro",
        "price": "Contact for pricing", "price_unit": "",
        "description": "For multi-room deployments · Best for hotels, universities, enterprises",
        "features": "Everything in Starter\n1 control unit per room\nUnlimited connected devices\nAI command module (BYOL — customer brings own LLM key)\nLINE integration (send commands + alerts)\nUp to 4 PTZ camera control (VISCA over IP)\nAuto video tracking (mic-driven)\nCalendar integration (auto-trigger scenes)\nSchedule rules engine\nVideo conferencing room control\nMulti-room dashboard (20 rooms/controller · รองรับการขยายได้ 200 ห้อง · Master Controller)\nAPI Keys (X-API-Key) for integrations\nOTA software updates + auto-rollback\nEncrypted auto-backup (AES-128, 30-day)\nSecure remote support (encrypted, on-demand)\nPriority phone support\n3-year warranty\nOn-site installation",
        "category": "purchase", "sort_order": 2, "is_featured": True,
    },
    {
        "code": "enterprise", "name": "Voscene Enterprise",
        "price": "Custom quote", "price_unit": "",
        "description": "For large-scale operations · Best for government, large enterprises",
        "features": "Everything in Pro\nUnlimited control units\nCustom protocol integration\nAD / LDAP authentication (กำลังพัฒนา)\nWhite-label option\nOn-premises LLM (optional)\nCentral management\nSLA 24/7\nDedicated account manager\n5-year warranty\nCustom training program\nSource code escrow (opt.)",
        "category": "purchase", "sort_order": 3, "is_featured": False,
    },

    # ===== IR Add-on Kits (network IR blaster — generic, no brand/model) =====
    {
        "code": "addon_base", "name": "Base Kit",
        "price": "Included", "price_unit": "in-box",
        "description": "มาในกล่อง · สำหรับห้องประชุมขนาดเล็ก",
        "features": "Voscene Controller\nIR blaster (network) 1 ตัว\nสำหรับ: ห้องประชุมขนาดเล็ก · คุมอุปกรณ์ IR ในห้องเดียวผ่านเครือข่าย",
        "category": "addon", "sort_order": 10, "is_featured": False,
    },
    {
        "code": "addon_ir_extension", "name": "IR Coverage Kit",
        "price": "Contact for pricing", "price_unit": "",
        "description": "เพิ่มจุดกระจาย IR · สำหรับห้องใหญ่/อุปกรณ์กระจายตัว",
        "features": "IR blaster (network) เพิ่มเติม ต่อโซน\nกระจายสัญญาณ IR ครอบคลุมทั้งห้องผ่าน Wi-Fi/LAN\nสำหรับ: ห้องประชุมใหญ่ · อุปกรณ์อยู่คนละจุด — ไม่ต้องเดินสาย",
        "category": "addon", "sort_order": 11, "is_featured": True,
    },
    {
        "code": "addon_multi_device", "name": "Multi-device Kit",
        "price": "Contact for pricing", "price_unit": "",
        "description": "คุมหลายอุปกรณ์ผ่าน IR พร้อมกัน",
        "features": "IR blaster (network) หลายตัว — 1 ตัว/กลุ่มอุปกรณ์\nคุม TV + Audio + Player พร้อมกันผ่านเครือข่าย\nสำหรับ: คุมหลายอุปกรณ์/หลายตู้ AV พร้อมกัน",
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
                role="owner", is_active=True,
            )
            db.add(user)
            print(f"[seed] created admin user: {settings.ADMIN_USERNAME}")
        # ทางกู้คืน: ถ้าไม่เหลือเจ้าของที่ใช้งานได้เลย (ไม่ควรเกิด — หน้าจัดการบัญชีกันไว้)
        # คืนสิทธิ์เจ้าของให้บัญชี ADMIN_USERNAME ตอนบูต ไม่งั้นไม่มีใครเข้าหน้าตั้งค่าได้
        elif not db.query(User).filter_by(role="owner", is_active=True).first():
            admin = db.query(User).filter_by(username=settings.ADMIN_USERNAME).first()
            admin.role, admin.is_active = "owner", True
            print(f"[seed] no active owner left - restored owner role to {settings.ADMIN_USERNAME}")

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
        # Phase-14 reposition: retire off-message values (voice-first brand line, the
        # AI-forward meta lead + internal AES-128 spec leak, and a mismatched stat
        # label). Force the new default ONLY while the stored value still carries the
        # retired marker — once updated it stops forcing, so a later admin edit sticks.
        REPOSITION_FORCE = {
            "seo_title": "The voice of smart spaces",
            "footer_tagline": "The voice of smart spaces",
            "seo_description": "17 โมดูลควบคุม",
            "stat_3_label": "AI-Driven",
        }
        # 2026-08-31: ปิดที่ปรึกษา AI บนเว็บไว้ก่อน (AI_CONSULT_ENABLED=False) จึงต้องเลิก
        # โฆษณาว่า "AI วิเคราะห์ให้ทันที" บนหน้า /contact ด้วย ไม่งั้นเว็บสัญญาสิ่งที่ไม่มี
        # บังคับค่าใหม่เฉพาะตอนที่สวิตช์ยังปิด และเฉพาะขณะที่ค่าเดิมยังมีคำที่เลิกใช้ —
        # พอแอดมินแก้ข้อความเองแล้วก็หยุดบังคับ (รูปแบบเดียวกับ REPOSITION_FORCE)
        AI_CONSULT_RETIRE = {} if settings.AI_CONSULT_ENABLED else {"contact_subtitle": "วิเคราะห์"}
        FORM_RETIRE = {"contact_subtitle": "กรอก"}
        # 2026-09-27 เจ้าของตัดสินถ้อยคำก่อนยิงโฆษณา: เลิกตัวเลข "ประหยัด 60-80%" (ไม่มีเอกสารเทียบราคารองรับ)
        # "ติดตั้งใน 24 ชั่วโมง" (ตัดออก ไม่สัญญาระยะเวลา) และ "~200 ห้อง" (ใช้ "รองรับการขยายได้ 200 ห้อง") — แทนเฉพาะวลีเก่าในค่าที่เก็บอยู่ ส่วนอื่นที่แอดมินแก้ไว้คงเดิม
        # stat_1 เป็นคู่ตัวเลข/คำอธิบาย → แทนเฉพาะเมื่อยังเป็นค่าเดิมทั้งช่อง
        CLAIM_REWRITES = {
            "stat_1_value": [("60-80%", "ประหยัดกว่า")],
            "stat_1_label": [("ประหยัดกว่าระบบ AV แบรนด์ใหญ่", "ระบบควบคุม AV ต่างประเทศ")],
            "hero_description": [("ราคาประหยัดกว่าระบบ AV ระดับโลก 60-80%", "ราคาประหยัดกว่าระบบควบคุม AV ต่างประเทศ"),
                                 ("ติดตั้งใน 24 ชั่วโมง ", "")],
            "about_description": [("แต่ราคาประหยัดกว่า 60-80%", "แต่ราคาประหยัดกว่าระบบควบคุม AV ต่างประเทศ")],
            "seo_description": [("ติดตั้งใน 24 ชั่วโมง · ", ""),
                                ("ประหยัด 60-80%", "ราคาประหยัดกว่าระบบควบคุม AV ต่างประเทศ"),
                                ("ออกแบบให้ขยายถึง ~200 ห้อง", "รองรับการขยายได้ 200 ห้อง"),
                                ("(20 ห้อง/controller · รองรับการขยาย)", "(20 ห้อง/controller · รองรับการขยายได้ 200 ห้อง)")],
        }
        WHOLE_FIELD = {"stat_1_value", "stat_1_label"}
        added = 0
        migrated = 0
        legal_forced = 0
        reposition_forced = 0
        ai_retired = 0
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
                # Force reposition fixes while the retired phrase is still present.
                if key in REPOSITION_FORCE and REPOSITION_FORCE[key] in (existing.value or ""):
                    existing.value = value
                    reposition_forced += 1
                    changed = True
                # เลิกข้อความที่อ้าง AI วิเคราะห์ ตอนที่ปิดที่ปรึกษา AI ไว้
                if key in AI_CONSULT_RETIRE and AI_CONSULT_RETIRE[key] in (existing.value or ""):
                    existing.value = value
                    ai_retired += 1
                    changed = True
                # 2026-09-27 เลิกใช้ฟอร์มบนเว็บ → ข้อความที่ยังชวน "กรอก" ต้องเปลี่ยน
                # (บังคับเฉพาะขณะยังมีคำนั้น พอแอดมินแก้เองแล้วก็หยุด — แบบเดียวกับด้านบน)
                if key in FORM_RETIRE and FORM_RETIRE[key] in (existing.value or ""):
                    existing.value = value
                    ai_retired += 1
                    changed = True
                if key == "contact_phone" and _lines(existing.value) in OLD_CONTACT_PHONES:
                    existing.value = value
                    changed = True
                for old, new in CLAIM_REWRITES.get(key, []):
                    current = existing.value or ""
                    if key in WHOLE_FIELD:
                        if current.strip() == old:
                            existing.value = new
                            changed = True
                    elif old in current:
                        existing.value = current.replace(old, new)
                        changed = True
                # ร่างนโยบายที่ยังเป็นฉบับแรกทุกตัวอักษร (ยังไม่มีใครแก้) → อัปเดตเป็นฉบับไม่มีฟอร์ม
                # ถ้าเจ้าของแก้ร่างไปแล้ว ไม่แตะ
                if key == "privacy_policy_draft" and _fingerprint(existing.value) in OLD_PRIVACY_DRAFTS:
                    existing.value = value
                    changed = True
                # ร่าง/ช่องจริงที่เจ้าของเติมข้อมูลแล้ว → แก้เฉพาะบรรทัดเก่าของเรา คงส่วนที่เจ้าของเขียน
                if key in ("privacy_policy_draft", "privacy_policy"):
                    patched = patch_privacy_text(existing.value)
                    if patched != existing.value:
                        existing.value = patched
                        changed = True
                if changed:
                    migrated += 1
            else:
                db.add(Content(key=key, value=value, label=label, section=section, field_type=field_type))
                added += 1
        print(f"[seed] content: +{added} new · ~{migrated} migrated · {legal_forced} legal-forced · {reposition_forced} reposition-forced · {ai_retired} ai-consult-retired ({len(DEFAULT_CONTENT)} total defined)")

        # Default packages — add new, and migrate features of core editions (starter/pro/enterprise)
        # to keep them aligned with the latest catalog. Add-on kits are NOT auto-migrated
        # in general (admin may have customized pricing) — EXCEPT the IR kits, which are
        # force-corrected if their features still contain a stale phrase: either the obsolete
        # wired-IR design (emitter cable / CAT5 extender / Y-splitter) OR a brand/model name
        # (Broadlink / RM4) that slipped in before. The site must use generic device terms
        # only, so both get rewritten to "IR blaster (network)". Price/price_unit are preserved.
        pkg_added = 0
        pkg_migrated = 0
        CORE_EDITIONS = {"starter", "pro", "enterprise"}
        IR_KIT_CODES = {"addon_base", "addon_ir_extension", "addon_multi_device"}
        IR_KIT_STALE_PHRASES = ("IR emitter cable", "IR Extender", "IR Y-splitter", "CAT5", "เดินสาย IR", "2U Controller", "Broadlink", "RM4")
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
            elif pkg_data["code"] in IR_KIT_CODES:
                # Force-correct only if stale wired-IR phrasing remains; keep operator's price.
                cur = existing.features or ""
                if any(p in cur for p in IR_KIT_STALE_PHRASES):
                    existing.features = pkg_data["features"]
                    existing.description = pkg_data["description"]
                    existing.name = pkg_data["name"]
                    pkg_migrated += 1
        print(f"[seed] packages: +{pkg_added} new · ~{pkg_migrated} migrated ({len(DEFAULT_PACKAGES)} total defined)")

        db.commit()
        print("[seed] done")
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()

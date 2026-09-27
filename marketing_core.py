"""ข้อมูลอ้างอิงและตรรกะของระบบการตลาด — ไม่แตะ HTTP ไม่แตะ template

แยกออกจาก marketing.py (routes) เพื่อให้ทดสอบได้ตรง ๆ และให้ migrations.py ใช้
ฟังก์ชันเดียวกันตอนเติมข้อมูลย้อนหลัง · นิยามตัวชี้วัดทั้งหมดอธิบายไว้ใน
docs/MARKETING-GUIDE.md — ถ้าแก้ความหมายตรงนี้ต้องแก้เอกสารนั้นด้วย
"""
import csv
import io
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

BKK = timezone(timedelta(hours=7))

UNKNOWN_SOURCE = "ไม่ทราบแหล่งที่มา"


# ============ บริการ ============
# claim = สถานะของข้อความโฆษณา ไม่ใช่สถานะงานพัฒนา:
#   ready       ใช้โฆษณาได้ตามที่เขียน
#   conditions  ใช้ได้ แต่ต้องพ่วงเงื่อนไขใน `note` ทุกครั้ง
#   unconfirmed ยังไม่มีใบยืนยันจาก SW/PM — ห้ามโฆษณาว่าพร้อมส่งมอบ
SERVICES = [
    {"key": "one_touch", "label": "เปิด–ปิดและเตรียมห้องประชุมปุ่มเดียว",
     "claim": "ready", "note": ""},
    {"key": "single_panel", "label": "รวมรีโมตไว้บนหน้าควบคุมเดียว",
     "claim": "ready", "note": ""},
    {"key": "floorplan", "label": "หน้าควบคุมแบบกราฟิกตามผังห้อง",
     "claim": "conditions",
     "note": "ช่างเป็นผู้วางผังและจุดอุปกรณ์ให้ตอนติดตั้ง ลูกค้าไม่ได้แก้ผังเอง"},
    {"key": "multi_room", "label": "ควบคุมหลายห้องจากศูนย์กลาง",
     "claim": "conditions",
     "note": "สูงสุด 20 ห้องต่อชุดควบคุม และทุกห้องต้องอยู่ในวงเครือข่ายเดียวกัน · "
             "เกินกว่านั้นใช้คำว่า \"รองรับการขยายได้ 200 ห้อง\" (เจ้าของตัดสิน 2026-09-27 · "
             "SW 2026-08-02: Master Controller ยังไม่มีโค้ด — เช็คสถานะก่อนรับงานเกิน 20 ห้อง)"},
    {"key": "integrator", "label": "ระบบควบคุมสำหรับบริษัทติดตั้ง AV / ผู้รับเหมา",
     "claim": "conditions",
     "note": "ใช้แนวทาง \"คุณรับงานติดตั้ง เราช่วยออกแบบและเชื่อมระบบควบคุม\" (เจ้าของ 2026-09-27) · "
             "ห้ามระบุส่วนลด ส่วนแบ่ง หรือเงื่อนไขราคาพันธมิตร — เจ้าของกำหนดเป็นรายกรณี"},
    {"key": "other", "label": "อื่น ๆ / ยังไม่ระบุ", "claim": "ready", "note": ""},
]
SERVICE_MAP = {s["key"]: s for s in SERVICES}

CLAIM_LABELS = {
    "ready": "ใช้โฆษณาได้",
    "conditions": "ต้องระบุเงื่อนไข",
    "unconfirmed": "ยังไม่ยืนยัน — ห้ามโฆษณาว่าพร้อมส่งมอบ",
}


# ============ ช่องทาง ============
# utm_source / utm_medium มาตรฐานของแต่ละช่องทาง — ลิงก์ที่ระบบสร้างใช้ค่านี้เสมอ
# spend=True = ช่องทางที่บันทึกค่าโฆษณาได้
CHANNELS = [
    {"key": "google_ads", "label": "Google Ads", "source": "google", "medium": "cpc",
     "open_url": "https://ads.google.com/", "spend": True},
    {"key": "facebook_ads", "label": "Facebook / Instagram Ads", "source": "facebook",
     "medium": "paid_social", "open_url": "https://adsmanager.facebook.com/", "spend": True},
    {"key": "facebook_page", "label": "Facebook Page", "source": "facebook", "medium": "social",
     "open_url": "https://www.facebook.com/", "spend": False},
    {"key": "facebook_group", "label": "กลุ่ม Facebook", "source": "facebook", "medium": "group",
     "open_url": "https://www.facebook.com/groups/", "spend": False},
    {"key": "tiktok", "label": "TikTok", "source": "tiktok", "medium": "social",
     "open_url": "https://www.tiktok.com/", "spend": True},
    {"key": "youtube", "label": "YouTube", "source": "youtube", "medium": "video",
     "open_url": "https://studio.youtube.com/", "spend": True},
    {"key": "line_oa", "label": "LINE OA", "source": "line", "medium": "social",
     "open_url": "https://manager.line.biz/", "spend": True},
    {"key": "email", "label": "อีเมล", "source": "email", "medium": "email",
     "open_url": "", "spend": False},
    {"key": "other", "label": "ช่องทางอื่น (มี UTM)", "source": "", "medium": "",
     "open_url": "", "spend": True},
]
# ช่องทางที่ระบบจัดให้เองจาก referrer — ไม่ได้เลือกตอนสร้างลิงก์
DERIVED_CHANNELS = [
    {"key": "organic_search", "label": "ค้นหาทั่วไป (ไม่ใช่โฆษณา)"},
    {"key": "referral", "label": "ลิงก์จากเว็บอื่น"},
    {"key": "unknown", "label": UNKNOWN_SOURCE},
]
CHANNEL_MAP = {c["key"]: c for c in CHANNELS + DERIVED_CHANNELS}
REPORT_CHANNELS = [c["key"] for c in CHANNELS] + [c["key"] for c in DERIVED_CHANNELS]
SPEND_CHANNELS = [c["key"] for c in CHANNELS if c.get("spend")]


def channel_label(key: str) -> str:
    return CHANNEL_MAP.get(key or "unknown", CHANNEL_MAP["unknown"])["label"]


_SEARCH_HOSTS = ("google.", "bing.", "yahoo.", "duckduckgo.", "baidu.", "yandex.")


def classify_channel(source: str, medium: str, referrer: str = "", own_host: str = "") -> str:
    """แปลง UTM (หรือ referrer ถ้าไม่มี UTM) เป็นคีย์ช่องทาง · ไม่รู้ = "unknown" ไม่เดา"""
    s = (source or "").strip().lower()
    m = (medium or "").strip().lower()
    if s:
        if s in ("google", "adwords") and m in ("cpc", "ppc", "paid", "paid_search"):
            return "google_ads"
        if s in ("facebook", "fb", "instagram", "ig", "meta"):
            if m in ("paid_social", "paid", "cpc", "ads", "paidsocial"):
                return "facebook_ads"
            if m in ("group", "fb_group"):
                return "facebook_group"
            return "facebook_page"
        if s == "tiktok":
            return "tiktok"
        if s in ("youtube", "yt"):
            return "youtube"
        if s == "line":
            return "line_oa"
        if m == "email" or s == "email":
            return "email"
        return "other"
    host = (urlsplit(referrer).hostname or "").lower() if referrer else ""
    if _same_site(host, own_host):
        host = ""  # คลิกภายในเว็บเอง ไม่ใช่แหล่งที่มา
    if host:
        if any(h in host for h in _SEARCH_HOSTS):
            return "organic_search"
        return "referral"
    return "unknown"


# ============ ขั้นการขาย / ผลคัดกรอง ============

SALES_STAGES = [
    ("new", "ใหม่ · รอติดต่อ"),
    ("contacted", "ติดต่อแล้ว"),
    ("demo", "นัดปรึกษาออกแบบ"),
    ("quoted", "เสนอราคา"),
    ("won", "ปิดงาน"),
    ("lost", "ไม่สำเร็จ"),
]
SALES_STAGE_LABELS = dict(SALES_STAGES)

QUALIFICATIONS = [
    ("pending", "รอตรวจ"),
    ("fit", "ตรงกลุ่ม"),
    ("unfit", "นอกกลุ่ม"),
    ("spam", "สงสัยสแปม"),
]
QUALIFICATION_LABELS = dict(QUALIFICATIONS)

CONTACT_METHODS = [
    ("line", "LINE"), ("phone", "โทรศัพท์"), ("email", "อีเมล"),
    ("walkin", "พบตัว / งานแสดงสินค้า / แนะนำต่อ"), ("web_form", "ฟอร์มบนเว็บ (รุ่นเก่า)"),
]
CONTACT_METHOD_LABELS = dict(CONTACT_METHODS)

# ============ หมวดเนื้อหา + แม่แบบ — เป็นแนวทาง ไม่ใช่โพสต์ (เจ้าของ 2026-09-27) ============
# ไม่มีชุดสาธิตควบคุมอุปกรณ์จริง → ห้ามคำว่า Demo / สาธิต · คลิปใช้บันทึกหน้าจอซอฟต์แวร์
AUDIENCES = [
    ("existing_customer", "ลูกค้าเดิมของ CSI"),
    ("room_admin", "ผู้ดูแลห้องประชุม / ผู้ใช้ห้อง"),
    ("it_team", "ทีม IT / ผู้ดูแลระบบ"),
    ("building", "ฝ่ายอาคาร"),
    ("partner", "พันธมิตร / ผู้ติดตั้ง"),
]
AUDIENCE_LABELS = dict(AUDIENCES)
CTAS = ["ส่งรายการอุปกรณ์เพื่อประเมินการเชื่อมต่อ", "นัดปรึกษาออกแบบระบบ"]
CONTENT_TEMPLATES = [
    {"key": "before_after", "title": "ก่อน–หลัง: จากหลายรีโมตเป็นหน้าควบคุมเดียว",
     "service": "single_panel", "audience": "existing_customer", "cta": CTAS[0],
     "outline": "\n".join([
         "ก่อน: รีโมตหลายตัว / ขั้นตอนเปิดห้องที่ยุ่งยาก",
         "หลัง: หน้าควบคุมเดียวที่รวมอุปกรณ์เดิมที่รองรับ",
         "เงื่อนไข: ตรวจรุ่น พอร์ต และโปรโตคอลก่อน — ไม่รับประกันว่าใช้ของเดิมได้ทั้งหมด"])},
    {"key": "screen_clip", "title": "คลิปหน้าจอควบคุม: กดปุ่มเดียวแล้วซีนทำงาน",
     "service": "one_touch", "audience": "room_admin", "cta": CTAS[1],
     "outline": "\n".join([
         "บันทึกหน้าจอซอฟต์แวร์: กด “เริ่มประชุม” → ซีนเปลี่ยน → กด “เลิกประชุม”",
         "ห้ามสื่อว่าเป็นการควบคุมอุปกรณ์จริงในคลิป (ยังไม่มีชุดสาธิต)",
         "เงื่อนไข: ควบคุมได้เฉพาะอุปกรณ์ที่รองรับและผ่านการตั้งค่าแล้ว"])},
    {"key": "user_problem", "title": "แก้ปัญหาผู้ใช้เปิดห้องประชุมไม่เป็น",
     "service": "one_touch", "audience": "room_admin", "cta": CTAS[1],
     "outline": "\n".join([
         "ปัญหา: ต้องเรียกเจ้าหน้าที่ทุกครั้ง / ไม่รู้ลำดับเปิดเครื่อง",
         "ทางแก้: ผู้ใช้เห็นเฉพาะปุ่มที่ต้องใช้ ช่างตั้งค่าให้ตอนติดตั้ง"])},
    {"key": "multi_room_it", "title": "ดูแลหลายห้องจากจุดเดียว สำหรับทีม IT",
     "service": "multi_room", "audience": "it_team", "cta": CTAS[1],
     "outline": "\n".join([
         "ปัญหา: ต้องเดินดูทีละห้อง",
         "ทางแก้: Dashboard ดูสถานะและสั่งงานอุปกรณ์ที่รองรับ",
         "เงื่อนไขทุกครั้ง: สูงสุด 20 ห้องต่อชุดควบคุม และทุกห้องอยู่ในเครือข่ายเดียวกัน"])},
    {"key": "installer", "title": "เพิ่มระบบควบคุมในงานของผู้ติดตั้ง",
     "service": "integrator", "audience": "partner", "cta": CTAS[1],
     "outline": "\n".join([
         "แนวทาง: “คุณรับงานติดตั้ง เราช่วยออกแบบและเชื่อมระบบควบคุม”",
         "ห้ามระบุส่วนลด ส่วนแบ่ง หรือเงื่อนไขราคาพันธมิตร"])},
]

REQUEST_TYPES = [("consult", "ปรึกษา / ประเมิน"), ("demo", "ขอนัดปรึกษาออกแบบ"), ("quote", "ขอใบเสนอราคา")]
REQUEST_TYPE_LABELS = dict(REQUEST_TYPES)

# สถานะเดิม (Lead.status) → (sales_stage, qualification) ใช้ตอน migrate ครั้งเดียว
# new_in_scope/new_out_scope เป็นผลของ AI ไม่ใช่คนตรวจ → ผลคัดกรองเป็น "รอตรวจ"
# (ผลของ AI ยังดูได้ที่ ai_in_scope เหมือนเดิม)
LEGACY_STATUS_MAP = {
    "new": ("new", "pending"),
    "new_in_scope": ("new", "pending"),
    "new_out_scope": ("new", "pending"),
    "anonymous": ("new", "pending"),
    "contacted": ("contacted", "pending"),
    "quoted": ("quoted", "pending"),
    "won": ("won", "pending"),
    "lost": ("lost", "pending"),
    "spam": ("new", "spam"),
}


def legacy_status_to_new(status: str) -> tuple:
    return LEGACY_STATUS_MAP.get((status or "").strip(), ("new", "pending"))


CAMPAIGN_GOALS = [
    ("demo", "นัดปรึกษาออกแบบระบบ"),
    ("quote", "ขอใบเสนอราคา"),
    ("lead", "ให้กรอกฟอร์ม / ติดต่อ"),
    ("awareness", "สร้างการรับรู้"),
]
CAMPAIGN_GOAL_LABELS = dict(CAMPAIGN_GOALS)
CAMPAIGN_STATUSES = [
    ("draft", "ร่าง"), ("active", "กำลังทำ"), ("paused", "พัก"),
    ("ended", "จบแล้ว"), ("archived", "เก็บเข้าคลัง"),
]
CAMPAIGN_STATUS_LABELS = dict(CAMPAIGN_STATUSES)

CONTENT_STATUSES = [
    ("draft", "ร่าง"), ("review", "รอตรวจ"), ("ready", "พร้อมลง"), ("published", "เผยแพร่แล้ว"),
]
CONTENT_STATUS_LABELS = dict(CONTENT_STATUSES)

GROUP_POST_STATUSES = [
    ("queued", "รอลง"), ("awaiting_approval", "รออนุมัติ"),
    ("published", "เผยแพร่แล้ว"), ("rejected", "ถูกปฏิเสธ"),
]
GROUP_POST_STATUS_LABELS = dict(GROUP_POST_STATUSES)

RELEVANCE = [("high", "ตรงมาก"), ("medium", "ปานกลาง"), ("low", "น้อย")]
RELEVANCE_LABELS = dict(RELEVANCE)


# ============ Lead: ซ้ำ / สแปม ============

def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("66") and len(digits) in (11, 12):
        digits = "0" + digits[2:]
    return digits if len(digits) >= 8 else ""


def normalize_email(email: str) -> str:
    email = (email or "").strip().lower()
    return email if "@" in email else ""


_URL_RE = re.compile(r"https?://|www\.", re.I)
# ต่ำพอที่คนวางข้อความ (paste) แล้วกดส่งทันทียังไม่โดน — ป้ายนี้ทำให้ไม่ถูกนับใน
# "Lead ไม่ซ้ำ" จึงต้องระวังจับคนจริงผิด
MIN_FILL_MS = 1500


def spam_signals(requirement: str, fill_ms: Optional[int]) -> str:
    """คืนเหตุผลที่น่าสงสัย ("" = ไม่พบ) — ใช้ติดป้ายเท่านั้น ไม่ลบ ไม่บล็อก

    fill_ms มาจากสคริปต์หน้าเว็บ (เวลาตั้งแต่แตะฟอร์มครั้งแรกจนกดส่ง) ถ้าไม่มีค่า
    (หน้าเก่าในแคช / ปิด JS) ถือว่าไม่รู้ ไม่นับเป็นสัญญาณ
    """
    if fill_ms is not None and 0 <= fill_ms < MIN_FILL_MS:
        return "too_fast"
    if len(_URL_RE.findall(requirement or "")) >= 3:
        return "many_links"
    return ""


SPAM_REASON_LABELS = {
    "honeypot": "กรอกช่องที่คนมองไม่เห็น (บอท)",
    "too_fast": "กรอกฟอร์มเร็วผิดปกติ",
    "many_links": "มีลิงก์หลายลิงก์ในข้อความ",
    "manual": "ทีมงานตั้งเอง",
}


# ============ UTM ============

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")


def slugify(text: str, max_len: int = 60) -> str:
    """ภาษาไทยตัดทิ้ง เหลือ a-z0-9 และขีด — ชื่อ UTM ต้องเป็นมาตรฐานเดียวกันทุกลิงก์"""
    s = (text or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:max_len].strip("-")


def valid_code(code: str) -> bool:
    return bool(code) and len(code) <= 80 and bool(_SLUG_RE.match(code))


def site_host(app_url: str) -> str:
    return (urlsplit(app_url).hostname or "").lower()


def _same_site(host: str, own_host: str) -> bool:
    if not host or not own_host:
        return False
    bare = lambda h: h[4:] if h.startswith("www.") else h  # noqa: E731
    return bare(host) == bare(own_host)


def normalize_destination(dest: str, app_url: str) -> tuple:
    """ตรวจหน้าปลายทาง → (URL เต็ม, ข้อความผิดพลาด)

    รับ path ในเว็บ ("/features") หรือ URL เต็มของเว็บเราเท่านั้น ลิงก์ติดตามที่พา
    ไปเว็บอื่นวัดผลอะไรไม่ได้ และเปิดทางให้ระบบถูกใช้สร้างลิงก์หลอก
    """
    dest = (dest or "").strip()
    base = (app_url or "").rstrip("/")
    if not dest:
        return "", "กรุณาระบุหน้าเว็บปลายทาง"
    if dest.startswith("/") and not dest.startswith("//"):
        dest = base + dest
    parts = urlsplit(dest)
    if parts.scheme not in ("https", "http"):
        return "", "หน้าปลายทางต้องเป็น path ในเว็บ เช่น /features หรือ URL ที่ขึ้นต้นด้วย https://"
    if parts.scheme == "http" and parts.hostname not in ("localhost", "127.0.0.1"):
        return "", "ใช้ https:// เท่านั้น"
    if not _same_site((parts.hostname or "").lower(), site_host(app_url)):
        return "", f"หน้าปลายทางต้องอยู่ในเว็บ {site_host(app_url)} เท่านั้น"
    if any(c in dest for c in " \t\r\n<>\"'"):
        return "", "URL มีอักขระที่ไม่อนุญาต"
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path or "/", parts.query, "")), ""


def build_utm_url(destination: str, source: str, medium: str, campaign: str,
                  content: str = "", term: str = "") -> str:
    """ต่อ UTM เข้ากับ URL ปลายทาง (ทับค่า utm_* เดิม คง query อื่นไว้)"""
    parts = urlsplit(destination)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith("utm_")]
    utm = [("utm_source", source), ("utm_medium", medium), ("utm_campaign", campaign)]
    if content:
        utm.append(("utm_content", content))
    if term:
        utm.append(("utm_term", term))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query + utm), ""))


def content_utm(item_id: int, title: str = "") -> str:
    tail = slugify(title, 30)
    return f"ci{item_id}-{tail}" if tail else f"ci{item_id}"


def group_post_utm(post_id: int) -> str:
    return f"fg{post_id}"


_CI_RE = re.compile(r"^ci(\d+)(?:-|$)")
_FG_RE = re.compile(r"^fg(\d+)$")


def parse_content_ref(utm_content: str) -> tuple:
    """utm_content → (content_item_id, group_post_id) ตามรูปแบบที่ระบบสร้าง"""
    c = (utm_content or "").strip().lower()
    m = _CI_RE.match(c)
    if m:
        return int(m.group(1)), None
    m = _FG_RE.match(c)
    if m:
        return None, int(m.group(1))
    return None, None


_CHAT_REF_RE = re.compile(r"(?:รหัสอ้างอิง\s*[:：]\s*)?([a-z0-9_\-]+(?:/[a-z0-9_.\-]+){0,2})", re.I)


def parse_chat_ref(text: str) -> Optional[dict]:
    """อ่านรหัสอ้างอิงที่ปุ่ม LINE บนเว็บพิมพ์ไว้ในข้อความแรก (vs-track.js → chatRef)

    รับได้ทั้งข้อความแชตทั้งก้อน หรือเฉพาะรหัส · รูปแบบ:
      แคมเปญ/source.medium[/content]  → มาจากลิงก์ติดตาม
      web · web/โฮสต์                  → เข้าเว็บตรง / มาจากเว็บอื่น (ไม่มี UTM)
    อ่านไม่ออก → None (ไม่เดา)
    """
    text = (text or "").strip()
    if not text:
        return None
    marked = re.search(r"รหัสอ้างอิง\s*[:：]\s*([^\s)]+)", text)
    raw = (marked.group(1) if marked else text).strip().lower()
    if not _CHAT_REF_RE.fullmatch(raw):
        return None
    parts = raw.split("/")
    if parts[0] == "web":
        host = parts[1] if len(parts) > 1 else ""
        return {"utm_source": "", "utm_medium": "", "utm_campaign": "", "utm_content": "",
                "referrer": f"https://{host}/" if host else ""}
    if len(parts) < 2 or "." not in parts[1]:
        return None
    source, medium = parts[1].split(".", 1)
    campaign = "" if parts[0] == "-" else parts[0]
    return {"utm_source": source, "utm_medium": medium, "utm_campaign": campaign,
            "utm_content": parts[2] if len(parts) > 2 else "", "referrer": ""}


def clean_utm_value(value: str) -> str:
    """ค่าที่มาจากเบราว์เซอร์ — ตัดความยาว ตัดอักขระควบคุม ไม่แปลงอย่างอื่น"""
    value = re.sub(r"[\x00-\x1f\x7f]", "", (value or "")).strip()
    return value[:128]


def clean_page_url(value: str, limit: int = 512) -> str:
    value = re.sub(r"[\x00-\x1f\x7f]", "", (value or "")).strip()
    if value and urlsplit(value).scheme not in ("http", "https"):
        return ""
    return value[:limit]


# ============ เวลา ============

def bkk_today() -> date:
    return datetime.now(BKK).date()


def bkk_range_to_utc(start: date, end: date) -> tuple:
    """ช่วงวันที่ (เวลาไทย รวมวันสุดท้าย) → datetime UTC แบบ naive ให้เทียบกับ created_at"""
    start_utc = datetime(start.year, start.month, start.day) - timedelta(hours=7)
    end_utc = datetime(end.year, end.month, end.day) + timedelta(days=1) - timedelta(hours=7)
    return start_utc, end_utc


def utc_to_bkk(dt: Optional[datetime]) -> Optional[datetime]:
    return dt + timedelta(hours=7) if dt else None


def parse_date(value: str) -> Optional[date]:
    """รับ YYYY-MM-DD หรือ DD/MM/YYYY (ปี พ.ศ. แปลงให้) · ผิดรูปแบบคืน None"""
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            d = datetime.strptime(value, fmt).date()
        except ValueError:
            continue
        if d.year > 2400:
            d = d.replace(year=d.year - 543)
        return d
    return None


def parse_money(value) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().replace(",", "").replace("฿", "").replace("THB", "").strip()
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return v if v >= 0 else None


def parse_int(value) -> Optional[int]:
    s = str(value or "").strip().replace(",", "")
    if not s:
        return None
    try:
        v = int(float(s))
    except ValueError:
        return None
    return v if v >= 0 else None


# ============ ค่าโฆษณา / CSV ============

SPEND_CSV_COLUMNS = ["date", "channel", "campaign", "spend", "impressions", "clicks", "currency"]


def spend_dedupe_key(d: date, channel: str, campaign_key: str) -> str:
    return f"{d.isoformat()}|{channel}|{(campaign_key or '').strip().lower()}"


def sample_spend_csv() -> str:
    """ไฟล์ตัวอย่าง — คอลัมน์ตรงกับที่ parse_spend_csv รับ"""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(SPEND_CSV_COLUMNS)
    w.writerow(["2026-10-01", "google_ads", "one-touch-gov-q4", "1250.50", "8400", "132", "THB"])
    w.writerow(["2026-10-01", "facebook_ads", "one-touch-gov-q4", "900", "15000", "210", "THB"])
    w.writerow(["2026-10-02", "tiktok", "", "300", "", "", "THB"])
    return out.getvalue()


def parse_spend_csv(text: str, campaign_codes: dict) -> list:
    """แปลง CSV เป็นแถวพร้อมผลตรวจ · campaign_codes = {code: id}

    คืน list ของ dict: row (เลขบรรทัด), ok, error, date, channel, campaign_id,
    campaign_label, spend, impressions, clicks, currency, key
    """
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []
    header = {h.strip().lower().lstrip("﻿"): h for h in reader.fieldnames if h}
    missing = [c for c in ("date", "channel", "spend") if c not in header]
    if missing:
        return [{"row": 1, "ok": False, "error": "ไม่มีคอลัมน์: " + ", ".join(missing)}]
    rows, seen = [], set()
    for i, raw in enumerate(reader, start=2):
        get = lambda k: (raw.get(header[k]) or "").strip() if k in header else ""  # noqa: E731
        if not any((v or "").strip() for v in raw.values() if isinstance(v, str)):
            continue
        err = []
        d = parse_date(get("date"))
        if not d:
            err.append("วันที่ไม่ถูกต้อง (ใช้ YYYY-MM-DD)")
        channel = get("channel").lower()
        if channel not in SPEND_CHANNELS:
            err.append(f"ช่องทาง '{channel}' ไม่รู้จัก")
        spend = parse_money(get("spend"))
        if spend is None:
            err.append("ค่าโฆษณาต้องเป็นตัวเลข ≥ 0")
        currency = (get("currency") or "THB").upper()
        if currency != "THB":
            err.append("รองรับเฉพาะ THB")
        label = get("campaign")
        code = slugify(label, 80) if label else ""
        campaign_id = campaign_codes.get(code) if code else None
        key = spend_dedupe_key(d, channel, code or label) if d else ""
        if key and key in seen:
            err.append("ซ้ำกับแถวก่อนหน้าในไฟล์เดียวกัน")
        seen.add(key)
        rows.append({
            "row": i, "ok": not err, "error": " · ".join(err),
            "date": d.isoformat() if d else get("date"), "channel": channel,
            "campaign_id": campaign_id, "campaign_label": label,
            "spend": spend, "impressions": parse_int(get("impressions")),
            "clicks": parse_int(get("clicks")), "currency": currency, "key": key,
        })
    return rows


# ============ ส่งออก CSV ============

_FORMULA_PREFIX = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value) -> str:
    """กันสูตร Excel/Sheets ในข้อมูลที่ลูกค้ากรอกเอง (CSV injection)"""
    if value is None:
        return ""
    s = str(value)
    if s.startswith(_FORMULA_PREFIX):
        # ตัวเลขติดลบที่เราคำนวณเองไม่มีในรายงานนี้ จึงใส่ ' นำหน้าได้ทุกกรณี
        return "'" + s
    return s


def to_csv(header: list, rows: list) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([csv_safe(h) for h in header])
    for r in rows:
        w.writerow([csv_safe(v) for v in r])
    # BOM ให้ Excel เปิดภาษาไทยถูก
    return "﻿" + out.getvalue()


def cost_per(spend: Optional[float], count: int) -> Optional[float]:
    """ต้นทุนต่อหน่วย · ไม่มีค่าโฆษณา หรือไม่มี Lead = None (แสดง "—") ไม่หารศูนย์"""
    if spend is None or not count:
        return None
    return spend / count

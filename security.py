"""ชั้นป้องกันพื้นฐานของเว็บ — จำกัดจำนวนครั้งต่อ IP · ล็อกหลังล็อกอินผิดซ้ำ · security headers

สถานะทั้งหมดเก็บใน memory ของโปรเซส ไม่ใช้ DB/Redis เพราะตอนนี้รันบน Render
instance เดียว ⚠️ ถ้าวันหนึ่งขยายเป็นหลาย instance ต้องย้ายไป Redis ไม่งั้นแต่ละ
เครื่องจะนับแยกกัน = เพดานจริงกลายเป็นคูณจำนวนเครื่อง และการล็อกล็อกอินก็หลบได้
ด้วยการยิงสลับเครื่อง
"""
import re
from collections import defaultdict, deque
from time import monotonic

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


# ============ ระบุตัวผู้เรียก ============

def client_ip(request: Request) -> str:
    """IP จริงของผู้ใช้ หลังผ่าน Cloudflare → Render

    `CF-Connecting-IP` เชื่อได้เพราะ Cloudflare เขียนทับค่าที่ client ส่งมาเองเสมอ
    และ origin รับ traffic ผ่าน Cloudflare ทางเดียว ส่วน `X-Forwarded-For` เป็นทาง
    สำรองตอนรันหลัง proxy อื่นหรือ dev — ค่านั้นปลอมได้ จึงใช้ต่อเมื่อไม่มี CF header
    """
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ============ จำกัดจำนวนครั้งต่อ IP (sliding window) ============

_HITS: dict[tuple[str, int], deque] = defaultdict(deque)
_MAX_TRACKED = 20_000


def _sweep(now: float) -> None:
    """ทิ้ง key ที่เงียบเกิน 1 ชม. กัน dict โตไม่มีที่สิ้นสุดตอนโดนยิงจากหลาย IP"""
    stale = [k for k, hits in _HITS.items() if not hits or now - hits[-1] > 3600]
    for k in stale:
        del _HITS[k]


def _too_many(scope: str, ip: str, limit: int, window: int) -> bool:
    now = monotonic()
    hits = _HITS[(f"{scope}:{ip}", window)]
    while hits and now - hits[0] > window:
        hits.popleft()
    if len(hits) >= limit:
        return True
    hits.append(now)
    if len(_HITS) > _MAX_TRACKED:
        _sweep(now)
    return False


def rate_limited(scope: str, ip: str, rules: tuple[tuple[int, int], ...]) -> bool:
    """True = เกินโควตา · rules = ((จำนวนครั้ง, ภายในกี่วินาที), ...)

    ประเมินทุกกฎก่อนสรุป (ไม่ short-circuit) เพื่อให้หน้าต่างยาวยังนับต่อเนื่อง
    แม้หน้าต่างสั้นจะบล็อกไปแล้ว
    """
    return any([_too_many(scope, ip, limit, window) for limit, window in rules])


# โควตาต่อ IP — ตั้งให้คนจริงไม่มีทางชน แต่บอทยิงรัวเจอทันที
# /api/analyze แพงที่สุด (1 ครั้ง = 1 Groq call จากโควตาฟรี 30/นาที ที่แชร์กันทั้งเว็บ)
ANALYZE_RULES = ((3, 60), (15, 3600))
LEAD_RULES = ((5, 60), (20, 3600))
LOGIN_RULES = ((10, 60), (60, 3600))


# ============ ล็อกหลังล็อกอินผิดซ้ำ ============

LOGIN_MAX_FAILS = 5
LOGIN_LOCK_SECONDS = 15 * 60

_LOGIN_FAILS: dict[str, deque] = defaultdict(deque)
_LOCKED_UNTIL: dict[str, float] = {}


def login_lock_remaining(ip: str) -> int:
    """เหลืออีกกี่วินาทีถึงจะลองใหม่ได้ · 0 = ไม่ได้ถูกล็อก"""
    until = _LOCKED_UNTIL.get(ip)
    if not until:
        return 0
    left = until - monotonic()
    if left <= 0:
        _LOCKED_UNTIL.pop(ip, None)
        return 0
    return int(left) + 1


def record_login_failure(ip: str) -> None:
    now = monotonic()
    fails = _LOGIN_FAILS[ip]
    while fails and now - fails[0] > LOGIN_LOCK_SECONDS:
        fails.popleft()
    fails.append(now)
    if len(fails) >= LOGIN_MAX_FAILS:
        _LOCKED_UNTIL[ip] = now + LOGIN_LOCK_SECONDS
        fails.clear()


def clear_login_failures(ip: str) -> None:
    _LOGIN_FAILS.pop(ip, None)
    _LOCKED_UNTIL.pop(ip, None)


# ============ กันบอทกรอกฟอร์ม ============

# ช่องล่อบอท: ซ่อนไว้นอกจอ คนจริงมองไม่เห็นและ tab ไปไม่ถึง ถ้ามีค่าส่งมา = บอท
# ตั้งชื่อว่า fax_number เพราะ password manager ไม่เติมให้ (ต่างจาก website/company)
HONEYPOT_FIELD = "fax_number"


def honeypot_tripped(value: str) -> bool:
    return bool((value or "").strip())


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]{2,}$")


def contact_format_error(phone: str, email: str) -> str | None:
    """ตรวจ*รูปแบบ*ของช่องติดต่อ — เว้นว่างได้ทั้งคู่ ไม่ถือว่าผิด

    ตั้งใจไม่บังคับว่าต้องกรอกอย่างน้อยหนึ่งช่อง เพราะเป็นการเปลี่ยนกติกาของฟอร์ม
    ที่ต้องให้เจ้าของตัดสินใจ ที่นี่กันแค่ค่าขยะอย่าง "asdf" หรือเบอร์ 3 หลัก
    """
    email = (email or "").strip()
    if email and not _EMAIL_RE.match(email):
        return "รูปแบบอีเมลไม่ถูกต้อง กรุณาตรวจสอบอีกครั้ง"
    digits = re.sub(r"\D", "", (phone or ""))
    if digits and not (8 <= len(digits) <= 15):
        return "รูปแบบเบอร์โทรไม่ถูกต้อง กรุณาตรวจสอบอีกครั้ง"
    return None


# ============ Security headers ============

# CSP นี้ยังต้องเปิด 'unsafe-inline' + 'unsafe-eval' เพราะเว็บใช้ Tailwind Play CDN
# (คอมไพล์ในเบราว์เซอร์) และมี <script>/style= inline อยู่ทั่วทุกหน้า จึงกัน XSS ได้
# ไม่เต็มที่ — ที่ได้เต็ม ๆ คือจำกัดโดเมนปลายทาง + frame-ancestors + form-action
# ถ้าจะให้แน่นกว่านี้ต้องเลิกใช้ Tailwind CDN ไปเป็นไฟล์ CSS ที่ build ไว้ก่อน
_CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com "
    "https://www.googletagmanager.com https://connect.facebook.net",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' data: https://fonts.gstatic.com",
    "img-src 'self' data: https://www.facebook.com https://www.google-analytics.com "
    "https://www.googletagmanager.com",
    "connect-src 'self' https://www.google-analytics.com https://analytics.google.com "
    "https://region1.google-analytics.com https://connect.facebook.net",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
])


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """ใส่ header ป้องกันให้ทุก response

    HSTS ใส่เฉพาะตอนมาทาง https จริง (ไม่งั้น dev บน localhost จะโดนเบราว์เซอร์
    จำว่าต้อง https ตลอดไป) และตั้งใจ *ไม่* ใส่ includeSubDomains/preload เพราะ
    subdomain อื่นของ voscene.com ยังไม่ได้ตรวจว่ารองรับ https ครบ
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("Content-Security-Policy", _CSP)
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=(), payment=()"
        )
        forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        if forwarded_proto == "https":
            headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return response

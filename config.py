from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "Voscene"
    # Absolute origin used to build og:url / og:image. The Render env var still
    # wins when set; the default is the live domain rather than localhost so a
    # forgotten dashboard entry cannot point every share preview at the
    # visitor's own machine. Override in .env for local work if needed.
    APP_URL: str = "https://www.voscene.com"
    SECRET_KEY: str = "change-this-to-random-string-min-32-chars"
    # ค่าเริ่มต้น "ปิด" — เดิมเป็น True และ Render ไม่ได้ตั้ง env นี้ production จึงรันโหมด DEBUG
    # มาตลอด (cookie ล็อกอินไม่ติดธง Secure) จนหน้า /admin/settings จับได้ 2026-09-27
    # เครื่องพัฒนาเปิดเองใน .env (DEBUG=True) เพราะ localhost เป็น http ล้วน
    DEBUG: bool = False

    DATABASE_URL: str = "sqlite:///./data.db"

    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "changeme"

    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # ที่ปรึกษา AI บนหน้าเว็บ (ฟอร์มหน้าแรก + /contact) — ปิดไว้ก่อนช่วงยิงโฆษณา
    # ตามคำสั่งเจ้าของ 2026-08-31: ให้ฟอร์มเป็นช่องกรอกข้อมูลธรรมดาส่งทีมงานไปก่อน
    # ตั้งเป็น True ใน Render เมื่อไหร่ ฟอร์มกลับไปเป็นแบบ AI วิเคราะห์ทันที
    # ไม่ต้องแก้โค้ด ไม่ต้อง deploy (รูปแบบเดียวกับ GA4_ID / META_PIXEL_ID)
    AI_CONSULT_ENABLED: bool = False

    # ฟอร์มฝากข้อมูลบนเว็บ — ตัดออกจากทุกหน้าแล้ว (เจ้าของสั่ง 2026-09-27: ลูกค้าทัก LINE / โทรเอง)
    # ปิด = /api/lead และ /api/analyze ไม่รับและไม่บันทึกข้อมูลใด ๆ (กันหน้าเก่าที่ค้างในแคช/บอท)
    # เปิดกลับได้ด้วย env ใน Render แต่ต้องใส่ฟอร์มกลับในเทมเพลต + แก้นโยบายความเป็นส่วนตัวด้วย
    WEB_FORMS_ENABLED: bool = False

    # ส่วนติดตามงานขายในหลังบ้าน (ขั้นการขาย · ผู้รับผิดชอบ · นัดติดตาม · ผลคัดกรอง · เสนอราคา/ปิดงาน)
    # เจ้าของ 2026-09-27: หลังบ้าน = เตรียมสื่อ + มอนิเตอร์สื่อเท่านั้น งานขายทำนอกเว็บ → ซ่อนไว้
    # ปิด = แค่ไม่แสดง ข้อมูลและ route เดิมยังอยู่ครบ เปิดกลับได้ด้วย env
    SALES_TRACKING_ENABLED: bool = False

    # Analytics / ad tracking. Empty = nothing is injected at all (no requests,
    # no cookies). Paste the IDs into the Render dashboard to switch them on
    # without a code change or redeploy.
    # ตั้งจากหลังบ้าน /admin/tracking ได้เลย ค่าใน env เหล่านี้เป็นแค่ตัวสำรอง
    # สำหรับค่าที่เคยตั้งไว้ใน Render — หลังบ้านชนะเสมอถ้ากรอกไว้
    GTM_ID: str = ""            # e.g. GTM-XXXXXXX
    GA4_ID: str = ""            # e.g. G-XXXXXXXXXX
    META_PIXEL_ID: str = ""     # e.g. 1234567890123456

    NOTIFY_EMAIL: str = ""
    NOTIFY_LINE_TOKEN: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()

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
    DEBUG: bool = True

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

    # Analytics / ad tracking. Empty = nothing is injected at all (no requests,
    # no cookies). Paste the IDs into the Render dashboard to switch them on
    # without a code change or redeploy.
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

"""ส่วนเชื่อมต่อแพลตฟอร์ม — รุ่นแรกยังไม่ดึงข้อมูลจริง แสดงสถานะตามจริงเท่านั้น

แต่ละแพลตฟอร์มเป็นคลาสลูกของ Connector: ระยะ 2 เพิ่ม fetch_spend()/sync() ในคลาส
ของตัวเองได้โดยไม่ต้องแตะหน้า Dashboard (หน้าอ่านแค่ status() กับ last_sync)

⚠️ ห้ามส่งค่าของรหัสออกไปหน้าเว็บหรือ log — status() ดูแค่ว่า "มีค่าไหม" เท่านั้น
"""
import os
from dataclasses import dataclass, field


@dataclass
class Connector:
    key: str
    label: str
    channels: tuple            # คีย์ช่องทางใน marketing_core.CHANNELS ที่ข้อมูลจะไปลง
    env_keys: tuple            # ชื่อตัวแปรที่ต้องตั้งฝั่งเซิร์ฟเวอร์ (Render → Environment)
    provides: str              # ข้อมูลที่จะได้เมื่อเชื่อมจริง
    notes: str = ""
    implemented: bool = False  # True เมื่อระยะ 2 เขียน sync จริงแล้ว
    extra: dict = field(default_factory=dict)

    def credentials_present(self) -> bool:
        return all(os.getenv(k, "").strip() for k in self.env_keys)

    def status(self) -> tuple:
        """(code, ข้อความ) — code: not_connected / credentials_only / connected"""
        if not self.credentials_present():
            return "not_connected", "ยังไม่เชื่อมต่อ"
        if not self.implemented:
            return "credentials_only", "ตั้งรหัสแล้ว แต่รุ่นนี้ยังไม่ดึงข้อมูล"
        return "connected", "เชื่อมต่อแล้ว"

    def fetch_spend(self, start, end) -> list:  # pragma: no cover - ระยะ 2
        raise NotImplementedError(f"{self.label}: ยังไม่ได้เชื่อมต่อจริง (ระยะ 2)")


CONNECTORS = [
    Connector(
        key="ga4", label="Google Analytics 4 (ผู้เข้าเว็บ)", channels=(),
        env_keys=("GA4_PROPERTY_ID", "GOOGLE_SERVICE_ACCOUNT_JSON"),
        provides="จำนวนผู้เข้าเว็บ / session แยกตามแหล่งที่มา",
        notes="ต้องเพิ่ม service account เป็นผู้อ่านใน GA4 property",
    ),
    Connector(
        key="google_ads", label="Google Ads", channels=("google_ads",),
        env_keys=("GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_CUSTOMER_ID",
                  "GOOGLE_ADS_REFRESH_TOKEN"),
        provides="ค่าโฆษณา / impressions / คลิก รายวันรายแคมเปญ",
        notes="developer token ต้องยื่นขอกับ Google และรออนุมัติ",
    ),
    Connector(
        key="meta", label="Facebook Page / Meta Ads", channels=("facebook_ads", "facebook_page"),
        env_keys=("META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID"),
        provides="ค่าโฆษณา Meta · สถิติโพสต์บน Page · (ภายหลัง) เผยแพร่โพสต์บน Page",
        notes="ต้องผ่าน Business verification + App Review · โพสต์เข้ากลุ่มอัตโนมัติทำไม่ได้ "
              "(Meta ปิด Groups API แล้ว)",
    ),
    Connector(
        key="tiktok", label="TikTok", channels=("tiktok",),
        env_keys=("TIKTOK_ACCESS_TOKEN", "TIKTOK_ADVERTISER_ID"),
        provides="ค่าโฆษณา TikTok ตามสิทธิ์ที่แพลตฟอร์มอนุญาต",
        notes="ต้องสมัคร TikTok for Business developer และรออนุมัติแอป",
    ),
    Connector(
        key="ai_assist", label="ผู้ช่วย AI (ร่างเนื้อหา · คัด Lead · สรุปผล)", channels=(),
        env_keys=("MARKETING_AI_API_KEY",),
        provides="ร่างข้อความจากข้อมูลบริการที่อนุมัติแล้ว · เสนอผลคัดกรองให้คนยืนยัน",
        notes="ระยะ 3 · AI จะไม่มีสิทธิ์เผยแพร่หรือปรับงบเอง",
    ),
]
CONNECTOR_MAP = {c.key: c for c in CONNECTORS}


def connector_for_channel(channel: str):
    for c in CONNECTORS:
        if channel in c.channels:
            return c
    return None

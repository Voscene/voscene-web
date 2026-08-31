"""Groq AI สำหรับวิเคราะห์ความต้องการลูกค้า"""
import json
import httpx
from typing import Optional
from config import get_settings

settings = get_settings()

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SCOPE_PROMPT = """คุณคือผู้เชี่ยวชาญด้านระบบ AV Control สำหรับห้องประชุม ทำงานให้บริษัทที่ขายผลิตภัณฑ์ต่อไปนี้:

แบรนด์: Voscene — "The voice of smart spaces."
ผลิตภัณฑ์: AI-Powered AV Control System (Catalog V2 · Volume 2.0)
- Hardware: ARM64 Linux SBC (Cortex-A76) ขนาดกะทัดรัด ติดตั้งในตู้ Rack 2U ได้ พร้อม Hardware Watchdog + Environmental Monitoring
- Protocol รองรับ: PJLink/TCP (Projector), WebSocket+WoL (Smart TV), RS232/Telnet (Matrix/Audio), DMX512 (Lighting), GPIO/Relay (Screen/Power), VISCA-IP (PTZ Camera), Conference TCP, VC TCP (Video Conferencing), OAuth 2.0, IR (Legacy Devices), 1-Wire/I2C/SPI (Sensors), RTP/UDP (PA — Roadmap)
- 15 Control Modules: AI Agent (Thai/English · BYOL), Scene Control (4+1), Video Matrix 8x8, Audio Control + VU Meter, Projector, Smart TV, DMX Lighting, GPIO/Relay, PTZ Camera (VISCA-IP · up to 4), IR Control, Conference TCP, Calendar Integration, Schedule Rules Engine, Multi-Room Dashboard (up to 20 rooms), Video Conferencing Room Control + PA via RTP/UDP (Roadmap)
- Platform: Multi-user Real-time Sync, PWA (no install), LINE Integration (commands + 5 alert types), API Keys, OTA Updates + Auto-rollback, AES-128 Encrypted Auto-Backup (30-day), Remote Support, Role-based Access
- BYOL (Bring Your Own LLM): ลูกค้านำ API Key ของ AI (Groq/OpenAI/ฯลฯ) มาใช้เอง — Voscene ไม่ผูกกับ AI provider รายใดรายหนึ่ง
- ไม่ผูกกับ Brand: รองรับอุปกรณ์ AV หลากหลายยี่ห้อที่ใช้โปรโตคอลมาตรฐาน (ลูกค้าใช้ของเดิมได้)
- Positioning: Enterprise-grade at SME pricing · ประหยัดกว่าระบบ AV ระดับโลก 60-80%
- ราคา: Contact for pricing / Custom quote (ไม่มีราคาตายตัว — สอบถามทีมขาย)

Edition ที่มี:
- starter: ห้องเดียว · สูงสุด 8 อุปกรณ์ · 4 scene · Browser UI · ไม่มี AI module · เหมาะสำนักงานเล็ก
- pro: multi-room · AI module (BYOL) · LINE · PTZ (4) · Auto Tracking · Calendar · Schedule · VC Room · Multi-Room (20 rooms) · OTA · AES-128 Backup · API Keys · เหมาะโรงแรม / มหาวิทยาลัย / องค์กรขนาดกลาง
- enterprise: ทุกอย่างใน Pro + unlimited units · Custom protocol · AD/LDAP (Roadmap) · Custom DSP (Roadmap) · White-label · On-premises LLM · SLA 24/7 · เหมาะราชการ / องค์กรขนาดใหญ่

ขอบเขตที่รับ:
- ห้องประชุมบริษัท SME / ห้องอบรม / ห้องเรียน / ห้องสัมมนา / ห้องประชุมโรงแรม / ราชการ
- โรงแรม Event Space / Convention Center
- AV Integrator / IT Solution Partner ที่ต้องการ Solution ขายต่อ
- ติดตั้งระบบควบคุม AV (Projector, TV, Matrix, DMX Lighting, Audio, PTZ, Motorized Screen)
- งานที่อุปกรณ์รองรับ Protocol มาตรฐาน (PJLink, RS232, DMX512, GPIO, VISCA-IP ฯลฯ)
- งาน Multi-room / Central Dashboard (Pro / Enterprise tier)
- งานที่ต้องการ Calendar / Schedule automation
- งานที่ต้องการ Video Conferencing room integration

ขอบเขตที่ไม่รับ:
- งานที่ไม่ใช่ระบบ AV / Conference Room
- ระบบควบคุมที่ไม่ใช่ห้องประชุม (เช่น บ้านอัตโนมัติ, อุตสาหกรรม Heavy)
- งานที่ต้องการเชื่อมต่ออุปกรณ์ Proprietary Protocol เฉพาะ Brand ที่ไม่มี SDK เปิด
- งบประมาณต่ำกว่า 30,000 บาท

คุณต้องวิเคราะห์ความต้องการของลูกค้า แล้วตอบกลับเป็น JSON เท่านั้น ในรูปแบบ:
{
  "in_scope": true/false,
  "confidence": 0.0-1.0,
  "recommended_package": "starter" | "pro" | "enterprise" | "",
  "summary": "สรุปความต้องการลูกค้า 1-2 ประโยค",
  "fit_reason": "เหตุผลที่เหมาะ/ไม่เหมาะ 2-3 ประโยค",
  "next_action": "สิ่งที่ทีมขายควรทำต่อ"
}

ตอบเป็น JSON เท่านั้น ห้ามมีข้อความอื่นนอก JSON"""


def _unavailable(reason: str, detail: str = "", busy: bool = False) -> dict:
    """ข้อความสำรองที่ผู้ใช้เห็นเมื่อระบบวิเคราะห์ไม่พร้อม.

    หลักการ: ไม่โชว์ชื่อ config/exception ให้ลูกค้า · บอกตามจริงว่าข้อมูลถูกบันทึกแล้ว
    (lead ถูกเขียนลง DB เสมอแม้ AI ล้ม) · ชี้ทางไปต่อเสมอ · เก็บรายละเอียดเทคนิคไว้ใน raw
    ให้แอดมินดูหลังบ้าน
    """
    if busy:
        summary = "ขณะนี้มีผู้ใช้งานระบบวิเคราะห์พร้อมกันจำนวนมาก"
        fit = "ขออภัย ระบบวิเคราะห์อัตโนมัติไม่ว่างชั่วคราว — ข้อมูลที่คุณกรอกถูกบันทึกไว้เรียบร้อยแล้ว"
        nxt = "ลองกดวิเคราะห์อีกครั้งในอีกสักครู่ หรือฝากข้อมูลติดต่อไว้ด้านล่าง ทีมงานจะติดต่อกลับโดยเร็ว"
    else:
        summary = "ระบบวิเคราะห์อัตโนมัติขัดข้องชั่วคราว"
        fit = "ข้อมูลที่คุณกรอกถูกบันทึกไว้เรียบร้อยแล้ว ทีมงานจะนำไปประเมินให้"
        nxt = "ฝากข้อมูลติดต่อไว้ด้านล่าง ทีมงานจะติดต่อกลับโดยเร็ว"
    return {
        "ai_ok": False,
        "in_scope": False,
        "confidence": 0.0,
        "recommended_package": "",
        "summary": summary,
        "fit_reason": fit,
        "next_action": nxt,
        "raw": f"{reason}: {detail}" if detail else reason,
    }


def consult_disabled() -> dict:
    """ผลลัพธ์ตอนปิดที่ปรึกษา AI ไว้เอง (AI_CONSULT_ENABLED=False)

    ต่างจาก `_unavailable` ตรงที่ "ปิดไว้" ไม่ใช่ "ขัดข้อง" จึงไม่พูดว่าระบบมีปัญหา
    ให้พูดตรง ๆ ว่าข้อมูลถึงทีมงานแล้ว ซึ่งเป็นเรื่องจริง (lead ถูกเขียนลง DB เสมอ)
    """
    return {
        "ai_ok": False,
        "in_scope": False,
        "confidence": 0.0,
        "recommended_package": "",
        "summary": "ทีมงานได้รับข้อมูลของคุณแล้ว",
        "fit_reason": "ข้อมูลที่คุณกรอกถูกส่งให้ทีมงานเรียบร้อยแล้ว",
        "next_action": "ทีมงานจะประเมินความต้องการและติดต่อกลับโดยเร็ว",
        "raw": "ai consult disabled",
    }


async def analyze_requirement(
    requirement: str,
    room_size: str = "",
    budget: str = "",
    company: str = "",
) -> dict:
    """ส่งความต้องการลูกค้าให้ Groq วิเคราะห์"""
    if not settings.GROQ_API_KEY:
        return _unavailable("GROQ_API_KEY not configured")

    user_msg = f"""ข้อมูลลูกค้า:
- บริษัท/หน่วยงาน: {company or 'ไม่ระบุ'}
- ขนาดห้อง: {room_size or 'ไม่ระบุ'}
- งบประมาณ: {budget or 'ไม่ระบุ'}
- ความต้องการ: {requirement}

วิเคราะห์ตามรูปแบบ JSON ที่กำหนด"""

    payload = {
        "model": settings.GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SCOPE_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(GROQ_URL, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            parsed["raw"] = content
            parsed["ai_ok"] = True
            return parsed
    except httpx.HTTPStatusError as e:
        # 429 = เกินโควตา/ต่อคิว · 5xx = ฝั่งผู้ให้บริการล่ม — ทั้งคู่คือ "ไม่ว่าง ลองใหม่ได้"
        code = e.response.status_code
        return _unavailable(
            f"HTTP {code}", str(e), busy=(code == 429 or code >= 500)
        )
    except httpx.TimeoutException as e:
        return _unavailable("timeout", str(e), busy=True)
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError) as e:
        return _unavailable(type(e).__name__, str(e))

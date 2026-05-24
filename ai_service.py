"""Groq AI สำหรับวิเคราะห์ความต้องการลูกค้า"""
import json
import httpx
from typing import Optional
from config import get_settings

settings = get_settings()

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SCOPE_PROMPT = """คุณคือผู้เชี่ยวชาญด้านระบบ AV Control สำหรับห้องประชุม ทำงานให้บริษัทที่ขายผลิตภัณฑ์ต่อไปนี้:

แบรนด์: Voscene — "The voice of smart spaces."
ผลิตภัณฑ์: AI-Powered AV Control System (รุ่น VS-1000 / VS-1000 PRO)
- Hardware: ARM64 Linux SBC ขนาดกะทัดรัด ติดตั้งในตู้ Rack 2U ได้
- Protocol รองรับ: PJLink/TCP (Projector), WebSocket+WoL (Smart TV), RS232/Telnet (Matrix/Audio), DMX512 (Lighting), GPIO/Relay (Screen/Power), RTP/UDP (PA - Roadmap)
- Software: AI Voice/Text Agent ภาษาไทย/อังกฤษ ขับเคลื่อนด้วย LLM, Scene Control (4+1), Video Matrix 8x8, Audio Control + VU Meter, Multi-user Real-time Sync, PWA, Browser-based ไม่ต้องติดตั้ง app
- ไม่ผูกกับ Brand: รองรับอุปกรณ์ทุกยี่ห้อที่ใช้ Protocol มาตรฐาน (ลูกค้าใช้ของเดิมได้)
- Positioning: Enterprise-grade at SME pricing
- คู่แข่ง: Crestron, AMX, QSC — Voscene ถูกกว่า 10-15 เท่า
- ราคา: Starter 89,000 / Professional 149,000 / Enterprise ตามขอบเขต
- เช่า: 4,900-8,900 บาท/เดือน หรือ 49,000-89,000 บาท/ปี

ขอบเขตที่รับ:
- ห้องประชุมบริษัท SME / ห้องอบรม / ห้องเรียน / ห้องสัมมนา / ห้องประชุมโรงพยาบาล / ราชการ
- โรงแรม Event Space
- AV Integrator / IT Solution Partner ที่ต้องการ Solution ขายต่อ
- ติดตั้งระบบควบคุม AV (โปรเจคเตอร์, ทีวี, Matrix, ไฟ DMX, เสียง, จอ Motorized)
- งานที่อุปกรณ์รองรับ Protocol มาตรฐาน (PJLink, WebSocket, RS232, DMX512, GPIO)
- งบประมาณ 50,000 บาทขึ้นไป (ซื้อขาด) หรือ 4,000 บาท/เดือนขึ้นไป (เช่า)
- งาน Multi-room / Central Dashboard (Enterprise tier)

ขอบเขตที่ไม่รับ:
- งานที่ไม่ใช่ระบบ AV / Conference Room
- งบประมาณต่ำกว่า 30,000 บาท
- ระบบควบคุมที่ไม่ใช่ห้องประชุม (เช่น บ้านอัตโนมัติ, อุตสาหกรรม Heavy)
- งานที่ต้องการเชื่อมต่ออุปกรณ์ Proprietary Protocol เฉพาะ Brand ที่ไม่มี SDK เปิด

คุณต้องวิเคราะห์ความต้องการของลูกค้า แล้วตอบกลับเป็น JSON เท่านั้น ในรูปแบบ:
{
  "in_scope": true/false,
  "confidence": 0.0-1.0,
  "recommended_package": "starter" | "professional" | "enterprise" | "monthly_starter" | "monthly_pro" | "yearly_starter" | "yearly_pro" | "",
  "summary": "สรุปความต้องการลูกค้า 1-2 ประโยค",
  "fit_reason": "เหตุผลที่เหมาะ/ไม่เหมาะ 2-3 ประโยค",
  "next_action": "สิ่งที่ทีมขายควรทำต่อ"
}

ตอบเป็น JSON เท่านั้น ห้ามมีข้อความอื่นนอก JSON"""


async def analyze_requirement(
    requirement: str,
    room_size: str = "",
    budget: str = "",
    company: str = "",
) -> dict:
    """ส่งความต้องการลูกค้าให้ Groq วิเคราะห์"""
    if not settings.GROQ_API_KEY:
        return {
            "in_scope": False,
            "confidence": 0.0,
            "recommended_package": "",
            "summary": "ยังไม่ได้ตั้งค่า GROQ_API_KEY",
            "fit_reason": "ระบบ AI ยังไม่พร้อมใช้งาน",
            "next_action": "ติดต่อทีมขายโดยตรง",
            "raw": "",
        }

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
            return parsed
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as e:
        return {
            "in_scope": False,
            "confidence": 0.0,
            "recommended_package": "",
            "summary": "ไม่สามารถวิเคราะห์อัตโนมัติได้",
            "fit_reason": f"AI Error: {type(e).__name__}",
            "next_action": "ติดต่อลูกค้าโดยตรงเพื่อสอบถามเพิ่ม",
            "raw": str(e),
        }

"""ผู้ช่วย AI ร่างโพสต์/โฆษณา (ระยะ 3 ข้อแรก) — ใช้ในหลังบ้านเท่านั้น

หลักที่ยึด (ตามใบงาน + บทเรียน PA ใน HANDOFF):
- AI เขียนจาก "ข้อเท็จจริงที่ยืนยันแล้ว" ในไฟล์นี้ + marketing_core.SERVICES เท่านั้น
  ไม่ใช้ SCOPE_PROMPT ของที่ปรึกษา AI หน้าเว็บ (มีข้อความที่ยังไม่ยืนยันปน)
- บริการที่ claim = "unconfirmed" → ไม่ร่างให้เลย
- ทุกร่างผ่าน check_draft() หาคำต้องห้าม/เงื่อนไขที่ขาด แล้วแสดงคำเตือนให้คนตัดสิน
- ระบบไม่บันทึก ไม่เผยแพร่เอง — คนกด "ใส่ในข้อความ" แล้วกดบันทึกเอง
- ส่งไปผู้ให้บริการ AI เฉพาะข้อมูลการตลาด ไม่มีข้อมูลลูกค้า

ถ้าข้อเท็จจริงเปลี่ยน (เช่น SW ยืนยัน PA หรือระบบไฟแล้ว) แก้ APPROVED_FACTS / FORBIDDEN
และ docs/MARKETING-GUIDE.md พร้อมกัน
"""
import re
from typing import Optional

import httpx

import marketing_core as mc
from config import get_settings

settings = get_settings()
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

APPROVED_FACTS = [
    "Voscene คือระบบควบคุมห้องประชุม (เสียง ภาพ อุปกรณ์ในห้อง) สั่งงานผ่านหน้าจอเดียว",
    "เปิดใช้งานผ่านเว็บเบราว์เซอร์บนแท็บเล็ต/คอมพิวเตอร์ ไม่ต้องติดตั้งแอป ไม่ต้องใช้ Touch Panel ราคาแพง",
    "มี 2 โหมด: 'โหมดผู้ใช้' สำหรับผู้เข้าประชุม แตะเพื่อเริ่มประชุมได้ทันที และ 'โหมดช่าง' สำหรับเจ้าหน้าที่ดูแลระบบ",
    "เปิด–ปิดและเตรียมห้องประชุมด้วยปุ่มเดียว (ซีน) — จอ ไมค์ เสียง พร้อมพร้อมกัน",
    "รวมรีโมตหลายตัวไว้บนหน้าควบคุมเดียว",
    "มีหน้าควบคุมแบบกราฟิกตามผังห้อง — ช่างเป็นผู้วางผังและจุดอุปกรณ์ให้ตอนติดตั้ง",
    "ควบคุมหลายห้องจากจุดเดียวได้สูงสุด 20 ห้อง โดยทุกห้องต้องอยู่ในวงเครือข่ายเดียวกัน",
    "ทยอยเพิ่มอุปกรณ์ทีละส่วนได้ และใช้อุปกรณ์เดิมได้ ถ้าอุปกรณ์มีพอร์ตเครือข่ายและเปิดการควบคุมผ่านเครือข่ายไว้",
    "รองรับอุปกรณ์ 48 ยี่ห้อ ผ่านโปรโตคอลมาตรฐาน",
    "ใช้งานจริงในหน่วยงานราชการ (ห้ามระบุชื่อหน่วยงาน ยี่ห้อ หรือรุ่น)",
    "พัฒนาโดย บริษัท เซ็นทรัล ซิสเท็ม อินทิเกรชั่น จำกัด (CSI) System Integrator ประสบการณ์ 18 ปี",
    "ปรึกษาฟรี ขอนัดสาธิต (Demo) หรือขอใบเสนอราคาได้ ราคาเป็นแบบเสนอราคาตามงาน",
]

FORBIDDEN = [
    "ห้ามอ้างว่าระบบประกาศเสียงตามสาย (PA / Paging / กระจายเสียงออกลำโพง) พร้อมใช้งาน — ยังอยู่ระหว่างพัฒนา",
    "ห้ามอ้างว่าควบคุมระบบไฟ/แสงได้ — ยังไม่ได้รับการยืนยัน",
    "ห้ามอ้างการควบคุมเกิน 20 ห้อง หรือศูนย์กลางหลายร้อยห้อง",
    "ห้ามอ้างความสามารถ AI สั่งงานด้วยเสียง/ภาษาไทย (ยังเป็นโครงการนำร่อง)",
    "ห้ามใส่ราคา ตัวเลขประหยัดเป็นเปอร์เซ็นต์ ระยะเวลาติดตั้ง หรือตัวเลขอื่นที่ไม่อยู่ในข้อเท็จจริง",
    "ห้ามใช้คำเกินจริง เช่น ที่สุด อันดับ 1 100% รับประกัน ทุกยี่ห้อ ทุกรุ่น",
    "ห้ามเอ่ยชื่อคู่แข่งหรือแบรนด์อื่น",
    "ห้ามใส่ลิงก์ URL (ระบบแนบลิงก์ติดตามให้เอง)",
    "ห้ามแต่งข้อมูลลูกค้า ผลงาน หรือคำรับรองที่ไม่มีในข้อเท็จจริง",
]

CHANNEL_FORMATS = {
    "facebook_page": "โพสต์ Facebook Page ยาว 60-120 คำ ย่อหน้าสั้น เปิดด้วยปัญหาที่ผู้อ่านเจอ ปิดด้วยคำชวนให้ติดต่อ ใส่แฮชแท็กไม่เกิน 3",
    "facebook_group": "โพสต์ในกลุ่ม Facebook น้ำเสียงเป็นกันเองแบบแบ่งปันความรู้ ไม่ขายตรงเกินไป ยาว 60-120 คำ ไม่ใส่แฮชแท็ก",
    "facebook_ads": "ข้อความโฆษณา Meta: ข้อความหลัก 1 ย่อหน้า (ไม่เกิน 60 คำ) + พาดหัว 3 แบบ (แต่ละแบบไม่เกิน 40 ตัวอักษร)",
    "google_ads": "โฆษณา Google Search: พาดหัว 5 แบบ (แต่ละแบบไม่เกิน 30 ตัวอักษร) และคำอธิบาย 2 แบบ (แต่ละแบบไม่เกิน 90 ตัวอักษร) เขียนเป็นรายการ",
    "tiktok": "สคริปต์คลิปสั้น 20-30 วินาที แบ่งเป็นฉาก (ภาพที่เห็น + คำพูด) ฉากแรกต้องดึงความสนใจใน 3 วินาที",
    "line_oa": "ข้อความ LINE OA สั้น 2-4 บรรทัด ปิดด้วยคำชวนให้ตอบกลับหรือโทร",
    "email": "อีเมล: บรรทัดแรกเป็นหัวเรื่อง (ขึ้นต้นด้วย 'หัวเรื่อง:') ตามด้วยเนื้อหา 80-150 คำ",
    "other": "ข้อความประชาสัมพันธ์ทั่วไป ยาว 60-120 คำ",
}

GOAL_CTA = {
    "demo": "ชวนให้ขอนัดสาธิต (Demo)",
    "quote": "ชวนให้ขอใบเสนอราคา",
    "lead": "ชวนให้กรอกแบบฟอร์มหรือติดต่อทีมงานเพื่อปรึกษาฟรี",
    "awareness": "เน้นให้รู้จักและเข้าใจประโยชน์ ไม่ต้องขายตรง",
}

# ============ ตรวจร่าง ============

_CHECKS = [
    (r"ที่สุด|อันดับ\s*1|อันดับหนึ่ง|100\s*%|รับประกัน|ทุกยี่ห้อ|ทุกรุ่น|ครบทุก", "คำเกินจริง/สัญญาเกินตัว"),
    (r"Crestron|AMX|Extron|QSC|Kramer|Biamp|Q-SYS", "มีชื่อแบรนด์อื่น"),
    (r"แสง|ระบบไฟ|ควบคุมไฟ|เปิด-?ปิดไฟ|หรี่ไฟ|DMX|ไฟส่องสว่าง", "อ้างเรื่องระบบไฟ/แสง (ยังไม่ยืนยัน)"),
    (r"ประกาศ|เสียงตามสาย|\bPA\b|Paging|กระจายเสียง", "อ้างระบบประกาศ PA (ยังพัฒนาอยู่)"),
    (r"หลายร้อยห้อง|[2-9]\d{2}\s*ห้อง|[3-9]\d\s*ห้อง|ไม่จำกัดห้อง", "อ้างจำนวนห้องเกิน 20"),
    (r"\d[\d,]*\s*(บาท|฿)|ประหยัด\s*\d|\d+\s*ชั่วโมง|\d+\s*นาที", "มีราคา/ตัวเลขที่ไม่ได้ยืนยัน"),
    (r"https?://|www\.", "มีลิงก์ (ระบบแนบลิงก์ติดตามให้เอง)"),
    (r"สั่งงานด้วยเสียง|สั่งด้วยเสียง|พูดสั่ง|AI\s*Assist", "อ้างความสามารถ AI/สั่งด้วยเสียง (นำร่อง)"),
]


def check_draft(text: str, service_key: str) -> list:
    """คืนรายการคำเตือน — ใช้เตือนคน ไม่ได้แก้ข้อความให้"""
    warnings = []
    for pattern, label in _CHECKS:
        found = re.search(pattern, text or "", re.I)
        if found:
            warnings.append(f"{label}: “{found.group(0)}”")
    svc = mc.SERVICE_MAP.get(service_key, {})
    if service_key == "multi_room" and not ("20" in text and "เครือข่าย" in text):
        warnings.append("บริการนี้ต้องระบุเงื่อนไข: สูงสุด 20 ห้อง ในวงเครือข่ายเดียวกัน")
    if service_key == "floorplan" and "ช่าง" not in text:
        warnings.append("บริการนี้ต้องระบุเงื่อนไข: ช่างเป็นผู้วางผังให้ตอนติดตั้ง")
    if svc.get("claim") == "unconfirmed":
        warnings.append("บริการนี้ยังไม่ยืนยัน — ห้ามโฆษณาว่าพร้อมส่งมอบ")
    return warnings


# ============ สร้างพรอมต์ + เรียก AI ============

def build_messages(service_key: str, channel: str, goal: str, audience: str = "",
                   notes: str = "") -> list:
    svc = mc.SERVICE_MAP[service_key]
    condition = f"\nเงื่อนไขที่ต้องเขียนไว้ในข้อความทุกครั้ง: {svc['note']}" if svc.get("note") else ""
    system = (
        "คุณเป็นนักเขียนคอนเทนต์การตลาดภาษาไทยให้แบรนด์ Voscene กลุ่มเป้าหมายคือเจ้าหน้าที่หน่วยงาน/องค์กร"
        "ที่ดูแลห้องประชุม เขียนภาษาไทยสุภาพ อ่านง่าย ไม่ใช้ศัพท์เทคนิคเกินจำเป็น\n\n"
        "ข้อเท็จจริงที่ใช้ได้ (ห้ามเพิ่มข้อเท็จจริงอื่นนอกจากนี้):\n"
        + "\n".join(f"- {f}" for f in APPROVED_FACTS)
        + "\n\nข้อห้าม:\n" + "\n".join(f"- {f}" for f in FORBIDDEN)
        + "\n\nตอบเฉพาะข้อความที่พร้อมใช้ ไม่ต้องอธิบาย ไม่ต้องมีคำนำหรือคำลงท้ายถึงผู้สั่งงาน"
    )
    user = (
        f"บริการที่โปรโมต: {svc['label']}{condition}\n"
        f"รูปแบบ: {CHANNEL_FORMATS.get(channel, CHANNEL_FORMATS['other'])}\n"
        f"เป้าหมาย: {GOAL_CTA.get(goal, GOAL_CTA['lead'])}\n"
        + (f"กลุ่มเป้าหมาย: {audience[:500]}\n" if audience else "")
        + (f"ข้อมูลเพิ่มเติมจากทีม: {notes[:800]}\n" if notes else "")
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def call_llm(messages: list) -> str:
    """เรียก Groq · ยกเว้น RuntimeError พร้อมข้อความภาษาไทยให้แสดงในหลังบ้าน"""
    if not settings.GROQ_API_KEY:
        raise RuntimeError("ยังไม่ได้ตั้งค่า GROQ_API_KEY ใน Render")
    payload = {"model": settings.GROQ_MODEL, "messages": messages,
               "temperature": 0.7, "max_tokens": 900}
    headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=40.0) as client:
            r = await client.post(GROQ_URL, json=payload, headers=headers)
            r.raise_for_status()
            return (r.json()["choices"][0]["message"]["content"] or "").strip()
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code == 429:
            raise RuntimeError("ผู้ให้บริการ AI ไม่ว่าง (เกินโควตาชั่วคราว) ลองใหม่ในอีกสักครู่")
        if code in (401, 403):
            raise RuntimeError("คีย์ GROQ_API_KEY ไม่ถูกต้องหรือหมดอายุ — สร้างคีย์ใหม่ที่ console.groq.com "
                               "แล้วใส่ใน Render → Environment")
        raise RuntimeError(f"ผู้ให้บริการ AI ตอบกลับผิดพลาด (HTTP {code})")
    except httpx.TimeoutException:
        raise RuntimeError("ผู้ให้บริการ AI ตอบช้าเกินไป ลองใหม่อีกครั้ง")
    except (httpx.HTTPError, KeyError, ValueError, IndexError) as e:
        raise RuntimeError(f"เรียกผู้ให้บริการ AI ไม่สำเร็จ ({type(e).__name__})")


async def draft(service_key: str, channel: str, goal: str, audience: str = "",
                notes: str = "") -> dict:
    svc = mc.SERVICE_MAP.get(service_key)
    if not svc or service_key == "other":
        return {"ok": False, "error": "เลือกบริการที่จะโปรโมตก่อน"}
    if svc.get("claim") == "unconfirmed":
        return {"ok": False, "error": f"บริการ '{svc['label']}' ยังไม่ได้รับการยืนยัน — "
                                      "AI จะไม่ร่างโฆษณาให้จนกว่า PM/SW ยืนยัน (ดู docs/MARKETING-GUIDE.md)"}
    try:
        text = await call_llm(build_messages(service_key, channel, goal, audience, notes))
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}
    if not text:
        return {"ok": False, "error": "AI ไม่ได้ส่งข้อความกลับมา ลองใหม่อีกครั้ง"}
    return {"ok": True, "text": text, "warnings": check_draft(text, service_key)}

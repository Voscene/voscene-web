# Web Copy — Multi-room Central Dashboard (Feature 09) · 2026-06-24

> สำหรับทีมเว็บ — ข้อความพร้อมวาง (ภาพกว้าง · ไม่มีสเปก HW) · ยึด honesty: ของจริง = LIVE · ส่วนขยาย = "ออกแบบให้ขยาย"

---

## Badge
`FEATURE 09 · DASHBOARD`  +  `LIVE`
> LIVE = ใช้กับ dashboard **20 ห้อง** ที่มีจริงในระบบ · ไม่ได้คลุมถึง 200/Master (ส่วนนั้นเป็น roadmap)

## Title
**Multi-room Central Dashboard**

## Description (TH)
> คุมและเฝ้าดูทุกห้องจากจอเดียว — **พร้อมใช้สูงสุด 20 ห้องต่อ controller** · ออกแบบให้ขยายสู่ระดับองค์กร (หลายอาคาร) ด้วย **Master Controller**

## Description (EN)
> Control and monitor every room from a single pane — **up to 20 rooms per controller today**, designed to scale to enterprise (multi-building) with a **Master Controller**.

## Bullets
- ✓ **Central Control + Monitoring** — สั่งงาน + เห็นสถานะทุกห้อง real-time จากจอเดียว
- ✓ **Federated** — สั่งข้ามห้องจาก single pane
- ✓ **Independent Rooms** — แต่ละห้องทำงานอิสระ · **ศูนย์กลางล่ม ห้องยังคุมเองได้** (no single point of failure)
- ⚡ **Enterprise-ready** — *ออกแบบให้ขยายถึง ~200 ห้อง* ด้วย Master Controller (รุ่นองค์กร · หลายอาคาร)

## ถ้าจะโชว์เป็นขั้น (tier)
| ขั้น | ข้อความ |
|---|---|
| **20 ห้อง** | พร้อมใช้ (LIVE) |
| **~200 ห้อง** | ออกแบบให้ขยาย · ด้วย Master Controller (รุ่นองค์กร) |
| **หลายอาคาร/หลายไซต์** | Multi-site federation · ขยายตามโครงการ |

## Visual
- คงกริดห้อง (3×3 จุดสถานะ) ไว้ได้ — สื่อ "เฝ้าหลายห้องจากจอเดียว" ได้ดี

---

## ✅ ใช้ได้ / ❌ ห้าม (honesty)
| ✅ ใช้ | ❌ ห้าม |
|---|---|
| "20 ห้อง = พร้อมใช้ / LIVE" | "ไม่จำกัด / Unlimited" |
| "ออกแบบให้ขยายถึง ~200 ห้อง" | "มีพร้อม 200 ห้องแล้ว" / 200 อยู่ใต้ LIVE |
| "ขยายตามโครงการ / Multi-site" | เลขสเปก HW (CPU/RAM/UPS/2U) บนเว็บ |
| "ศูนย์กลางล่ม ห้องยังคุมเองได้" | เคลม Master/push ว่า "ใช้งานได้แล้ว" |

**เหตุผล:** dashboard 20 ห้อง = ของจริง deploy แล้ว (LIVE ได้) · แต่ Master/200/multi-site = สถาปัตยกรรม roadmap → ใช้คำ "ออกแบบให้ขยาย / ตามโครงการ" กัน over-claim (PDPA/จัดซื้อราชการ) · และ "ไม่จำกัด" = คำสัมบูรณ์พิสูจน์ไม่ได้ ห้ามบนเว็บสาธารณะ

---
*— SW · 2026-06-24 · เฉพาะ section Multi-room Dashboard · ภาพกว้าง ไม่มีสเปก (สเปกอยู่ใน internal: VOSCENE/Master-Controller-Design+Datasheet)*

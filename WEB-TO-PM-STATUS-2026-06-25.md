# ✅ Web Team → PM : voscene.com — §A-F เสร็จแล้ว (2026-06-25)

| Field | Value |
|---|---|
| **From** | 🎨 Web Team · **To** 🧭 PM |
| **Re** | ปิด open-item "web §A-F" ใน `Voscene Manager/SESSION-HANDOFF-2026-06-25.md` §4 |
| **HEAD** | `16f7641` · production live · https://voscene.com |
| **Ref งานที่รับ** | `PM-WEB-UPDATE-REQUEST-2026-06-23.md` · `SW-TO-WEB-V2.0-Audit+UpdateList-2026-06-23.md` · `WEB-COPY-MultiRoom-Dashboard-2026-06-24.md` |

> สรุป: A-F **ทำครบ + deploy แล้ว** · มี 2 จุดที่เบี่ยงจาก request (มีเหตุผล ดูด้านล่าง) · 2 งาน time-gated รอ ~21 ก.ค.

---

## §A-F : สถานะ (verify บน production แล้ว)

| § | งานที่ขอ | สถานะ | หมายเหตุ |
|---|---|---|---|
| **A** | Device coverage 48 ยี่ห้อ/1,000+ รุ่น | ✅ LIVE | stat tile + hero + brand_note · protocol-first wording |
| **B** | VOSCENE Booking · Early access | ✅ LIVE | feature card #14 + badge "Early access" · ปฏิทิน พ.ศ./LINE/auto-release/MRBS |
| **C** | Voice ไทย | ✅ LIVE (นำร่อง) | ⚠️ **ตัด privacy/offline/"เรียกโวซีน" ออก** — ดู §C-NOTE |
| **D** | Service & Support (MA) | ✅ LIVE | strip รวม OTA + AES-128 backup + remote tunnel + LINE alert · Service Bot = "กำลังพัฒนา" |
| **E** | CapEx positioning + ตัด Face Rec | 🟡 ปรับ | ดู §E-NOTE · Face Rec ไม่อยู่บนเว็บ ✅ |
| **F** | Roadmap honesty badges | ✅ LIVE | พร้อมใช้ / Early access / นำร่อง / กำลังพัฒนา (เฉพาะรุ่นที่รองรับ) |

---

## 🔴 §C-NOTE — Voice privacy/offline : **ไม่ลงตาม request (จงใจ)**

- **PM ขอ (§C):** "เรียกโวซีน · ออฟไลน์ on-prem · เสียงไม่ออกนอกหน่วยงาน · privacy-first"
- **SW Audit V2.0 (ออกทีหลัง · authoritative) สั่งห้าม:** Voice ตอนนี้ผ่าน Gboard → เสียงขึ้น Google = **ไม่ใช่ offline/privacy** → เคลม = ผิด PDPA + โฆษณาเท็จ
- **Web ทำ:** Voice = badge "นำร่อง" เท่านั้น · ไม่มีคำ privacy/offline/เรียกโวซีน บนเว็บ (verified = 0 hits)
- **ปลดล็อกได้เมื่อ:** on-prem STT (Vflex/CM5 · โปรเจค Local_Voice) ship จริง → ตอนนั้นค่อยชู privacy

## 🟡 §E-NOTE — CapEx strip : เจ้าของสั่งตัด

- เคยลง navy strip "ขายขาด (CapEx) · ผ่านเกณฑ์จัดซื้อภาครัฐ" แล้ว → **เจ้าของสั่งตัดออก** (commit `9d367bb`)
- CapEx angle ยังอยู่แบบ subtle: SEO description ("เหมาะกับงานราชการ · ขายขาด") + Service & Support strip + pricing = "Contact for pricing" (ไม่มี subscription)
- ถ้า PM ต้องการ CapEx เด่นกว่านี้ → ขอ direction (วางตรงไหน/รูปแบบไหน) จะได้ไม่ชนเจ้าของอีก

---

## 🆕 งานเพิ่มหลัง §A-F (Jun 24 · จาก SW)

- **IR Control** → network IR blaster · **ลบยี่ห้อ/รุ่นออกจาก copy** (ใช้ generic "IR blaster (network)") — ตามกฎ no-third-party-brand
- **Multi-Room** → honest framing: **20 ห้อง = LIVE · ~200 ห้อง = "ออกแบบให้ขยาย" (Master Controller)** · 200 ไม่อยู่ใต้ badge LIVE (ref `WEB-COPY-MultiRoom-Dashboard-2026-06-24.md`)

---

## ⏳ Time-gated (รอ ~21 ก.ค. · ยังไม่ลง — ถูกต้อง)

- Case study **กระทรวงพลังงาน** — รอลูกค้าใช้ครบ 1 เดือน + ขออนุญาตก่อน (gov sensitive)
- **Blog โพสต์แรก** (ข่าว deploy) — ผูกกับ case study
- → ทำผ่าน `/admin` blog ตอนถึงเวลา

## 📋 Web open-items (low priority · ไม่บล็อก)

- OG image 1200×630 (เจ้าของทำรูป) · `APP_URL` env ใน Render · features.html Target Customer (6→4 cards ให้ตรง homepage) · mockup migration → repo · ลบ logo เก่า

---

## 🙏 ขอ PM

1. ตัด **"web §A-F"** ออกจาก open-items (เสร็จแล้ว) · assign D-0xx ใน DECISIONS-LOG ได้
2. ตัดสินใจ §E — ต้องการ CapEx positioning เด่นกว่านี้ไหม (ถ้าใช่ ขอ direction)
3. แจ้งเมื่อ on-prem voice (Vflex/CM5) พร้อม → web จะเปิด privacy claim ให้

— 🎨 Web Team · 2026-06-25 · ref `cc web/HANDOFF.md` (Phase 11) · production `16f7641`

# 🚀 Deploy Voscene บน Render Free

> **เวลาที่ใช้:** ~30 นาที (ครั้งแรก)
> **ค่าใช้จ่าย:** ฟรี (มีข้อจำกัดด้านล่าง)

---

## ⚠️ ข้อจำกัดของ Render Free Tier

| รายการ | ข้อจำกัด |
|--------|---------|
| **Sleep** | เว็บจะ "หลับ" หลังไม่มี traffic 15 นาที — ครั้งแรกที่เปิดจะช้า (~30 วินาที) |
| **Database** | ❌ ไม่มี persistent disk → ข้อมูล Lead, content, blog **หายเมื่อ deploy ใหม่/restart** |
| **RAM** | 512 MB (พอใช้สำหรับ landing + AI) |
| **Bandwidth** | 100 GB/เดือน |
| **Region** | Singapore — ping จากไทยดี |

**สำหรับ launch จริง** ควร upgrade เป็น **Starter ($7/เดือน)** เพื่อ:
- ✅ Always-on (ไม่ sleep)
- ✅ Persistent disk (ข้อมูลไม่หาย)
- ✅ Custom domain ฟรี

---

## 📋 ขั้นตอน (3 phases)

### Phase A: สมัคร GitHub + Render (5 นาที)

#### A1. GitHub Account
1. ไปที่ https://github.com/signup
2. สมัครด้วยอีเมล + ตั้ง username (เช่น `chanwit-voscene`)
3. Verify email

#### A2. Render Account
1. ไปที่ https://render.com
2. กด **"Get Started for Free"**
3. เลือก **"Sign up with GitHub"** ← สำคัญ! ใช้ GitHub login จะง่ายตอน deploy
4. อนุญาตให้ Render เข้าถึง GitHub

---

### Phase B: Push Code ไป GitHub (10 นาที)

#### B1. ติดตั้ง Git (ถ้ายังไม่มี)
ดาวน์โหลด: https://git-scm.com/download/win — install ตามค่า default

#### B2. สร้าง Repo บน GitHub
1. กดเมนู **+** มุมขวาบน → **New repository**
2. ชื่อ: `voscene-web`
3. ✅ เลือก **Private** (เพราะมี config สำคัญ)
4. **อย่า** ติ๊ก "Add README" หรือ ".gitignore" (เรามีอยู่แล้ว)
5. กด **Create repository**
6. GitHub จะแสดงคำสั่งสำหรับ push — เก็บไว้ใช้ต่อ

#### B3. Push Code จากเครื่อง

เปิด PowerShell ที่โฟลเดอร์โปรเจค:

```powershell
cd "C:\Users\BANK CSI\Desktop\cc web"

# ตั้งค่า Git ครั้งแรก (เปลี่ยน email/name)
git config --global user.email "your-email@example.com"
git config --global user.name "Your Name"

# Init + commit
git init
git add .
git commit -m "Initial commit — Voscene v1.1"

# Connect to GitHub (เปลี่ยน USERNAME)
git branch -M main
git remote add origin https://github.com/USERNAME/voscene-web.git
git push -u origin main
```

ระบบอาจขอให้ login GitHub — ใช้ token แทนรหัสผ่าน (GitHub บังคับตั้งแต่ 2021)
สร้าง token: https://github.com/settings/tokens → Generate new token (classic) → ติ๊ก `repo` scope → กด Generate → copy token ไปวางตอน push

---

### Phase C: Deploy บน Render (15 นาที)

#### C1. Create Web Service
1. เข้า https://dashboard.render.com
2. กด **"+ New"** มุมบนขวา → **"Web Service"**
3. เลือก repo **`voscene-web`** ที่เพิ่ง push (อาจต้องกด "Configure GitHub App" เพื่อให้สิทธิ์ Render เข้าถึง repo)
4. กด **"Connect"**

#### C2. Render จะอ่าน `render.yaml` อัตโนมัติ
- ✅ Name: `voscene`
- ✅ Region: Singapore
- ✅ Branch: `main`
- ✅ Build: `pip install -r requirements.txt`
- ✅ Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- ✅ Plan: **Free**

#### C3. ตั้ง Environment Variables (สำคัญ!)
ใน Environment section ใส่ค่าต่อไปนี้:

| Key | Value |
|-----|-------|
| `ADMIN_PASSWORD` | **เปลี่ยนเป็นรหัสที่ปลอดภัย** (อย่าใช้ "changeme") |
| `GROQ_API_KEY` | `gsk_...` (จาก https://console.groq.com) |
| `APP_URL` | `https://voscene.onrender.com` (จะรู้หลัง deploy ครั้งแรก) |

> 🔒 **เตือน:** Groq API key ที่เคยใส่ใน chat ก่อนหน้านี้ถือว่า "leak" แล้ว — ควรไป Console สร้าง key ใหม่ + revoke key เก่า

#### C4. Deploy!
1. กด **"Create Web Service"**
2. รอประมาณ 3-5 นาที (Render จะ pull code → install deps → start server)
3. ดู log ที่ Render dashboard — รอเห็น `Application startup complete.`

#### C5. เข้าเว็บ
URL ของคุณ: **`https://voscene-XXXX.onrender.com`** (Render ตั้งให้)

ทดสอบ:
- หน้าแรก: `/`
- Admin: `/admin` → user: `admin` / pass: ที่ตั้งไว้
- AI form: scroll หน้าแรกลงไปที่ AI Consultation

---

## 🌐 ผูก Custom Domain (Optional, Render Free รองรับ)

ถ้ามี domain (เช่น voscene.com):

1. Render dashboard → Web Service → **Settings → Custom Domain**
2. กด **"Add Custom Domain"** → ใส่ `voscene.com`
3. Render บอก DNS records ที่ต้องตั้ง — ไปตั้งที่ domain registrar:
   - **A record:** `@` → IP ของ Render
   - **CNAME:** `www` → `voscene-XXXX.onrender.com`
4. รอ DNS propagate (15 นาที - 24 ชม.) — Render จะออก SSL ฟรีให้

---

## 🔧 ทุกครั้งที่อัปเดตเนื้อหา

```powershell
cd "C:\Users\BANK CSI\Desktop\cc web"
git add .
git commit -m "Update content"
git push
```

Render จะ auto-deploy ภายใน 1-3 นาที 🎉

---

## 🆘 ปัญหาที่อาจเจอ

### Build fail — bcrypt error
แก้: ตรวจ `requirements.txt` ว่ามี `bcrypt==4.2.0` (ไม่ใช่ 5.x)

### "Application failed to respond" หลัง deploy
1. ดู log ที่ Render dashboard
2. ตรวจ env vars ครบไหม (ADMIN_PASSWORD, GROQ_API_KEY)
3. ตรวจ start command ใน `render.yaml` ว่าใช้ `$PORT` (ไม่ใช่ 8000 fixed)

### หน้าแรกเข้าได้แต่ AI form ไม่ตอบ
แก้: ตรวจว่าใส่ `GROQ_API_KEY` ใน Environment แล้ว → restart service

### Lead/Content หายหลัง restart
นี่คือข้อจำกัด Free tier (ไม่มี persistent disk) → ต้อง upgrade เป็น Starter หรือต่อ external DB

---

## 📞 ต้องการความช่วยเหลือ

- Render docs: https://render.com/docs
- Render community: https://community.render.com
- GitHub docs: https://docs.github.com

หรือบอกผม (web team) — จะ debug ให้ครับ

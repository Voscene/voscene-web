# Voscene — เว็บไซต์การตลาด + ระบบหลังบ้าน

> **The voice of smart spaces.** — เว็บไซต์ขายระบบ AV Control แบรนด์ Voscene พร้อม Admin Panel แก้ไขเนื้อหา และ AI วิเคราะห์ความต้องการลูกค้าผ่านฟอร์มอัตโนมัติ

## ฟีเจอร์

- **หน้าเว็บ Public** — หน้าแรก, ฟีเจอร์, ราคา, บทความ, ติดต่อ
- **AI วิเคราะห์ Lead** — กรอกฟอร์ม → AI (Groq llama-3.3-70b) วิเคราะห์ว่าอยู่ในขอบเขตให้บริการหรือไม่ + แนะนำ Package
- **Admin Panel** — แก้ไขเนื้อหาหน้าเว็บ, จัดการ Package/ราคา, ดู Lead, เขียนบทความ Blog
- **Authentication** — JWT cookie session, เปลี่ยนรหัสผ่านได้

## โครงสร้างไฟล์

```
cc web/
├── main.py              # FastAPI app
├── database.py          # SQLite schema
├── seed.py              # ข้อมูลเริ่มต้น
├── auth.py              # Login / Session
├── ai_service.py        # Groq AI integration
├── config.py            # Settings (.env)
├── requirements.txt
├── .env.example         # ก๊อปเป็น .env
├── templates/
│   ├── public/          # หน้าเว็บ
│   └── admin/           # Admin Panel
└── static/              # CSS/JS/Images
```

## ติดตั้ง (Local Development)

### 1. ติดตั้ง Python 3.10+

ดาวน์โหลด: https://www.python.org/downloads/

### 2. สร้าง Virtual Environment

```powershell
# Windows PowerShell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. ติดตั้ง Dependencies

```powershell
pip install -r requirements.txt
```

### 4. ตั้งค่า .env

```powershell
copy .env.example .env
notepad .env
```

แก้ไขค่าต่อไปนี้ในไฟล์ `.env`:

```env
SECRET_KEY="สุ่มข้อความยาวๆ อย่างน้อย 32 ตัว"
ADMIN_USERNAME="admin"
ADMIN_PASSWORD="รหัสผ่านที่ปลอดภัย"
GROQ_API_KEY="gsk_xxx..."  # จาก https://console.groq.com
```

### 5. รันเซิร์ฟเวอร์

```powershell
python main.py
```

เปิดเบราว์เซอร์: http://localhost:8000

- หน้าเว็บ: http://localhost:8000
- Admin: http://localhost:8000/admin

## Deploy บน VPS (Hostneverdie)

### ติดตั้งบน Ubuntu/Debian VPS

```bash
# 1. SSH เข้า VPS
ssh user@your-server-ip

# 2. ติดตั้ง Python + pip
sudo apt update
sudo apt install python3 python3-pip python3-venv nginx -y

# 3. คัดลอกโปรเจคขึ้น Server
# วิธี A: ใช้ SCP จากเครื่อง local
# scp -r ./cc-web/ user@server:/home/user/

# วิธี B: Clone จาก git
# git clone https://github.com/your-repo.git

# 4. ติดตั้ง dependencies
cd /home/user/cc-web
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 5. ตั้งค่า .env
cp .env.example .env
nano .env  # แก้ไขค่า

# 6. ทดสอบรัน
python main.py
# กด Ctrl+C เพื่อหยุด
```

### ตั้งค่า systemd (รันถาวร)

สร้างไฟล์ `/etc/systemd/system/avcontrol.service`:

```ini
[Unit]
Description=AV Control Website
After=network.target

[Service]
User=your-username
WorkingDirectory=/home/your-username/cc-web
Environment="PATH=/home/your-username/cc-web/venv/bin"
ExecStart=/home/your-username/cc-web/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable avcontrol
sudo systemctl start avcontrol
sudo systemctl status avcontrol
```

### ตั้งค่า Nginx Reverse Proxy

สร้างไฟล์ `/etc/nginx/sites-available/avcontrol`:

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    client_max_body_size 20M;

    location /static/ {
        alias /home/your-username/cc-web/static/;
        expires 30d;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/avcontrol /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### ตั้งค่า SSL ด้วย Let's Encrypt (ฟรี)

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

## การใช้งานหลังจาก Deploy

1. เข้าเว็บที่ `https://yourdomain.com`
2. เข้า Admin Panel ที่ `/admin` ใช้ username/password จาก `.env`
3. **เปลี่ยนรหัสผ่านทันที** ผ่านเมนู "ตั้งค่า"

### แก้ไขเนื้อหาหน้าเว็บ

`/admin/content` — แก้ข้อความ Hero, สถิติ, About, ข้อมูลติดต่อ, Footer, SEO

### จัดการราคา/Package

`/admin/packages` — เพิ่ม/แก้ไขราคาและ Features ทั้ง 7 Package

### ดูและจัดการ Lead

`/admin/leads` — ดูรายการลูกค้าที่กรอกฟอร์ม พร้อม AI Analysis
- Filter: ทั้งหมด / ในขอบเขต / นอกขอบเขต / รอติดต่อ
- เปลี่ยนสถานะ (new → contacted → quoted → won/lost)

### เขียนบทความ Blog

`/admin/blog` — เขียน, แก้ไข, เผยแพร่บทความ

## รับ Groq API Key (ฟรี)

1. ไปที่ https://console.groq.com
2. สมัครด้วย Google/GitHub
3. ไปที่ "API Keys" → "Create API Key"
4. ก๊อป key ไปใส่ในไฟล์ `.env`

โควต้าฟรี: 30 requests/min — เพียงพอสำหรับเริ่มต้น

## Backup ข้อมูล

ฐานข้อมูล SQLite อยู่ที่ไฟล์ `data.db` ก๊อปไฟล์นี้ = backup ครบ

```bash
# Backup
cp data.db data-backup-$(date +%Y%m%d).db

# Restore
cp data-backup-20260101.db data.db
sudo systemctl restart avcontrol
```

## Troubleshooting

**ลืมรหัสผ่าน Admin**
```bash
# ลบไฟล์ data.db (ระวัง! จะลบข้อมูลทั้งหมด)
# หรือใช้ python interactive shell แก้ไข
python
>>> from database import SessionLocal, User
>>> from auth import pwd_context
>>> db = SessionLocal()
>>> u = db.query(User).first()
>>> u.password_hash = pwd_context.hash("newpassword")
>>> db.commit()
```

**Port 8000 ถูกใช้**
แก้ที่ `main.py` บรรทัดสุดท้าย เปลี่ยน `port=8000` เป็นอย่างอื่น

**AI ไม่ทำงาน**
- เช็คว่า `GROQ_API_KEY` ถูกต้องใน `.env`
- เช็คโควต้าที่ https://console.groq.com

## License

Proprietary — Central System Integration Co., Ltd.

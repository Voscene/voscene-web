"""สร้างไฟล์ WebP + manifest ของภาพหน้าเว็บ — รันเองบนเครื่องเมื่อเพิ่ม/เปลี่ยนภาพ แล้ว commit ผลลัพธ์

    python build_images.py

ต่อภาพ <name>.jpg/.png ใน static/images สร้าง:
  <name>.webp          ขนาดเต็ม
  <name>-900.webp      กว้าง 900px (เฉพาะภาพที่กว้างกว่า 1200px) ให้จอคอมความหนาแน่นปกติโหลดไฟล์เล็ก
และเขียน static/images/manifest.json = {name: {ext, w, h, v, sizes}} — v = hash เนื้อหา ใช้ต่อท้าย URL (?v=)
เพื่อให้ตั้ง Cache-Control แบบ immutable 1 ปีได้ (ภาพเปลี่ยน → hash เปลี่ยน → URL ใหม่)

เซิร์ฟเวอร์ (Render) ไม่ต้องมี Pillow — อ่านแค่ manifest.json
"""
import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parent / "static" / "images"
# ภาพที่ใช้ผ่าน macro pic() — เพิ่มชื่อที่นี่เมื่อใช้ macro กับภาพใหม่
PREFIXES = ("feature-",)
QUALITY = 80
SMALL_W = 900


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:10]


def main() -> None:
    manifest = {}
    for src in sorted(ROOT.iterdir()):
        if src.suffix.lower() not in (".jpg", ".jpeg", ".png") or not src.name.startswith(PREFIXES):
            continue
        name = src.stem
        if src.suffix.lower() == ".png" and (ROOT / f"{name}.jpg").exists():
            continue  # มีทั้ง .jpg และ .png ชื่อเดียวกัน (feature-pa) — หน้าเว็บใช้ .jpg
        with Image.open(src) as im:
            im = im.convert("RGB")
            w, h = im.size
            im.save(ROOT / f"{name}.webp", "WEBP", quality=QUALITY, method=6)
            sizes = [w]
            if w > 1200:
                small = im.resize((SMALL_W, round(h * SMALL_W / w)), Image.LANCZOS)
                small.save(ROOT / f"{name}-{SMALL_W}.webp", "WEBP", quality=QUALITY, method=6)
                sizes.insert(0, SMALL_W)
        manifest[name] = {"ext": src.suffix.lower(), "w": w, "h": h, "v": _hash(src), "sizes": sizes}
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    jpg = sum((ROOT / f"{n}{m['ext']}").stat().st_size for n, m in manifest.items())
    webp = sum((ROOT / f"{n}.webp").stat().st_size for n in manifest)
    print(f"{len(manifest)} ภาพ · ต้นฉบับ {jpg / 1024:.0f} KB → WebP เต็ม {webp / 1024:.0f} KB")


if __name__ == "__main__":
    main()

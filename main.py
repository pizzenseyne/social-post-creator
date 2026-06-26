from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import anthropic
import sqlite3
import os
import json
import base64
import shutil
import mimetypes
import httpx
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
DB_PATH = BASE_DIR / "posts.db"
UPLOAD_DIR.mkdir(exist_ok=True)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        media_path TEXT NOT NULL,
        media_type TEXT NOT NULL,
        platform TEXT NOT NULL,
        caption TEXT NOT NULL,
        hashtags TEXT DEFAULT '[]',
        scheduled_at TEXT,
        status TEXT DEFAULT 'pending',
        error_message TEXT,
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS platform_config (
        platform TEXT PRIMARY KEY,
        config TEXT NOT NULL
    )''')
    # ── Food Cost tables ──────────────────────────────────────────
    c.execute('''CREATE TABLE IF NOT EXISTS fc_ingredients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        unit TEXT NOT NULL,
        purchase_price REAL NOT NULL,
        purchase_quantity REAL NOT NULL,
        category TEXT DEFAULT 'Autre',
        waste_pct REAL DEFAULT 0,
        price_history TEXT DEFAULT '[]',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS fc_recipes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT DEFAULT 'Pizza',
        selling_price_small REAL DEFAULT 0,
        selling_price_medium REAL DEFAULT 0,
        selling_price_large REAL DEFAULT 0,
        selling_price REAL NOT NULL,
        notes TEXT DEFAULT '',
        monthly_volume INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS fc_recipe_ingredients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipe_id INTEGER NOT NULL,
        ingredient_id INTEGER NOT NULL,
        quantity_small REAL DEFAULT 0,
        quantity_medium REAL DEFAULT 0,
        quantity_large REAL DEFAULT 0,
        quantity REAL NOT NULL,
        FOREIGN KEY (recipe_id) REFERENCES fc_recipes(id) ON DELETE CASCADE,
        FOREIGN KEY (ingredient_id) REFERENCES fc_ingredients(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS fc_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS fc_base_recipes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        type TEXT DEFAULT 'Pâte',
        yield_g REAL NOT NULL,
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS fc_base_recipe_ingredients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        base_recipe_id INTEGER NOT NULL,
        ingredient_id INTEGER NOT NULL,
        quantity_g REAL NOT NULL,
        FOREIGN KEY (base_recipe_id) REFERENCES fc_base_recipes(id) ON DELETE CASCADE,
        FOREIGN KEY (ingredient_id) REFERENCES fc_ingredients(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS fc_charges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        amount REAL NOT NULL,
        category TEXT DEFAULT 'Autre',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS fc_suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        contact TEXT DEFAULT '',
        phone TEXT DEFAULT '',
        email TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS fc_resale_products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT DEFAULT 'Boissons soft',
        buy_price_ht REAL NOT NULL,
        vat_rate REAL DEFAULT 10,
        resale_price_ttc REAL NOT NULL,
        supplier TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )''')
    # Migrations pour colonnes manquantes
    try:
        c.execute("ALTER TABLE fc_ingredients ADD COLUMN waste_pct REAL DEFAULT 0")
    except Exception: pass
    try:
        c.execute("ALTER TABLE fc_ingredients ADD COLUMN price_history TEXT DEFAULT '[]'")
    except Exception: pass
    try:
        c.execute("ALTER TABLE fc_recipes ADD COLUMN selling_price_small REAL DEFAULT 0")
    except Exception: pass
    try:
        c.execute("ALTER TABLE fc_recipes ADD COLUMN selling_price_medium REAL DEFAULT 0")
    except Exception: pass
    try:
        c.execute("ALTER TABLE fc_recipes ADD COLUMN selling_price_large REAL DEFAULT 0")
    except Exception: pass
    try:
        c.execute("ALTER TABLE fc_recipes ADD COLUMN monthly_volume INTEGER DEFAULT 0")
    except Exception: pass
    try:
        c.execute("ALTER TABLE fc_recipe_ingredients ADD COLUMN quantity_small REAL DEFAULT 0")
    except Exception: pass
    try:
        c.execute("ALTER TABLE fc_recipe_ingredients ADD COLUMN quantity_medium REAL DEFAULT 0")
    except Exception: pass
    try:
        c.execute("ALTER TABLE fc_recipe_ingredients ADD COLUMN quantity_large REAL DEFAULT 0")
    except Exception: pass
    conn.commit()
    conn.close()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


async def run_scheduler():
    """Vérifie chaque minute les posts planifiés à publier"""
    while True:
        try:
            db = get_db()
            now = datetime.now().strftime('%Y-%m-%dT%H:%M')
            pending = db.execute(
                "SELECT id FROM posts WHERE status = 'pending' AND scheduled_at IS NOT NULL AND scheduled_at <= ?",
                (now,)
            ).fetchall()
            db.close()
            for row in pending:
                asyncio.create_task(publish_post(row["id"]))
        except Exception as e:
            print(f"[Scheduler] Erreur: {e}")
        await asyncio.sleep(60)


def create_icons():
    """Génère les icônes PWA au démarrage."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        for size in [192, 512]:
            path = BASE_DIR / f"icon-{size}.png"
            if path.exists():
                continue
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            r = size // 5
            draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill="#6366f1")
            fs = int(size * 0.52)
            try:
                font = ImageFont.truetype("arial.ttf", fs)
            except Exception:
                font = ImageFont.load_default()
            bb = draw.textbbox((0, 0), "S", font=font)
            x = (size - (bb[2] - bb[0])) // 2 - bb[0]
            y = (size - (bb[3] - bb[1])) // 2 - bb[1]
            draw.text((x, y), "S", fill="white", font=font)
            img.save(path, "PNG")
    except Exception as e:
        print(f"[Icons] {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    create_icons()
    task = asyncio.create_task(run_scheduler())
    yield
    task.cancel()


app = FastAPI(title="Social Post Creator", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


# ──────────────────────────────────────────────
# Compression image pour Claude (max 5 Mo)
# ──────────────────────────────────────────────

def compress_image_for_claude(image_path: str, max_bytes: int = 4 * 1024 * 1024) -> tuple:
    try:
        from PIL import Image
        import io
        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "P", "CMYK"):
                img = img.convert("RGB")
            # Réduire les dimensions si trop grandes
            max_dim = 1568
            if max(img.size) > max_dim:
                img.thumbnail((max_dim, max_dim), Image.LANCZOS)
            # Compresser jusqu'à passer sous la limite
            for quality in [85, 70, 55, 35, 20]:
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=quality, optimize=True)
                if buf.tell() <= max_bytes:
                    return buf.getvalue(), "image/jpeg"
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=15)
            return buf.getvalue(), "image/jpeg"
    except ImportError:
        # Pillow absent : lire tel quel (risque si > 5 Mo)
        with open(image_path, "rb") as f:
            data = f.read()
        mime, _ = mimetypes.guess_type(image_path)
        return data, mime or "image/jpeg"


# ──────────────────────────────────────────────
# IA : génération de contenu avec Claude
# ──────────────────────────────────────────────

def generate_with_claude(media_path: str, media_type: str, platform: str, tone: str, questionnaire: dict = {}) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("Clé API Anthropic manquante. Ajoutez ANTHROPIC_API_KEY dans le fichier .env")

    client = anthropic.Anthropic(api_key=api_key)

    platforms_info = {
        "instagram": "Instagram (max 2200 caractères, utiliser des emojis pertinents, style visuel et lifestyle)",
        "facebook": "Facebook (conversationnel, peut être plus long, encourager les commentaires et le partage)",
        "tiktok": "TikTok (très court max 150 caractères, dynamique, accrocheur, langage jeune)",
        "google_my_business": "Google My Business (professionnel, informatif sur le business local, max 1500 caractères, inclure un appel à l'action)",
    }

    tones_info = {
        "professionnel": "professionnel, soigné et crédible",
        "fun": "amusant, léger et engageant avec un peu d'humour",
        "storytelling": "narratif et émotionnel, qui raconte une histoire et crée de la connexion",
    }

    platform_desc = platforms_info.get(platform, platforms_info["instagram"])
    tone_desc = tones_info.get(tone, tones_info["professionnel"])

    objectif_labels = {
        "vendre": "vendre un produit ou service",
        "informer": "informer l'audience",
        "divertir": "divertir et amuser",
        "engager": "créer de l'engagement et de la discussion",
        "evenement": "annoncer un événement",
        "inspirer": "inspirer et motiver",
    }

    context_parts = []
    if questionnaire.get("sujet"):
        context_parts.append(f"Sujet du contenu : {questionnaire['sujet']}")
    if questionnaire.get("objectif"):
        context_parts.append(f"Objectif du post : {objectif_labels.get(questionnaire['objectif'], questionnaire['objectif'])}")
    if questionnaire.get("cible"):
        context_parts.append(f"Audience cible : {questionnaire['cible']}")
    if questionnaire.get("offre"):
        context_parts.append(f"Offre / info clé à mentionner : {questionnaire['offre']}")
    if questionnaire.get("cta"):
        context_parts.append(f"Appel à l'action souhaité : {questionnaire['cta']}")

    # Charger le profil business sauvegardé
    try:
        db = get_db()
        biz_row = db.execute("SELECT config FROM platform_config WHERE platform = '__business__'").fetchone()
        db.close()
        business = json.loads(biz_row["config"]) if biz_row else {}
    except Exception:
        business = {}

    biz_block = ""
    if business.get("nom"):
        biz_lines = [f"- Commerce : {business['nom']}"]
        if business.get("secteur"):    biz_lines.append(f"- Secteur : {business['secteur']}")
        if business.get("description"): biz_lines.append(f"- Activité : {business['description']}")
        if business.get("audience"):   biz_lines.append(f"- Clientèle : {business['audience']}")
        if business.get("valeurs"):    biz_lines.append(f"- Valeurs : {business['valeurs']}")
        if business.get("site"):       biz_lines.append(f"- Site web : {business['site']}")
        biz_block = "\n\nProfil du commerce (contexte permanent — intègre-le naturellement) :\n" + "\n".join(biz_lines)

    context_block = biz_block
    if context_parts:
        context_block += "\n\nInformations spécifiques à ce post (PRIORITÉ — utilise-les impérativement) :\n" + "\n".join(f"- {p}" for p in context_parts)

    prompt = f"""Tu es un expert en réseaux sociaux. Génère du contenu pour {platform_desc}.

Crée une légende avec un ton {tone_desc}.{context_block}

Réponds UNIQUEMENT avec du JSON valide (pas de texte avant ou après):
{{
  "caption": "la légende ici",
  "hashtags": ["#tag1", "#tag2", "#tag3"],
  "description": "brève description de ce que tu vois"
}}

Règles importantes:
- La légende doit être en français
- Entre 15 et 20 hashtags pertinents et populaires
- Intègre naturellement les informations utilisateur dans la légende
- Le contenu doit être authentique et adapté exactement à la plateforme"""

    if media_type == "image":
        img_bytes, mime = compress_image_for_claude(media_path)
        img_data = base64.standard_b64encode(img_bytes).decode()

        msg = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=1500,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": mime, "data": img_data}},
                    {"type": "text", "text": prompt}
                ]
            }]
        )
    else:
        msg = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=1000,
            messages=[{"role": "user", "content": f"Génère du contenu pour une vidéo.\n\n{prompt}"}]
        )

    text = msg.content[0].text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    return json.loads(text)


# ──────────────────────────────────────────────
# Publication sur les réseaux sociaux
# ──────────────────────────────────────────────

async def publish_to_instagram(post: dict, config: dict) -> None:
    token = config.get("access_token")
    ig_id = config.get("ig_user_id")
    if not token or not ig_id:
        raise ValueError("Configuration Instagram incomplète (access_token et ig_user_id requis)")

    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    media_url = f"{base_url}/{post['media_path']}"

    async with httpx.AsyncClient(timeout=120) as client:
        params_container = {
            "caption": post["full_caption"],
            "access_token": token,
        }
        if post["media_type"] == "image":
            params_container["image_url"] = media_url
        else:
            params_container["video_url"] = media_url
            params_container["media_type"] = "REELS"

        r = await client.post(
            f"https://graph.facebook.com/v19.0/{ig_id}/media",
            params=params_container
        )
        r.raise_for_status()
        container_id = r.json()["id"]

        r2 = await client.post(
            f"https://graph.facebook.com/v19.0/{ig_id}/media_publish",
            params={"creation_id": container_id, "access_token": token}
        )
        r2.raise_for_status()


async def publish_to_facebook(post: dict, config: dict) -> None:
    token = config.get("access_token")
    page_id = config.get("page_id")
    if not token or not page_id:
        raise ValueError("Configuration Facebook incomplète (access_token et page_id requis)")

    media_path = str(BASE_DIR / post["media_path"])

    async with httpx.AsyncClient(timeout=120) as client:
        if post["media_type"] == "image":
            with open(media_path, "rb") as f:
                r = await client.post(
                    f"https://graph.facebook.com/v19.0/{page_id}/photos",
                    data={"caption": post["full_caption"], "access_token": token},
                    files={"source": ("photo.jpg", f, "image/jpeg")}
                )
        else:
            with open(media_path, "rb") as f:
                r = await client.post(
                    f"https://graph.facebook.com/v19.0/{page_id}/videos",
                    data={"description": post["full_caption"], "access_token": token},
                    files={"source": ("video.mp4", f, "video/mp4")}
                )
        r.raise_for_status()


async def publish_to_tiktok(post: dict, config: dict) -> None:
    token = config.get("access_token")
    if not token:
        raise ValueError("Configuration TikTok incomplète (access_token requis)")
    if post["media_type"] != "video":
        raise ValueError("TikTok ne supporte que les vidéos")

    media_path = str(BASE_DIR / post["media_path"])
    file_size = os.path.getsize(media_path)

    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(
            "https://open.tiktokapis.com/v2/post/publish/video/init/",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "post_info": {
                    "title": post["caption"][:150],
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": file_size,
                    "chunk_size": file_size,
                    "total_chunk_count": 1
                }
            }
        )
        r.raise_for_status()
        upload_url = r.json()["data"]["upload_url"]

        with open(media_path, "rb") as f:
            video_bytes = f.read()
        r2 = await client.put(
            upload_url,
            content=video_bytes,
            headers={
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes 0-{file_size-1}/{file_size}"
            }
        )
        r2.raise_for_status()


async def publish_to_gmb(post: dict, config: dict) -> None:
    token = config.get("access_token")
    account_id = config.get("account_id")
    location_id = config.get("location_id")
    if not token or not account_id or not location_id:
        raise ValueError("Configuration Google My Business incomplète (access_token, account_id, location_id requis)")

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"https://mybusiness.googleapis.com/v4/accounts/{account_id}/locations/{location_id}/localPosts",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "languageCode": "fr",
                "summary": post["full_caption"],
                "topicType": "STANDARD",
            }
        )
        r.raise_for_status()


async def publish_with_ayrshare(post: dict, api_key: str) -> None:
    """Publication via Ayrshare — une seule clé pour tous les réseaux."""
    platform_map = {
        "instagram": "instagram",
        "facebook": "facebook",
        "tiktok": "tiktok",
        "google_my_business": "gmb",
    }
    ayr_platform = platform_map.get(post["platform"])
    if not ayr_platform:
        raise ValueError(f"Plateforme non supportée par Ayrshare : {post['platform']}")

    media_path = str(BASE_DIR / post["media_path"])
    headers = {"Authorization": f"Bearer {api_key}"}

    async with httpx.AsyncClient(timeout=120) as client:
        # 1. Upload du média sur Ayrshare
        with open(media_path, "rb") as f:
            mime = "video/mp4" if post["media_type"] == "video" else "image/jpeg"
            up = await client.post(
                "https://app.ayrshare.com/api/media/upload",
                headers=headers,
                files={"file": (os.path.basename(media_path), f, mime)},
            )
        up.raise_for_status()
        media_url = up.json().get("url") or up.json().get("contentUrl", "")
        if not media_url:
            raise ValueError("Ayrshare n'a pas retourné d'URL pour le média uploadé")

        # 2. Publication
        body = {
            "post": post["full_caption"],
            "platforms": [ayr_platform],
            "mediaUrls": [media_url],
        }
        resp = await client.post(
            "https://app.ayrshare.com/api/post",
            headers={**headers, "Content-Type": "application/json"},
            json=body,
        )
        resp.raise_for_status()


async def publish_post(post_id: int):
    db = get_db()
    try:
        row = db.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
        if not row or row["status"] == "published":
            return
        post = dict(row)

        hashtags = json.loads(post.get("hashtags") or "[]")
        full_caption = post["caption"]
        if hashtags:
            full_caption += "\n\n" + " ".join(hashtags)
        post["full_caption"] = full_caption

        # Essayer Ayrshare en premier (plus simple)
        ayr_row = db.execute("SELECT config FROM platform_config WHERE platform = 'ayrshare'").fetchone()
        if ayr_row:
            ayr_config = json.loads(ayr_row["config"])
            api_key = ayr_config.get("api_key", "")
            if api_key:
                await publish_with_ayrshare(post, api_key)
                db.execute("UPDATE posts SET status = 'published' WHERE id = ?", (post_id,))
                db.commit()
                print(f"[OK] Post {post_id} publié via Ayrshare sur {post['platform']}")
                return

        # Sinon, utiliser la config directe par plateforme
        config_row = db.execute("SELECT config FROM platform_config WHERE platform = ?", (post["platform"],)).fetchone()
        if not config_row:
            raise ValueError(
                "Aucune configuration trouvée. Configurez Ayrshare (recommandé) ou les clés API directes dans Paramètres."
            )

        config = json.loads(config_row["config"])
        if post["platform"] == "instagram":
            await publish_to_instagram(post, config)
        elif post["platform"] == "facebook":
            await publish_to_facebook(post, config)
        elif post["platform"] == "tiktok":
            await publish_to_tiktok(post, config)
        elif post["platform"] == "google_my_business":
            await publish_to_gmb(post, config)

        db.execute("UPDATE posts SET status = 'published' WHERE id = ?", (post_id,))
        db.commit()
        print(f"[OK] Post {post_id} publié sur {post['platform']}")

    except Exception as e:
        db.execute("UPDATE posts SET status = 'failed', error_message = ? WHERE id = ?", (str(e), post_id))
        db.commit()
        print(f"[ERREUR] Post {post_id}: {e}")
    finally:
        db.close()


# ──────────────────────────────────────────────
# Routes API
# ──────────────────────────────────────────────

@app.get("/api/check")
async def health_check():
    return {"status": "ok", "anthropic_key": bool(os.getenv("ANTHROPIC_API_KEY"))}


@app.post("/api/upload")
async def upload_media(file: UploadFile = File(...)):
    ALLOWED = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "video/x-msvideo": ".avi",
        "video/webm": ".webm",
    }
    ct = file.content_type or ""
    if ct not in ALLOWED:
        raise HTTPException(400, f"Format non supporté: {ct}. Acceptés: JPG, PNG, WEBP, GIF, MP4, MOV, AVI, WEBM")

    ext = ALLOWED[ct]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{ts}{ext}"
    dest = UPLOAD_DIR / filename

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    media_type = "image" if ct.startswith("image") else "video"
    return {
        "filename": filename,
        "path": f"uploads/{filename}",
        "media_type": media_type,
        "size": os.path.getsize(dest),
    }


@app.post("/api/generate")
async def generate_content(
    media_path: str = Form(...),
    platform: str = Form(...),
    tone: str = Form("professionnel"),
    questionnaire: str = Form("{}"),
):
    full_path = BASE_DIR / media_path
    if not full_path.exists():
        raise HTTPException(404, "Fichier média introuvable")

    media_type = "image" if any(str(media_path).lower().endswith(e) for e in [".jpg", ".jpeg", ".png", ".webp", ".gif"]) else "video"

    try:
        q = json.loads(questionnaire)
    except Exception:
        q = {}

    try:
        result = generate_with_claude(str(full_path), media_type, platform, tone, q)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except json.JSONDecodeError:
        raise HTTPException(500, "Erreur de parsing de la réponse IA. Réessayez.")
    except Exception as e:
        raise HTTPException(500, f"Erreur IA: {str(e)}")


@app.get("/api/posts")
async def list_posts():
    db = get_db()
    rows = db.execute("SELECT * FROM posts ORDER BY created_at DESC").fetchall()
    db.close()
    return [dict(r) for r in rows]


@app.post("/api/posts")
async def create_post(
    media_path: str = Form(...),
    media_type: str = Form(...),
    platform: str = Form(...),
    caption: str = Form(...),
    hashtags: str = Form("[]"),
    scheduled_at: Optional[str] = Form(None),
):
    db = get_db()
    cur = db.execute(
        "INSERT INTO posts (media_path, media_type, platform, caption, hashtags, scheduled_at, status) VALUES (?, ?, ?, ?, ?, ?, 'pending')",
        (media_path, media_type, platform, caption, hashtags, scheduled_at),
    )
    post_id = cur.lastrowid
    db.commit()
    db.close()
    return {"id": post_id, "status": "pending"}


@app.post("/api/publish/{post_id}")
async def publish_now(post_id: int):
    db = get_db()
    row = db.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(404, "Post introuvable")

    await publish_post(post_id)

    db = get_db()
    updated = dict(db.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone())
    db.close()

    if updated["status"] == "failed":
        raise HTTPException(500, updated.get("error_message") or "Erreur de publication")
    return {"status": "published"}


@app.delete("/api/posts/{post_id}")
async def delete_post(post_id: int):
    db = get_db()
    db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    db.commit()
    db.close()
    return {"deleted": True}


@app.get("/api/business")
async def get_business():
    db = get_db()
    row = db.execute("SELECT config FROM platform_config WHERE platform = '__business__'").fetchone()
    db.close()
    return json.loads(row["config"]) if row else {}


@app.post("/api/business")
async def save_business(request: Request):
    body = await request.json()
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO platform_config (platform, config) VALUES ('__business__', ?)",
        (json.dumps(body),),
    )
    db.commit()
    db.close()
    return {"saved": True}


@app.post("/api/business/generate")
async def generate_business_profile(request: Request):
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(400, "Nom du commerce requis")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(400, "Clé API Anthropic manquante")

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=600,
        messages=[{
            "role": "user",
            "content": f"""Tu es un expert en marketing. Génère un profil business complet pour un commerce français nommé "{name}".

Réponds UNIQUEMENT avec du JSON valide, sans texte avant ou après :
{{
  "nom": "{name}",
  "secteur": "secteur d'activité le plus probable",
  "description": "description courte et accrocheuse en 2 phrases maximum",
  "audience": "clientèle cible typique décrite en une phrase",
  "valeurs": "3 à 5 valeurs clés séparées par des virgules"
}}"""
        }]
    )

    text = msg.content[0].text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    return json.loads(text)


@app.get("/api/config/{platform}")
async def get_platform_config(platform: str):
    db = get_db()
    row = db.execute("SELECT config FROM platform_config WHERE platform = ?", (platform,)).fetchone()
    db.close()
    if not row:
        return {}
    config = json.loads(row["config"])
    return {k: ("•" * 8 + str(v)[-4:] if v and len(str(v)) > 8 else v) for k, v in config.items()}


@app.get("/api/config")
async def get_config():
    db = get_db()
    rows = db.execute("SELECT * FROM platform_config").fetchall()
    db.close()
    result = {}
    for r in rows:
        config = json.loads(r["config"])
        result[r["platform"]] = {
            k: ("•" * 8 + str(v)[-4:] if v and len(str(v)) > 8 else v)
            for k, v in config.items()
        }
    return result


@app.post("/api/config/{platform}")
async def save_config(platform: str, request: Request):
    body = await request.json()
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO platform_config (platform, config) VALUES (?, ?)",
        (platform, json.dumps(body)),
    )
    db.commit()
    db.close()
    return {"saved": True}


@app.get("/manifest.json")
async def serve_manifest():
    return FileResponse(str(BASE_DIR / "manifest.json"), media_type="application/manifest+json")

@app.get("/sw.js")
async def serve_sw():
    return FileResponse(str(BASE_DIR / "sw.js"), media_type="application/javascript")

@app.get("/icon-{size}.png")
async def serve_icon(size: int):
    path = BASE_DIR / f"icon-{size}.png"
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(str(path), media_type="image/png")

@app.get("/")
async def serve_frontend():
    return FileResponse(str(BASE_DIR / "index.html"))

@app.get("/foodcost")
async def serve_foodcost():
    return FileResponse(str(BASE_DIR / "foodcost.html"))


# ══════════════════════════════════════════════════════════════════
#  FOOD COST API v2
# ══════════════════════════════════════════════════════════════════

def _compute_recipe(rec: dict, items: list) -> dict:
    """Calcule coûts pour les 3 tailles + taille principale."""
    sizes = ["small", "medium", "large"]
    for size in sizes:
        cost = sum(
            ((it["purchase_price"] / it["purchase_quantity"]) * (1 + it.get("waste_pct", 0) / 100)) * it.get(f"quantity_{size}", 0)
            for it in items
        )
        price = rec.get(f"selling_price_{size}", 0) or 0
        rec[f"cost_{size}"] = round(cost, 4)
        rec[f"fc_pct_{size}"] = round(cost / price * 100, 2) if price > 0 else 0
        rec[f"margin_{size}"] = round(price - cost, 4) if price > 0 else 0

    # Taille principale
    cost_main = sum(
        ((it["purchase_price"] / it["purchase_quantity"]) * (1 + it.get("waste_pct", 0) / 100)) * it["quantity"]
        for it in items
    )
    price_main = rec.get("selling_price", 0) or 0
    rec["ingredient_cost"] = round(cost_main, 4)
    rec["food_cost_pct"] = round(cost_main / price_main * 100, 2) if price_main > 0 else 0
    rec["margin"] = round(price_main - cost_main, 4)

    # Rentabilité mensuelle estimée
    vol = rec.get("monthly_volume", 0) or 0
    rec["monthly_profit"] = round(rec["margin"] * vol, 2)
    rec["monthly_revenue"] = round(price_main * vol, 2)
    return rec


# ── Ingrédients ──────────────────────────────────────────────────

@app.get("/api/fc/ingredients")
async def list_ingredients():
    db = get_db()
    rows = db.execute("SELECT * FROM fc_ingredients ORDER BY category, name").fetchall()
    db.close()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["price_history"] = json.loads(d.get("price_history") or "[]")
        except Exception:
            d["price_history"] = []
        result.append(d)
    return result

@app.post("/api/fc/ingredients")
async def create_ingredient(data: dict):
    db = get_db()
    history = json.dumps([{"date": datetime.now().strftime("%Y-%m-%d"), "price": data["purchase_price"], "qty": data["purchase_quantity"]}])
    cur = db.execute(
        "INSERT INTO fc_ingredients (name, unit, purchase_price, purchase_quantity, category, waste_pct, price_history) VALUES (?,?,?,?,?,?,?)",
        (data["name"], data["unit"], data["purchase_price"], data["purchase_quantity"],
         data.get("category", "Autre"), data.get("waste_pct", 0), history)
    )
    db.commit()
    row = db.execute("SELECT * FROM fc_ingredients WHERE id=?", (cur.lastrowid,)).fetchone()
    db.close()
    d = dict(row)
    d["price_history"] = json.loads(d.get("price_history") or "[]")
    return d

@app.put("/api/fc/ingredients/{ing_id}")
async def update_ingredient(ing_id: int, data: dict):
    db = get_db()
    old = db.execute("SELECT * FROM fc_ingredients WHERE id=?", (ing_id,)).fetchone()
    if not old:
        db.close()
        raise HTTPException(404)
    # Enregistrer l'historique si le prix change
    try:
        history = json.loads(old["price_history"] or "[]")
    except Exception:
        history = []
    new_price = data["purchase_price"]
    new_qty = data["purchase_quantity"]
    if old["purchase_price"] != new_price or old["purchase_quantity"] != new_qty:
        history.append({"date": datetime.now().strftime("%Y-%m-%d"), "price": new_price, "qty": new_qty})
        history = history[-24:]  # garder 24 entrées max
    db.execute(
        "UPDATE fc_ingredients SET name=?, unit=?, purchase_price=?, purchase_quantity=?, category=?, waste_pct=?, price_history=? WHERE id=?",
        (data["name"], data["unit"], new_price, new_qty, data.get("category", "Autre"),
         data.get("waste_pct", 0), json.dumps(history), ing_id)
    )
    db.commit()
    row = db.execute("SELECT * FROM fc_ingredients WHERE id=?", (ing_id,)).fetchone()
    db.close()
    d = dict(row)
    d["price_history"] = json.loads(d.get("price_history") or "[]")
    return d

@app.delete("/api/fc/ingredients/{ing_id}")
async def delete_ingredient(ing_id: int):
    db = get_db()
    db.execute("DELETE FROM fc_ingredients WHERE id=?", (ing_id,))
    db.commit()
    db.close()
    return {"ok": True}


# ── Recettes ─────────────────────────────────────────────────────

@app.get("/api/fc/recipes")
async def list_recipes():
    db = get_db()
    recipes = db.execute("SELECT * FROM fc_recipes ORDER BY category, name").fetchall()
    result = []
    for r in recipes:
        rec = dict(r)
        items = db.execute(
            """SELECT ri.id, ri.quantity, ri.quantity_small, ri.quantity_medium, ri.quantity_large,
                      i.id as ingredient_id, i.name, i.unit, i.purchase_price, i.purchase_quantity, i.waste_pct
               FROM fc_recipe_ingredients ri
               JOIN fc_ingredients i ON i.id = ri.ingredient_id
               WHERE ri.recipe_id=?""", (rec["id"],)
        ).fetchall()
        items_list = [dict(it) for it in items]
        rec["ingredients"] = items_list
        rec = _compute_recipe(rec, items_list)
        result.append(rec)
    db.close()
    return result

@app.post("/api/fc/recipes")
async def create_recipe(data: dict):
    db = get_db()
    cur = db.execute(
        """INSERT INTO fc_recipes (name, category, selling_price, selling_price_small, selling_price_medium,
           selling_price_large, notes, monthly_volume) VALUES (?,?,?,?,?,?,?,?)""",
        (data["name"], data.get("category", "Pizza"), data["selling_price"],
         data.get("selling_price_small", 0), data.get("selling_price_medium", 0),
         data.get("selling_price_large", 0), data.get("notes", ""), data.get("monthly_volume", 0))
    )
    recipe_id = cur.lastrowid
    for ing in data.get("ingredients", []):
        db.execute(
            """INSERT INTO fc_recipe_ingredients
               (recipe_id, ingredient_id, quantity, quantity_small, quantity_medium, quantity_large)
               VALUES (?,?,?,?,?,?)""",
            (recipe_id, ing["ingredient_id"], ing["quantity"],
             ing.get("quantity_small", 0), ing.get("quantity_medium", 0), ing.get("quantity_large", 0))
        )
    db.commit()
    db.close()
    recipes = await list_recipes()
    return next(r for r in recipes if r["id"] == recipe_id)

@app.put("/api/fc/recipes/{recipe_id}")
async def update_recipe(recipe_id: int, data: dict):
    db = get_db()
    db.execute(
        """UPDATE fc_recipes SET name=?, category=?, selling_price=?, selling_price_small=?,
           selling_price_medium=?, selling_price_large=?, notes=?, monthly_volume=? WHERE id=?""",
        (data["name"], data.get("category", "Pizza"), data["selling_price"],
         data.get("selling_price_small", 0), data.get("selling_price_medium", 0),
         data.get("selling_price_large", 0), data.get("notes", ""),
         data.get("monthly_volume", 0), recipe_id)
    )
    db.execute("DELETE FROM fc_recipe_ingredients WHERE recipe_id=?", (recipe_id,))
    for ing in data.get("ingredients", []):
        db.execute(
            """INSERT INTO fc_recipe_ingredients
               (recipe_id, ingredient_id, quantity, quantity_small, quantity_medium, quantity_large)
               VALUES (?,?,?,?,?,?)""",
            (recipe_id, ing["ingredient_id"], ing["quantity"],
             ing.get("quantity_small", 0), ing.get("quantity_medium", 0), ing.get("quantity_large", 0))
        )
    db.commit()
    db.close()
    recipes = await list_recipes()
    match = next((r for r in recipes if r["id"] == recipe_id), None)
    if not match:
        raise HTTPException(404)
    return match

@app.delete("/api/fc/recipes/{recipe_id}")
async def delete_recipe(recipe_id: int):
    db = get_db()
    db.execute("DELETE FROM fc_recipe_ingredients WHERE recipe_id=?", (recipe_id,))
    db.execute("DELETE FROM fc_recipes WHERE id=?", (recipe_id,))
    db.commit()
    db.close()
    return {"ok": True}


# ── Paramètres ───────────────────────────────────────────────────

@app.get("/api/fc/settings")
async def get_settings():
    db = get_db()
    rows = db.execute("SELECT key, value FROM fc_settings").fetchall()
    db.close()
    return {r["key"]: r["value"] for r in rows}

@app.post("/api/fc/settings")
async def save_settings(data: dict):
    db = get_db()
    for k, v in data.items():
        db.execute("INSERT OR REPLACE INTO fc_settings (key, value) VALUES (?,?)", (k, str(v)))
    db.commit()
    db.close()
    return {"ok": True}


# ── Dashboard stats ───────────────────────────────────────────────

@app.get("/api/fc/stats")
async def fc_stats():
    db = get_db()
    recipes = await list_recipes()
    total = len(recipes)
    avg_fc = round(sum(r["food_cost_pct"] for r in recipes) / total, 2) if total else 0
    best = min(recipes, key=lambda r: r["food_cost_pct"]) if recipes else None
    worst = max(recipes, key=lambda r: r["food_cost_pct"]) if recipes else None
    ing_count = db.execute("SELECT COUNT(*) FROM fc_ingredients").fetchone()[0]
    total_monthly_profit = sum(r.get("monthly_profit", 0) for r in recipes)
    total_monthly_revenue = sum(r.get("monthly_revenue", 0) for r in recipes)
    settings_rows = db.execute("SELECT key, value FROM fc_settings").fetchall()
    db.close()
    settings = {r["key"]: r["value"] for r in settings_rows}
    target_fc = float(settings.get("target_fc", 30))
    alerts = [r for r in recipes if r["food_cost_pct"] > target_fc and r["food_cost_pct"] > 0]
    return {
        "total_recipes": total,
        "avg_food_cost_pct": avg_fc,
        "ingredient_count": ing_count,
        "best_recipe": best,
        "worst_recipe": worst,
        "total_monthly_profit": round(total_monthly_profit, 2),
        "total_monthly_revenue": round(total_monthly_revenue, 2),
        "target_fc": target_fc,
        "alerts": [{"name": r["name"], "fc": r["food_cost_pct"]} for r in alerts],
    }


# ── Recettes de base (sous-recettes : pâte, sauce…) ─────────────

@app.get("/api/fc/base-recipes")
async def list_base_recipes():
    db = get_db()
    rows = db.execute("SELECT * FROM fc_base_recipes ORDER BY type, name").fetchall()
    result = []
    for r in rows:
        rec = dict(r)
        items = db.execute(
            """SELECT bri.quantity_g, i.id as ingredient_id, i.name, i.unit, i.purchase_price, i.purchase_quantity, i.waste_pct
               FROM fc_base_recipe_ingredients bri
               JOIN fc_ingredients i ON i.id = bri.ingredient_id
               WHERE bri.base_recipe_id=?""", (rec["id"],)
        ).fetchall()
        items_list = [dict(it) for it in items]
        total_cost = sum(
            (it["purchase_price"] / it["purchase_quantity"]) * (1 + (it.get("waste_pct") or 0) / 100) * it["quantity_g"]
            for it in items_list
        )
        rec["ingredients"] = items_list
        rec["total_cost"] = round(total_cost, 4)
        rec["cost_per_g"] = round(total_cost / rec["yield_g"], 6) if rec["yield_g"] > 0 else 0
        result.append(rec)
    db.close()
    return result

@app.post("/api/fc/base-recipes")
async def create_base_recipe(data: dict):
    db = get_db()
    cur = db.execute(
        "INSERT INTO fc_base_recipes (name, type, yield_g, notes) VALUES (?,?,?,?)",
        (data["name"], data.get("type", "Pâte"), data["yield_g"], data.get("notes", ""))
    )
    rid = cur.lastrowid
    for ing in data.get("ingredients", []):
        db.execute("INSERT INTO fc_base_recipe_ingredients (base_recipe_id, ingredient_id, quantity_g) VALUES (?,?,?)",
                   (rid, ing["ingredient_id"], ing["quantity_g"]))
    db.commit()
    db.close()
    rows = await list_base_recipes()
    return next(r for r in rows if r["id"] == rid)

@app.put("/api/fc/base-recipes/{rid}")
async def update_base_recipe(rid: int, data: dict):
    db = get_db()
    db.execute("UPDATE fc_base_recipes SET name=?, type=?, yield_g=?, notes=? WHERE id=?",
               (data["name"], data.get("type", "Pâte"), data["yield_g"], data.get("notes", ""), rid))
    db.execute("DELETE FROM fc_base_recipe_ingredients WHERE base_recipe_id=?", (rid,))
    for ing in data.get("ingredients", []):
        db.execute("INSERT INTO fc_base_recipe_ingredients (base_recipe_id, ingredient_id, quantity_g) VALUES (?,?,?)",
                   (rid, ing["ingredient_id"], ing["quantity_g"]))
    db.commit()
    db.close()
    rows = await list_base_recipes()
    return next((r for r in rows if r["id"] == rid), None)

@app.delete("/api/fc/base-recipes/{rid}")
async def delete_base_recipe(rid: int):
    db = get_db()
    db.execute("DELETE FROM fc_base_recipe_ingredients WHERE base_recipe_id=?", (rid,))
    db.execute("DELETE FROM fc_base_recipes WHERE id=?", (rid,))
    db.commit()
    db.close()
    return {"ok": True}


# ── Frais fixes mensuels ──────────────────────────────────────────

@app.get("/api/fc/charges")
async def list_charges():
    db = get_db()
    rows = db.execute("SELECT * FROM fc_charges ORDER BY category, name").fetchall()
    db.close()
    return [dict(r) for r in rows]

@app.post("/api/fc/charges")
async def create_charge(data: dict):
    db = get_db()
    cur = db.execute("INSERT INTO fc_charges (name, amount, category) VALUES (?,?,?)",
                     (data["name"], data["amount"], data.get("category", "Autre")))
    db.commit()
    row = db.execute("SELECT * FROM fc_charges WHERE id=?", (cur.lastrowid,)).fetchone()
    db.close()
    return dict(row)

@app.delete("/api/fc/charges/{charge_id}")
async def delete_charge(charge_id: int):
    db = get_db()
    db.execute("DELETE FROM fc_charges WHERE id=?", (charge_id,))
    db.commit()
    db.close()
    return {"ok": True}


# ── Fournisseurs ──────────────────────────────────────────────────

@app.get("/api/fc/suppliers")
async def list_suppliers():
    db = get_db()
    rows = db.execute("SELECT * FROM fc_suppliers ORDER BY name").fetchall()
    db.close()
    return [dict(r) for r in rows]

@app.post("/api/fc/suppliers")
async def create_supplier(data: dict):
    db = get_db()
    cur = db.execute("INSERT INTO fc_suppliers (name, contact, phone, email, notes) VALUES (?,?,?,?,?)",
                     (data["name"], data.get("contact",""), data.get("phone",""), data.get("email",""), data.get("notes","")))
    db.commit()
    row = db.execute("SELECT * FROM fc_suppliers WHERE id=?", (cur.lastrowid,)).fetchone()
    db.close()
    return dict(row)

@app.put("/api/fc/suppliers/{sup_id}")
async def update_supplier(sup_id: int, data: dict):
    db = get_db()
    db.execute("UPDATE fc_suppliers SET name=?, contact=?, phone=?, email=?, notes=? WHERE id=?",
               (data["name"], data.get("contact",""), data.get("phone",""), data.get("email",""), data.get("notes",""), sup_id))
    db.commit()
    row = db.execute("SELECT * FROM fc_suppliers WHERE id=?", (sup_id,)).fetchone()
    db.close()
    return dict(row)

@app.delete("/api/fc/suppliers/{sup_id}")
async def delete_supplier(sup_id: int):
    db = get_db()
    db.execute("DELETE FROM fc_suppliers WHERE id=?", (sup_id,))
    db.commit()
    db.close()
    return {"ok": True}


# ── Produits de revente ───────────────────────────────────────────

@app.get("/api/fc/resale")
async def list_resale():
    db = get_db()
    rows = db.execute("SELECT * FROM fc_resale_products ORDER BY category, name").fetchall()
    db.close()
    result = []
    for r in rows:
        d = dict(r)
        buy_ht = d["buy_price_ht"]
        resale_ttc = d["resale_price_ttc"]
        vat = d["vat_rate"]
        resale_ht = resale_ttc / (1 + vat / 100)
        d["resale_price_ht"] = round(resale_ht, 4)
        d["margin_ht"] = round(resale_ht - buy_ht, 4)
        d["margin_pct"] = round((resale_ht - buy_ht) / resale_ht * 100, 2) if resale_ht > 0 else 0
        result.append(d)
    return result

@app.post("/api/fc/resale")
async def create_resale(data: dict):
    db = get_db()
    cur = db.execute(
        "INSERT INTO fc_resale_products (name, category, buy_price_ht, vat_rate, resale_price_ttc, supplier, notes) VALUES (?,?,?,?,?,?,?)",
        (data["name"], data.get("category","Boissons soft"), data["buy_price_ht"],
         data.get("vat_rate", 10), data["resale_price_ttc"], data.get("supplier",""), data.get("notes",""))
    )
    db.commit()
    row = db.execute("SELECT * FROM fc_resale_products WHERE id=?", (cur.lastrowid,)).fetchone()
    db.close()
    return dict(row)

@app.put("/api/fc/resale/{prod_id}")
async def update_resale(prod_id: int, data: dict):
    db = get_db()
    db.execute(
        "UPDATE fc_resale_products SET name=?, category=?, buy_price_ht=?, vat_rate=?, resale_price_ttc=?, supplier=?, notes=? WHERE id=?",
        (data["name"], data.get("category","Boissons soft"), data["buy_price_ht"],
         data.get("vat_rate", 10), data["resale_price_ttc"], data.get("supplier",""), data.get("notes",""), prod_id)
    )
    db.commit()
    row = db.execute("SELECT * FROM fc_resale_products WHERE id=?", (prod_id,)).fetchone()
    db.close()
    return dict(row)

@app.delete("/api/fc/resale/{prod_id}")
async def delete_resale(prod_id: int):
    db = get_db()
    db.execute("DELETE FROM fc_resale_products WHERE id=?", (prod_id,))
    db.commit()
    db.close()
    return {"ok": True}


# ── Analyse IA ────────────────────────────────────────────────────

@app.post("/api/fc/ai-analysis")
async def fc_ai_analysis():
    db = get_db()
    settings_rows = db.execute("SELECT key, value FROM fc_settings").fetchall()
    db.close()
    cfg = {r["key"]: r["value"] for r in settings_rows}

    provider   = cfg.get("ai_provider", "claude")
    api_claude = cfg.get("api_claude", "") or os.getenv("ANTHROPIC_API_KEY", "")
    api_openai = cfg.get("api_openai", "") or os.getenv("OPENAI_API_KEY", "")
    api_gemini = cfg.get("api_gemini", "") or os.getenv("GEMINI_API_KEY", "")
    pizzeria   = cfg.get("name", "Pizz'en Seyne")

    recipes = await list_recipes()
    if not recipes:
        raise HTTPException(400, "Aucune recette à analyser")

    summary = "\n".join(
        f"- {r['name']} ({r['category']}) : food cost {r['food_cost_pct']}%, coût matière {r['ingredient_cost']}€, prix vente {r['selling_price']}€, marge {r['margin']}€"
        for r in recipes
    )
    prompt = f"""Tu es un consultant en restauration spécialisé en pizzeria. Voici les données food cost de la pizzeria {pizzeria} :

{summary}

Analyse ces données et donne :
1. Un diagnostic global (2-3 phrases)
2. Les 3 principales recommandations pour améliorer la rentabilité (concrètes et actionnables)
3. Les recettes à surveiller en priorité et pourquoi
4. Un conseil sur la stratégie de prix si pertinent

Réponds en français, de manière concise et pratique. Format Markdown."""

    if provider == "claude":
        if not api_claude:
            raise HTTPException(400, "Clé API Claude manquante — ajoutez-la dans Paramètres")
        client = anthropic.Anthropic(api_key=api_claude)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        return {"analysis": msg.content[0].text}

    elif provider == "openai":
        if not api_openai:
            raise HTTPException(400, "Clé API OpenAI manquante — ajoutez-la dans Paramètres")
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_openai}", "Content-Type": "application/json"},
                json={"model": "gpt-4o-mini", "max_tokens": 1000,
                      "messages": [{"role": "user", "content": prompt}]}
            )
            r.raise_for_status()
            return {"analysis": r.json()["choices"][0]["message"]["content"]}

    elif provider == "gemini":
        if not api_gemini:
            raise HTTPException(400, "Clé API Gemini manquante — ajoutez-la dans Paramètres")
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_gemini}",
                json={"contents": [{"parts": [{"text": prompt}]}]}
            )
            r.raise_for_status()
            return {"analysis": r.json()["candidates"][0]["content"]["parts"][0]["text"]}

    raise HTTPException(400, "Provider IA inconnu")

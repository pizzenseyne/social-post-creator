from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import sqlite3
import os
import json
import httpx
import base64
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "foodcost.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS fc_ingredients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        unit TEXT NOT NULL,
        purchase_price REAL NOT NULL,
        purchase_quantity REAL NOT NULL,
        category TEXT DEFAULT 'Autre',
        waste_pct REAL DEFAULT 0,
        price_history TEXT DEFAULT '[]',
        supplier TEXT DEFAULT '',
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
    # Migrations
    for migration in [
        "ALTER TABLE fc_ingredients ADD COLUMN waste_pct REAL DEFAULT 0",
        "ALTER TABLE fc_ingredients ADD COLUMN price_history TEXT DEFAULT '[]'",
        "ALTER TABLE fc_ingredients ADD COLUMN supplier TEXT DEFAULT ''",
        "ALTER TABLE fc_recipes ADD COLUMN selling_price_small REAL DEFAULT 0",
        "ALTER TABLE fc_recipes ADD COLUMN selling_price_medium REAL DEFAULT 0",
        "ALTER TABLE fc_recipes ADD COLUMN selling_price_large REAL DEFAULT 0",
        "ALTER TABLE fc_recipes ADD COLUMN monthly_volume INTEGER DEFAULT 0",
        "ALTER TABLE fc_recipe_ingredients ADD COLUMN quantity_small REAL DEFAULT 0",
        "ALTER TABLE fc_recipe_ingredients ADD COLUMN quantity_medium REAL DEFAULT 0",
        "ALTER TABLE fc_recipe_ingredients ADD COLUMN quantity_large REAL DEFAULT 0",
    ]:
        try:
            c.execute(migration)
        except Exception:
            pass
    conn.commit()
    conn.close()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Pizz'en Seyne — Food Cost", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def serve_frontend():
    return FileResponse(str(BASE_DIR / "foodcost.html"))

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


# ══════════════════════════════════════════════════════════════════
#  FOOD COST API
# ══════════════════════════════════════════════════════════════════

def _compute_recipe(rec: dict, items: list) -> dict:
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

    cost_main = sum(
        ((it["purchase_price"] / it["purchase_quantity"]) * (1 + it.get("waste_pct", 0) / 100)) * it["quantity"]
        for it in items
    )
    price_main = rec.get("selling_price", 0) or 0
    rec["ingredient_cost"] = round(cost_main, 4)
    rec["food_cost_pct"] = round(cost_main / price_main * 100, 2) if price_main > 0 else 0
    rec["margin"] = round(price_main - cost_main, 4)

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
        "INSERT INTO fc_ingredients (name, unit, purchase_price, purchase_quantity, category, waste_pct, price_history, supplier) VALUES (?,?,?,?,?,?,?,?)",
        (data["name"], data["unit"], data["purchase_price"], data["purchase_quantity"],
         data.get("category", "Autre"), data.get("waste_pct", 0), history, data.get("supplier", ""))
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
    try:
        history = json.loads(old["price_history"] or "[]")
    except Exception:
        history = []
    new_price = data["purchase_price"]
    new_qty = data["purchase_quantity"]
    if old["purchase_price"] != new_price or old["purchase_quantity"] != new_qty:
        history.append({"date": datetime.now().strftime("%Y-%m-%d"), "price": new_price, "qty": new_qty})
        history = history[-24:]
    db.execute(
        "UPDATE fc_ingredients SET name=?, unit=?, purchase_price=?, purchase_quantity=?, category=?, waste_pct=?, price_history=?, supplier=? WHERE id=?",
        (data["name"], data["unit"], new_price, new_qty, data.get("category", "Autre"),
         data.get("waste_pct", 0), json.dumps(history), data.get("supplier", ""), ing_id)
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


# ── Recettes de base ─────────────────────────────────────────────

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


# ── Frais fixes ───────────────────────────────────────────────────

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


# ── Export / Import ───────────────────────────────────────────────

@app.get("/api/fc/export")
async def fc_export():
    db = get_db()
    ingredients = [dict(r) for r in db.execute("SELECT * FROM fc_ingredients").fetchall()]
    for i in ingredients:
        try:
            i["price_history"] = json.loads(i.get("price_history") or "[]")
        except Exception:
            i["price_history"] = []

    recipes_rows = db.execute("SELECT * FROM fc_recipes").fetchall()
    recipes_out = []
    for rec in recipes_rows:
        r = dict(rec)
        r["ingredients"] = [dict(x) for x in db.execute(
            "SELECT * FROM fc_recipe_ingredients WHERE recipe_id=?", (r["id"],)
        ).fetchall()]
        recipes_out.append(r)

    base_recipes_rows = db.execute("SELECT * FROM fc_base_recipes").fetchall()
    base_recipes_out = []
    for rec in base_recipes_rows:
        r = dict(rec)
        r["ingredients"] = [dict(x) for x in db.execute(
            "SELECT * FROM fc_base_recipe_ingredients WHERE base_recipe_id=?", (r["id"],)
        ).fetchall()]
        base_recipes_out.append(r)

    charges = [dict(r) for r in db.execute("SELECT * FROM fc_charges").fetchall()]
    suppliers = [dict(r) for r in db.execute("SELECT * FROM fc_suppliers").fetchall()]
    resale = [dict(r) for r in db.execute("SELECT * FROM fc_resale_products").fetchall()]
    settings = {r["key"]: r["value"] for r in db.execute("SELECT key, value FROM fc_settings").fetchall()}
    db.close()

    return {
        "version": 1,
        "exported_at": datetime.now().isoformat(),
        "ingredients": ingredients,
        "recipes": recipes_out,
        "base_recipes": base_recipes_out,
        "charges": charges,
        "suppliers": suppliers,
        "resale": resale,
        "settings": settings,
    }


@app.post("/api/fc/import")
async def fc_import(request: Request):
    data = await request.json()
    db = get_db()
    ing_id_map = {}

    for ing in data.get("ingredients", []):
        old_id = ing["id"]
        history = json.dumps(ing.get("price_history", []))
        cur = db.execute(
            "INSERT INTO fc_ingredients (name, unit, purchase_price, purchase_quantity, category, waste_pct, price_history, supplier) VALUES (?,?,?,?,?,?,?,?)",
            (ing["name"], ing["unit"], ing["purchase_price"], ing["purchase_quantity"],
             ing.get("category", "Autre"), ing.get("waste_pct", 0), history, ing.get("supplier", ""))
        )
        ing_id_map[old_id] = cur.lastrowid

    for rec in data.get("recipes", []):
        cur = db.execute(
            "INSERT INTO fc_recipes (name, category, selling_price, selling_price_small, selling_price_medium, selling_price_large, notes, monthly_volume) VALUES (?,?,?,?,?,?,?,?)",
            (rec["name"], rec.get("category", "Pizza"), rec["selling_price"],
             rec.get("selling_price_small", 0), rec.get("selling_price_medium", 0),
             rec.get("selling_price_large", 0), rec.get("notes", ""), rec.get("monthly_volume", 0))
        )
        new_recipe_id = cur.lastrowid
        for ing in rec.get("ingredients", []):
            new_ing_id = ing_id_map.get(ing["ingredient_id"])
            if new_ing_id:
                db.execute(
                    "INSERT INTO fc_recipe_ingredients (recipe_id, ingredient_id, quantity, quantity_small, quantity_medium, quantity_large) VALUES (?,?,?,?,?,?)",
                    (new_recipe_id, new_ing_id, ing["quantity"],
                     ing.get("quantity_small", 0), ing.get("quantity_medium", 0), ing.get("quantity_large", 0))
                )

    for rec in data.get("base_recipes", []):
        cur = db.execute(
            "INSERT INTO fc_base_recipes (name, type, yield_g, notes) VALUES (?,?,?,?)",
            (rec["name"], rec.get("type", "Pâte"), rec["yield_g"], rec.get("notes", ""))
        )
        new_br_id = cur.lastrowid
        for ing in rec.get("ingredients", []):
            new_ing_id = ing_id_map.get(ing["ingredient_id"])
            if new_ing_id:
                db.execute(
                    "INSERT INTO fc_base_recipe_ingredients (base_recipe_id, ingredient_id, quantity_g) VALUES (?,?,?)",
                    (new_br_id, new_ing_id, ing["quantity_g"])
                )

    for charge in data.get("charges", []):
        db.execute("INSERT INTO fc_charges (name, amount, category) VALUES (?,?,?)",
                   (charge["name"], charge["amount"], charge.get("category", "Autre")))

    for sup in data.get("suppliers", []):
        db.execute("INSERT INTO fc_suppliers (name, contact, phone, email, notes) VALUES (?,?,?,?,?)",
                   (sup["name"], sup.get("contact",""), sup.get("phone",""), sup.get("email",""), sup.get("notes","")))

    for prod in data.get("resale", []):
        db.execute(
            "INSERT INTO fc_resale_products (name, category, buy_price_ht, vat_rate, resale_price_ttc, supplier, notes) VALUES (?,?,?,?,?,?,?)",
            (prod["name"], prod.get("category","Boissons soft"), prod["buy_price_ht"],
             prod.get("vat_rate", 10), prod["resale_price_ttc"], prod.get("supplier",""), prod.get("notes",""))
        )

    for k, v in data.get("settings", {}).items():
        if k != "api_openai":
            db.execute("INSERT OR REPLACE INTO fc_settings (key, value) VALUES (?,?)", (k, str(v)))

    db.commit()
    db.close()
    return {"ok": True, "imported": {
        "ingredients": len(data.get("ingredients", [])),
        "recipes": len(data.get("recipes", [])),
        "base_recipes": len(data.get("base_recipes", [])),
        "charges": len(data.get("charges", [])),
        "suppliers": len(data.get("suppliers", [])),
        "resale": len(data.get("resale", [])),
    }}


# ── Analyse IA ────────────────────────────────────────────────────

@app.post("/api/fc/ai-analysis")
async def fc_ai_analysis():
    db = get_db()
    settings_rows = db.execute("SELECT key, value FROM fc_settings").fetchall()
    db.close()
    cfg = {r["key"]: r["value"] for r in settings_rows}

    api_openai = cfg.get("api_openai", "") or os.getenv("OPENAI_API_KEY", "")
    pizzeria = cfg.get("name", "Pizz'en Seyne")

    if not api_openai:
        raise HTTPException(400, "Clé API OpenAI manquante — ajoutez-la dans Paramètres")

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

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_openai}", "Content-Type": "application/json"},
            json={"model": "gpt-4o-mini", "max_tokens": 1000,
                  "messages": [{"role": "user", "content": prompt}]}
        )
        r.raise_for_status()
        return {"analysis": r.json()["choices"][0]["message"]["content"]}


# ── Import facture / devis ─────────────────────────────────────────

@app.post("/api/fc/analyze-invoice")
async def analyze_invoice(file: UploadFile = File(...)):
    db = get_db()
    settings_rows = db.execute("SELECT key, value FROM fc_settings").fetchall()
    db.close()
    cfg = {r["key"]: r["value"] for r in settings_rows}
    api_openai = cfg.get("api_openai", "") or os.getenv("OPENAI_API_KEY", "")
    if not api_openai:
        raise HTTPException(400, "Clé API OpenAI manquante — ajoutez-la dans Paramètres")

    content = await file.read()
    mime = file.content_type or ""

    # Conversion PDF → image PNG (première page) si pymupdf disponible
    if mime == "application/pdf" or file.filename.lower().endswith(".pdf"):
        try:
            import fitz
            doc = fitz.open(stream=content, filetype="pdf")
            page = doc[0]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            content = pix.tobytes("png")
            mime = "image/png"
        except ImportError:
            raise HTTPException(400, "PDF non supporté sur ce serveur — envoyez une photo (JPG/PNG) de la facture")

    if mime not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(400, "Format non supporté. Envoyez une image JPG, PNG ou un PDF.")

    img_b64 = base64.b64encode(content).decode()

    prompt = """Tu es un assistant pour une pizzeria. Analyse cette facture ou ce devis fournisseur.
Extrais tous les articles (matières premières, ingrédients, produits alimentaires).

Réponds UNIQUEMENT avec du JSON valide, sans texte avant ou après :
{
  "supplier": "nom du fournisseur si visible, sinon null",
  "date": "date de la facture si visible (format YYYY-MM-DD), sinon null",
  "items": [
    {
      "name": "nom de l'article",
      "quantity": 1.0,
      "unit": "kg",
      "unit_price": 0.0,
      "category": "catégorie suggérée parmi: Farines & Céréales, Viandes & Charcuterie, Fromages & Laitages, Légumes & Fruits, Conserves & Sauces, Boissons, Emballages, Autre"
    }
  ]
}

Règles :
- unit doit être : kg, g, L, cl, pcs, boite, sachet
- unit_price = prix par unité (HT de préférence)
- Si tu vois une quantité et un prix total, calcule le prix unitaire = prix_total / quantité
- N'inclus pas les frais de livraison, remises, TVA comme articles
- Si un article n'est clairement pas un ingrédient alimentaire, ignore-le"""

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_openai}", "Content-Type": "application/json"},
            json={
                "model": "gpt-4o",
                "max_tokens": 2000,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}", "detail": "high"}},
                        {"type": "text", "text": prompt}
                    ]
                }]
            }
        )
        r.raise_for_status()

    text = r.json()["choices"][0]["message"]["content"].strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    return json.loads(text)

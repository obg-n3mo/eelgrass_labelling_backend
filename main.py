from fastapi import FastAPI, UploadFile, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, text
import shutil, os, uuid
from fastapi.staticfiles import StaticFiles


# --- FastAPI app ---
app = FastAPI()



# --- SQLite engine ---
engine = create_engine("sqlite:///eelgrass.db")

# --- Create tables automatically ---
with engine.begin() as conn:
    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT UNIQUE NOT NULL
    );
    """))
    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL
    );
    """))
    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS labels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        image_id INTEGER,
        answer TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """))
    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS masks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        image_id INTEGER,
        mask_path TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """))

# --- Ensure storage folders exist ---
os.makedirs("images", exist_ok=True)
os.makedirs("masks", exist_ok=True)



def populate_images():
    import os
    from sqlalchemy import text

    IMAGE_DIR = "images"

    with engine.begin() as conn:
        for fname in os.listdir(IMAGE_DIR):
            if fname.lower().endswith((".jpg", ".png", ".jpeg")):
                conn.execute(
                    text("INSERT INTO images (filename) VALUES (:f)"),
                    {"f": fname}
                )

# --- Routes ---

'''
# Upload image
@app.post("/upload")
async def upload(file: UploadFile):
    filename = f"{uuid.uuid4()}_{file.filename}"
    path = f"images/{filename}"
    with open(path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    with engine.begin() as conn:
        conn.execute(text("INSERT INTO images (filename) VALUES (:f)"), {"f": filename})

    return {"status": "ok", "filename": filename}
'''
# Login
@app.post("/login")
def login(user: str = Form(...)):
    with engine.begin() as conn:
        conn.execute(text("INSERT OR IGNORE INTO users (user) VALUES (:e)"), {"e": user})
        user = conn.execute(text("SELECT id FROM users WHERE user=:e"), {"e": user}).fetchone()
    return {"user_id": user[0]}

# Get random image
@app.get("/image") 
def get_image():
    with engine.begin() as conn:
        img = conn.execute(text("SELECT id, filename FROM images ORDER BY RANDOM() LIMIT 1")).fetchone()
    
    if img is None:
        return {"id": None, "url": None}

    return {"id": img[0], "url": f"/images/{img[1]}"}

# Save label
@app.post("/label")
def save_label(user_id: int = Form(...), image_id: int = Form(...), answer: str = Form(...)):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO labels (user_id, image_id, answer)
            VALUES (:u,:i,:a)
        """), {"u": user_id, "i": image_id, "a": answer})
    return {"status": "saved"}

# Save mask
@app.post("/mask")
async def save_mask(user_id: int = Form(...), image_id: int = Form(...), file: UploadFile = Form(...)):
    name = f"{uuid.uuid4()}.png"
    path = f"masks/{name}"
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO masks (user_id, image_id, mask_path)
            VALUES (:u,:i,:p)
        """), {"u": user_id, "i": image_id, "p": name})

    return {"status": "saved"}

# --- Serve static files ---
app.mount("/images", StaticFiles(directory="images"), name="images")
app.mount("/masks", StaticFiles(directory="masks"), name="masks")
app.mount("/", StaticFiles(directory="static", html=True), name="static")

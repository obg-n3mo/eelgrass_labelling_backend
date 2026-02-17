from fastapi import FastAPI, UploadFile, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, text
import shutil, os, uuid
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import random

# --- Configuration ---
load_dotenv()

ENV = os.getenv("ENV", "dev")  # dev by default

R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL")

BASE_URL = (
    os.getenv("BASE_URL")
    if os.getenv("BASE_URL")
    else "http://127.0.0.1:8000"
)


# --- FastAPI app ---
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://obg-n3mo.github.io",  # your GitHub Pages site
        "http://localhost:5500",      # local dev
        "http://127.0.0.1:5500"
        ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- SQLalchemy engine ---
DB_PATH = os.getenv("DB_PATH", "eelgrass.db")
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def init_db():
    DB_PATH = "eelgrass.db"  # path to your SQLite DB
    with open("filenames.txt") as f:
        R2_FILENAMES = [line.strip() for line in f]

    with engine.connect() as conn:
        
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT UNIQUE NOT NULL
        );
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE NOT NULL
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
        CREATE TABLE IF NOT EXISTS user_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            image_id INTEGER,
            label TEXT,
            mask_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, image_id)
            );
        """))

        for fname in R2_FILENAMES:
            # Use OR IGNORE to avoid duplicates
            conn.execute(
                text("INSERT OR IGNORE INTO images (filename) VALUES (:f)"),
                {"f": fname}
            )

init_db()

print("DB_PATH:", os.getenv("DB_PATH"))
print("ENGINE:", engine.url)


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
        filename TEXT UNIQUE NOT NULL
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
    CREATE TABLE IF NOT EXISTS user_images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        image_id INTEGER,
        label TEXT,
        mask_path TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, image_id)
        );
    """))

     


# --- Ensure storage folders exist ---
os.makedirs("images", exist_ok=True)



def populate_images():
    import os
    from sqlalchemy import text

    IMAGE_DIR = "images"

    if not os.path.exists(IMAGE_DIR):
        print("Images directory not found")
        return

    with engine.begin() as conn:
        for fname in os.listdir(IMAGE_DIR):
            if fname.lower().endswith((".jpg", ".png", ".jpeg")):
                conn.execute(
                    text("INSERT OR IGNORE INTO images (filename) VALUES (:f)"),
                    {"f": fname}
                )

# --- Routes ---


# Login
@app.post("/login")
def login(
    user: str = Form(...),
    user_type: str = Form(...)  # "new" or "returning"
):
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM users WHERE user = :u"),
            {"u": user}
        ).fetchone()

        if user_type == "new":
            if existing:
                raise HTTPException(status_code=400, detail="Username already taken")

            conn.execute(
                text("INSERT INTO users (user) VALUES (:u)"),
                {"u": user}
            )

            user_id = conn.execute(
                text("SELECT id FROM users WHERE user = :u"),
                {"u": user}
            ).fetchone()[0]

        else:  # returning user
            if not existing:
                raise HTTPException(status_code=400, detail="User does not exist")

            user_id = existing[0]

    return {"user_id": user_id}

# Get random image

@app.get("/image")
def get_image(user: str):
    sql = text("""
        SELECT images.id, images.filename
        FROM images
        LEFT JOIN labels
          ON images.id = labels.image_id
         AND labels.user_id = :user
        WHERE labels.image_id IS NULL
        ORDER BY RANDOM()
        LIMIT 1
    """)
    with engine.connect() as conn:
        result = conn.execute(sql, {"user": user}).fetchone()

    if result is None:
        return {"done": True,"message": "You have labelled all images!"}

    return {
        "id": result.id,
        "url": f"{R2_PUBLIC_URL}/{result.filename}"
    }



@app.get("/download-db")
def download_db():
    db_path = os.getenv("DB_PATH")  # make sure this points to your SQLite file
    return FileResponse(db_path, filename="eelgrass.db")


'''
Link to download database:

https://eelgrass-labelling-backend.onrender.com/download-db

Script to convert to csv:

import pandas as pd
from sqlalchemy import create_engine

engine = create_engine('sqlite:///eelgrass.db')

query = "SELECT * FROM labels;" 
df = pd.read_sql(query, engine)
output_path = "eelgrass.csv"
df.to_csv(output_path, index=False, encoding="utf-8")
print(f"Data successfully exported to {output_path}")
'''


# Save label
@app.post("/label")
def save_label(
    user_id: int = Form(...),
    image_id: int = Form(...),
    label: str = Form(...)
):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO user_images (user_id, image_id, label)
            VALUES (:u, :i, :l)
        """), {"u": user_id, "i": image_id, "l": label})

    return {"status": "ok"}


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

@app.get("/stats/{user_id}")
def user_stats(user_id: int):
    with engine.begin() as conn:
        count = conn.execute(text("""
            SELECT COUNT(*) FROM user_images WHERE user_id = :u
        """), {"u": user_id}).fetchone()[0]

    return {"count": count}

@app.get("/leaderboard")
def leaderboard():
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT users.user, COUNT(user_images.id)
            FROM users
            JOIN user_images ON users.id = user_images.user_id
            GROUP BY users.id
            ORDER BY COUNT(user_images.id) DESC
            LIMIT 10
        """)).fetchall()

    return [{"user": r[0], "total": r[1]} for r in rows]




if ENV == "dev":
    app.mount("/images", StaticFiles(directory="images"), name="images")

@app.on_event("startup")
def startup():
    populate_images()


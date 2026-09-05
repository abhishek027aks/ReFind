"""ReFind API - complete local demo backend. Uses SQLite; migrate to PostgreSQL for deployment."""
from contextlib import asynccontextmanager, closing
from datetime import datetime, timezone
from pathlib import Path
import base64, hashlib, hmac, json, os, re, sqlite3
import logging
from collections import defaultdict
from time import monotonic
from typing import Literal
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

logger = logging.getLogger("refind")
logging.basicConfig(level=os.environ.get("REFIND_LOG_LEVEL", "INFO"))

DATABASE = Path(os.environ.get("REFIND_DATABASE_PATH", Path(__file__).with_name("refind.db")))
UPLOAD_DIR = Path(os.environ.get("REFIND_UPLOAD_DIR", Path(__file__).with_name("uploads")))
UPLOAD_DIR.mkdir(exist_ok=True)
ENVIRONMENT = os.environ.get("REFIND_ENV", "development").lower()
STORAGE_PROVIDER = os.environ.get("REFIND_STORAGE_PROVIDER", "local").lower()
S3_BUCKET = os.environ.get("REFIND_S3_BUCKET", "")
S3_REGION = os.environ.get("REFIND_S3_REGION", "")
S3_ENDPOINT_URL = os.environ.get("REFIND_S3_ENDPOINT_URL", "")
REDIS_URL = os.environ.get("REFIND_REDIS_URL", "")
DATABASE_URL = os.environ.get("REFIND_DATABASE_URL", f"sqlite:///{DATABASE.as_posix()}")
TOKEN_SECRET_VALUE = os.environ.get("REFIND_TOKEN_SECRET")
if not TOKEN_SECRET_VALUE:
    TOKEN_SECRET_VALUE = "local-development-only-change-before-deployment"
TOKEN_SECRET = TOKEN_SECRET_VALUE.encode()
if len(TOKEN_SECRET) < 32:
    logger.warning("REFIND_TOKEN_SECRET is shorter than 32 bytes; use a long random secret in production")
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "REFIND_CORS_ORIGINS",
        "http://localhost:5173,http://localhost:4173,http://localhost:4174,"
        "http://127.0.0.1:5173,http://127.0.0.1:4173,http://127.0.0.1:4174",
    ).split(",")
    if origin.strip()
]
@asynccontextmanager
async def lifespan(_app):
    validate_configuration()
    initialise_database()
    yield

app = FastAPI(title="ReFind API", version="2.0.0", lifespan=lifespan)
rate_windows = defaultdict(list)
RATE_LIMIT = int(os.environ.get("REFIND_RATE_LIMIT", "60"))
RATE_WINDOW_SECONDS = 60
redis_client = None

def validate_configuration():
    if not DATABASE_URL.startswith("sqlite"):
        raise RuntimeError(
            "The request API uses the SQLite adapter. Run Alembic against PostgreSQL first, "
            "then provide a PostgreSQL runtime adapter before switching REFIND_DATABASE_URL."
        )
    if ENVIRONMENT == "production":
        if len(TOKEN_SECRET) < 32 or TOKEN_SECRET_VALUE.startswith(("replace-", "local-development")):
            raise RuntimeError("REFIND_TOKEN_SECRET must be a unique 32+ byte secret in production")
        if not ALLOWED_ORIGINS or any(origin.startswith("http://") for origin in ALLOWED_ORIGINS):
            raise RuntimeError("Production CORS origins must use HTTPS")
        if DATABASE_URL.startswith("sqlite"):
            logger.warning("Production is using SQLite; configure REFIND_DATABASE_URL for PostgreSQL")
    if STORAGE_PROVIDER not in {"local", "s3"}:
        raise RuntimeError("REFIND_STORAGE_PROVIDER must be local or s3")
    if STORAGE_PROVIDER == "s3" and not S3_BUCKET:
        raise RuntimeError("REFIND_S3_BUCKET is required when S3 storage is enabled")

def get_redis():
    global redis_client
    if not REDIS_URL:
        return None
    if redis_client is None:
        try:
            import redis
            redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
            redis_client.ping()
        except Exception as error:
            logger.error("Redis rate limiter unavailable: %s", error)
            redis_client = None
    return redis_client

def allow_request(key: str) -> bool:
    current = monotonic()
    client = get_redis()
    if client:
        redis_key = f"refind:rate:{key}:{int(current // RATE_WINDOW_SECONDS)}"
        count = client.incr(redis_key)
        if count == 1:
            client.expire(redis_key, RATE_WINDOW_SECONDS + 1)
        return count <= RATE_LIMIT
    recent = [stamp for stamp in rate_windows[key] if current - stamp < RATE_WINDOW_SECONDS]
    if len(recent) >= RATE_LIMIT:
        return False
    recent.append(current)
    rate_windows[key] = recent
    return True

@app.middleware("http")
async def request_guard(request, call_next):
    client = request.client.host if request.client else "unknown"
    path = request.url.path
    if path.startswith("/auth/") or path == "/uploads":
        key = f"{client}:{path.split('/')[1]}"
        if not allow_request(key):
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=429, content={"detail": "Too many requests. Please try again shortly."}, headers={"Retry-After": "60"})
    response = await call_next(request)
    logger.info("%s %s %s", request.method, path, response.status_code)
    return response
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

class RegisterInput(BaseModel): name: str = Field(min_length=2, max_length=80); email: str = Field(min_length=5, max_length=160); password: str = Field(min_length=8, max_length=128)
class LoginInput(BaseModel): email: str; password: str
class ReportInput(BaseModel): kind: Literal["lost", "found"]; name: str = Field(min_length=2, max_length=100); category: str = Field(min_length=2, max_length=60); location: str = Field(min_length=2, max_length=150); description: str = Field(min_length=8, max_length=2000); photo_url: str | None = Field(default=None, max_length=300)
class ClaimInput(BaseModel): report_id: int; ownership_detail: str = Field(min_length=8, max_length=1000); return_point: str = Field(min_length=2, max_length=150)
class StatusInput(BaseModel): status: Literal["open", "possible_match", "claimed", "verified", "returned", "closed", "flagged"]
class ClaimUpdateInput(BaseModel): status: Literal["pending", "verified", "flagged", "returned"]
class MatchInput(BaseModel): status: Literal["open", "dismissed", "verified"]

def connection():
    db = sqlite3.connect(DATABASE); db.row_factory = sqlite3.Row; db.execute("PRAGMA foreign_keys = ON"); return db
def now(): return datetime.now(timezone.utc).isoformat()
def row(item): return dict(item) if item else None
def hash_password(password, salt=None):
    salt = salt or os.urandom(16); return base64.urlsafe_b64encode(salt + hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)).decode()
def verify_password(password, stored):
    try:
        raw = base64.urlsafe_b64decode(stored.encode())
        return len(raw) > 16 and hmac.compare_digest(raw[16:], hashlib.pbkdf2_hmac("sha256", password.encode(), raw[:16], 310_000))
    except (ValueError, TypeError):
        return False
def token_for(user):
    payload = base64.urlsafe_b64encode(json.dumps({"sub": user["id"], "role": user["role"], "exp": int(datetime.now(timezone.utc).timestamp()) + 28800}, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"{payload}.{hmac.new(TOKEN_SECRET, payload.encode(), hashlib.sha256).hexdigest()}"
def user_from_header(authorization: str | None, required=True):
    if not authorization or not authorization.startswith("Bearer "):
        if required: raise HTTPException(401, "Please sign in to continue")
        return None
    try:
        payload, signature = authorization[7:].split("."); expected = hmac.new(TOKEN_SECRET, payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected): raise ValueError()
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if data["exp"] < int(datetime.now(timezone.utc).timestamp()): raise ValueError()
    except Exception: raise HTTPException(401, "Your session is invalid or expired")
    with closing(connection()) as db: user = db.execute("SELECT id,name,email,role,created_at FROM users WHERE id=?", [data["sub"]]).fetchone()
    if not user: raise HTTPException(401, "Account not found")
    return row(user)
def require_admin(authorization):
    user = user_from_header(authorization)
    if user["role"] != "admin": raise HTTPException(403, "Admin access required")
    return user
def words(value): return set(re.findall(r"[a-z0-9]+", value.lower()))
def match_score(left, right):
    a, b = words(left), words(right); overlap = len(a & b) / max(1, len(a | b)); return round(overlap * 100)
def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
def notify(db, user_id, kind, message, report_id=None):
    if user_id: db.execute("INSERT INTO notifications (user_id,kind,message,report_id,read,created_at) VALUES (?,?,?,?,0,?)", (user_id, kind, message, report_id, now()))

def store_upload(filename: str, content: bytes, content_type: str) -> str:
    if STORAGE_PROVIDER == "local":
        target = UPLOAD_DIR / filename
        target.write_bytes(content)
        return f"/uploads/{filename}"
    import boto3
    client = boto3.client("s3", region_name=S3_REGION or None, endpoint_url=S3_ENDPOINT_URL or None)
    client.put_object(Bucket=S3_BUCKET, Key=f"uploads/{filename}", Body=content, ContentType=content_type)
    return f"s3://{S3_BUCKET}/uploads/{filename}"

def initialise_database():
    with closing(connection()) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,email TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'student' CHECK(role IN ('student','admin')),created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER REFERENCES users(id),kind TEXT NOT NULL CHECK(kind IN ('lost','found')),name TEXT NOT NULL,category TEXT NOT NULL,location TEXT NOT NULL,description TEXT NOT NULL,photo_url TEXT,status TEXT NOT NULL DEFAULT 'open',created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS claims (id INTEGER PRIMARY KEY AUTOINCREMENT,report_id INTEGER NOT NULL REFERENCES reports(id),user_id INTEGER REFERENCES users(id),ownership_detail TEXT NOT NULL,return_point TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS matches (id INTEGER PRIMARY KEY AUTOINCREMENT,lost_report_id INTEGER NOT NULL REFERENCES reports(id),found_report_id INTEGER NOT NULL REFERENCES reports(id),score INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'open',created_at TEXT NOT NULL,UNIQUE(lost_report_id,found_report_id));
        CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL REFERENCES users(id),kind TEXT NOT NULL,message TEXT NOT NULL,report_id INTEGER REFERENCES reports(id),read INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_reports_kind_status_created ON reports(kind, status, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_reports_user_id_created ON reports(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_claims_report_id_status ON claims(report_id, status);
        CREATE INDEX IF NOT EXISTS idx_claims_user_id_status ON claims(user_id, status);
        CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id, read, created_at DESC);
        """)
        columns = {item[1] for item in db.execute("PRAGMA table_info(reports)")}
        if "user_id" not in columns: db.execute("ALTER TABLE reports ADD COLUMN user_id INTEGER REFERENCES users(id)")
        if "photo_url" not in columns: db.execute("ALTER TABLE reports ADD COLUMN photo_url TEXT")
        claim_columns = {item[1] for item in db.execute("PRAGMA table_info(claims)")}
        if "user_id" not in claim_columns: db.execute("ALTER TABLE claims ADD COLUMN user_id INTEGER REFERENCES users(id)")
        if not db.execute("SELECT 1 FROM users WHERE email=?", ["admin@refind.local"]).fetchone(): db.execute("INSERT INTO users(name,email,password_hash,role,created_at) VALUES (?,?,?,?,?)", ("ReFind Admin", "admin@refind.local", hash_password("refind-admin"), "admin", now()))
        if not db.execute("SELECT 1 FROM reports LIMIT 1").fetchone():
            db.executemany("INSERT INTO reports(kind,name,category,location,description,status,created_at) VALUES (?,?,?,?,?,?,?)", [("found","Black Samsung Galaxy","Electronics","Central Library","Black phone with a slim protective case, found near the reading desks.","possible_match","2026-09-04T10:24:00+00:00"),("lost","Blue Hydro Flask","Personal items","Room 204, Science Block","Blue bottle with a small superhero sticker and metal cap.","possible_match","2026-09-03T12:00:00+00:00"),("found","Student ID card","Documents","North Canteen","ID safely held by the campus security desk.","open","2026-09-03T08:45:00+00:00"),("lost","Canvas tote bag","Bags","Parking area","Cream canvas tote with class notes and a green keychain.","open","2026-09-02T14:10:00+00:00")])
        db.commit()

@app.get("/health")
def health():
    with closing(connection()) as db:
        summary = {
            "status": "ok",
            "storage": "sqlite",
            "version": "2.0.0",
            "database": "ready",
            "timestamp": now(),
            "report_count": db.execute("SELECT COUNT(*) FROM reports").fetchone()[0],
            "user_count": db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        }
    return summary

@app.get("/reports/summary")
def reports_summary():
    with closing(connection()) as db:
        return {
            "total_reports": db.execute("SELECT COUNT(*) FROM reports").fetchone()[0],
            "lost_reports": db.execute("SELECT COUNT(*) FROM reports WHERE kind='lost'").fetchone()[0],
            "found_reports": db.execute("SELECT COUNT(*) FROM reports WHERE kind='found'").fetchone()[0],
            "possible_matches": db.execute("SELECT COUNT(*) FROM reports WHERE status='possible_match'").fetchone()[0],
            "pending_claims": db.execute("SELECT COUNT(*) FROM claims WHERE status='pending'").fetchone()[0],
            "successful_returns": db.execute("SELECT COUNT(*) FROM reports WHERE status IN ('returned','closed')").fetchone()[0],
            "updated_at": now(),
        }
@app.post("/auth/register", status_code=201)
def register(payload: RegisterInput):
    with closing(connection()) as db:
        try: cursor = db.execute("INSERT INTO users(name,email,password_hash,role,created_at) VALUES (?,?,?,?,?)", (payload.name.strip(),payload.email.lower().strip(),hash_password(payload.password),"student",now())); db.commit()
        except sqlite3.IntegrityError: raise HTTPException(409,"An account with that email already exists")
        user = row(db.execute("SELECT id,name,email,role,created_at FROM users WHERE id=?",[cursor.lastrowid]).fetchone())
    return {"user":user,"token":token_for(user)}
@app.post("/auth/login")
def login(payload: LoginInput):
    with closing(connection()) as db: account = db.execute("SELECT * FROM users WHERE email=?",[payload.email.lower().strip()]).fetchone()
    if not account or not verify_password(payload.password, account["password_hash"]): raise HTTPException(401,"Incorrect email or password")
    user = {key:account[key] for key in ("id","name","email","role","created_at")}; return {"user":user,"token":token_for(user)}
@app.get("/auth/me")
def me(authorization: str | None = Header(None)): return user_from_header(authorization)

@app.get("/reports")
def list_reports(kind: Literal["lost","found"] | None=None, query: str=""):
    sql, args = "SELECT id,kind,name,category,location,description,photo_url,status,created_at FROM reports WHERE 1=1", []
    if kind: sql += " AND kind=?"; args.append(kind)
    search = clean_text(query)[:100]
    if search: sql += " AND (name LIKE ? OR category LIKE ? OR location LIKE ? OR description LIKE ?)"; args.extend([f"%{search}%"] * 4)
    with closing(connection()) as db: return [row(item) for item in db.execute(sql+" ORDER BY id DESC",args)]
@app.post("/reports",status_code=201)
def create_report(payload: ReportInput, authorization: str | None = Header(None)):
    user = user_from_header(authorization)
    name = clean_text(payload.name)
    category = clean_text(payload.category)
    location = clean_text(payload.location)
    description = clean_text(payload.description)
    if min(map(len, (name, category, location, description))) < 2 or len(description) < 8:
        raise HTTPException(422, "Report fields must contain meaningful text")
    with closing(connection()) as db:
        cursor = db.execute("INSERT INTO reports(user_id,kind,name,category,location,description,photo_url,status,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (user["id"],payload.kind,name,category,location,description,payload.photo_url,"open",now())); report_id=cursor.lastrowid
        report = row(db.execute("SELECT * FROM reports WHERE id=?",[report_id]).fetchone()); opposite = db.execute("SELECT * FROM reports WHERE kind != ?",[payload.kind]).fetchall(); matches=[]
        for other in opposite:
            score = match_score(f"{report['name']} {report['category']} {report['location']} {report['description']}",f"{other['name']} {other['category']} {other['location']} {other['description']}")
            if score >= 20:
                lost, found = (report_id,other["id"]) if report["kind"]=="lost" else (other["id"],report_id)
                db.execute("INSERT OR IGNORE INTO matches(lost_report_id,found_report_id,score,status,created_at) VALUES (?,?,?,?,?)",(lost,found,score,"open",now())); matches.append({"report_id":other["id"],"name":other["name"],"score":score})
                db.execute("UPDATE reports SET status='possible_match' WHERE id IN (?,?)",(report_id,other["id"])); notify(db,other["user_id"],"match",f"Possible match found for {other['name']}",other["id"])
        if matches: notify(db,user["id"],"match",f"We found {len(matches)} possible match(es) for {report['name']}",report_id)
        db.commit()
    return {"report":report,"possible_matches":sorted(matches,key=lambda item:item["score"],reverse=True)}
@app.post("/uploads", status_code=201)
async def upload_photo(file: UploadFile = File(...), authorization: str | None = Header(None)):
    """Save one non-sensitive item image locally. Images only; max 5 MB."""
    user_from_header(authorization)
    allowed = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    if file.content_type not in allowed: raise HTTPException(415, "Upload a JPG, PNG, or WebP image")
    content = await file.read()
    if not content or len(content) > 5 * 1024 * 1024: raise HTTPException(413, "Image must be between 1 byte and 5 MB")
    signatures = {
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": content.startswith(b"RIFF") and content[8:12] == b"WEBP",
    }
    if not signatures.get(file.content_type, False):
        raise HTTPException(415, "The uploaded file content does not match its image type")
    filename = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}{allowed[file.content_type]}"
    return {"photo_url": store_upload(filename, content, file.content_type)}
@app.get("/reports/my")
def my_reports(authorization: str | None = Header(None)):
    user = user_from_header(authorization)
    with closing(connection()) as db:
        sql = "SELECT id,kind,name,category,location,description,photo_url,status,created_at FROM reports WHERE user_id=? ORDER BY id DESC"
        return [row(item) for item in db.execute(sql, [user["id"]])]

@app.get("/claims/my")
def my_claims(authorization: str | None = Header(None)):
    user = user_from_header(authorization)
    with closing(connection()) as db:
        sql = """
            SELECT c.id, c.report_id, c.user_id, c.ownership_detail, c.return_point, c.status, c.created_at,
                   r.name AS report_name, r.kind AS report_kind, r.status AS report_status
            FROM claims c
            JOIN reports r ON r.id = c.report_id
            WHERE c.user_id = ?
            ORDER BY c.id DESC
        """
        return [row(item) for item in db.execute(sql, [user["id"]])]

@app.post("/claims",status_code=201)
def create_claim(payload: ClaimInput, authorization: str | None = Header(None)):
    user=user_from_header(authorization)
    with closing(connection()) as db:
        report=db.execute("SELECT * FROM reports WHERE id=?",[payload.report_id]).fetchone()
        if not report: raise HTTPException(404,"Report not found")
        if report["user_id"] == user["id"]:
            raise HTTPException(400, "You cannot claim your own report")
        existing = db.execute("SELECT 1 FROM claims WHERE report_id=? AND user_id=? AND status IN ('pending','verified')", (payload.report_id, user["id"])).fetchone()
        if existing:
            raise HTTPException(409, "You already have an active claim for this report")
        ownership_detail = clean_text(payload.ownership_detail)
        return_point = clean_text(payload.return_point)
        cursor=db.execute("INSERT INTO claims(report_id,user_id,ownership_detail,return_point,status,created_at) VALUES (?,?,?,?,?,?)",(payload.report_id,user["id"],ownership_detail,return_point,"pending",now())); db.execute("UPDATE reports SET status='claimed' WHERE id=?",[payload.report_id]); notify(db,report["user_id"],"claim",f"A secure claim was submitted for {report['name']}",report["id"]); db.commit()
        return row(db.execute("SELECT * FROM claims WHERE id=?",[cursor.lastrowid]).fetchone())
@app.get("/matches")
def list_matches(authorization: str | None = Header(None)):
    user=user_from_header(authorization)
    sql="SELECT m.*,l.name AS lost_name,f.name AS found_name FROM matches m JOIN reports l ON l.id=m.lost_report_id JOIN reports f ON f.id=m.found_report_id WHERE l.user_id=? OR f.user_id=? ORDER BY m.score DESC"
    with closing(connection()) as db: return [row(item) for item in db.execute(sql,[user["id"],user["id"]])]
@app.patch("/matches/{match_id}")
def update_match(match_id:int,payload:MatchInput,authorization: str | None=Header(None)):
    require_admin(authorization)
    with closing(connection()) as db:
        if not db.execute("SELECT 1 FROM matches WHERE id=?",[match_id]).fetchone(): raise HTTPException(404,"Match not found")
        db.execute("UPDATE matches SET status=? WHERE id=?",[payload.status,match_id]); db.commit()
    return {"id":match_id,"status":payload.status}
@app.get("/notifications")
def list_notifications(authorization: str | None=Header(None)):
    user=user_from_header(authorization)
    with closing(connection()) as db: return [row(item) for item in db.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC",[user["id"]])]
@app.post("/notifications/{notification_id}/read")
def read_notification(notification_id:int,authorization: str | None=Header(None)):
    user=user_from_header(authorization)
    with closing(connection()) as db: db.execute("UPDATE notifications SET read=1 WHERE id=? AND user_id=?",[notification_id,user["id"]]); db.commit()
    return {"ok":True}
@app.get("/admin/summary")
def admin_summary(authorization: str | None=Header(None)):
    require_admin(authorization)
    with closing(connection()) as db: return {"total_users":db.execute("SELECT COUNT(*) FROM users").fetchone()[0],"total_reports":db.execute("SELECT COUNT(*) FROM reports").fetchone()[0],"lost_reports":db.execute("SELECT COUNT(*) FROM reports WHERE kind='lost'").fetchone()[0],"found_reports":db.execute("SELECT COUNT(*) FROM reports WHERE kind='found'").fetchone()[0],"pending_claims":db.execute("SELECT COUNT(*) FROM claims WHERE status='pending'").fetchone()[0],"successful_returns":db.execute("SELECT COUNT(*) FROM reports WHERE status IN ('returned','closed')").fetchone()[0],"flagged_reports":db.execute("SELECT COUNT(*) FROM reports WHERE status='flagged'").fetchone()[0]}
@app.get("/admin/claims")
def admin_claims(authorization: str | None=Header(None)):
    require_admin(authorization)
    with closing(connection()) as db: return [row(item) for item in db.execute("SELECT c.id,c.status,c.created_at,c.ownership_detail,c.return_point,r.name AS report_name,u.name AS claimant FROM claims c JOIN reports r ON r.id=c.report_id JOIN users u ON u.id=c.user_id ORDER BY c.id DESC")]
@app.patch("/admin/claims/{claim_id}")
def update_claim_status(claim_id:int,payload:ClaimUpdateInput,authorization: str | None=Header(None)):
    require_admin(authorization)
    with closing(connection()) as db:
        claim=db.execute("SELECT c.*,r.name AS report_name,r.user_id AS owner_id FROM claims c JOIN reports r ON r.id=c.report_id WHERE c.id=?",[claim_id]).fetchone()
        if not claim: raise HTTPException(404,"Claim not found")
        db.execute("UPDATE claims SET status=? WHERE id=?",[payload.status,claim_id])
        if payload.status == "verified":
            db.execute("UPDATE reports SET status='verified' WHERE id=?",[claim["report_id"]])
        elif payload.status == "flagged":
            db.execute("UPDATE reports SET status='flagged' WHERE id=?",[claim["report_id"]])
        elif payload.status == "returned":
            db.execute("UPDATE reports SET status='returned' WHERE id=?",[claim["report_id"]])
        if claim["owner_id"]: notify(db,claim["owner_id"],"status",f"Claim review for {claim['report_name']} is now {payload.status}",claim["report_id"])
        notify(db,claim["user_id"],"status",f"Your claim for {claim['report_name']} is now {payload.status}",claim["report_id"])
        db.commit()
    return {"id":claim_id,"status":payload.status}
@app.patch("/admin/reports/{report_id}")
def set_report_status(report_id:int,payload:StatusInput,authorization: str | None=Header(None)):
    require_admin(authorization)
    with closing(connection()) as db:
        report=db.execute("SELECT * FROM reports WHERE id=?",[report_id]).fetchone()
        if not report: raise HTTPException(404,"Report not found")
        db.execute("UPDATE reports SET status=? WHERE id=?",[payload.status,report_id]); notify(db,report["user_id"],"status",f"Your {report['name']} report is now {payload.status.replace('_',' ')}",report_id); db.commit()
    return {"id":report_id,"status":payload.status}

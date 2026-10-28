# ============================================================
# DZ Connect - منصة تواصل جزائرية
# ملف واحد كامل (app.py)
# FastAPI + Supabase PostgreSQL + Storage
# ============================================================

import os
import re
import uuid
import time
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI, Request, Form, File, UploadFile,
    HTTPException, Query, Depends
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    Client = None

# ====================== إعدادات البيئة ======================
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)
APP_ENV = os.getenv("APP_ENV", "development").lower()
PORT = int(os.getenv("PORT", "8000"))

MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_IMAGE = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_AUDIO = {"audio/mpeg", "audio/mp4", "audio/ogg", "audio/webm", "audio/wav", "audio/x-m4a"}
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 أيام
TYPING_STATE: Dict[str, Dict[str, float]] = {}  # conv_key -> {user_id: timestamp}


# حساب المطوّر — رقم ثابت + كلمة مرور
DEV_PHONE = "0553933833"

def is_dev_phone(phone: str) -> bool:
    return normalize_phone(phone) == DEV_PHONE

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return f"pbkdf2${salt}${dk.hex()}"

def verify_password(password: str, stored: str) -> bool:
    try:
        if not stored or not stored.startswith("pbkdf2$"):
            return False
        _, salt, hx = stored.split("$", 2)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
        return secrets.compare_digest(dk.hex(), hx)
    except Exception:
        return False

POST_CATEGORIES = [
    "تعارف",
    "اهتمامات مشتركة",
    "نصائح علاقات",
    "صداقات",
    "عام",
]
BOT_STATUSES = []
REPORT_REASONS = [
    "محتوى غير لائق",
    "تحرش أو إساءة",
    "حساب وهمي",
    "معلومات مضللة",
    "سبب آخر",
]
INTEREST_OPTIONS = [
    "رياضة", "موسيقى", "قراءة", "سفر", "طبخ", "ألعاب",
    "تقنية", "فن", "سينما", "دراسة", "عمل", "طبيعة",
]

supabase: Optional[Any] = None
db_ready = False
storage_ready = False
config_error: Optional[str] = None

# rate-limit بسيط في الذاكرة
_rate: Dict[str, List[float]] = {}


def init_supabase():
    global supabase, db_ready, storage_ready, config_error
    if not SUPABASE_AVAILABLE:
        config_error = "مكتبة supabase غير مثبتة. نفّذ: pip install -r requirements.txt"
        return
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        config_error = "المتغيرات SUPABASE_URL و SUPABASE_SERVICE_ROLE_KEY مطلوبة"
        return
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        # اختبار وجود جدول users
        supabase.table("users").select("id").limit(1).execute()
        db_ready = True
        storage_ready = True
        config_error = None
    except Exception as e:
        msg = str(e)
        if "relation" in msg.lower() or "does not exist" in msg.lower():
            config_error = "جداول قاعدة البيانات غير موجودة. نفّذ ملف supabase_schema.sql في SQL Editor"
        else:
            config_error = f"فشل الاتصال بـ Supabase: {msg[:180]}"
        db_ready = False
        storage_ready = False


# ====================== أدوات ======================
def normalize_phone(phone: str) -> str:
    if not phone:
        return ""
    phone = re.sub(r"[\s\-\(\)\.]", "", phone.strip())
    if phone.startswith("+213"):
        phone = "0" + phone[4:]
    elif phone.startswith("213") and len(phone) >= 12:
        phone = "0" + phone[3:]
    elif phone.startswith("00213"):
        phone = "0" + phone[5:]
    return phone


def is_valid_dz_phone(phone: str) -> bool:
    return bool(re.match(r"^0[567]\d{8}$", phone))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def public_id() -> str:
    return "dz_" + secrets.token_hex(5)


def check_rate(key: str, max_req: int = 25, window: int = 60) -> bool:
    t = time.time()
    h = hashlib.sha256(key.encode()).hexdigest()[:12]
    if h not in _rate:
        _rate[h] = []
    _rate[h] = [x for x in _rate[h] if t - x < window]
    if len(_rate[h]) >= max_req:
        return False
    _rate[h].append(t)
    return True


def db():
    if not db_ready or supabase is None:
        raise HTTPException(503, detail=config_error or "قاعدة البيانات غير جاهزة")
    return supabase


# ====================== الجلسات ======================
def get_user(request: Request) -> Optional[dict]:
    u = request.session.get("user")
    if not u:
        return None
    if u.get("exp") and time.time() > u["exp"]:
        request.session.clear()
        return None
    return u


def require_user(request: Request) -> dict:
    u = get_user(request)
    if not u:
        raise HTTPException(401, detail="يجب تسجيل الدخول أولاً")
    return u


def require_admin(request: Request) -> dict:
    u = require_user(request)
    row = get_user_by_id(u["id"])
    if not row or row.get("phone") != DEV_PHONE:
        raise HTTPException(403, "لوحة الإدارة خاصة بحساب المطوّر فقط")
    return u


def set_session(request: Request, row: dict):
    request.session["user"] = {
        "id": row["id"],
        "name": row.get("name") or "مستخدم",
        "public_id": row.get("public_id"),
        "avatar_url": row.get("avatar_url"),
        "is_admin": bool(row.get("is_admin")),
        "exp": time.time() + SESSION_MAX_AGE,
    }


# ====================== دوال قاعدة البيانات ======================
def get_user_by_phone(phone: str) -> Optional[dict]:
    try:
        r = db().table("users").select("*").eq("phone", phone).limit(1).execute()
        return r.data[0] if r.data else None
    except Exception:
        return None


def get_user_by_id(uid: str) -> Optional[dict]:
    try:
        r = db().table("users").select("*").eq("id", uid).limit(1).execute()
        return r.data[0] if r.data else None
    except Exception:
        return None


def create_user_row(phone: str, name: Optional[str] = None, is_admin: bool = False) -> dict:
    data = {
        "id": str(uuid.uuid4()),
        "phone": phone,
        "name": (name or "").strip()[:80] or None,
        "public_id": public_id(),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "is_admin": bool(is_admin) or (phone == DEV_PHONE),
        "is_restricted": False,
    }
    r = db().table("users").insert(data).execute()
    if not r.data:
        raise HTTPException(500, "فشل إنشاء الحساب")
    return r.data[0]

def set_user_password(user_id: str, password: str):
    ph = hash_password(password)
    try:
        db().table("users").update({"password_hash": ph, "updated_at": now_iso()}).eq("id", user_id).execute()
    except Exception as e:
        raise HTTPException(500, "تعذر حفظ كلمة المرور. نفّذ SQL: ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;")

def ensure_dev_admin(row: dict) -> dict:
    """ضمان صلاحية الأدمن لرقم المطوّر"""
    if row.get("phone") == DEV_PHONE and not row.get("is_admin"):
        try:
            db().table("users").update({"is_admin": True, "updated_at": now_iso()}).eq("id", row["id"]).execute()
            row["is_admin"] = True
        except Exception:
            pass
    return row


async def upload_media(file: UploadFile, folder: str, user_id: str) -> dict:
    if not storage_ready:
        raise HTTPException(503, "التخزين غير جاهز. أنشئ bucket باسم media (Public) في Supabase Storage")
    ctype = (file.content_type or "").lower()
    filename = (file.filename or "file").lower()
    ext = filename.rsplit(".", 1)[-1][:8] if "." in filename else "bin"

    # الهواتف قد ترسل application/octet-stream
    if ctype in ALLOWED_IMAGE or ext in {"jpg", "jpeg", "png", "webp", "gif"}:
        mtype = "image"
        if ctype not in ALLOWED_IMAGE:
            ctype = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/jpeg")
    elif ctype in ALLOWED_AUDIO or ext in {"mp3", "m4a", "ogg", "wav", "webm", "aac"}:
        mtype = "audio"
        if ctype not in ALLOWED_AUDIO:
            ctype = {"mp3": "audio/mpeg", "m4a": "audio/mp4", "ogg": "audio/ogg", "wav": "audio/wav", "webm": "audio/webm", "aac": "audio/mp4"}.get(ext, "audio/webm")
    else:
        raise HTTPException(400, f"نوع الملف غير مسموح ({ctype or ext})")

    data = await file.read()
    if len(data) == 0:
        raise HTTPException(400, "الملف فارغ")
    if len(data) > MAX_UPLOAD_SIZE:
        raise HTTPException(400, "حجم الملف أكبر من 5 ميجابايت")

    if ext == "bin":
        ext = "jpg" if mtype == "image" else "webm"
    object_path = f"{folder}/{user_id}/{uuid.uuid4().hex}.{ext}"
    try:
        db().storage.from_("media").upload(
            object_path, data,
            file_options={"content-type": ctype, "upsert": "false"},
        )
        url = db().storage.from_("media").get_public_url(object_path)
        return {"path": object_path, "url": url, "media_type": mtype, "size": len(data)}
    except Exception as e:
        err = str(e)
        if "Bucket" in err or "not found" in err.lower():
            raise HTTPException(500, "حاوية media غير موجودة. أنشئها من Storage في Supabase واجعلها Public")
        raise HTTPException(500, f"فشل الرفع: {err[:120]}")


# ====================== نماذج ======================
class RegisterBody(BaseModel):
    phone: str
    name: Optional[str] = None
    accept_privacy: bool = False
    password: Optional[str] = None


class LoginBody(BaseModel):
    phone: str
    password: Optional[str] = None


class PasswordBody(BaseModel):
    password: str
    old_password: Optional[str] = None


class ForgotPasswordBody(BaseModel):
    phone: str
    new_password: str


class CommentBody(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    parent_id: Optional[str] = None


class ReportBody(BaseModel):
    reason: str
    details: Optional[str] = None


class ChatBody(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)
    reply_to: Optional[str] = None


class ProfileBody(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    origin: Optional[str] = None
    interests: Optional[str] = None  # قائمة مفصولة بفواصل


# ====================== التطبيق ======================
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_supabase()
    yield


app = FastAPI(title="DZ Connect", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="dz_session",
    max_age=SESSION_MAX_AGE,
    same_site="lax",
    https_only=(APP_ENV == "production"),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if APP_ENV != "production" else [],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ====================== صحة النظام ======================
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app": "DZ Connect",
        "db_ready": db_ready,
        "storage_ready": storage_ready,
        "config_error": config_error,
        "env": APP_ENV,
    }


@app.get("/api/status")
async def api_status():
    return {
        "db_ready": db_ready,
        "storage_ready": storage_ready,
        "error": config_error,
        "categories": POST_CATEGORIES,
        "bot_statuses": BOT_STATUSES,
        "report_reasons": REPORT_REASONS,
    }


# ====================== المصادقة ======================
@app.get("/api/auth/check-phone")
async def check_phone(phone: str = Query("")):
    """هل الرقم حساب مطوّر؟"""
    p = normalize_phone(phone)
    return {"is_developer": p == DEV_PHONE, "phone": p if is_valid_dz_phone(p) else None}


@app.post("/api/register")
async def register(request: Request, body: RegisterBody):
    if not check_rate(f"reg:{request.client.host if request.client else 'x'}"):
        raise HTTPException(429, "محاولات كثيرة، حاول لاحقًا")
    if not body.accept_privacy:
        raise HTTPException(400, "يجب الموافقة على سياسة الخصوصية")
    phone = normalize_phone(body.phone)
    if not is_valid_dz_phone(phone):
        raise HTTPException(400, "رقم هاتف جزائري غير صالح (05/06/07 + 8 أرقام)")
    # حساب المطوّر: التسجيل عبر الدخول مع كلمة المرور
    if phone == DEV_PHONE:
        raise HTTPException(400, "حساب المطوّر يُدخل من صفحة الدخول مع كلمة المرور")
    if get_user_by_phone(phone):
        raise HTTPException(400, "هذا الرقم مسجل مسبقًا. استخدم صفحة الدخول")
    row = create_user_row(phone, body.name, is_admin=False)
    if body.password and len(body.password.strip()) >= 6:
        set_user_password(row["id"], body.password.strip())
        row = get_user_by_id(row["id"]) or row
    set_session(request, row)
    return {
        "ok": True,
        "message": "تم إنشاء الحساب",
        "user": {
            "id": row["id"],
            "name": row.get("name") or "مستخدم",
            "public_id": row["public_id"],
            "avatar_url": row.get("avatar_url"),
            "is_admin": False,
            "is_developer": False,
            "has_password": bool(body.password and len(body.password.strip()) >= 6),
        },
    }


@app.post("/api/login")
async def login(request: Request, body: LoginBody):
    if not check_rate(f"login:{request.client.host if request.client else 'x'}"):
        raise HTTPException(429, "محاولات كثيرة")
    phone = normalize_phone(body.phone)
    if not is_valid_dz_phone(phone):
        raise HTTPException(400, "رقم هاتف غير صالح")

    # ——— حساب المطوّر ———
    if phone == DEV_PHONE:
        row = get_user_by_phone(phone)
        if not row:
            # إنشاء حساب المطوّر لأول مرة
            if not body.password or len(body.password.strip()) < 6:
                return {
                    "ok": False,
                    "needs_password_setup": True,
                    "is_developer": True,
                    "message": "أنشئ كلمة مرور لحساب المطوّر (6 أحرف على الأقل)",
                }
            row = create_user_row(phone, "المطوّر", is_admin=True)
            set_user_password(row["id"], body.password.strip())
            row = get_user_by_id(row["id"]) or row
            row = ensure_dev_admin(row)
            set_session(request, row)
            return {
                "ok": True,
                "message": "تم إنشاء حساب المطوّر وحفظ كلمة المرور",
                "user": {
                    "id": row["id"],
                    "name": row.get("name") or "المطوّر",
                    "public_id": row.get("public_id"),
                    "avatar_url": row.get("avatar_url"),
                    "is_admin": True,
                    "is_developer": True,
                },
            }
        row = ensure_dev_admin(row)
        if row.get("is_restricted"):
            raise HTTPException(403, "هذا الحساب مقيد")
        stored = row.get("password_hash") or ""
        if not stored:
            if not body.password or len(body.password.strip()) < 6:
                return {
                    "ok": False,
                    "needs_password_setup": True,
                    "is_developer": True,
                    "message": "أنشئ كلمة مرور لحساب المطوّر (6 أحرف على الأقل)",
                }
            set_user_password(row["id"], body.password.strip())
            set_session(request, row)
            return {
                "ok": True,
                "message": "تم حفظ كلمة مرور المطوّر وتسجيل الدخول",
                "user": {
                    "id": row["id"],
                    "name": row.get("name") or "المطوّر",
                    "public_id": row.get("public_id"),
                    "avatar_url": row.get("avatar_url"),
                    "is_admin": True,
                    "is_developer": True,
                },
            }
        if not body.password or not verify_password(body.password.strip(), stored):
            raise HTTPException(401, "كلمة مرور المطوّر غير صحيحة")
        set_session(request, row)
        return {
            "ok": True,
            "message": "تم دخول المطوّر",
            "user": {
                "id": row["id"],
                "name": row.get("name") or "المطوّر",
                "public_id": row.get("public_id"),
                "avatar_url": row.get("avatar_url"),
                "is_admin": True,
                "is_developer": True,
            },
        }

    # ——— مستخدم عادي ———
    row = get_user_by_phone(phone)
    if not row:
        raise HTTPException(404, "الحساب غير موجود. سجّل حسابًا جديدًا")
    if row.get("is_restricted"):
        raise HTTPException(403, "هذا الحساب مقيد من قبل الإدارة")
    # تقييد مؤقت 24 ساعة
    ru = row.get("restricted_until")
    if ru:
        try:
            until = datetime.fromisoformat(str(ru).replace("Z", "+00:00"))
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            if until > datetime.now(timezone.utc):
                raise HTTPException(403, "الحساب مقيّد مؤقتًا حتى " + str(ru)[:16])
            else:
                db().table("users").update({"is_restricted": False, "restricted_until": None}).eq("id", row["id"]).execute()
        except HTTPException:
            raise
        except Exception:
            pass
    stored = row.get("password_hash") or ""
    if stored:
        if not body.password or not verify_password(body.password.strip(), stored):
            raise HTTPException(401, "كلمة المرور غير صحيحة")
    elif body.password and len(body.password.strip()) >= 6:
        # تعيين كلمة مرور اختيارية عند أول دخول
        set_user_password(row["id"], body.password.strip())
    set_session(request, row)
    return {
        "ok": True,
        "message": "تم تسجيل الدخول",
        "user": {
            "id": row["id"],
            "name": row.get("name") or "مستخدم",
            "public_id": row["public_id"],
            "avatar_url": row.get("avatar_url"),
            "cover_url": row.get("cover_url"),
            "bio": row.get("bio"),
            "is_admin": bool(row.get("is_admin")) and phone == DEV_PHONE,
            "is_developer": phone == DEV_PHONE,
            "has_password": bool(stored or body.password),
        },
    }


@app.post("/api/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True, "message": "تم تسجيل الخروج"}


@app.get("/api/me")
async def me(request: Request):
    u = get_user(request)
    if not u:
        return {"authenticated": False}
    row = get_user_by_id(u["id"])
    if not row:
        request.session.clear()
        return {"authenticated": False}
    # عدد المنشورات
    try:
        cnt = db().table("posts").select("id", count="exact").eq("user_id", row["id"]).execute()
        posts_count = cnt.count or 0
    except Exception:
        posts_count = 0
    return {
        "authenticated": True,
        "user": {
            "id": row["id"],
            "name": row.get("name") or "مستخدم",
            "public_id": row.get("public_id"),
            "avatar_url": row.get("avatar_url"),
            "cover_url": row.get("cover_url"),
            "bio": row.get("bio"),
            "gender": row.get("gender"),
            "age": row.get("age"),
            "origin": row.get("origin"),
            "interests": row.get("interests"),
            "created_at": row.get("created_at"),
            "is_admin": bool(row.get("is_admin")) and row.get("phone") == DEV_PHONE,
            "is_developer": row.get("phone") == DEV_PHONE,
            "has_password": bool(row.get("password_hash")),
            "posts_count": posts_count,
        },
    }


# ====================== الملف الشخصي ======================
@app.put("/api/profile")
async def update_profile(request: Request, body: ProfileBody):
    u = require_user(request)
    updates = {"updated_at": now_iso()}
    if body.name is not None:
        updates["name"] = body.name.strip()[:80] or None
    if body.bio is not None:
        updates["bio"] = body.bio.strip()[:500] or None
    if body.gender is not None:
        g = body.gender.strip()
        if g and g not in ("ذكر", "أنثى", "أفضل عدم القول"):
            raise HTTPException(400, "قيمة الجنس غير صالحة")
        updates["gender"] = g or None
    if body.age is not None:
        if body.age < 13 or body.age > 120:
            raise HTTPException(400, "العمر يجب بين 13 و 120")
        updates["age"] = body.age
    if body.origin is not None:
        updates["origin"] = body.origin.strip()[:80] or None
    if body.interests is not None:
        # تنظيف قائمة الاهتمامات
        parts = [x.strip() for x in body.interests.split(",") if x.strip()]
        parts = parts[:12]
        updates["interests"] = ",".join(parts) if parts else None
    db().table("users").update(updates).eq("id", u["id"]).execute()
    row = get_user_by_id(u["id"])
    set_session(request, row)
    return {"ok": True, "message": "تم تحديث الملف"}


@app.post("/api/profile/avatar")
async def update_avatar(request: Request, avatar: UploadFile = File(...)):
    u = require_user(request)
    m = await upload_media(avatar, "avatars", u["id"])
    db().table("users").update({
        "avatar_url": m["url"],
        "updated_at": now_iso(),
    }).eq("id", u["id"]).execute()
    row = get_user_by_id(u["id"])
    set_session(request, row)
    return {"ok": True, "avatar_url": m["url"]}


# ====================== المنشورات ======================
@app.get("/api/posts")
async def list_posts(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=40),
    category: Optional[str] = None,
    user_id: Optional[str] = None,
):
    try:
        q = (
            db()
            .table("posts")
            .select(
                "id, content, category, bot_status, is_verified, created_at, updated_at, user_id, "
                "users(id, name, public_id, avatar_url), "
                "post_media(id, url, media_type)"
            )
            .order("created_at", desc=True)
        )
        if category:
            q = q.eq("category", category)
        if user_id:
            q = q.eq("user_id", user_id)
        start = (page - 1) * limit
        r = q.range(start, start + limit - 1).execute()
        posts = r.data or []

        current = get_user(request)
        liked = set()
        saved = set()
        if current and posts:
            ids = [p["id"] for p in posts]
            lk = db().table("likes").select("post_id").eq("user_id", current["id"]).in_("post_id", ids).execute()
            liked = {x["post_id"] for x in (lk.data or [])}
            sv = db().table("saved_posts").select("post_id").eq("user_id", current["id"]).in_("post_id", ids).execute()
            saved = {x["post_id"] for x in (sv.data or [])}

        # عدّ الإعجابات والتعليقات
        result = []
        for p in posts:
            try:
                lc = db().table("likes").select("id", count="exact").eq("post_id", p["id"]).execute()
                cc = db().table("comments").select("id", count="exact").eq("post_id", p["id"]).execute()
                likes_count = lc.count or 0
                comments_count = cc.count or 0
            except Exception:
                likes_count = comments_count = 0
            p["liked_by_me"] = p["id"] in liked
            p["saved_by_me"] = p["id"] in saved
            p["likes_count"] = likes_count
            p["comments_count"] = comments_count
            result.append(p)
        return {"posts": result, "page": page, "limit": limit}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"خطأ جلب المنشورات: {str(e)[:140]}")


@app.get("/api/posts/{post_id}")
async def get_post(post_id: str, request: Request):
    try:
        r = (
            db()
            .table("posts")
            .select(
                "id, content, category, bot_status, is_verified, created_at, updated_at, user_id, "
                "users(id, name, public_id, avatar_url), "
                "post_media(id, url, media_type)"
            )
            .eq("id", post_id)
            .limit(1)
            .execute()
        )
        if not r.data:
            raise HTTPException(404, "المنشور غير موجود")
        p = r.data[0]
        current = get_user(request)
        p["liked_by_me"] = False
        p["saved_by_me"] = False
        if current:
            lk = db().table("likes").select("id").eq("post_id", post_id).eq("user_id", current["id"]).limit(1).execute()
            p["liked_by_me"] = bool(lk.data)
            sv = db().table("saved_posts").select("id").eq("post_id", post_id).eq("user_id", current["id"]).limit(1).execute()
            p["saved_by_me"] = bool(sv.data)
        lc = db().table("likes").select("id", count="exact").eq("post_id", post_id).execute()
        cc = db().table("comments").select("id", count="exact").eq("post_id", post_id).execute()
        p["likes_count"] = lc.count or 0
        p["comments_count"] = cc.count or 0
        return p
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e)[:140])


@app.post("/api/posts")
async def create_post(
    request: Request,
    content: Optional[str] = Form(None),
    category: str = Form(...),
    bot_status: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None),
):
    u = require_user(request)
    if not check_rate(f"post:{u['id']}", max_req=8, window=120):
        raise HTTPException(429, "معدل النشر مرتفع، انتظر قليلاً")
    content = (content or "").strip()
    if not content and not (image and image.filename) and not (audio and audio.filename):
        raise HTTPException(400, "أدخل نصًا أو صورة أو تسجيلًا صوتيًا")
    if category not in POST_CATEGORIES:
        raise HTTPException(400, "تصنيف غير صالح")
    if category == "العروض التي تم التحقق منها" and not u.get("is_admin"):
        raise HTTPException(403, "تصنيف التحقق يحتاج صلاحية إدارية")
    if category == "بوتات الإنترنت" and bot_status and bot_status not in BOT_STATUSES:
        raise HTTPException(400, "حالة البوت غير صالحة")

    post_id = str(uuid.uuid4())
    row = {
        "id": post_id,
        "user_id": u["id"],
        "content": content[:5000] if content else None,
        "category": category,
        "bot_status": bot_status if category == "بوتات الإنترنت" else None,
        "is_verified": False,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    try:
        db().table("posts").insert(row).execute()
        media_list = []
        if image and image.filename:
            m = await upload_media(image, "posts", u["id"])
            media_list.append({
                "id": str(uuid.uuid4()),
                "post_id": post_id,
                "url": m["url"],
                "path": m["path"],
                "media_type": m["media_type"],
                "created_at": now_iso(),
            })
        if audio and audio.filename:
            m = await upload_media(audio, "posts", u["id"])
            media_list.append({
                "id": str(uuid.uuid4()),
                "post_id": post_id,
                "url": m["url"],
                "path": m["path"],
                "media_type": m["media_type"],
                "created_at": now_iso(),
            })
        if media_list:
            db().table("post_media").insert(media_list).execute()
        return {"ok": True, "post_id": post_id, "message": "تم نشر المنشور بنجاح"}
    except HTTPException:
        raise
    except Exception as e:
        try:
            db().table("posts").delete().eq("id", post_id).execute()
        except Exception:
            pass
        raise HTTPException(500, f"فشل النشر: {str(e)[:140]}")


@app.put("/api/posts/{post_id}")
async def update_post(
    post_id: str,
    request: Request,
    content: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    bot_status: Optional[str] = Form(None),
):
    u = require_user(request)
    r = db().table("posts").select("*").eq("id", post_id).limit(1).execute()
    if not r.data:
        raise HTTPException(404, "المنشور غير موجود")
    post = r.data[0]
    if post["user_id"] != u["id"] and not u.get("is_admin"):
        raise HTTPException(403, "لا تملك صلاحية التعديل")
    updates = {"updated_at": now_iso()}
    if content is not None:
        updates["content"] = content.strip()[:5000]
    if category and category in POST_CATEGORIES:
        if category == "العروض التي تم التحقق منها" and not u.get("is_admin"):
            raise HTTPException(403, "تصنيف التحقق إداري فقط")
        updates["category"] = category
    if bot_status and bot_status in BOT_STATUSES:
        updates["bot_status"] = bot_status
    db().table("posts").update(updates).eq("id", post_id).execute()
    return {"ok": True, "message": "تم التعديل"}


@app.delete("/api/posts/{post_id}")
async def delete_post(post_id: str, request: Request):
    u = require_user(request)
    r = db().table("posts").select("*").eq("id", post_id).limit(1).execute()
    if not r.data:
        raise HTTPException(404, "المنشور غير موجود")
    post = r.data[0]
    if post["user_id"] != u["id"] and not u.get("is_admin"):
        raise HTTPException(403, "لا تملك صلاحية الحذف")
    # حذف الملفات من Storage
    media = db().table("post_media").select("path").eq("post_id", post_id).execute()
    paths = [m["path"] for m in (media.data or []) if m.get("path")]
    if paths:
        try:
            db().storage.from_("media").remove(paths)
        except Exception:
            pass
    db().table("post_media").delete().eq("post_id", post_id).execute()
    db().table("likes").delete().eq("post_id", post_id).execute()
    db().table("comments").delete().eq("post_id", post_id).execute()
    db().table("saved_posts").delete().eq("post_id", post_id).execute()
    db().table("reports").delete().eq("post_id", post_id).execute()
    db().table("posts").delete().eq("id", post_id).execute()
    return {"ok": True, "message": "تم حذف المنشور"}


# ====================== الإعجابات ======================
@app.post("/api/posts/{post_id}/like")
async def toggle_like(post_id: str, request: Request):
    u = require_user(request)
    existing = (
        db()
        .table("likes")
        .select("id")
        .eq("post_id", post_id)
        .eq("user_id", u["id"])
        .limit(1)
        .execute()
    )
    if existing.data:
        db().table("likes").delete().eq("id", existing.data[0]["id"]).execute()
        return {"ok": True, "liked": False}
    try:
        db().table("likes").insert({
            "id": str(uuid.uuid4()),
            "post_id": post_id,
            "user_id": u["id"],
            "created_at": now_iso(),
        }).execute()
        return {"ok": True, "liked": True}
    except Exception:
        return {"ok": True, "liked": True}


# ====================== التعليقات ======================
@app.get("/api/posts/{post_id}/comments")
async def list_comments(post_id: str, page: int = Query(1, ge=1), limit: int = Query(40, ge=1, le=100)):
    start = (page - 1) * limit
    r = (
        db()
        .table("comments")
        .select(
            "id, content, created_at, updated_at, parent_id, user_id, "
            "users(id, name, public_id, avatar_url)"
        )
        .eq("post_id", post_id)
        .order("created_at", desc=False)
        .range(start, start + limit - 1)
        .execute()
    )
    return {"comments": r.data or []}


@app.post("/api/posts/{post_id}/comments")
async def add_comment(post_id: str, request: Request, body: CommentBody):
    u = require_user(request)
    if not check_rate(f"cmt:{u['id']}", max_req=20, window=60):
        raise HTTPException(429, "معدل تعليقات مرتفع")
    content = body.content.strip()
    if not content:
        raise HTTPException(400, "التعليق فارغ")
    # التحقق من وجود المنشور
    p = db().table("posts").select("id").eq("id", post_id).limit(1).execute()
    if not p.data:
        raise HTTPException(404, "المنشور غير موجود")
    data = {
        "id": str(uuid.uuid4()),
        "post_id": post_id,
        "user_id": u["id"],
        "content": content[:2000],
        "parent_id": body.parent_id,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    db().table("comments").insert(data).execute()
    try:
        post = db().table("posts").select("user_id").eq("id", post_id).limit(1).execute()
        if post.data and post.data[0]["user_id"] != u["id"]:
            create_notification(
                post.data[0]["user_id"], "comment",
                "تعليق جديد على منشورك",
                (body.content or "")[:80],
                post_id,
            )
        if body.parent_id:
            parent = db().table("comments").select("user_id").eq("id", body.parent_id).limit(1).execute()
            if parent.data and parent.data[0]["user_id"] != u["id"]:
                create_notification(
                    parent.data[0]["user_id"], "reply",
                    "رد على تعليقك",
                    (body.content or "")[:80],
                    body.parent_id,
                )
    except Exception:
        pass
    return {"ok": True, "comment_id": data["id"], "message": "تم إضافة التعليق"}


@app.put("/api/comments/{comment_id}")
async def edit_comment(comment_id: str, request: Request, body: CommentBody):
    u = require_user(request)
    r = db().table("comments").select("*").eq("id", comment_id).limit(1).execute()
    if not r.data:
        raise HTTPException(404, "التعليق غير موجود")
    c = r.data[0]
    if c["user_id"] != u["id"] and not u.get("is_admin"):
        raise HTTPException(403, "لا تملك صلاحية التعديل")
    db().table("comments").update({
        "content": body.content.strip()[:2000],
        "updated_at": now_iso(),
    }).eq("id", comment_id).execute()
    return {"ok": True, "message": "تم تعديل التعليق"}


@app.delete("/api/comments/{comment_id}")
async def delete_comment(comment_id: str, request: Request):
    u = require_user(request)
    r = db().table("comments").select("*").eq("id", comment_id).limit(1).execute()
    if not r.data:
        raise HTTPException(404, "التعليق غير موجود")
    c = r.data[0]
    if c["user_id"] != u["id"] and not u.get("is_admin"):
        raise HTTPException(403, "لا تملك صلاحية الحذف")
    db().table("comments").delete().eq("id", comment_id).execute()
    return {"ok": True, "message": "تم حذف التعليق"}


# ====================== المحفوظات ======================
@app.post("/api/posts/{post_id}/save")
async def toggle_save(post_id: str, request: Request):
    u = require_user(request)
    existing = (
        db()
        .table("saved_posts")
        .select("id")
        .eq("post_id", post_id)
        .eq("user_id", u["id"])
        .limit(1)
        .execute()
    )
    if existing.data:
        db().table("saved_posts").delete().eq("id", existing.data[0]["id"]).execute()
        return {"ok": True, "saved": False}
    try:
        db().table("saved_posts").insert({
            "id": str(uuid.uuid4()),
            "user_id": u["id"],
            "post_id": post_id,
            "created_at": now_iso(),
        }).execute()
        return {"ok": True, "saved": True}
    except Exception:
        return {"ok": True, "saved": True}


@app.get("/api/saved")
async def list_saved(request: Request, page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=50)):
    u = require_user(request)
    start = (page - 1) * limit
    r = (
        db()
        .table("saved_posts")
        .select(
            "id, created_at, post_id, "
            "posts(id, content, category, created_at, is_verified, "
            "users(id, name, public_id, avatar_url), "
            "post_media(id, url, media_type))"
        )
        .eq("user_id", u["id"])
        .order("created_at", desc=True)
        .range(start, start + limit - 1)
        .execute()
    )
    return {"saved": r.data or []}


# ====================== البلاغات ======================
@app.post("/api/posts/{post_id}/report")
async def report_post(post_id: str, request: Request, body: ReportBody):
    u = require_user(request)
    if body.reason not in REPORT_REASONS:
        raise HTTPException(400, "سبب غير صالح")
    # منع الإغراق: بلاغ واحد لكل مستخدم لكل منشور كل 24 ساعة تقريبًا
    if not check_rate(f"report:{u['id']}:{post_id}", max_req=1, window=86400):
        raise HTTPException(429, "لقد أبلغت عن هذا المنشور مسبقًا")
    p = db().table("posts").select("id").eq("id", post_id).limit(1).execute()
    if not p.data:
        raise HTTPException(404, "المنشور غير موجود")
    db().table("reports").insert({
        "id": str(uuid.uuid4()),
        "reporter_id": u["id"],
        "post_id": post_id,
        "reason": body.reason,
        "details": (body.details or "")[:500],
        "status": "جديد",
        "created_at": now_iso(),
    }).execute()
    return {"ok": True, "message": "تم إرسال البلاغ. شكرًا لمساعدتك"}


# ====================== الدردشة العامة ======================
@app.get("/api/chat")
async def list_chat(
    request: Request,
    before: Optional[str] = None,
    limit: int = Query(40, ge=1, le=80),
):
    require_user(request)  # الدردشة للمستخدمين المسجلين فقط
    cleanup_old_messages()
    q = (
        db()
        .table("chat_messages")
        .select(
            "id, content, created_at, reply_to, user_id, "
            "users(id, name, public_id, avatar_url)"
        )
        .order("created_at", desc=True)
        .limit(limit)
    )
    if before:
        q = q.lt("created_at", before)
    r = q.execute()
    msgs = list(reversed(r.data or []))
    return {"messages": msgs}


@app.post("/api/chat")
async def send_chat(request: Request, body: ChatBody):
    u = require_user(request)
    if not check_rate(f"chat:{u['id']}", max_req=15, window=60):
        raise HTTPException(429, "معدل إرسال مرتفع، انتظر قليلاً")
    content = body.content.strip()
    if not content:
        raise HTTPException(400, "الرسالة فارغة")
    data = {
        "id": str(uuid.uuid4()),
        "user_id": u["id"],
        "content": content[:1000],
        "reply_to": body.reply_to,
        "created_at": now_iso(),
    }
    db().table("chat_messages").insert(data).execute()
    return {"ok": True, "message_id": data["id"]}


@app.post("/api/chat/{msg_id}/report")
async def report_chat(msg_id: str, request: Request, body: ReportBody):
    u = require_user(request)
    if body.reason not in REPORT_REASONS:
        raise HTTPException(400, "سبب غير صالح")
    db().table("reports").insert({
        "id": str(uuid.uuid4()),
        "reporter_id": u["id"],
        "message_id": msg_id,
        "reason": body.reason,
        "details": (body.details or "")[:500],
        "status": "جديد",
        "created_at": now_iso(),
    }).execute()
    return {"ok": True, "message": "تم إرسال البلاغ"}



# ====================== الأصدقاء والبحث ======================
def _ordered_pair(uid1: str, uid2: str):
    return (uid1, uid2) if uid1 < uid2 else (uid2, uid1)


def are_friends(uid1: str, uid2: str) -> bool:
    a, b = _ordered_pair(uid1, uid2)
    try:
        r = db().table("friendships").select("id").eq("user_a", a).eq("user_b", b).limit(1).execute()
        return bool(r.data)
    except Exception:
        return False


@app.get("/api/users/search")
async def search_users(request: Request, q: str = Query("", min_length=1), limit: int = Query(20, ge=1, le=50)):
    """بحث عن مستخدمين بالاسم أو public_id"""
    u = require_user(request)
    q = q.strip()[:40]
    if len(q) < 1:
        return {"users": []}
    try:
        # بحث بالاسم
        r1 = db().table("users").select("id, name, public_id, avatar_url, created_at").ilike("name", f"%{q}%").limit(limit).execute()
        r2 = db().table("users").select("id, name, public_id, avatar_url, created_at").ilike("public_id", f"%{q}%").limit(limit).execute()
        seen = set()
        users = []
        for row in (r1.data or []) + (r2.data or []):
            if row["id"] in seen or row["id"] == u["id"]:
                continue
            seen.add(row["id"])
            # حالة الصداقة
            status = "none"
            if are_friends(u["id"], row["id"]):
                status = "friends"
            else:
                fr = db().table("friend_requests").select("id, status, from_user_id").or_(
                    f"and(from_user_id.eq.{u['id']},to_user_id.eq.{row['id']}),and(from_user_id.eq.{row['id']},to_user_id.eq.{u['id']})"
                ).limit(1).execute()
                if fr.data:
                    req = fr.data[0]
                    if req["status"] == "pending":
                        status = "outgoing" if req["from_user_id"] == u["id"] else "incoming"
                    elif req["status"] == "accepted":
                        status = "friends"
            row["friend_status"] = status
            users.append(row)
            if len(users) >= limit:
                break
        return {"users": users}
    except Exception as e:
        raise HTTPException(500, f"خطأ البحث: {str(e)[:120]}")


@app.get("/api/users/{user_id}/profile")
async def public_profile(user_id: str, request: Request):
    u = get_user(request)
    row = get_user_by_id(user_id)
    if not row:
        raise HTTPException(404, "المستخدم غير موجود")
    try:
        cnt = db().table("posts").select("id", count="exact").eq("user_id", user_id).execute()
        posts_count = cnt.count or 0
    except Exception:
        posts_count = 0
    status = "none"
    if u:
        if u["id"] == user_id:
            status = "self"
        elif are_friends(u["id"], user_id):
            status = "friends"
        else:
            try:
                fr = db().table("friend_requests").select("id, status, from_user_id").or_(
                    f"and(from_user_id.eq.{u['id']},to_user_id.eq.{user_id}),and(from_user_id.eq.{user_id},to_user_id.eq.{u['id']})"
                ).limit(1).execute()
                if fr.data:
                    req = fr.data[0]
                    if req["status"] == "pending":
                        status = "outgoing" if req["from_user_id"] == u["id"] else "incoming"
                    elif req["status"] == "accepted":
                        status = "friends"
            except Exception:
                pass
    return {
        "id": row["id"],
        "name": row.get("name") or "مستخدم",
        "public_id": row.get("public_id"),
        "avatar_url": row.get("avatar_url"),
        "created_at": row.get("created_at"),
        "posts_count": posts_count,
        "friend_status": status,
    }


@app.post("/api/friends/request/{to_user_id}")
async def send_friend_request(to_user_id: str, request: Request):
    u = require_user(request)
    if to_user_id == u["id"]:
        raise HTTPException(400, "لا يمكنك إضافة نفسك")
    target = get_user_by_id(to_user_id)
    if not target:
        raise HTTPException(404, "المستخدم غير موجود")
    if are_friends(u["id"], to_user_id):
        raise HTTPException(400, "أنتما صديقان بالفعل")
    # تحقق من طلب قائم
    existing = db().table("friend_requests").select("*").or_(
        f"and(from_user_id.eq.{u['id']},to_user_id.eq.{to_user_id}),and(from_user_id.eq.{to_user_id},to_user_id.eq.{u['id']})"
    ).limit(1).execute()
    if existing.data:
        req = existing.data[0]
        if req["status"] == "pending":
            raise HTTPException(400, "يوجد طلب صداقة قيد الانتظار")
        if req["status"] == "accepted":
            raise HTTPException(400, "أنتما صديقان بالفعل")
        # إعادة فتح طلب مرفوض/ملغى
        db().table("friend_requests").update({
            "from_user_id": u["id"],
            "to_user_id": to_user_id,
            "status": "pending",
            "updated_at": now_iso(),
        }).eq("id", req["id"]).execute()
        return {"ok": True, "message": "تم إرسال طلب الصداقة"}
    db().table("friend_requests").insert({
        "id": str(uuid.uuid4()),
        "from_user_id": u["id"],
        "to_user_id": to_user_id,
        "status": "pending",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }).execute()
    return {"ok": True, "message": "تم إرسال طلب الصداقة"}


@app.post("/api/friends/accept/{request_id}")
async def accept_friend_request(request_id: str, request: Request):
    u = require_user(request)
    r = db().table("friend_requests").select("*").eq("id", request_id).limit(1).execute()
    if not r.data:
        raise HTTPException(404, "الطلب غير موجود")
    req = r.data[0]
    if req["to_user_id"] != u["id"]:
        raise HTTPException(403, "هذا الطلب ليس لك")
    if req["status"] != "pending":
        raise HTTPException(400, "الطلب لم يعد معلقاً")
    db().table("friend_requests").update({
        "status": "accepted",
        "updated_at": now_iso(),
    }).eq("id", request_id).execute()
    a, b = _ordered_pair(req["from_user_id"], req["to_user_id"])
    try:
        db().table("friendships").insert({
            "id": str(uuid.uuid4()),
            "user_a": a,
            "user_b": b,
            "created_at": now_iso(),
        }).execute()
    except Exception:
        pass  # قد يكون موجوداً
    return {"ok": True, "message": "أصبحتما صديقين"}


@app.post("/api/friends/reject/{request_id}")
async def reject_friend_request(request_id: str, request: Request):
    u = require_user(request)
    r = db().table("friend_requests").select("*").eq("id", request_id).limit(1).execute()
    if not r.data:
        raise HTTPException(404, "الطلب غير موجود")
    req = r.data[0]
    if req["to_user_id"] != u["id"] and req["from_user_id"] != u["id"]:
        raise HTTPException(403, "غير مصرح")
    db().table("friend_requests").update({
        "status": "rejected" if req["to_user_id"] == u["id"] else "cancelled",
        "updated_at": now_iso(),
    }).eq("id", request_id).execute()
    return {"ok": True}


@app.get("/api/friends")
async def list_friends(request: Request):
    u = require_user(request)
    try:
        r1 = db().table("friendships").select("user_a, user_b, created_at").eq("user_a", u["id"]).execute()
        r2 = db().table("friendships").select("user_a, user_b, created_at").eq("user_b", u["id"]).execute()
        friend_ids = set()
        for row in (r1.data or []) + (r2.data or []):
            fid = row["user_b"] if row["user_a"] == u["id"] else row["user_a"]
            friend_ids.add(fid)
        friends = []
        for fid in friend_ids:
            row = get_user_by_id(fid)
            if row:
                friends.append({
                    "id": row["id"],
                    "name": row.get("name") or "مستخدم",
                    "public_id": row.get("public_id"),
                    "avatar_url": row.get("avatar_url"),
                })
        return {"friends": friends}
    except Exception as e:
        # إذا لم تُنشأ الجداول بعد
        if "relation" in str(e).lower() or "does not exist" in str(e).lower():
            raise HTTPException(503, "جداول الأصدقاء غير موجودة. نفّذ supabase_schema_friends.sql")
        raise HTTPException(500, str(e)[:120])


@app.get("/api/friends/requests")
async def list_friend_requests(request: Request):
    u = require_user(request)
    try:
        incoming = db().table("friend_requests").select(
            "id, from_user_id, status, created_at, users!friend_requests_from_user_id_fkey(id, name, public_id, avatar_url)"
        ).eq("to_user_id", u["id"]).eq("status", "pending").order("created_at", desc=True).execute()
        outgoing = db().table("friend_requests").select(
            "id, to_user_id, status, created_at, users!friend_requests_to_user_id_fkey(id, name, public_id, avatar_url)"
        ).eq("from_user_id", u["id"]).eq("status", "pending").order("created_at", desc=True).execute()
        return {
            "incoming": incoming.data or [],
            "outgoing": outgoing.data or [],
        }
    except Exception as e:
        # fallback بدون join إن فشل اسم الـ FK
        try:
            inc = db().table("friend_requests").select("*").eq("to_user_id", u["id"]).eq("status", "pending").execute()
            out = db().table("friend_requests").select("*").eq("from_user_id", u["id"]).eq("status", "pending").execute()
            incoming = []
            for r in (inc.data or []):
                fu = get_user_by_id(r["from_user_id"])
                r["users"] = {"id": fu["id"], "name": fu.get("name"), "public_id": fu.get("public_id"), "avatar_url": fu.get("avatar_url")} if fu else {}
                incoming.append(r)
            outgoing = []
            for r in (out.data or []):
                tu = get_user_by_id(r["to_user_id"])
                r["users"] = {"id": tu["id"], "name": tu.get("name"), "public_id": tu.get("public_id"), "avatar_url": tu.get("avatar_url")} if tu else {}
                outgoing.append(r)
            return {"incoming": incoming, "outgoing": outgoing}
        except Exception as e2:
            raise HTTPException(500, str(e2)[:120])


# ====================== الرسائل الخاصة (مثل فيسبوك) ======================
def get_or_create_conversation(uid1: str, uid2: str) -> str:
    a, b = _ordered_pair(uid1, uid2)
    r = db().table("conversations").select("id").eq("user_a", a).eq("user_b", b).limit(1).execute()
    if r.data:
        return r.data[0]["id"]
    cid = str(uuid.uuid4())
    db().table("conversations").insert({
        "id": cid,
        "user_a": a,
        "user_b": b,
        "last_message_at": now_iso(),
        "created_at": now_iso(),
    }).execute()
    return cid


@app.get("/api/messages/conversations")
async def list_conversations(request: Request):
    u = require_user(request)
    try:
        r1 = db().table("conversations").select("*").eq("user_a", u["id"]).order("last_message_at", desc=True).execute()
        r2 = db().table("conversations").select("*").eq("user_b", u["id"]).order("last_message_at", desc=True).execute()
        convs = []
        for c in (r1.data or []) + (r2.data or []):
            other_id = c["user_b"] if c["user_a"] == u["id"] else c["user_a"]
            other = get_user_by_id(other_id)
            # آخر رسالة
            last = db().table("private_messages").select("content, media_type, created_at, sender_id").eq(
                "conversation_id", c["id"]
            ).order("created_at", desc=True).limit(1).execute()
            last_msg = last.data[0] if last.data else None
            convs.append({
                "id": c["id"],
                "other": {
                    "id": other["id"] if other else other_id,
                    "name": (other.get("name") if other else None) or "مستخدم",
                    "public_id": other.get("public_id") if other else None,
                    "avatar_url": other.get("avatar_url") if other else None,
                },
                "last_message": last_msg,
                "last_message_at": c.get("last_message_at"),
            })
        convs.sort(key=lambda x: x.get("last_message_at") or "", reverse=True)
        return {"conversations": convs}
    except Exception as e:
        if "relation" in str(e).lower() or "does not exist" in str(e).lower():
            raise HTTPException(503, "جداول الرسائل غير موجودة. نفّذ supabase_schema_friends.sql")
        raise HTTPException(500, str(e)[:120])


@app.get("/api/messages/{other_user_id}")
async def get_private_messages(
    other_user_id: str,
    request: Request,
    before: Optional[str] = None,
    limit: int = Query(40, ge=1, le=80),
):
    u = require_user(request)
    cleanup_old_messages()
    if other_user_id == u["id"]:
        raise HTTPException(400, "لا يمكن مراسلة نفسك")
    # السماح بالمراسلة لأي مستخدم مسجّل (بحث من صفحة الرسائل)
    a, b = _ordered_pair(u["id"], other_user_id)
    conv = db().table("conversations").select("id").eq("user_a", a).eq("user_b", b).limit(1).execute()
    if not conv.data:
        return {"messages": [], "conversation_id": None}
    cid = conv.data[0]["id"]
    q = (
        db()
        .table("private_messages")
        .select("id, content, media_url, media_type, sender_id, created_at, read_at")
        .eq("conversation_id", cid)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if before:
        q = q.lt("created_at", before)
    r = q.execute()
    msgs = list(reversed(r.data or []))
    # تعليم كمقروء
    try:
        db().table("private_messages").update({"read_at": now_iso()}).eq(
            "conversation_id", cid
        ).neq("sender_id", u["id"]).is_("read_at", "null").execute()
    except Exception:
        pass
    return {"messages": msgs, "conversation_id": cid}


@app.post("/api/messages/{other_user_id}")
async def send_private_message(
    other_user_id: str,
    request: Request,
    content: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None),
):
    u = require_user(request)
    if other_user_id == u["id"]:
        raise HTTPException(400, "لا يمكن مراسلة نفسك")
    target = get_user_by_id(other_user_id)
    if not target:
        raise HTTPException(404, "المستخدم غير موجود")
    if not check_rate(f"dm:{u['id']}", max_req=30, window=60):
        raise HTTPException(429, "معدل إرسال مرتفع")
    content = (content or "").strip()
    if not content and not (image and image.filename) and not (audio and audio.filename):
        raise HTTPException(400, "أدخل نصاً أو صورة أو تسجيلاً")
    cid = get_or_create_conversation(u["id"], other_user_id)
    media_url = media_type = media_path = None
    if image and image.filename:
        m = await upload_media(image, "dm", u["id"])
        media_url, media_type, media_path = m["url"], m["media_type"], m["path"]
    elif audio and audio.filename:
        m = await upload_media(audio, "dm", u["id"])
        media_url, media_type, media_path = m["url"], m["media_type"], m["path"]
    mid = str(uuid.uuid4())
    db().table("private_messages").insert({
        "id": mid,
        "conversation_id": cid,
        "sender_id": u["id"],
        "content": content[:2000] if content else None,
        "media_url": media_url,
        "media_type": media_type,
        "media_path": media_path,
        "created_at": now_iso(),
    }).execute()
    db().table("conversations").update({"last_message_at": now_iso()}).eq("id", cid).execute()
    return {"ok": True, "message_id": mid, "conversation_id": cid}



# ====================== الإدارة ======================

def cleanup_old_messages():
    """حذف الرسائل الخاصة والعامة الأقدم من 24 ساعة"""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        db().table("private_messages").delete().lt("created_at", cutoff).execute()
    except Exception:
        pass
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        db().table("chat_messages").delete().lt("created_at", cutoff).execute()
    except Exception:
        pass


@app.get("/api/admin/reports")
async def admin_reports(request: Request, status: Optional[str] = None):
    require_admin(request)
    q = (
        db()
        .table("reports")
        .select(
            "id, reason, details, status, created_at, post_id, message_id, "
            "reporter_id, users!reports_reporter_id_fkey(name, public_id)"
        )
        .order("created_at", desc=True)
        .limit(100)
    )
    if status:
        q = q.eq("status", status)
    r = q.execute()
    return {"reports": r.data or []}


@app.put("/api/admin/reports/{report_id}")
async def admin_update_report(
    report_id: str,
    request: Request,
    status: str = Form(...),
    action: Optional[str] = Form(None),
):
    """action: delete_post | restrict_24h | delete_user | none"""
    u = require_admin(request)
    if status not in ("جديد", "قيد المراجعة", "تمت المعالجة", "رُفض البلاغ"):
        raise HTTPException(400, "حالة غير صالحة")
    rep = db().table("reports").select("*").eq("id", report_id).limit(1).execute()
    if not rep.data:
        raise HTTPException(404, "بلاغ غير موجود")
    report = rep.data[0]
    action_done = None
    if status == "تمت المعالجة" and action:
        post_id = report.get("post_id")
        if action == "delete_post" and post_id:
            try:
                db().table("post_media").delete().eq("post_id", post_id).execute()
                db().table("likes").delete().eq("post_id", post_id).execute()
                db().table("comments").delete().eq("post_id", post_id).execute()
                db().table("posts").delete().eq("id", post_id).execute()
                action_done = "delete_post"
                # إشعار صاحب المنشور
                post = None
                try:
                    # already deleted
                    pass
                except Exception:
                    pass
            except Exception as e:
                raise HTTPException(500, f"فشل حذف المنشور: {str(e)[:60]}")
        elif action == "restrict_24h":
            # تقييد صاحب المنشور أو المبلّغ عنه
            target_uid = None
            if post_id:
                pr = db().table("posts").select("user_id").eq("id", post_id).limit(1).execute()
                if pr.data:
                    target_uid = pr.data[0]["user_id"]
            if target_uid and target_uid != u["id"]:
                until = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
                try:
                    db().table("users").update({
                        "is_restricted": True,
                        "restricted_until": until,
                        "updated_at": now_iso(),
                    }).eq("id", target_uid).execute()
                except Exception:
                    db().table("users").update({
                        "is_restricted": True,
                        "updated_at": now_iso(),
                    }).eq("id", target_uid).execute()
                action_done = "restrict_24h"
                create_notification(target_uid, "restrict", "تم تقييد حسابك", "تقييد لمدة 24 ساعة بعد بلاغ مقبول", report_id)
        elif action == "delete_user":
            target_uid = None
            if post_id:
                pr = db().table("posts").select("user_id").eq("id", post_id).limit(1).execute()
                if pr.data:
                    target_uid = pr.data[0]["user_id"]
            if target_uid:
                target = get_user_by_id(target_uid)
                if target and target.get("phone") != DEV_PHONE and target_uid != u["id"]:
                    try:
                        db().table("posts").delete().eq("user_id", target_uid).execute()
                        db().table("users").delete().eq("id", target_uid).execute()
                        action_done = "delete_user"
                    except Exception as e:
                        raise HTTPException(500, f"فشل حذف الحساب: {str(e)[:60]}")
    db().table("reports").update({
        "status": status,
        "reviewed_at": now_iso(),
        "reviewed_by": u["id"],
    }).eq("id", report_id).execute()
    # إشعار المبلّغ
    rid = report.get("reporter_id")
    if rid:
        create_notification(
            rid, "report_update",
            f"تحديث بلاغك: {status}",
            f"السبب: {report.get('reason') or ''}",
            report_id,
        )
    return {"ok": True, "action_done": action_done}


@app.post("/api/admin/restrict/{user_id}")
async def admin_restrict(user_id: str, request: Request, restrict: str = Form("true")):
    require_admin(request)
    flag = str(restrict).lower() in ("1", "true", "yes", "on")
    db().table("users").update({
        "is_restricted": flag,
        "updated_at": now_iso(),
    }).eq("id", user_id).execute()
    return {"ok": True, "restricted": flag}


@app.get("/api/admin/stats")
async def admin_stats(request: Request):
    require_admin(request)
    try:
        cleanup_old_messages()
        users = db().table("users").select("id", count="exact").execute()
        posts = db().table("posts").select("id", count="exact").execute()
        reports = db().table("reports").select("id", count="exact").eq("status", "جديد").execute()
        msgs = db().table("chat_messages").select("id", count="exact").execute()
        pm = db().table("private_messages").select("id", count="exact").execute()
        media_count = 0
        try:
            media_count = db().table("post_media").select("id", count="exact").execute().count or 0
        except Exception:
            pass
        return {
            "users": users.count or 0,
            "posts": posts.count or 0,
            "open_reports": reports.count or 0,
            "chat_messages": msgs.count or 0,
            "private_messages": pm.count or 0,
            "media_files": media_count,
            "storage_note": "الخطة المجانية لـ Supabase عادة 1 جيجابايت تخزين. راقب الاستهلاك من Dashboard → Settings → Usage.",
            "note": "الرسائل (خاصة وعامة) تُحذف تلقائيًا بعد 24 ساعة.",
        }
    except Exception as e:
        raise HTTPException(500, str(e)[:100])


@app.get("/api/admin/users")
async def admin_list_users(
    request: Request,
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
):
    """قائمة المستخدمين للمطوّر — تشمل الأرقام"""
    require_admin(request)
    start = (page - 1) * limit
    query = (
        db()
        .table("users")
        .select("id, phone, name, public_id, is_admin, is_restricted, created_at, avatar_url")
        .order("created_at", desc=True)
        .range(start, start + limit - 1)
    )
    if q and q.strip():
        qq = q.strip()
        # بحث تقريبي بالاسم أو الرقم أو public_id
        query = query.or_(f"name.ilike.%{qq}%,phone.ilike.%{qq}%,public_id.ilike.%{qq}%")
    r = query.execute()
    return {"users": r.data or [], "page": page}


@app.delete("/api/admin/users/{user_id}")
async def admin_delete_user(user_id: str, request: Request):
    u = require_admin(request)
    if user_id == u["id"]:
        raise HTTPException(400, "لا يمكن حذف حسابك أنت")
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(404, "المستخدم غير موجود")
    if target.get("phone") == DEV_PHONE:
        raise HTTPException(403, "لا يمكن حذف حساب المطوّر")
    # حذف المنشورات المرتبطة يتم عبر CASCADE إن وُجد، وإلا محاولة يدوية
    try:
        posts = db().table("posts").select("id").eq("user_id", user_id).execute()
        for p in (posts.data or []):
            try:
                db().table("post_media").delete().eq("post_id", p["id"]).execute()
                db().table("likes").delete().eq("post_id", p["id"]).execute()
                db().table("comments").delete().eq("post_id", p["id"]).execute()
                db().table("reports").delete().eq("post_id", p["id"]).execute()
            except Exception:
                pass
        db().table("posts").delete().eq("user_id", user_id).execute()
    except Exception:
        pass
    try:
        db().table("users").delete().eq("id", user_id).execute()
    except Exception as e:
        raise HTTPException(500, f"فشل الحذف: {str(e)[:80]}")
    return {"ok": True, "message": "تم حذف الحساب"}


@app.post("/api/admin/verify-post/{post_id}")
async def admin_verify_post(post_id: str, request: Request, verified: bool = Form(True)):
    require_admin(request)
    db().table("posts").update({
        "is_verified": verified,
        "updated_at": now_iso(),
    }).eq("id", post_id).execute()
    return {"ok": True, "verified": verified}


@app.get("/api/admin/alerts")
async def admin_alerts(request: Request):
    """إشعارات المطوّر: بلاغات جديدة"""
    require_admin(request)
    r = (
        db()
        .table("reports")
        .select(
            "id, reason, details, status, created_at, post_id, message_id, "
            "reporter_id, users!reports_reporter_id_fkey(name, public_id, phone)"
        )
        .eq("status", "جديد")
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return {"alerts": r.data or [], "count": len(r.data or [])}



@app.post("/api/profile/cover")
async def update_cover(request: Request, cover: UploadFile = File(...)):
    u = require_user(request)
    m = await upload_media(cover, "covers", u["id"])
    db().table("users").update({
        "cover_url": m["url"],
        "updated_at": now_iso(),
    }).eq("id", u["id"]).execute()
    row = get_user_by_id(u["id"])
    set_session(request, row)
    return {"ok": True, "cover_url": m["url"]}


@app.post("/api/password/set")
async def set_password(request: Request, body: PasswordBody):
    u = require_user(request)
    row = get_user_by_id(u["id"])
    if not row:
        raise HTTPException(401, "جلسة غير صالحة")
    if not body.password or len(body.password.strip()) < 6:
        raise HTTPException(400, "كلمة المرور 6 أحرف على الأقل")
    stored = row.get("password_hash") or ""
    if stored:
        if not body.old_password or not verify_password(body.old_password.strip(), stored):
            raise HTTPException(401, "كلمة المرور الحالية غير صحيحة")
    set_user_password(row["id"], body.password.strip())
    return {"ok": True, "message": "تم حفظ كلمة المرور"}


@app.post("/api/password/forgot")
async def forgot_password(body: ForgotPasswordBody):
    """إعادة تعيين بكلمة مرور جديدة عبر رقم الهاتف (بدون بريد)"""
    if not check_rate(f"forgot:{body.phone}", max_req=5, window=3600):
        raise HTTPException(429, "محاولات كثيرة")
    phone = normalize_phone(body.phone)
    if not is_valid_dz_phone(phone):
        raise HTTPException(400, "رقم غير صالح")
    if phone == DEV_PHONE:
        raise HTTPException(400, "حساب المطوّر: استخدم كلمة المرور الحالية للتغيير من الإعدادات")
    if not body.new_password or len(body.new_password.strip()) < 6:
        raise HTTPException(400, "كلمة المرور الجديدة 6 أحرف على الأقل")
    row = get_user_by_phone(phone)
    if not row:
        raise HTTPException(404, "الحساب غير موجود")
    set_user_password(row["id"], body.new_password.strip())
    return {"ok": True, "message": "تم تعيين كلمة المرور الجديدة. سجّل الدخول بها"}


@app.delete("/api/account")
async def delete_my_account(request: Request):
    u = require_user(request)
    row = get_user_by_id(u["id"])
    if row and row.get("phone") == DEV_PHONE:
        raise HTTPException(403, "لا يمكن حذف حساب المطوّر من هنا")
    uid = u["id"]
    try:
        posts = db().table("posts").select("id").eq("user_id", uid).execute()
        for p in (posts.data or []):
            try:
                db().table("post_media").delete().eq("post_id", p["id"]).execute()
            except Exception:
                pass
        db().table("posts").delete().eq("user_id", uid).execute()
    except Exception:
        pass
    db().table("users").delete().eq("id", uid).execute()
    request.session.clear()
    return {"ok": True, "message": "تم حذف حسابك"}


def create_notification(user_id: str, ntype: str, title: str, body: str = "", ref_id: str = None):
    try:
        db().table("notifications").insert({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "type": ntype,
            "title": title,
            "body": body or None,
            "ref_id": ref_id,
            "is_read": False,
            "created_at": now_iso(),
        }).execute()
    except Exception:
        pass


@app.get("/api/notifications")
async def list_notifications(request: Request, limit: int = Query(40, ge=1, le=80)):
    u = require_user(request)
    try:
        r = (
            db()
            .table("notifications")
            .select("*")
            .eq("user_id", u["id"])
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        unread = db().table("notifications").select("id", count="exact").eq("user_id", u["id"]).eq("is_read", False).execute()
        return {"notifications": r.data or [], "unread": unread.count or 0}
    except Exception:
        return {"notifications": [], "unread": 0, "hint": "نفّذ جدول notifications"}


@app.post("/api/notifications/read")
async def read_notifications(request: Request):
    u = require_user(request)
    try:
        db().table("notifications").update({"is_read": True}).eq("user_id", u["id"]).eq("is_read", False).execute()
    except Exception:
        pass
    return {"ok": True}


@app.get("/api/my-reports")
async def my_reports(request: Request):
    """تفاصيل بلاغات المستخدم (ما أرسله)"""
    u = require_user(request)
    r = (
        db()
        .table("reports")
        .select("id, reason, details, status, created_at, post_id, reviewed_at")
        .eq("reporter_id", u["id"])
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return {"reports": r.data or []}


@app.post("/api/typing/{other_user_id}")
async def set_typing(other_user_id: str, request: Request):
    u = require_user(request)
    key = "|".join(sorted([u["id"], other_user_id]))
    if key not in TYPING_STATE:
        TYPING_STATE[key] = {}
    TYPING_STATE[key][u["id"]] = time.time()
    return {"ok": True}


@app.get("/api/typing/{other_user_id}")
async def get_typing(other_user_id: str, request: Request):
    u = require_user(request)
    key = "|".join(sorted([u["id"], other_user_id]))
    now = time.time()
    others = TYPING_STATE.get(key, {})
    active = [uid for uid, ts in others.items() if uid != u["id"] and now - ts < 4]
    return {"typing": len(active) > 0}


@app.post("/api/admin/report-action/{report_id}")
async def admin_report_action(
    report_id: str,
    request: Request,
    action: str = Form(...),
):
    """بعد قبول البلاغ: delete_post | restrict_24h | delete_user | dismiss"""
    admin = require_admin(request)
    r = db().table("reports").select("*").eq("id", report_id).limit(1).execute()
    if not r.data:
        raise HTTPException(404, "البلاغ غير موجود")
    rep = r.data[0]
    post_id = rep.get("post_id")
    target_user_id = None
    if post_id:
        p = db().table("posts").select("user_id, content").eq("id", post_id).limit(1).execute()
        if p.data:
            target_user_id = p.data[0]["user_id"]

    if action == "delete_post" and post_id:
        try:
            db().table("post_media").delete().eq("post_id", post_id).execute()
            db().table("likes").delete().eq("post_id", post_id).execute()
            db().table("comments").delete().eq("post_id", post_id).execute()
            db().table("posts").delete().eq("id", post_id).execute()
        except Exception as e:
            raise HTTPException(500, str(e)[:80])
        if target_user_id:
            create_notification(target_user_id, "post_deleted", "تم حذف منشورك", "حُذف منشور بعد مراجعة بلاغ", post_id)
        create_notification(rep["reporter_id"], "report_resolved", "تمت معالجة بلاغك", "تم حذف المحتوى المبلّغ عنه", report_id)

    elif action == "restrict_24h" and target_user_id:
        until = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        db().table("users").update({
            "is_restricted": True,
            "restricted_until": until,
            "updated_at": now_iso(),
        }).eq("id", target_user_id).execute()
        create_notification(target_user_id, "restricted", "تم تقييد حسابك 24 ساعة", "بناءً على بلاغ تمت مراجعته")
        create_notification(rep["reporter_id"], "report_resolved", "تمت معالجة بلاغك", "تم تقييد الحساب مؤقتًا", report_id)

    elif action == "delete_user" and target_user_id:
        t = get_user_by_id(target_user_id)
        if t and t.get("phone") == DEV_PHONE:
            raise HTTPException(403, "لا يمكن حذف المطوّر")
        try:
            db().table("users").delete().eq("id", target_user_id).execute()
        except Exception as e:
            raise HTTPException(500, str(e)[:80])
        create_notification(rep["reporter_id"], "report_resolved", "تمت معالجة بلاغك", "تم حذف الحساب المخالف", report_id)

    elif action == "dismiss":
        create_notification(rep["reporter_id"], "report_resolved", "تم رفض البلاغ", rep.get("reason") or "", report_id)
    else:
        raise HTTPException(400, "إجراء غير صالح أو بيانات ناقصة")

    status = "رُفض البلاغ" if action == "dismiss" else "تمت المعالجة"
    db().table("reports").update({
        "status": status,
        "reviewed_at": now_iso(),
        "reviewed_by": admin["id"],
    }).eq("id", report_id).execute()
    return {"ok": True, "action": action, "status": status}





# ====================== اكتشاف وتعارف ======================
@app.get("/api/discover/random")
async def discover_random(request: Request):
    """بحث عشوائي: يظهر الجنس الآخر مع تفضيل تطابق الاهتمامات"""
    u = require_user(request)
    me = get_user_by_id(u["id"]) or {}
    my_gender = (me.get("gender") or "").strip()
    my_interests = set()
    if me.get("interests"):
        my_interests = {x.strip() for x in str(me.get("interests")).split(",") if x.strip()}

    # الجنس المقابل
    target_gender = None
    if my_gender == "ذكر":
        target_gender = "أنثى"
    elif my_gender == "أنثى":
        target_gender = "ذكر"

    try:
        q = (
            db()
            .table("users")
            .select("id, name, public_id, avatar_url, cover_url, bio, gender, age, origin, interests, created_at")
            .neq("id", u["id"])
            .limit(80)
        )
        if target_gender:
            q = q.eq("gender", target_gender)
        r = q.execute()
        rows = r.data or []
        if not rows and target_gender:
            # إن لم يوجد أحد بالجنس المقابل، أي مستخدم آخر
            r = (
                db()
                .table("users")
                .select("id, name, public_id, avatar_url, cover_url, bio, gender, age, origin, interests, created_at")
                .neq("id", u["id"])
                .limit(80)
                .execute()
            )
            rows = r.data or []
        if not rows:
            return {"match": None, "message": "لا يوجد أعضاء بعد. ادعُ أصدقاءك!"}

        def score(row):
            s = 0
            their = set()
            if row.get("interests"):
                their = {x.strip() for x in str(row.get("interests")).split(",") if x.strip()}
            s += len(my_interests & their) * 10
            if row.get("avatar_url"):
                s += 2
            if row.get("bio"):
                s += 1
            return s

        # ترتيب حسب التطابق ثم اختيار عشوائي من أفضل 10
        import random as _rnd
        ranked = sorted(rows, key=score, reverse=True)
        top = ranked[: max(5, min(10, len(ranked)))]
        pick = _rnd.choice(top)
        their = set()
        if pick.get("interests"):
            their = {x.strip() for x in str(pick.get("interests")).split(",") if x.strip()}
        common = sorted(my_interests & their)
        return {
            "match": pick,
            "common_interests": common,
            "score": score(pick),
        }
    except Exception as e:
        raise HTTPException(500, str(e)[:120])


@app.get("/api/friends/suggestions")
async def friend_suggestions(request: Request, limit: int = Query(12, ge=1, le=30)):
    """اقتراحات صداقة حسب الجنس المقابل والاهتمامات المشتركة"""
    u = require_user(request)
    me = get_user_by_id(u["id"]) or {}
    my_gender = (me.get("gender") or "").strip()
    my_interests = set()
    if me.get("interests"):
        my_interests = {x.strip() for x in str(me.get("interests")).split(",") if x.strip()}
    target_gender = "أنثى" if my_gender == "ذكر" else ("ذكر" if my_gender == "أنثى" else None)

    # أصدقاء حاليون
    friend_ids = set()
    try:
        fa = db().table("friendships").select("user_a, user_b").or_(f"user_a.eq.{u['id']},user_b.eq.{u['id']}").execute()
        for row in (fa.data or []):
            friend_ids.add(row["user_a"] if row["user_b"] == u["id"] else row["user_b"])
    except Exception:
        pass

    try:
        q = (
            db()
            .table("users")
            .select("id, name, public_id, avatar_url, bio, gender, age, origin, interests")
            .neq("id", u["id"])
            .limit(60)
        )
        if target_gender:
            q = q.eq("gender", target_gender)
        r = q.execute()
        rows = [x for x in (r.data or []) if x["id"] not in friend_ids]

        def score(row):
            their = set()
            if row.get("interests"):
                their = {x.strip() for x in str(row.get("interests")).split(",") if x.strip()}
            return len(my_interests & their) * 10 + (2 if row.get("avatar_url") else 0)

        rows.sort(key=score, reverse=True)
        out = []
        for row in rows[:limit]:
            their = set()
            if row.get("interests"):
                their = {x.strip() for x in str(row.get("interests")).split(",") if x.strip()}
            row["common_interests"] = sorted(my_interests & their)
            out.append(row)
        return {"suggestions": out}
    except Exception as e:
        raise HTTPException(500, str(e)[:120])


# ====================== دعم المتابعين ======================
SUPPORT_PLATFORMS = ("facebook", "instagram", "tiktok", "youtube")
SUPPORT_LEVELS = [
    (0, "برونزي", "bronze"),
    (10, "فضي", "silver"),
    (25, "ذهبي", "gold"),
    (50, "بلاتيني", "platinum"),
    (100, "ماسي", "diamond"),
]


def support_level(points: int) -> dict:
    pts = int(points or 0)
    name, key = "برونزي", "bronze"
    for threshold, n, k in SUPPORT_LEVELS:
        if pts >= threshold:
            name, key = n, k
    return {"name": name, "key": key, "icon": "", "points": pts}


def validate_profile_url(platform: str, url: str) -> str:
    url = (url or "").strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    low = url.lower()
    checks = {
        "facebook": ("facebook.com", "fb.com", "fb.watch"),
        "instagram": ("instagram.com", "instagr.am"),
        "tiktok": ("tiktok.com", "vm.tiktok.com"),
        "youtube": ("youtube.com", "youtu.be"),
    }
    allowed = checks.get(platform, ())
    if not any(d in low for d in allowed):
        raise HTTPException(400, f"الرابط لا يبدو لـ {platform}")
    if len(url) > 500:
        raise HTTPException(400, "الرابط طويل جدًا")
    return url


@app.get("/api/support/status")
async def support_status(request: Request):
    """حالة المستخدم في نظام الدعم + ملفاته"""
    u = require_user(request)
    try:
        r = (
            db()
            .table("support_profiles")
            .select("*")
            .eq("user_id", u["id"])
            .eq("is_active", True)
            .order("created_at", desc=True)
            .execute()
        )
        profiles = r.data or []
        total_pts = sum(int(p.get("points") or 0) for p in profiles)
        total_coins = sum(int(p.get("coins") or 0) for p in profiles)
        # إن لم يوجد ملف، النقاط من مجموع الإجراءات
        if not profiles:
            try:
                acts = (
                    db()
                    .table("support_follows")
                    .select("points_awarded")
                    .eq("follower_user_id", u["id"])
                    .execute()
                )
                total_pts = sum(int(a.get("points_awarded") or 0) for a in (acts.data or []))
            except Exception:
                total_pts = 0
        return {
            "profiles": profiles,
            "total_points": total_pts,
            "total_coins": total_coins,
            "level": support_level(total_pts),
            "platforms": list(SUPPORT_PLATFORMS),
            "rules": {
                "register_points": 1,
                "follow_points": 2,
                "list_min_points": 10,
                "levels": [{"min": t, "name": n, "icon": ic} for t, n, ic in SUPPORT_LEVELS],
            },
        }
    except Exception as e:
        raise HTTPException(503, "جداول الدعم غير موجودة. نفّذ SQL الخاص بنظام الدعم. " + str(e)[:80])


@app.post("/api/support/register")
async def support_register(
    request: Request,
    platform: str = Form(...),
    profile_url: str = Form(...),
):
    u = require_user(request)
    platform = (platform or "").strip().lower()
    if platform not in SUPPORT_PLATFORMS:
        raise HTTPException(400, "منصة غير مدعومة")
    url = validate_profile_url(platform, profile_url)
    if not check_rate(f"support_reg:{u['id']}", max_req=10, window=3600):
        raise HTTPException(429, "محاولات كثيرة")
    try:
        existing = (
            db()
            .table("support_profiles")
            .select("id, points")
            .eq("user_id", u["id"])
            .eq("platform", platform)
            .limit(1)
            .execute()
        )
        if existing.data:
            db().table("support_profiles").update({
                "profile_url": url,
                "is_active": True,
                "updated_at": now_iso(),
            }).eq("id", existing.data[0]["id"]).execute()
            return {
                "ok": True,
                "message": "تم تحديث رابط ملفك في نظام الدعم",
                "profile_id": existing.data[0]["id"],
                "points": existing.data[0].get("points") or 1,
            }
        row = {
            "id": str(uuid.uuid4()),
            "user_id": u["id"],
            "platform": platform,
            "profile_url": url,
            "points": 1,
            "coins": 0,
            "is_active": True,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        db().table("support_profiles").insert(row).execute()
        return {
            "ok": True,
            "message": "تم تسجيل ملفك في تطبيق الدعم ومنحت نقطة واحدة",
            "profile_id": row["id"],
            "points": 1,
            "level": support_level(1),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, "تعذر التسجيل. تأكد من تنفيذ جداول الدعم. " + str(e)[:100])


@app.get("/api/support/tasks")
async def support_tasks(request: Request, limit: int = Query(20, ge=1, le=50)):
    """
    مرحلة الإطلاق (أقل من 100 مستخدم): كل الملفات المسجّلة تظهر في المهام.
    بعد وصول عدد المستخدمين إلى 100: يظهر فقط من لديه 10 نقاط فأكثر.
    """
    u = require_user(request)
    try:
        users_count = 0
        try:
            uc = db().table("users").select("id", count="exact").execute()
            users_count = uc.count or 0
        except Exception:
            users_count = 0
        # عتبة التحويل التلقائي للنظام الناضج
        MATURE_USER_COUNT = 100
        min_points = 10 if users_count >= MATURE_USER_COUNT else 1
        phase = "mature" if users_count >= MATURE_USER_COUNT else "launch"

        q = (
            db()
            .table("support_profiles")
            .select(
                "id, platform, profile_url, points, coins, user_id, created_at, "
                "users(id, name, public_id, avatar_url)"
            )
            .eq("is_active", True)
            .gte("points", min_points)
            .neq("user_id", u["id"])
            .order("points", desc=True)
            .limit(100)
        )
        r = q.execute()
        rows = r.data or []
        done = set()
        try:
            fr = (
                db()
                .table("support_follows")
                .select("profile_id")
                .eq("follower_user_id", u["id"])
                .execute()
            )
            done = {x["profile_id"] for x in (fr.data or [])}
        except Exception:
            pass
        tasks = []
        for p in rows:
            if p["id"] in done:
                continue
            p["level"] = support_level(p.get("points") or 0)
            tasks.append(p)
            if len(tasks) >= limit:
                break
        return {
            "tasks": tasks,
            "phase": phase,
            "users_count": users_count,
            "min_points_required": min_points,
            "phase_note": (
                "مرحلة ناضجة: يظهر في المهام من لديه 10 نقاط فأكثر"
                if phase == "mature"
                else "مرحلة الإطلاق: كل الملفات المسجّلة تظهر في المهام حتى يصل عدد المستخدمين إلى 100"
            ),
        }
    except Exception as e:
        raise HTTPException(503, "جداول الدعم غير جاهزة: " + str(e)[:100])


@app.post("/api/support/follow/{profile_id}")
async def support_follow(profile_id: str, request: Request):
    """تأكيد المتابعة: +2 نقطة للمتابع، +1 عملة لصاحب الملف"""
    u = require_user(request)
    if not check_rate(f"support_follow:{u['id']}", max_req=40, window=3600):
        raise HTTPException(429, "معدل مرتفع، حاول لاحقًا")
    try:
        pr = (
            db()
            .table("support_profiles")
            .select("*")
            .eq("id", profile_id)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        if not pr.data:
            raise HTTPException(404, "الملف غير موجود")
        profile = pr.data[0]
        if profile["user_id"] == u["id"]:
            raise HTTPException(400, "لا يمكن متابعة ملفك أنت")
        # هل سبق؟
        prev = (
            db()
            .table("support_follows")
            .select("id")
            .eq("follower_user_id", u["id"])
            .eq("profile_id", profile_id)
            .limit(1)
            .execute()
        )
        if prev.data:
            raise HTTPException(400, "لقد سجّلت متابعة هذا الملف مسبقًا")
        db().table("support_follows").insert({
            "id": str(uuid.uuid4()),
            "follower_user_id": u["id"],
            "profile_id": profile_id,
            "points_awarded": 2,
            "created_at": now_iso(),
        }).execute()
        # +2 نقاط لأحد ملفات المتابع (أو نجمعها لاحقًا من follows)
        my_prof = (
            db()
            .table("support_profiles")
            .select("id, points")
            .eq("user_id", u["id"])
            .eq("is_active", True)
            .order("created_at", desc=False)
            .limit(1)
            .execute()
        )
        new_pts = 2
        if my_prof.data:
            np = int(my_prof.data[0].get("points") or 0) + 2
            db().table("support_profiles").update({
                "points": np,
                "updated_at": now_iso(),
            }).eq("id", my_prof.data[0]["id"]).execute()
            new_pts = np
        # +1 عملة لصاحب الملف
        db().table("support_profiles").update({
            "coins": int(profile.get("coins") or 0) + 1,
            "updated_at": now_iso(),
        }).eq("id", profile_id).execute()
        return {
            "ok": True,
            "message": "تم تسجيل المتابعة. حصلت على نقطتين",
            "points_gained": 2,
            "your_points": new_pts,
            "level": support_level(new_pts),
            "open_url": profile.get("profile_url"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e)[:120])


@app.get("/api/support/leaderboard")
async def support_leaderboard(limit: int = Query(20, ge=1, le=50)):
    try:
        r = (
            db()
            .table("support_profiles")
            .select("id, platform, profile_url, points, coins, users(name, public_id, avatar_url)")
            .eq("is_active", True)
            .order("points", desc=True)
            .limit(limit)
            .execute()
        )
        rows = r.data or []
        for p in rows:
            p["level"] = support_level(p.get("points") or 0)
        return {"leaders": rows}
    except Exception as e:
        return {"leaders": [], "error": str(e)[:80]}


# ====================== الواجهة (HTML مدمج) ======================
# نستخدم صفحة واحدة مع JavaScript للتنقل بين الأقسام

APP_HTML = r'''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>DZ Connect</title>
<style>
:root {
  --bg: #1a0a10;
  --bg2: #2a1018;
  --bg3: #3d1522;
  --bg4: #4a1a2a;
  --border: rgba(255,120,150,0.12);
  --text: #fff5f7;
  --text2: #c4a0ab;
  --blue: #e11d48;
  --blue2: #be123c;
  --green: #22c55e;
  --red: #fb7185;
  --orange: #f43f5e;
  --radius: 16px;
  --nav-h: 68px;
  --love: #e11d48;
  --love2: #fb7185;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Segoe UI', Tahoma, 'Noto Sans Arabic', Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  padding-bottom: calc(var(--nav-h) + 16px);
  line-height: 1.5;
}
a { color: var(--blue); text-decoration: none; }
button, .btn {
  cursor: pointer;
  border: none;
  border-radius: 8px;
  padding: 10px 16px;
  font-size: 15px;
  font-weight: 600;
  transition: opacity .15s, transform .1s;
}
button:active, .btn:active { transform: scale(0.97); }
button:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: linear-gradient(135deg, var(--blue), var(--blue2)); color: #fff; box-shadow: 0 4px 14px rgba(37,99,235,.35); }
.btn-ghost { background: transparent; color: var(--text2); border: 1px solid var(--border); }
.btn-danger { background: var(--red); color: #fff; }
.btn-sm { padding: 6px 12px; font-size: 13px; }
input, textarea, select {
  width: 100%;
  background: var(--bg3);
  border: 1px solid var(--border);
  color: var(--text);
  border-radius: 8px;
  padding: 12px;
  font-size: 15px;
  outline: none;
}
input:focus, textarea:focus, select:focus { border-color: var(--blue); }
textarea { min-height: 100px; resize: vertical; }
label { display: block; margin-bottom: 6px; color: var(--text2); font-size: 13px; }
.form-group { margin-bottom: 14px; }

/* شاشة الترحيب */
#welcome {
  position: fixed; inset: 0; z-index: 100;
  background: linear-gradient(160deg, #0d1117 0%, #0a1628 50%, #0d1117 100%);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 24px; text-align: center;
}
#welcome .logo {
  font-size: 2.4rem; font-weight: 800;
  background: linear-gradient(90deg, var(--blue), #a5d6ff);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  margin-bottom: 12px;
}
#welcome p { color: var(--text2); max-width: 320px; margin-bottom: 28px; }

/* هيدر عصري */
.app-top {
  position: sticky; top: 0; z-index: 50;
  background: linear-gradient(180deg, rgba(7,15,26,.97) 0%, rgba(13,27,42,.92) 100%);
  backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
  border-bottom: 1px solid var(--border);
}
.app-top-hero {
  background:
    linear-gradient(180deg, rgba(7,15,26,.5) 0%, rgba(7,15,26,.88) 75%, var(--bg) 100%),
    radial-gradient(ellipse at 70% 20%, rgba(37,99,235,.28), transparent 55%),
    linear-gradient(135deg, #0a1628, #132337);
  padding: 14px 16px 12px;
}
.app-top-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.brand-block { text-align: center; flex: 1; }
.brand-block .brand {
  font-size: 1.35rem; font-weight: 800;
  background: linear-gradient(90deg, #fff, #60a5fa);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.brand-block .tagline { font-size: 11px; color: var(--text2); margin-top: 2px; }
.top-icon-btn {
  width: 40px; height: 40px; border-radius: 50%;
  background: rgba(255,255,255,.06); border: 1px solid var(--border);
  color: var(--text); display: flex; align-items: center; justify-content: center;
  font-size: 18px; padding: 0;
}
.top-avatar {
  width: 40px; height: 40px; border-radius: 50%; border: 2px solid var(--blue);
  background: var(--bg3); display: flex; align-items: center; justify-content: center;
  font-weight: 700; color: var(--blue); font-size: 14px; overflow: hidden; cursor: pointer;
}
.top-avatar img { width: 100%; height: 100%; object-fit: cover; }

.compose-bar {
  margin: 12px 16px 8px; background: var(--bg2); border: 1px solid var(--border);
  border-radius: 999px; padding: 8px 10px 8px 12px;
  display: flex; align-items: center; gap: 10px;
  box-shadow: 0 4px 20px rgba(0,0,0,.25);
}
.compose-bar .hint {
  flex: 1; color: var(--text2); font-size: 14px; cursor: pointer;
  padding: 6px 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.compose-bar .publish-btn {
  background: linear-gradient(135deg, #3b82f6, #2563eb); color: #fff;
  border-radius: 999px; padding: 8px 16px; font-size: 13px; white-space: nowrap;
  box-shadow: 0 2px 10px rgba(37,99,235,.4); border: none; font-weight: 600;
}

.empty-state { text-align: center; padding: 48px 24px 32px; color: var(--text2); }
.empty-state .empty-icon {
  width: 88px; height: 88px; margin: 0 auto 16px; background: var(--bg3);
  border-radius: 20px; display: flex; align-items: center; justify-content: center;
  font-size: 40px; position: relative; border: 1px solid var(--border);
  box-shadow: 0 0 40px rgba(59,130,246,.12);
}
.empty-state .empty-icon .plus-badge {
  position: absolute; bottom: -6px; left: -6px; width: 28px; height: 28px;
  border-radius: 50%; background: var(--blue); color: #fff; font-size: 18px;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 2px 8px rgba(37,99,235,.5);
}
.empty-state h3 { color: var(--text); font-size: 17px; margin-bottom: 6px; }
.empty-state p { font-size: 13px; max-width: 260px; margin: 0 auto 18px; line-height: 1.6; }


/* الهيدر */
/* .header قديم — الهيدر الجديد .app-top */
.header { display: none !important; }
.header .brand { font-weight: 800; font-size: 1.25rem; color: var(--blue); }
.header-actions { display: flex; gap: 8px; align-items: center; }

/* شريط التنقل السفلي */
body.dm-open .bottom-nav { display: none !important; }
body.dm-open { padding-bottom: 0; }
body.dm-open .dm-box { height: calc(100vh - 60px); }
.admin-user-card { font-size: 13px; }
.admin-user-card .phone { direction: ltr; font-family: monospace; color: var(--orange); }
.linkified a { color: var(--blue); text-decoration: underline; word-break: break-all; }
.bottom-nav {
  position: fixed; bottom: 0; left: 0; right: 0; height: var(--nav-h);
  background: rgba(13,27,42,.96); backdrop-filter: blur(16px); border-top: 1px solid var(--border);
  display: flex; justify-content: space-around; align-items: center;
  z-index: 60; padding-bottom: env(safe-area-inset-bottom);
}
.nav-item {
  display: flex; flex-direction: column; align-items: center; gap: 2px;
  color: var(--text2); font-size: 11px; background: none; border: none; padding: 8px 12px;
}
.nav-item.active { color: var(--blue); }
.nav-item .icon { font-size: 22px; }
.nav-item.create {
  background: linear-gradient(145deg, #3b82f6, #1d4ed8); color: #fff; border-radius: 50%;
  width: 52px; height: 52px; justify-content: center; margin-top: -22px;
  box-shadow: 0 6px 20px rgba(37,99,235,.5);
}
.nav-item.create .icon { font-size: 28px; font-weight: 300; }
.nav-item.create span:not(.icon) { display: none; }

/* الصفحات */
.page { display: none; padding: 16px; max-width: 640px; margin: 0 auto; }
.page.active { display: block; }

/* بطاقة المنشور */
.card {
  background: var(--bg2); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 14px; margin: 0 16px 12px;
}
.card-header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.avatar {
  width: 40px; height: 40px; border-radius: 50%;
  background: var(--bg3); object-fit: cover;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; color: var(--blue); font-size: 14px; flex-shrink: 0;
}
.avatar img { width: 100%; height: 100%; border-radius: 50%; object-fit: cover; }
.user-meta { flex: 1; min-width: 0; }
.user-meta .name { font-weight: 600; font-size: 14px; }
.user-meta .time { font-size: 12px; color: var(--text2); }
.badge {
  display: inline-block; padding: 2px 8px; border-radius: 20px;
  font-size: 11px; font-weight: 600; background: var(--bg3); color: var(--text2);
}
.badge.verified { background: rgba(63,185,80,.15); color: var(--green); }
.badge.bot { background: rgba(88,166,255,.12); color: var(--blue); }
.card-body { margin-bottom: 10px; white-space: pre-wrap; word-break: break-word; }
.card-body img, .card-body audio {
  max-width: 100%; border-radius: 8px; margin-top: 8px; display: block;
}
.card-body img {
  width: 100%; max-height: 420px; object-fit: cover; background: var(--bg3);
  cursor: pointer;
}
.card-body audio { width: 100%; }

/* أصدقاء ورسائل */
.user-row {
  display: flex; align-items: center; gap: 12px; padding: 12px;
  background: var(--bg2); border: 1px solid var(--border); border-radius: var(--radius);
  margin-bottom: 8px;
}
.user-row .info { flex: 1; min-width: 0; }
.user-row .info .name { font-weight: 600; }
.user-row .info .sub { font-size: 12px; color: var(--text2); }

/* محادثة خاصة */
.dm-box { display: flex; flex-direction: column; height: calc(100vh - var(--nav-h) - 70px); }
.dm-messages { flex: 1; overflow-y: auto; padding: 8px 0; display: flex; flex-direction: column; gap: 6px; }
.dm-bubble {
  max-width: 80%; padding: 10px 14px; border-radius: 16px; font-size: 14px;
  word-break: break-word; white-space: pre-wrap;
}
.dm-bubble.mine { align-self: flex-start; background: var(--blue2); color: #fff; border-bottom-right-radius: 4px; }
.dm-bubble.theirs { align-self: flex-end; background: var(--bg3); border-bottom-left-radius: 4px; }
.dm-bubble img { max-width: 100%; border-radius: 10px; margin-top: 6px; display: block; }
.dm-bubble audio { width: 220px; margin-top: 6px; display: block; }
.dm-meta { font-size: 11px; opacity: 0.75; margin-top: 4px; }

/* تسجيل صوت بالضغط */
.rec-btn {
  width: 48px; height: 48px; border-radius: 50%; background: var(--bg3);
  border: 2px solid var(--border); color: var(--text); font-size: 22px;
  display: flex; align-items: center; justify-content: center;
  user-select: none; -webkit-user-select: none; touch-action: none;
}
.rec-btn.recording {
  background: var(--red); border-color: var(--red); color: #fff;
  animation: pulse 1s infinite;
}
@keyframes pulse {
  0%, 100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(248,81,73,.5); }
  50% { transform: scale(1.08); box-shadow: 0 0 0 12px rgba(248,81,73,0); }
}
.rec-hint { font-size: 12px; color: var(--text2); text-align: center; margin-top: 4px; }
.search-bar { display: flex; gap: 8px; margin-bottom: 12px; }
.search-bar input { flex: 1; }

.card-actions {
  display: flex; gap: 6px; flex-wrap: wrap; border-top: 1px solid var(--border);
  padding-top: 10px; margin-top: 4px;
}
.action-btn {
  background: transparent; color: var(--text2); border: none;
  padding: 6px 10px; font-size: 13px; border-radius: 6px;
  display: flex; align-items: center; gap: 4px;
}
.action-btn:hover { background: var(--bg3); color: var(--text); }
.action-btn.liked { color: var(--red); }
.action-btn.saved { color: var(--orange); }

/* حالات */
.empty, .loading, .error-box {
  text-align: center; padding: 40px 20px; color: var(--text2);
}
.error-box { color: var(--red); background: rgba(248,81,73,.08);
  border: 1px solid rgba(248,81,73,.25); border-radius: var(--radius); margin: 16px 0; }
.toast {
  position: fixed; bottom: calc(var(--nav-h) + 20px); left: 50%; transform: translateX(-50%);
  background: var(--bg3); border: 1px solid var(--border); color: var(--text);
  padding: 12px 20px; border-radius: 10px; z-index: 200; font-size: 14px;
  box-shadow: 0 8px 24px rgba(0,0,0,.4); max-width: 90%;
  animation: fadeIn .2s ease;
}
@keyframes fadeIn { from { opacity: 0; transform: translateX(-50%) translateY(10px); } }

/* الدردشة */
.chat-box {
  display: flex; flex-direction: column; height: calc(100vh - var(--nav-h) - 70px);
}
.chat-messages { flex: 1; overflow-y: auto; padding: 8px 0; }
.chat-msg {
  background: var(--bg2); border-radius: 12px; padding: 10px 12px;
  margin-bottom: 8px; max-width: 90%;
}
.chat-msg .meta { font-size: 12px; color: var(--text2); margin-bottom: 4px; }
.chat-input-row {
  display: flex; gap: 8px; padding: 8px 0; border-top: 1px solid var(--border);
}
.chat-input-row input { flex: 1; }

/* مودال */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.7); z-index: 150;
  display: flex; align-items: flex-end; justify-content: center;
}
.modal {
  background: var(--bg2); border-radius: 16px 16px 0 0;
  width: 100%; max-width: 500px; max-height: 85vh; overflow-y: auto;
  padding: 20px; animation: slideUp .25s ease;
}
@keyframes slideUp { from { transform: translateY(40px); opacity: 0; } }
.modal h3 { margin-bottom: 14px; }
.modal-close { float: left; background: none; border: none; color: var(--text2); font-size: 22px; }

/* فلاتر */
.filters { display: flex; gap: 8px; overflow-x: auto; padding: 8px 0 12px; scrollbar-width: none; }
.filters::-webkit-scrollbar { display: none; }
.filter-chip {
  white-space: nowrap; padding: 8px 16px; border-radius: 999px;
  background: var(--bg3); border: 1px solid var(--border); color: var(--text2);
  font-size: 13px; font-weight: 600; cursor: pointer;
  display: inline-flex; align-items: center; gap: 6px;
}
.filter-chip.active {
  background: linear-gradient(135deg, var(--blue), var(--blue2));
  color: #fff; border-color: transparent;
  box-shadow: 0 4px 12px rgba(37,99,235,.3);
}

/* إعدادات */
.settings-list { list-style: none; }
.settings-list li {
  padding: 14px 0; border-bottom: 1px solid var(--border);
  display: flex; justify-content: space-between; align-items: center;
}
.settings-list li button, .settings-list li a { color: var(--text); }

@media (min-width: 640px) {
  .bottom-nav { max-width: 640px; left: 50%; transform: translateX(-50%); border-radius: 16px 16px 0 0; }
  .modal { border-radius: 16px; margin-bottom: 40px; }
}

/* منشورات بعرض كامل */
.card { margin-left: 0 !important; margin-right: 0 !important; border-radius: 0 !important; border-left: none; border-right: none; }
@media (min-width: 640px) {
  .card { margin-left: 16px !important; margin-right: 16px !important; border-radius: var(--radius) !important; border: 1px solid var(--border); }
}
/* محادثة خاصة — شاشة كاملة مع شريط كتابة ثابت أسفل */
body.dm-open {
  overflow: hidden;
  padding-bottom: 0 !important;
}
body.dm-open main { padding-bottom: 0 !important; }
body.dm-open .bottom-nav { display: none !important; }
body.dm-open #mainHeader { display: none !important; }
body.dm-open #page-messages {
  position: fixed; inset: 0; z-index: 80; background: var(--bg);
  display: flex !important; flex-direction: column; padding: 0 !important; margin: 0 !important;
  max-width: none !important;
}
body.dm-open #convListView { display: none !important; }
body.dm-open #dmView {
  display: flex !important; flex-direction: column;
  flex: 1; height: 100%; min-height: 0; background: var(--bg);
}
body.dm-open #dmView > div:first-child {
  flex-shrink: 0; padding: 12px 16px;
  border-bottom: 1px solid var(--border); background: var(--bg2);
}
body.dm-open .dm-box {
  position: relative !important; inset: auto !important;
  flex: 1; min-height: 0; height: auto !important;
  display: flex; flex-direction: column;
  background: var(--bg);
}
body.dm-open .dm-messages {
  flex: 1; min-height: 0; overflow-y: auto; -webkit-overflow-scrolling: touch;
  padding: 12px 16px;
}
body.dm-open .chat-input-row {
  flex-shrink: 0 !important;
  background: var(--bg2);
  border-top: 1px solid var(--border);
  padding: 10px 12px;
  padding-bottom: max(12px, env(safe-area-inset-bottom, 0px));
  position: relative; z-index: 5;
}
body.dm-open .rec-hint {
  flex-shrink: 0; background: var(--bg2);
  padding-bottom: max(4px, env(safe-area-inset-bottom, 0px));
}

/* دردشة عامة — ملء الشاشة */
body.chat-open { overflow: hidden; padding-bottom: 0 !important; }
body.chat-open .bottom-nav { display: none !important; }
body.chat-open #mainHeader { display: none !important; }
body.chat-open #page-chat {
  position: fixed; inset: 0; z-index: 80; background: var(--bg);
  display: flex !important; flex-direction: column; padding: 0 !important;
  max-width: none !important;
}
body.chat-open #chatBackBtn { display: inline-flex !important; }
body.chat-open #page-chat .page-pad {
  flex-shrink: 0; padding: 12px 16px; border-bottom: 1px solid var(--border); background: var(--bg2);
}
body.chat-open .chat-box {
  position: relative !important; inset: auto !important;
  flex: 1; min-height: 0; height: auto !important;
  display: flex; flex-direction: column;
}
body.chat-open .chat-messages {
  flex: 1; min-height: 0; overflow-y: auto; -webkit-overflow-scrolling: touch;
}
body.chat-open .chat-input-row {
  flex-shrink: 0 !important;
  padding-bottom: max(12px, env(safe-area-inset-bottom, 0px));
  background: var(--bg2);
}

.chat-color-dot {
  width: 22px; height: 22px; border-radius: 50%; border: 2px solid rgba(255,255,255,.35);
  cursor: pointer; padding: 0;
}
.chat-color-dot:hover { transform: scale(1.1); }
body.chat-themed .chat-box, body.chat-themed .dm-box {
  --chat-accent: var(--chat-theme, #e11d48);
}
body.chat-themed .chat-input-row button.btn-primary,
body.chat-themed .btn-primary {
  background: var(--chat-theme, #e11d48) !important;
}
.discover-card { text-align: center; }
.discover-card .avatar { width: 88px; height: 88px; margin: 0 auto 12px; font-size: 28px; }
.interest-tag {
  display: inline-block; padding: 4px 10px; margin: 3px;
  border-radius: 999px; font-size: 11px;
  background: rgba(225,29,72,.15); color: #fb7185;
}
.header-title { color: #fb7185 !important; }
.compose-bar { border-color: rgba(225,29,72,.25) !important; }
.nav-item.create { background: linear-gradient(135deg,#e11d48,#fb7185) !important; box-shadow: 0 4px 16px rgba(225,29,72,.4) !important; }
.act-ico { width: 18px; height: 18px; display: inline-block; vertical-align: middle; }
.action-btn { gap: 6px; }
.lvl-badge {
  display: inline-block; padding: 2px 10px; border-radius: 999px;
  font-size: 11px; font-weight: 700; letter-spacing: 0.02em;
  background: var(--bg4); color: var(--text2);
}
.lvl-bronze { background: rgba(180,120,60,.2); color: #d4a574; }
.lvl-silver { background: rgba(160,170,180,.2); color: #c0c8d0; }
.lvl-gold { background: rgba(234,179,8,.18); color: #eab308; }
.lvl-platinum { background: rgba(148,163,184,.25); color: #94a3b8; }
.lvl-diamond { background: rgba(59,130,246,.2); color: #60a5fa; }
.top-icon-btn svg { pointer-events: none; }
#supportFab { display: flex; align-items: center; justify-content: center; gap: 8px; }
.app-top-hero {
  border-bottom: 1px solid var(--border);
}
.filter-chip { letter-spacing: 0.01em; }

.nav-icon-svg { width: 24px; height: 24px; stroke: currentColor; fill: none; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.nav-item.create .nav-icon-svg { stroke: #fff; width: 28px; height: 28px; }
.theme-light {
  --bg: #fff5f7; --bg2: #ffffff; --bg3: #ffe4e9; --bg4: #fecdd3;
  --border: rgba(225,29,72,0.12); --text: #4c0519; --text2: #9f1239;
  --blue: #e11d48; --blue2: #be123c;
}
.typing-indicator { font-size: 12px; color: var(--text2); padding: 4px 16px; font-style: italic; }

</style>
</head>
<body>

<!-- شاشة الترحيب -->
<div id="welcome">
  <div class="logo">DZ Connect</div>
  <p>منصة تعارف جزائرية — تواصل بصدق، اعثر على من يشاركك الاهتمامات</p>
  <button class="btn btn-primary" style="padding:14px 40px;font-size:16px" onclick="startApp()">ابدأ الآن</button>
  <p style="margin-top:16px;font-size:12px;color:var(--text2)">تعارف • صداقة • اهتمامات مشتركة</p>
</div>

<!-- الهيدر العصري -->
<div class="app-top" id="mainHeader" style="display:none">
  <div class="app-top-hero">
    <div class="app-top-row">
      <button class="top-icon-btn" onclick="showPage('settings')" title="الإعدادات"><svg class="nav-icon-svg" viewBox="0 0 24 24" style="width:20px;height:20px"><circle cx="12" cy="12" r="3"/><path d="M12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4"/></svg></button>
      <div class="brand-block">
        <div class="brand">DZ Connect</div>
        <div class="tagline">تعارف · اهتمامات · رسائل</div>
      </div>
      <div class="top-avatar" id="headerAvatar" onclick="showPage('profile')" title="حسابي">?</div>
    </div>
  </div>
</div>

<!-- الصفحات -->
<main>
  <!-- الرئيسية -->
  <div id="page-home" class="page">
    <button type="button" class="btn btn-primary" id="discoverFab" style="margin:10px 16px 0;width:calc(100% - 32px);border-radius:999px;padding:14px;font-size:15px;font-weight:700" onclick="runDiscover()">بحث عشوائي — اعثر على شخص متوافق</button>
    <button type="button" class="btn-ghost" style="margin:8px 16px 0;width:calc(100% - 32px);border-radius:999px;padding:10px;font-size:13px" onclick="showPage('friends')">اقتراحات صداقة</button>
    <div class="compose-bar" id="composeBar" onclick="showPage('create')">
      <div class="avatar" id="composeAvatar" style="width:36px;height:36px;font-size:12px">?</div>
      <div class="hint">شارك شيئًا مع المجتمع...</div>
      <button class="publish-btn" type="button" onclick="event.stopPropagation();showPage('create')">نشر</button>
    </div>
    <div class="filters" id="categoryFilters"></div>
    <div id="postsList" class="loading">جاري التحميل...</div>
    <div style="text-align:center;margin:16px 0">
      <button class="btn-ghost btn-sm" id="loadMoreBtn" style="display:none" onclick="loadMorePosts()">تحميل المزيد</button>
    </div>
  </div>

  <!-- إنشاء منشور -->
  <div id="page-create" class="page">
    <h2 style="margin-bottom:16px">منشور جديد</h2>
    <div class="form-group">
      <label>التصنيف</label>
      <select id="postCategory"></select>
    </div>
    <div class="form-group" id="botStatusGroup" style="display:none">
      <label>حالة البوت</label>
      <select id="botStatus"></select>
    </div>
    <div class="form-group">
      <label>النص (اختياري)</label>
      <textarea id="postContent" placeholder="اكتب تجربتك أو تفاصيل العرض..."></textarea>
    </div>
    <div class="form-group">
      <label>صورة (اختياري)</label>
      <input type="file" id="postImage" accept="image/*">
    </div>
    <div class="form-group">
      <label>تسجيل صوتي (اختياري)</label>
      <input type="file" id="postAudio" accept="audio/*">
      <div style="display:flex;align-items:center;gap:12px;margin-top:10px">
        <button type="button" class="rec-btn" id="postRecBtn" title="اضغط مطولاً"><svg class="act-ico" viewBox="0 0 24 24"><rect x="9" y="3" width="6" height="11" rx="3" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3" fill="none" stroke="currentColor" stroke-width="1.6"/></svg></button>
        <span class="rec-hint" id="postRecHint">اضغط مطولاً للتسجيل الصوتي ثم أفلت</span>
      </div>
    </div>
    <div id="previewBox" style="display:none;margin-bottom:12px" class="card"></div>
    <button class="btn btn-primary" style="width:100%" id="publishBtn" onclick="publishPost()">نشر</button>
  </div>

  <!-- الدردشة -->
  <div id="page-chat" class="page">
    <div class="page-pad" style="display:flex;align-items:center;gap:10px">
      <button class="btn-ghost btn-sm" onclick="showPage('home')" style="display:none" id="chatBackBtn">→</button>
      <div>
        <h2 style="margin:0;font-size:1.1rem">الدردشة العامة</h2>
        <p style="color:var(--text2);font-size:12px;margin:0">غرفة مفتوحة · غيّر لون المحادثة · الرسائل تُجدَّد كل 24 ساعة</p>
        <div style="display:flex;gap:6px;margin-top:8px;align-items:center">
          <span style="font-size:11px;color:var(--text2)">لون الدردشة</span>
          <button type="button" class="chat-color-dot" style="background:#e11d48" onclick="setChatTheme('#e11d48')"></button>
          <button type="button" class="chat-color-dot" style="background:#db2777" onclick="setChatTheme('#db2777')"></button>
          <button type="button" class="chat-color-dot" style="background:#7c3aed" onclick="setChatTheme('#7c3aed')"></button>
          <button type="button" class="chat-color-dot" style="background:#0891b2" onclick="setChatTheme('#0891b2')"></button>
          <button type="button" class="chat-color-dot" style="background:#16a34a" onclick="setChatTheme('#16a34a')"></button>
        </div>
      </div>
    </div>
    <div class="chat-box">
      <div class="chat-messages" id="chatMessages">
        <div class="loading">جاري تحميل الرسائل...</div>
      </div>
      <div class="chat-input-row">
        <input type="text" id="chatInput" placeholder="اكتب رسالة..." maxlength="1000"
               onkeydown="if(event.key==='Enter')sendChat()">
        <button class="btn btn-primary" onclick="sendChat()">إرسال</button>
      </div>
    </div>
  </div>

  <!-- الملف الشخصي -->
  <div id="page-profile" class="page">
    <div id="profileInfo" class="loading">جاري التحميل...</div>
    <h3 style="margin:20px 0 12px">منشوراتي</h3>
    <div id="myPosts"></div>
  </div>

  <!-- الأصدقاء والبحث -->
  <div id="page-friends" class="page">
    <div class="page-pad">
    <h2 style="margin-bottom:12px">الأصدقاء</h2>
    <div id="friendSuggestions" style="margin-bottom:14px"></div>
    <div class="search-bar">
      <input type="text" id="friendSearch" placeholder="ابحث بالاسم أو المعرّف..." onkeydown="if(event.key==='Enter')searchFriends()">
      <button class="btn btn-primary btn-sm" onclick="searchFriends()">بحث</button>
    </div>
    <div id="friendSearchResults"></div>
    <h3 style="margin:16px 0 8px">طلبات واردة</h3>
    <div id="incomingRequests"><div class="empty">لا طلبات</div></div>
    <h3 style="margin:16px 0 8px">أصدقائي</h3>
    <div id="friendsList"><div class="loading">جاري التحميل...</div></div>
  </div>

  <!-- الرسائل الخاصة -->
  <div id="page-messages" class="page">
    <div id="convListView">
      <div style="padding:16px 16px 8px">
        <h2 style="margin-bottom:12px">الرسائل</h2>
        <div class="search-bar" style="margin:0 0 12px">
          <input type="text" id="msgSearch" placeholder="ابحث عن شخص لبدء محادثة..." onkeydown="if(event.key==='Enter')searchMsgUsers()">
          <button class="btn btn-primary btn-sm" onclick="searchMsgUsers()">بحث</button>
        </div>
        <div id="msgSearchResults"></div>
      </div>
      <div class="section-title">محادثاتك</div>
      <div id="conversationsList"><div class="loading">جاري التحميل...</div></div>
    </div>
    <div id="dmView" style="display:none">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
        <button class="btn-ghost btn-sm" onclick="backToConvs()">→</button>
        <div id="dmHeader" style="font-weight:700"></div>
      </div>
      <div class="dm-box">
        <div class="dm-messages" id="dmMessages"></div>
        <div class="chat-input-row" style="align-items:center">
          <input type="text" id="dmInput" placeholder="اكتب رسالة..." maxlength="2000"
                 onkeydown="if(event.key==='Enter')sendDM()">
          <input type="file" id="dmImage" accept="image/*" style="display:none" onchange="sendDMImage()">
          <button class="btn-ghost btn-sm" onclick="$('dmImage').click()" title="صورة"><svg class="act-ico" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="9" cy="10" r="1.5" fill="currentColor"/><path d="M3 16l5-4 4 3 3-2 6 4" fill="none" stroke="currentColor" stroke-width="1.5"/></svg></button>
          <button class="rec-btn" id="dmRecBtn" title="اضغط مطولاً للتسجيل"><svg class="act-ico" viewBox="0 0 24 24"><rect x="9" y="3" width="6" height="11" rx="3" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3" fill="none" stroke="currentColor" stroke-width="1.6"/></svg></button>
          <button class="btn btn-primary btn-sm" onclick="sendDM()">إرسال</button>
        </div>
        <div class="rec-hint" id="dmRecHint">اضغط مطولاً على الميكروفون للتسجيل</div>
      </div>
    </div>
  </div>


  <div id="page-notifications" class="page">
    <div class="page-pad">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <h2>الإشعارات</h2>
        <button class="btn-ghost btn-sm" onclick="markNotifsRead()">تعليم الكل كمقروء</button>
      </div>
      <div id="notifList"><div class="loading">جاري التحميل...</div></div>
    </div>
  </div>

  <!-- دعم المتابعين -->
  <div id="page-support" class="page">
    <div class="page-pad">
      <h2 style="margin-bottom:8px">دعم المتابعين</h2>
      <div id="supportHome">
        <div class="card" style="margin:0 0 12px">
          <div id="supportMyStats" class="loading">جاري التحميل...</div>
        </div>
        <div class="card" style="margin:0 0 12px;font-size:13px;line-height:1.7;color:var(--text2)">
          <strong style="color:var(--text)">كيف يعمل النظام؟</strong>
          <ol style="padding-right:18px;margin-top:8px">
            <li>سجّل رابط حسابك (فيسبوك / إنستغرام / تيك توك / يوتيوب) واحصل على <b>نقطة واحدة</b>.</li>
            <li>تابع ملفات الآخرين من قائمة المهام واحصل على <b>نقطتين</b> لكل متابعة.</li>
            <li>في البداية يظهر ملفك في المهام فور التسجيل. بعد وصول المنصة لـ <b>100 مستخدم</b> يصبح شرط الظهور <b>10 نقاط</b>.</li>
            <li>كل متابعة لملفك تمنحك <b>عملة واحدة</b>. المستويات: برونزي → فضي → ذهبي → بلاتيني → ماسي.</li>
          </ol>
        </div>
        <button class="btn btn-primary" style="width:100%;border-radius:999px;padding:14px;margin-bottom:10px" onclick="supportStartRegister()">تسجيل ملفي / إضافة منصة</button>
        <button class="btn-ghost" style="width:100%;border-radius:999px;padding:12px;margin-bottom:10px" onclick="loadSupportTasks()">عرض مهام المتابعة</button>
        <button class="btn-ghost" style="width:100%;border-radius:999px;padding:12px" onclick="loadSupportLeaders()">لوحة المتصدرين</button>
        <div id="supportTasksBox" style="margin-top:16px"></div>
        <div id="supportLeadersBox" style="margin-top:12px"></div>
      </div>
      <div id="supportRegisterFlow" style="display:none">
        <button class="btn-ghost btn-sm" onclick="supportCancelReg()" style="margin-bottom:12px">→ رجوع</button>
        <div id="supportStepExplain" class="card" style="margin:0 0 12px;font-size:14px;line-height:1.75">
          <strong>قبل المتابعة</strong>
          <p style="margin-top:8px;color:var(--text2)">نظام دعم المتابعين يساعد الأعضاء على تبادل المتابعة بشفافية. بعد تسجيل رابطك الحقيقي، تظهر مهام لمتابعة آخرين. التلاعب أو الروابط الوهمية قد يؤدي لتقييد الحساب. اضغط متابعة إذا وافقت.</p>
          <button class="btn btn-primary" style="width:100%;margin-top:12px;border-radius:999px" onclick="supportShowPlatforms()">متابعة</button>
        </div>
        <div id="supportStepPlatform" style="display:none">
          <p style="margin-bottom:10px;font-weight:600">اختر المنصة</p>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px" id="supportPlatformGrid">
            <button type="button" class="btn-ghost support-plat" data-p="facebook" onclick="supportPickPlatform('facebook')">فيسبوك</button>
            <button type="button" class="btn-ghost support-plat" data-p="instagram" onclick="supportPickPlatform('instagram')">إنستغرام</button>
            <button type="button" class="btn-ghost support-plat" data-p="tiktok" onclick="supportPickPlatform('tiktok')">تيك توك</button>
            <button type="button" class="btn-ghost support-plat" data-p="youtube" onclick="supportPickPlatform('youtube')">يوتيوب</button>
          </div>
        </div>
        <div id="supportStepUrl" style="display:none;margin-top:14px">
          <div class="form-group">
            <label>رابط ملفك على <span id="supportPlatName"></span></label>
            <input type="url" id="supportUrl" placeholder="https://..." dir="ltr">
          </div>
          <button class="btn btn-primary" style="width:100%;border-radius:999px;padding:14px" onclick="supportSubmitRegister()">تسجيل الملف</button>
        </div>
        <div id="supportStepDone" style="display:none" class="card">
          <h3 style="color:var(--green)">تم التسجيل</h3>
          <p id="supportDoneMsg" style="margin-top:8px"></p>
          <button class="btn btn-primary" style="width:100%;margin-top:12px;border-radius:999px" onclick="supportCancelReg()">العودة للدعم</button>
        </div>
      </div>
    </div>
  </div>

  <!-- الإعدادات -->
  <div id="page-settings" class="page">
    <div class="page-pad">
      <h2 style="margin-bottom:16px">الإعدادات</h2>
      <ul class="settings-list" style="margin:0">
        <li><span>دعم المتابعين</span>
          <button class="btn-primary btn-sm" onclick="showPage('support')">فتح</button>
        </li>
        <li><span>المظهر</span>
          <button class="btn-ghost btn-sm" onclick="toggleTheme()">ليلي / نهاري</button>
        </li>
        <li><span>كلمة المرور</span>
          <button class="btn-ghost btn-sm" onclick="openPasswordModal()">تعيين / تغيير</button>
        </li>
        <li><span>نسيت كلمة المرور</span>
          <button class="btn-ghost btn-sm" onclick="openForgotPassword()">إعادة تعيين</button>
        </li>
        <li><span>بلاغاتي</span>
          <a href="#" onclick="showMyReports();return false">عرض</a>
        </li>
        <li><span>سياسة الخصوصية والشروط</span><a href="#" onclick="showPrivacy();return false">عرض</a></li>
        <li><span>عن التطبيق</span><span style="color:var(--text2);font-size:13px">تعارف جزائري</span></li>
        <li id="adminLink" style="display:none"><span>لوحة المطوّر</span><a href="#" onclick="showPage('admin');return false">فتح</a></li>
        <li><button class="btn-danger btn-sm" onclick="deleteMyAccount()">حذف حسابي نهائيًا</button></li>
        <li><button class="btn-danger btn-sm" onclick="doLogout()">تسجيل الخروج</button></li>
      </ul>
      <div id="myReportsBox" style="display:none;margin-top:16px"></div>
    </div>
  </div>

  <!-- الإدارة -->
  <div id="page-admin" class="page">
    <div class="page-pad">
      <h2 style="margin-bottom:8px">لوحة المطوّر</h2>
      <p style="color:var(--text2);font-size:12px;margin-bottom:12px">إحصاءات · مستخدمون · بلاغات · إدارة كاملة</p>
      <div id="adminAlerts" style="display:none;margin-bottom:12px"></div>
      <div id="adminStats" class="card" style="margin:0 0 16px"></div>
      <h3 style="margin:16px 0 10px">المستخدمون</h3>
      <div class="search-bar" style="margin:0 0 10px">
        <input type="text" id="adminUserSearch" placeholder="بحث بالاسم أو الرقم..." onkeydown="if(event.key==='Enter')loadAdminUsers()">
        <button class="btn btn-primary btn-sm" onclick="loadAdminUsers()">بحث</button>
      </div>
      <div id="adminUsers"><div class="loading">جاري التحميل...</div></div>
      <h3 style="margin:20px 0 10px">البلاغات والإشعارات</h3>
      <div id="adminReports" class="loading">جاري التحميل...</div>
    </div>
  </div>

  <!-- الدخول / التسجيل -->
  <div id="page-auth" class="page">
    <div style="max-width:360px;margin:40px auto">
      <h2 style="text-align:center;margin-bottom:8px" id="authTitle">تسجيل الدخول</h2>
      <p style="text-align:center;color:var(--text2);font-size:13px;margin-bottom:20px">
        أدخل رقم هاتفك الجزائري للمتابعة. حساب المطوّر يتطلب كلمة مرور.
      </p>
      <div class="form-group">
        <label>رقم الهاتف (جزائري)</label>
        <input type="tel" id="authPhone" placeholder="05XXXXXXXX" dir="ltr" oninput="onAuthPhoneInput()">
      </div>
      <div class="form-group" id="authPasswordGroup" style="display:none">
        <label id="authPasswordLabel">كلمة مرور المطوّر</label>
        <input type="password" id="authPassword" placeholder="كلمة المرور" dir="ltr" autocomplete="current-password">
        <p id="authPasswordHint" style="font-size:12px;color:var(--text2);margin-top:6px;display:none">أول مرة: أنشئ كلمة مرور (6 أحرف على الأقل)</p>
      </div>
      <div class="form-group" id="authNameGroup" style="display:none">
        <label>الاسم (اختياري)</label>
        <input type="text" id="authName" placeholder="اسمك">
      </div>
      <div class="form-group" id="authPrivacyGroup" style="display:none">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
          <input type="checkbox" id="authPrivacy" style="width:auto">
          أوافق على <a href="#" onclick="showPrivacy();return false">سياسة الخصوصية</a>
        </label>
      </div>
      <button class="btn btn-primary" style="width:100%;margin-bottom:12px" id="authSubmit" onclick="doAuth()">متابعة</button>
      <p style="text-align:center;font-size:14px">
        <a href="#" id="authToggle" onclick="toggleAuthMode();return false">ليس لديك حساب؟ سجّل الآن</a>
      </p>
      <div id="authError" class="error-box" style="display:none"></div>
    </div>
  </div>

  <!-- الخصوصية -->
  <div id="page-privacy" class="page">
    <div class="page-pad">
      <button class="btn-ghost btn-sm" onclick="showPage('settings')" style="margin-bottom:12px">→ رجوع</button>
      <h2 style="margin-bottom:8px">سياسة الخصوصية وشروط الاستخدام</h2>
      <p style="color:var(--text2);font-size:12px;margin-bottom:16px">آخر تحديث: أكتوبر 2026 — DZ Connect</p>
      <div class="card" style="margin:0 0 16px;font-size:14px;line-height:1.85">
        <h3 style="margin-bottom:8px">1. مقدمة</h3>
        <p>مرحبًا بك في منصة DZ Connect. باستخدامك للتطبيق فإنك توافق على هذه السياسة وشروط الاستخدام. إذا لم توافق، يُرجى عدم استخدام الخدمة.</p>
        <h3 style="margin:16px 0 8px">2. البيانات التي نجمعها</h3>
        <p>رقم الهاتف، الاسم، صور الملف والغلاف، السيرة والبيانات الاختيارية (الجنس، العمر، مكان المنشأ)، المنشورات والتعليقات والرسائل والتفاعلات، البلاغات، وبيانات تقنية أساسية لتحسين الخدمة.</p>
        <h3 style="margin:16px 0 8px">3. أغراض المعالجة</h3>
        <p>تشغيل الحساب، عرض المحتوى، منع الإساءة، مراجعة البلاغات، تحسين الأمان والأداء، والامتثال للقانون عند الاقتضاء.</p>
        <h3 style="margin:16px 0 8px">4. مشاركة البيانات</h3>
        <p>لا نبيع بياناتك. المعلومات العامة (الاسم والصورة والمنشورات) تظهر للمستخدمين. أرقام الهواتف لا تُعرض للعامة. قد يطّلع المشرفون على ما يلزم لمراجعة البلاغات.</p>
        <h3 style="margin:16px 0 8px">5. الرسائل والمحتوى</h3>
        <p>الرسائل الخاصة والعامة قد تُحذف تلقائيًا بعد 24 ساعة. أنت مسؤول عن محتواك. يُحظر الاحتيال والإساءة والروابط الضارة.</p>
        <h3 style="margin:16px 0 8px">6. الأمان</h3>
        <p>نطبّق إجراءات معقولة. عيّن كلمة مرور قوية ولا تشارك بيانات دخولك.</p>
        <h3 style="margin:16px 0 8px">7. حقوقك</h3>
        <p>تعديل الملف، كلمة المرور، بلاغاتك، وحذف حسابك من الإعدادات.</p>
        <h3 style="margin:16px 0 8px">8. الإشراف</h3>
        <p>المطوّر مخوّل بمراجعة البلاغات وتقييد الحسابات وحذف المحتوى المخالف لحماية المجتمع.</p>
        <h3 style="margin:16px 0 8px">9. إخلاء المسؤولية</h3>
        <p>محتوى المستخدمين يعبّر عنهم. العروض والروابط الخارجية غير مضمونة من المنصة. تحقق بنفسك قبل أي إجراء.</p>
        <h3 style="margin:16px 0 8px">10. التعديلات والقانون</h3>
        <p>قد نحدّث السياسة. استمرار الاستخدام يعني القبول. تخضع العلاقة لقوانين الجزائر.</p>
        <h3 style="margin:16px 0 8px">11. التواصل</h3>
        <p>استخدم أدوات البلاغ داخل المنصة أو تواصل مع الإدارة عبر القنوات الرسمية داخل التطبيق.</p>
      </div>
    </div>
  </div>

</main>

<!-- شريط التنقل -->
<nav class="bottom-nav" id="bottomNav" style="display:none">
  <button class="nav-item active" data-page="home" onclick="showPage('home')">
    <svg class="nav-icon-svg" viewBox="0 0 24 24"><path d="M3 10.5L12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1v-9.5z"/></svg>
    <span>الرئيسية</span>
  </button>
  <button class="nav-item" data-page="friends" onclick="showPage('friends')">
    <svg class="nav-icon-svg" viewBox="0 0 24 24"><path d="M16 11a4 4 0 1 0-4-4 4 4 0 0 0 4 4zM8 13a4 4 0 1 0-4-4 4 4 0 0 0 4 4z"/><path d="M8 14c-3.3 0-6 1.8-6 4v1h8"/><path d="M16 13c-2.7 0-5 1.3-5.8 3"/></svg>
    <span>أصدقاء</span>
  </button>
  <button class="nav-item create" data-page="create" onclick="showPage('create')">
    <svg class="nav-icon-svg" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>
  </button>
  <button class="nav-item" data-page="messages" onclick="showPage('messages')">
    <svg class="nav-icon-svg" viewBox="0 0 24 24"><path d="M4 6h16v12H4z"/><path d="M4 7l8 6 8-6"/></svg>
    <span>رسائل</span>
    <span class="nav-badge" id="msgBadge" style="display:none">0</span>
  </button>
  <button class="nav-item" data-page="chat" onclick="showPage('chat')">
    <svg class="nav-icon-svg" viewBox="0 0 24 24"><path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5z"/></svg>
    <span>عامة</span>
  </button>
  <button class="nav-item" data-page="profile" onclick="showPage('profile')">
    <svg class="nav-icon-svg" viewBox="0 0 24 24"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>
    <span>حسابي</span>
  </button>
</nav>

<!-- اكتشاف عشوائي -->
<div id="discoverModal" class="modal-overlay" style="display:none" onclick="if(event.target===this)closeDiscover()">
  <div class="modal" style="border:1px solid rgba(225,29,72,.3)">
    <button class="modal-close" onclick="closeDiscover()">×</button>
    <h3 style="color:var(--love2)">شخص قد يعجبك</h3>
    <div id="discoverBody"><div class="loading">جاري البحث...</div></div>
  </div>
</div>

<!-- مودال البلاغ -->
<div id="reportModal" class="modal-overlay" style="display:none" onclick="if(event.target===this)closeReport()">
  <div class="modal">
    <button class="modal-close" onclick="closeReport()">×</button>
    <h3>الإبلاغ عن محتوى</h3>
    <div class="form-group">
      <label>السبب</label>
      <select id="reportReason"></select>
    </div>
    <div class="form-group">
      <label>تفاصيل إضافية (اختياري)</label>
      <textarea id="reportDetails"></textarea>
    </div>
    <button class="btn btn-danger" style="width:100%" onclick="submitReport()">إرسال البلاغ</button>
  </div>
</div>

<script>
// ====================== الحالة العامة ======================
const state = {
  user: null,
  page: 1,
  category: null,
  loading: false,
  hasMore: true,
  authMode: 'login',
  reportPostId: null,
  chatPoll: null,
  dmOtherId: null,
  dmPoll: null,
  mediaRecorder: null,
  audioChunks: [],
  recordingFor: null, // 'post' | 'dm'
  config: { categories: [], bot_statuses: [], report_reasons: [] },
};

// ====================== أدوات ======================
function $(id) { return document.getElementById(id); }
function toast(msg, ms=3000) {
  const t = document.createElement('div');
  t.className = 'toast';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), ms);
}
function avatarHtml(user) {
  if (user && user.avatar_url) {
    return `<div class="avatar"><img src="${esc(user.avatar_url)}" alt=""></div>`;
  }
  const letter = (user && user.name) ? user.name[0] : '?';
  return `<div class="avatar">${esc(letter)}</div>`;
}
function esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function linkify(text) {
  const e = esc(text);
  return e.replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>')
          .replace(/(^|\s)(www\.[^\s<]+)/g, '$1<a href="https://$2" target="_blank" rel="noopener noreferrer">$2</a>');
}
function timeAgo(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const sec = Math.floor((Date.now() - d.getTime()) / 1000);
  if (sec < 60) return 'الآن';
  if (sec < 3600) return Math.floor(sec/60) + ' د';
  if (sec < 86400) return Math.floor(sec/3600) + ' س';
  return Math.floor(sec/86400) + ' ي';
}

async function api(path, opts={}) {
  const res = await fetch(path, {
    credentials: 'same-origin',
    headers: opts.body && !(opts.body instanceof FormData)
      ? { 'Content-Type': 'application/json', ...opts.headers }
      : opts.headers,
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.detail || data.message || 'خطأ في الطلب');
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

// ====================== التهيئة ======================
async function init() {
  try {
    const st = await api('/api/status');
    state.config = st;
    if (st.error) {
      toast('تحذير: ' + st.error, 6000);
    }
  } catch(e) {}

  // ملء التصنيفات
  const catSel = $('postCategory');
  const filters = $('categoryFilters');
  filters.innerHTML = `<span class="filter-chip active" data-cat="">الكل</span>`;
  (state.config.categories || []).forEach(c => {
    catSel.innerHTML += `<option value="${esc(c)}">${esc(c)}</option>`;
    filters.innerHTML += `<span class="filter-chip" data-cat="${esc(c)}">${esc(c)}</span>`;
  });
  filters.querySelectorAll('.filter-chip').forEach(el => {
    el.onclick = () => {
      filters.querySelectorAll('.filter-chip').forEach(x => x.classList.remove('active'));
      el.classList.add('active');
      state.category = el.dataset.cat || null;
      state.page = 1;
      state.hasMore = true;
      loadPosts(true);
    };
  });
  (state.config.bot_statuses || []).forEach(s => {
    $('botStatus').innerHTML += `<option value="${esc(s)}">${esc(s)}</option>`;
  });
  (state.config.report_reasons || []).forEach(r => {
    $('reportReason').innerHTML += `<option value="${esc(r)}">${esc(r)}</option>`;
  });

  $('postCategory').onchange = () => {
    $('botStatusGroup').style.display =
      $('postCategory').value === 'بوتات الإنترنت' ? 'block' : 'none';
  };

  // معاينة الصورة قبل النشر
  const imgInput = $('postImage');
  if (imgInput) {
    imgInput.onchange = () => {
      const f = imgInput.files[0];
      const prev = $('previewBox');
      if (f && prev) {
        prev.style.display = 'block';
        prev.innerHTML = '<img src="' + URL.createObjectURL(f) + '" style="max-width:100%;border-radius:8px" alt="معاينة">';
      }
    };
  }

  // تحقق الجلسة
  try {
    const me = await api('/api/me');
    if (me.authenticated) {
      state.user = me.user;
      if (localStorage.getItem('dz_welcomed')) {
        enterApp();
      }
    }
  } catch(e) {}
}


function updateHeaderUser() {
  const u = state.user;
  const el = $('headerAvatar');
  const ca = $('composeAvatar');
  if (!u) return;
  if (el) {
    if (u.avatar_url) el.innerHTML = '<img src="'+esc(u.avatar_url)+'" alt="">';
    else el.textContent = (u.name || '?')[0];
  }
  if (ca) {
    if (u.avatar_url) ca.innerHTML = '<img src="'+esc(u.avatar_url)+'" alt="">';
    else ca.textContent = (u.name || '?')[0];
  }
}

function startApp() {
  localStorage.setItem('dz_welcomed', '1');
  $('welcome').style.display = 'none';
  if (state.user) {
    enterApp();
  } else {
    showPage('auth');
    $('mainHeader').style.display = 'block';
  }
}

function enterApp() {
  const w = $('welcome');
  if (w) w.style.display = 'none';
  const auth = $('page-auth');
  if (auth) auth.classList.remove('active');
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  $('mainHeader').style.display = 'block';
  $('bottomNav').style.display = 'flex';
  document.body.classList.remove('dm-open', 'chat-open');
  const al = $('adminLink');
  if (al) {
    al.style.display = (state.user && state.user.is_developer) ? 'flex' : 'none';
  }
  updateHeaderUser();
  try { pollNotifBadge(); } catch(e) {}
  showPage('home');
  try {
    history.replaceState({ page: 'home' }, '', '#home');
  } catch(e) {}
}

// ====================== التنقل ======================
function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  const el = $('page-' + name);
  if (el) el.classList.add('active');
  else console.warn('page missing', name);

  document.querySelectorAll('.nav-item').forEach(n => {
    n.classList.toggle('active', n.dataset.page === name);
  });

  try {
    if (location.hash !== '#' + name) {
      history.pushState({ page: name }, '', '#' + name);
    }
  } catch(e) {}

  if (name === 'home') { state.page = 1; state.hasMore = true; loadPosts(true); }
  if (name === 'chat') {
    document.body.classList.add('chat-open');
    loadChat(); startChatPoll();
  } else {
    document.body.classList.remove('chat-open');
    stopChatPoll();
  }

  if (name === 'profile') loadProfile();
  if (name === 'admin') {
    if (!state.user || !state.user.is_developer) {
      toast('لوحة المطوّر خاصة بحساب المطوّر فقط');
      showPage('home');
      return;
    }
    loadAdmin();
  }
  if (name === 'friends') { loadFriends(); loadFriendRequests(); loadFriendSuggestions(); }
  if (name === 'support') { loadSupportStatus(); supportCancelReg(); }
  if (name !== 'messages') {
    document.body.classList.remove('dm-open');
    if ($('bottomNav') && state.user) $('bottomNav').style.display = 'flex';
  }
  if (name === 'messages') { showConvList(); loadConversations(); }
  if (name === 'auth') { /* ok */ }
  if (name === 'create' && !state.user) { showPage('auth'); toast('سجّل الدخول أولًا'); }
  if (name === 'create' && state.user) { setTimeout(() => setupRecButton('postRecBtn', 'post'), 100); }
}

function showPrivacy() { showPage('privacy'); }

// ====================== المصادقة ======================
function toggleAuthMode() {
  state.authMode = state.authMode === 'login' ? 'register' : 'login';
  const isReg = state.authMode === 'register';
  $('authTitle').textContent = isReg ? 'إنشاء حساب' : 'تسجيل الدخول';
  $('authNameGroup').style.display = isReg ? 'block' : 'none';
  $('authPrivacyGroup').style.display = isReg ? 'block' : 'none';
  $('authToggle').textContent = isReg ? 'لديك حساب؟ ادخل' : 'ليس لديك حساب؟ سجّل الآن';
  $('authError').style.display = 'none';
}

const DEV_PHONE_UI = '0553933833';

function normalizePhoneUI(p) {
  p = (p || '').replace(/[\s\-\(\)\.]/g, '');
  if (p.startsWith('+213')) p = '0' + p.slice(4);
  else if (p.startsWith('213') && p.length >= 12) p = '0' + p.slice(3);
  return p;
}

function onAuthPhoneInput() {
  const p = normalizePhoneUI($('authPhone').value);
  const isDev = p === DEV_PHONE_UI;
  const grp = $('authPasswordGroup');
  if (!grp) return;
  grp.style.display = 'block';
  const lab = $('authPasswordLabel');
  const hint = $('authPasswordHint');
  if (isDev) {
    if (lab) lab.textContent = 'كلمة مرور المطوّر (إلزامية)';
    if (hint) {
      hint.style.display = 'block';
      hint.textContent = 'أول مرة: أنشئ كلمة مرور (6 أحرف فأكثر). بعدها أدخلها للدخول.';
    }
  } else {
    if (lab) lab.textContent = 'كلمة المرور (مستحسنة)';
    if (hint) {
      hint.style.display = 'block';
      hint.textContent = 'عند التسجيل: اختياري. إن وُجدت كلمة مرور على الحساب فهي مطلوبة عند الدخول.';
    }
  }
}

async function doAuth() {
  const phone = $('authPhone').value.trim();
  const btn = $('authSubmit');
  btn.disabled = true;
  $('authError').style.display = 'none';
  const isDev = normalizePhoneUI(phone) === DEV_PHONE_UI;
  const password = ($('authPassword') && $('authPassword').value) || '';
  try {
    let data;
    if (state.authMode === 'register') {
      if (isDev) {
        throw new Error('حساب المطوّر: استخدم تسجيل الدخول مع كلمة المرور');
      }
      data = await api('/api/register', {
        method: 'POST',
        body: JSON.stringify({
          phone,
          name: $('authName').value.trim() || null,
          accept_privacy: $('authPrivacy').checked,
        }),
      });
    } else {
      if (isDev) {
        onAuthPhoneInput();
        if (!password) throw new Error('أدخل كلمة مرور المطوّر');
      }
      data = await api('/api/login', {
        method: 'POST',
        body: JSON.stringify({ phone, password: password || null }),
      });
      if (data.needs_password_setup) {
        onAuthPhoneInput();
        const hint = $('authPasswordHint');
        if (hint) {
          hint.style.display = 'block';
          hint.textContent = data.message || 'أنشئ كلمة مرور (6 أحرف على الأقل)';
        }
        throw new Error(data.message || 'أنشئ كلمة مرور للمطوّر ثم اضغط متابعة');
      }
      if (data.ok === false) {
        throw new Error(data.message || 'فشل الدخول');
      }
    }
    if (!data.user) throw new Error(data.message || 'فشل العملية');
    state.user = data.user;
    updateHeaderUser();
    /* لا نعرض رسائل تحذير النسخة التجريبية */
    if (data.user.is_developer) toast('مرحبًا أيها المطوّر', 2500);
    enterApp();
  } catch(e) {
    $('authError').style.display = 'block';
    $('authError').textContent = e.message || 'فشل العملية';
  } finally {
    btn.disabled = false;
  }
}

async function searchMsgUsers() {
  if (!state.user) { showPage('auth'); return; }
  const q = ($('msgSearch') && $('msgSearch').value.trim()) || '';
  if (!q) { toast('اكتب اسمًا أو معرّفًا'); return; }
  const box = $('msgSearchResults');
  if (!box) return;
  box.innerHTML = '<div class="loading">جاري البحث...</div>';
  try {
    const data = await api('/api/users/search?q=' + encodeURIComponent(q));
    box.innerHTML = '';
    if (!data.users || !data.users.length) {
      box.innerHTML = '<div class="empty-state" style="padding:12px"><p>لا نتائج</p></div>';
      return;
    }
    data.users.forEach(u => {
      const div = document.createElement('div');
      div.className = 'user-row';
      div.innerHTML = `
        ${avatarHtml(u)}
        <div class="info">
          <div class="name">${esc(u.name || 'مستخدم')}</div>
          <div class="sub">${esc(u.public_id || '')}</div>
        </div>
        <button class="btn btn-primary btn-sm" onclick="openDM('${u.id}','${esc(u.name||'مستخدم')}')">رسالة</button>
      `;
      box.appendChild(div);
    });
  } catch(e) {
    box.innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
  }
}


function toggleTheme() {
  document.body.classList.toggle('theme-light');
  const on = document.body.classList.contains('theme-light');
  try { localStorage.setItem('dz_theme', on ? 'light' : 'dark'); } catch(e) {}
  toast(on ? 'الوضع النهاري' : 'الوضع الليلي');
}

function openPasswordModal() {
  if (!state.user) { showPage('auth'); return; }
  const has = state.user.has_password;
  const oldP = has ? prompt('كلمة المرور الحالية:') : null;
  if (has && (oldP === null)) return;
  const np = prompt('كلمة المرور الجديدة (6 أحرف فأكثر):');
  if (!np) return;
  if (np.length < 6) { toast('كلمة المرور قصيرة'); return; }
  api('/api/password/set', {
    method: 'POST',
    body: JSON.stringify({ password: np, old_password: oldP || null }),
  }).then(() => {
    if (state.user) state.user.has_password = true;
    toast('تم حفظ كلمة المرور');
  }).catch(e => toast(e.message));
}

function openForgotPassword() {
  const phone = prompt('رقم الهاتف المسجّل:');
  if (!phone) return;
  const np = prompt('كلمة المرور الجديدة (6 أحرف فأكثر):');
  if (!np || np.length < 6) { toast('كلمة مرور غير صالحة'); return; }
  api('/api/password/forgot', {
    method: 'POST',
    body: JSON.stringify({ phone, new_password: np }),
  }).then(() => toast('تم التعيين — سجّل الدخول بالكلمة الجديدة'))
    .catch(e => toast(e.message));
}

async function showMyReports() {
  if (!state.user) { showPage('auth'); return; }
  const box = $('myReportsBox');
  if (!box) { toast('تعذر العرض'); return; }
  box.style.display = 'block';
  box.innerHTML = '<div class="loading">جاري التحميل...</div>';
  try {
    const data = await api('/api/my-reports');
    if (!data.reports || !data.reports.length) {
      box.innerHTML = '<div class="empty-state" style="padding:16px"><p>لا بلاغات أرسلتها</p></div>';
      return;
    }
    box.innerHTML = '<h3 style="margin-bottom:8px">بلاغاتي</h3>';
    data.reports.forEach(r => {
      const div = document.createElement('div');
      div.className = 'card';
      div.style.margin = '0 0 8px';
      div.innerHTML = `<div style="font-size:12px;color:var(--text2)">${timeAgo(r.created_at)} · ${esc(r.status)}</div>
        <strong>${esc(r.reason)}</strong>
        <div style="font-size:13px">${esc(r.details||'')}</div>`;
      box.appendChild(div);
    });
  } catch(e) {
    box.innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
  }
}

async function deleteMyAccount() {
  if (!state.user) return;
  if (!confirm('حذف حسابك نهائيًا؟ لا يمكن التراجع.')) return;
  if (!confirm('تأكيد أخير: سيتم حذف منشوراتك وبياناتك.')) return;
  try {
    await api('/api/account', { method: 'DELETE' });
    state.user = null;
    toast('تم حذف الحساب');
    $('bottomNav').style.display = 'none';
    $('mainHeader').style.display = 'none';
    showPage('auth');
  } catch(e) { toast(e.message); }
}

async function uploadAvatar(input) {
  const f = input.files && input.files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append('avatar', f);
  try {
    await api('/api/profile/avatar', { method: 'POST', body: fd });
    toast('تم تحديث الصورة');
    loadProfile();
  } catch(e) { toast(e.message); }
  input.value = '';
}

async function uploadCover(input) {
  const f = input.files && input.files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append('cover', f);
  try {
    await api('/api/profile/cover', { method: 'POST', body: fd });
    toast('تم تحديث الغلاف');
    loadProfile();
  } catch(e) { toast(e.message); }
  input.value = '';
}

async function doLogout() {
  if (!confirm('هل تريد تسجيل الخروج؟')) return;
  try { await api('/api/logout', { method: 'POST' }); } catch(e) {}
  state.user = null;
  $('bottomNav').style.display = 'none';
  showPage('auth');
  toast('تم تسجيل الخروج');
}

// ====================== المنشورات ======================
async function loadPosts(reset=false) {
  if (state.loading) return;
  state.loading = true;
  const list = $('postsList');
  if (reset) list.innerHTML = '<div class="loading">جاري التحميل...</div>';
  try {
    let url = `/api/posts?page=${state.page}&limit=12`;
    if (state.category) url += `&category=${encodeURIComponent(state.category)}`;
    const data = await api(url);
    const posts = data.posts || [];
    if (reset) list.innerHTML = '';
    if (posts.length === 0 && state.page === 1) {
      list.innerHTML = `<div class="empty-state">
      <div class="empty-icon"><svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/></svg><span class="plus-badge">+</span></div>
      <h3>لا توجد منشورات بعد</h3>
      <p>كن أول من يشارك شيئًا مع مجتمع DZ Connect وابدأ في التواصل مع الآخرين.</p>
      <button class="btn btn-primary" style="border-radius:999px;padding:12px 28px" onclick="showPage('create')">إنشاء منشور</button>
    </div>`;
    } else {
      posts.forEach(p => list.appendChild(renderPost(p)));
    }
    state.hasMore = posts.length >= 12;
    $('loadMoreBtn').style.display = state.hasMore ? 'inline-block' : 'none';
  } catch(e) {
    if (reset) list.innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
  } finally {
    state.loading = false;
  }
}

function loadMorePosts() {
  if (!state.hasMore || state.loading) return;
  state.page++;
  loadPosts(false);
}

function renderPost(p) {
  const div = document.createElement('div');
  div.className = 'card';
  div.dataset.id = p.id;
  const u = p.users || {};
  let media = '';
  (p.post_media || []).forEach(m => {
    if (m.media_type === 'image') media += `<img src="${esc(m.url)}" alt="صورة" loading="lazy">`;
    if (m.media_type === 'audio') media += `<audio controls src="${esc(m.url)}"></audio>`;
  });
  const isOwner = state.user && (state.user.id === p.user_id || state.user.is_admin);
  div.innerHTML = `
    <div class="card-header">
      ${avatarHtml(u)}
      <div class="user-meta">
        <div class="name">${esc(u.name || 'مستخدم')}</div>
        <div class="time">${timeAgo(p.created_at)}${p.updated_at && p.updated_at !== p.created_at ? ' · معدّل' : ''}</div>
      </div>
      <span class="badge">${esc(p.category)}</span>
      ${p.is_verified ? '<span class="badge verified">تم التحقق</span>' : ''}
      ${p.bot_status ? `<span class="badge bot">${esc(p.bot_status)}</span>` : ''}
    </div>
    <div class="card-body linkified">${linkify(p.content || '')}${media}</div>
    <div class="card-actions">
      <button class="action-btn ${p.liked_by_me ? 'liked' : ''}" onclick="toggleLike('${p.id}', this)">
        <svg class="act-ico" viewBox="0 0 24 24"><path d="M12 21s-7-4.4-9.5-8.2C.7 9.8 2.2 6 6 6c2 0 3.4 1.2 4 2.2C10.6 7.2 12 6 14 6c3.8 0 5.3 3.8 3.5 6.8C19 16.6 12 21 12 21z" fill="${p.liked_by_me ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="1.6"/></svg>
        <span>${p.likes_count || 0}</span>
      </button>
      <button class="action-btn" onclick="toggleComments('${p.id}', this)">
        <svg class="act-ico" viewBox="0 0 24 24"><path d="M4 6h16v10H7l-3 3V6z" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>
        <span>${p.comments_count || 0}</span>
      </button>
      <button class="action-btn ${p.saved_by_me ? 'saved' : ''}" onclick="toggleSave('${p.id}', this)">
        <svg class="act-ico" viewBox="0 0 24 24"><path d="M7 3h10v18l-5-3-5 3V3z" fill="${p.saved_by_me ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="1.6"/></svg>
      </button>
      <button class="action-btn" onclick="sharePost('${p.id}')">
        <svg class="act-ico" viewBox="0 0 24 24"><circle cx="6" cy="12" r="2" fill="currentColor"/><circle cx="18" cy="6" r="2" fill="currentColor"/><circle cx="18" cy="18" r="2" fill="currentColor"/><path d="M8 11l8-4M8 13l8 4" fill="none" stroke="currentColor" stroke-width="1.4"/></svg>
      </button>
      <button class="action-btn" onclick="openReport('${p.id}')">
        <svg class="act-ico" viewBox="0 0 24 24"><path d="M5 3v18M5 4h10l-2 3 2 3H5" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>
      </button>
      ${isOwner ? `<button class="action-btn" onclick="deletePost('${p.id}')"><svg class="act-ico" viewBox="0 0 24 24"><path d="M4 7h16M9 7V5h6v2M8 7v12h8V7" fill="none" stroke="currentColor" stroke-width="1.6"/></svg></button>` : ''}
    </div>
    <div class="comments-box" id="comments-${p.id}" style="display:none;margin-top:10px"></div>
  `;
  return div;
}

async function toggleLike(postId, btn) {
  if (!state.user) { showPage('auth'); return; }
  try {
    const data = await api(`/api/posts/${postId}/like`, { method: 'POST' });
    const span = btn.querySelector('span');
    let n = parseInt(span.textContent) || 0;
    if (data.liked) {
      btn.classList.add('liked');
      btn.innerHTML = `<svg class="act-ico" viewBox="0 0 24 24"><path d="M12 21s-7-4.4-9.5-8.2C.7 9.8 2.2 6 6 6c2 0 3.4 1.2 4 2.2C10.6 7.2 12 6 14 6c3.8 0 5.3 3.8 3.5 6.8C19 16.6 12 21 12 21z" fill="currentColor" stroke="currentColor" stroke-width="1.6"/></svg><span>${n+1}</span>`;
    } else {
      btn.classList.remove('liked');
      btn.innerHTML = `<svg class="act-ico" viewBox="0 0 24 24"><path d="M12 21s-7-4.4-9.5-8.2C.7 9.8 2.2 6 6 6c2 0 3.4 1.2 4 2.2C10.6 7.2 12 6 14 6c3.8 0 5.3 3.8 3.5 6.8C19 16.6 12 21 12 21z" fill="none" stroke="currentColor" stroke-width="1.6"/></svg><span>${Math.max(0,n-1)}</span>`;
    }
  } catch(e) { toast(e.message); }
}

async function toggleSave(postId, btn) {
  if (!state.user) { showPage('auth'); return; }
  try {
    const data = await api(`/api/posts/${postId}/save`, { method: 'POST' });
    btn.classList.toggle('saved', data.saved);
    btn.innerHTML = data.saved
      ? '<svg class="act-ico" viewBox="0 0 24 24"><path d="M7 3h10v18l-5-3-5 3V3z" fill="currentColor" stroke="currentColor" stroke-width="1.6"/></svg>'
      : '<svg class="act-ico" viewBox="0 0 24 24"><path d="M7 3h10v18l-5-3-5 3V3z" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>';
    toast(data.saved ? 'تم الحفظ' : 'أُزيل من المحفوظات');
  } catch(e) { toast(e.message); }
}

async function toggleComments(postId, btn) {
  const box = $('comments-' + postId);
  if (box.style.display === 'block') { box.style.display = 'none'; return; }
  box.style.display = 'block';
  box.innerHTML = '<div class="loading">جاري التحميل...</div>';
  try {
    const data = await api(`/api/posts/${postId}/comments`);
    let html = '';
    (data.comments || []).forEach(c => {
      const cu = c.users || {};
      const canEdit = state.user && (state.user.id === c.user_id || state.user.is_admin);
      html += `<div style="padding:8px 0;border-bottom:1px solid var(--border);font-size:14px">
        <strong>${esc(cu.name || 'مستخدم')}</strong>
        <span style="color:var(--text2);font-size:12px"> · ${timeAgo(c.created_at)}</span>
        <div class="linkified">${linkify(c.content)}</div>
        ${canEdit ? `<button class="btn-sm btn-ghost" onclick="deleteComment('${c.id}','${postId}')">حذف</button>` : ''}
      </div>`;
    });
    html += `<div style="display:flex;gap:8px;margin-top:10px">
      <input type="text" id="cmt-input-${postId}" placeholder="اكتب تعليقًا..." maxlength="2000" style="flex:1">
      <button class="btn btn-primary btn-sm" onclick="addComment('${postId}')">إرسال</button>
    </div>`;
    box.innerHTML = html || '<div class="empty">لا تعليقات بعد</div>' + html;
  } catch(e) { box.innerHTML = `<div class="error-box">${esc(e.message)}</div>`; }
}

async function addComment(postId) {
  if (!state.user) { showPage('auth'); return; }
  const input = $('cmt-input-' + postId);
  const content = input.value.trim();
  if (!content) return;
  try {
    await api(`/api/posts/${postId}/comments`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    });
    input.value = '';
    toggleComments(postId); // إعادة تحميل
    toast('تم إضافة التعليق');
  } catch(e) { toast(e.message); }
}

async function deleteComment(cid, postId) {
  if (!confirm('حذف التعليق؟')) return;
  try {
    await api(`/api/comments/${cid}`, { method: 'DELETE' });
    toggleComments(postId);
  } catch(e) { toast(e.message); }
}

async function deletePost(postId) {
  if (!confirm('هل تريد حذف هذا المنشور نهائيًا؟')) return;
  try {
    await api(`/api/posts/${postId}`, { method: 'DELETE' });
    toast('تم الحذف');
    loadPosts(true);
  } catch(e) { toast(e.message); }
}

function sharePost(postId) {
  const url = location.origin + '/?post=' + postId;
  if (navigator.share) {
    navigator.share({ title: 'DZ Connect', url }).catch(() => {});
  } else {
    navigator.clipboard.writeText(url).then(() => toast('تم نسخ الرابط')).catch(() => prompt('انسخ الرابط:', url));
  }
}

// ====================== نشر منشور ======================
async function publishPost() {
  if (!state.user) { showPage('auth'); return; }
  const btn = $('publishBtn');
  btn.disabled = true;
  btn.textContent = 'جاري النشر...';
  const fd = new FormData();
  const content = $('postContent').value.trim();
  if (content) fd.append('content', content);
  fd.append('category', $('postCategory').value);
  if ($('postCategory').value === 'بوتات الإنترنت') {
    fd.append('bot_status', $('botStatus').value);
  }
  const img = $('postImage').files[0];
  const aud = $('postAudio').files[0];
  if (img) fd.append('image', img);
  if (aud) fd.append('audio', aud);
  try {
    await api('/api/posts', { method: 'POST', body: fd });
    toast('تم النشر بنجاح');
    $('postContent').value = '';
    $('postImage').value = '';
    $('postAudio').value = '';
    showPage('home');
  } catch(e) {
    toast(e.message || 'فشل النشر');
  } finally {
    btn.disabled = false;
    btn.textContent = 'نشر';
  }
}

// ====================== البلاغ ======================
function openReport(postId) {
  if (!state.user) { showPage('auth'); return; }
  state.reportPostId = postId;
  $('reportModal').style.display = 'flex';
}
function closeReport() { $('reportModal').style.display = 'none'; }
async function submitReport() {
  try {
    await api(`/api/posts/${state.reportPostId}/report`, {
      method: 'POST',
      body: JSON.stringify({
        reason: $('reportReason').value,
        details: $('reportDetails').value.trim() || null,
      }),
    });
    closeReport();
    toast('تم إرسال البلاغ');
  } catch(e) { toast(e.message); }
}

// ====================== الدردشة ======================
async function loadChat() {
  if (!state.user) { showPage('auth'); return; }
  const box = $('chatMessages');
  try {
    const data = await api('/api/chat?limit=50');
    box.innerHTML = '';
    (data.messages || []).forEach(m => {
      const u = m.users || {};
      const div = document.createElement('div');
      div.className = 'chat-msg';
      div.innerHTML = `<div class="meta">${esc(u.name || 'مستخدم')} · ${timeAgo(m.created_at)}</div>
        <div class="linkified">${linkify(m.content)}</div>`;
      box.appendChild(div);
    });
    box.scrollTop = box.scrollHeight;
  } catch(e) {
    box.innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
  }
}

async function sendChat() {
  if (!state.user) return;
  const input = $('chatInput');
  const content = input.value.trim();
  if (!content) return;
  input.value = '';
  try {
    await api('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ content }),
    });
    loadChat();
  } catch(e) { toast(e.message); input.value = content; }
}

function startChatPoll() {
  stopChatPoll();
  state.chatPoll = setInterval(() => {
    if ($('page-chat').classList.contains('active')) loadChat();
  }, 8000);
}
function stopChatPoll() {
  if (state.chatPoll) { clearInterval(state.chatPoll); state.chatPoll = null; }
}

// ====================== الملف الشخصي ======================
async function loadProfile() {
  if (!state.user) { showPage('auth'); return; }
  const info = $('profileInfo');
  try {
    const me = await api('/api/me');
    const u = me.user;
    state.user = u;
    updateHeaderUser();
    const cover = u.cover_url
      ? `<div style="height:120px;border-radius:12px 12px 0 0;background:url('${esc(u.cover_url)}') center/cover;margin:-14px -14px 12px"></div>`
      : `<div style="height:80px;border-radius:12px 12px 0 0;background:linear-gradient(135deg,#1e3a5f,#2563eb);margin:-14px -14px 12px"></div>`;
    info.innerHTML = `
      <div class="card" style="text-align:center;overflow:hidden;padding-top:14px">
        ${cover}
        <div style="margin-top:-40px;display:inline-block;position:relative">
          ${avatarHtml(u)}
        </div>
        <h3 style="margin:10px 0 4px">${esc(u.name || 'مستخدم')}</h3>
        <div style="color:var(--text2);font-size:13px">${esc(u.public_id)}</div>
        <div style="color:var(--text2);font-size:13px;margin-top:4px">انضم ${timeAgo(u.created_at)} · ${u.posts_count || 0} منشور</div>
        ${u.bio ? `<p style="margin-top:8px;font-size:13px">${esc(u.bio)}</p>` : ''}
        <div style="font-size:12px;color:var(--text2);margin-top:6px">
          ${u.gender ? esc(u.gender)+' · ' : ''}${u.age ? esc(String(u.age))+' سنة · ' : ''}${u.origin ? esc(u.origin) : ''}
        </div>
        <div style="margin-top:8px">${(u.interests||'').split(',').filter(Boolean).map(x=>'<span class="interest-tag">'+esc(x.trim())+'</span>').join('')}</div>
        <div style="display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin-top:14px">
          <button class="btn-ghost btn-sm" onclick="editProfile()">تعديل الملف</button>
          <label class="btn-ghost btn-sm" style="cursor:pointer;margin:0">
            صورة شخصية
            <input type="file" accept="image/*" style="display:none" onchange="uploadAvatar(this)">
          </label>
          <label class="btn-ghost btn-sm" style="cursor:pointer;margin:0">
            صورة غلاف
            <input type="file" accept="image/*" style="display:none" onchange="uploadCover(this)">
          </label>
        </div>
      </div>
    `;
    const data = await api(`/api/posts?user_id=${u.id}&limit=20`);
    const box = $('myPosts');
    box.innerHTML = '';
    if (!data.posts || !data.posts.length) {
      box.innerHTML = '<div class="empty">لا منشورات بعد</div>';
    } else {
      data.posts.forEach(p => box.appendChild(renderPost(p)));
    }
  } catch(e) {
    info.innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
  }
}

async function editProfile() {
  if (!state.user) return;
  const name = prompt('الاسم:', state.user.name || '');
  if (name === null) return;
  const bio = prompt('نبذة عنك:', state.user.bio || '');
  if (bio === null) return;
  const gender = prompt('الجنس (ذكر أو أنثى):', state.user.gender || '');
  if (gender === null) return;
  if (gender && gender !== 'ذكر' && gender !== 'أنثى' && gender !== 'أفضل عدم القول') {
    toast('الجنس: ذكر أو أنثى');
    return;
  }
  const ageStr = prompt('العمر (18+):', state.user.age != null ? String(state.user.age) : '');
  if (ageStr === null) return;
  const origin = prompt('المدينة / الولاية:', state.user.origin || '');
  if (origin === null) return;
  const interests = prompt(
    'اهتماماتك (مفصولة بفاصلة)\nمثال: رياضة, موسيقى, سفر, قراءة',
    state.user.interests || ''
  );
  if (interests === null) return;
  const age = ageStr.trim() ? parseInt(ageStr, 10) : null;
  if (age && age < 18) { toast('يجب أن يكون العمر 18 سنة فأكثر'); return; }
  try {
    await api('/api/profile', {
      method: 'PUT',
      body: JSON.stringify({
        name,
        bio,
        gender,
        age: (age && age >= 18 && age < 120) ? age : null,
        origin,
        interests,
      }),
    });
    toast('تم تحديث الملف');
    const me = await api('/api/me');
    if (me.user) state.user = me.user;
    loadProfile();
  } catch(e) { toast(e.message); }
}

// ====================== الإدارة ======================
async function loadAdmin() {
  if (!state.user || !state.user.is_admin) { toast('غير مصرح'); showPage('home'); return; }
  try {
    const stats = await api('/api/admin/stats');
    $('adminStats').innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;text-align:center">
        <div><strong style="font-size:1.4rem;color:var(--blue)">${stats.users}</strong><br><span style="color:var(--text2);font-size:12px">مستخدم</span></div>
        <div><strong style="font-size:1.4rem">${stats.posts}</strong><br><span style="color:var(--text2);font-size:12px">منشور</span></div>
        <div><strong style="font-size:1.4rem;color:var(--red)">${stats.open_reports}</strong><br><span style="color:var(--text2);font-size:12px">بلاغ جديد</span></div>
        <div><strong style="font-size:1.4rem">${stats.chat_messages||0}</strong><br><span style="color:var(--text2);font-size:12px">دردشة عامة</span></div>
        <div><strong style="font-size:1.4rem">${stats.private_messages||0}</strong><br><span style="color:var(--text2);font-size:12px">رسائل خاصة</span></div>
        <div><strong style="font-size:1.4rem">${stats.media_files||0}</strong><br><span style="color:var(--text2);font-size:12px">ملفات وسائط</span></div>
      </div>
      <p style="margin-top:12px;font-size:11px;color:var(--text2)">${esc(stats.note||'')}</p>
      <p style="font-size:11px;color:var(--blue)">${esc(stats.storage_note||'')}</p>
      <p style="font-size:11px;color:var(--orange)">ملفات الوسائط المسجّلة: ${stats.media_files||0}</p>
    `;
    await loadAdminUsers();
    await loadAdminReports();
    await loadAdminAlerts();
  } catch(e) {
    if ($('adminReports')) $('adminReports').innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
  }
}

async function loadAdminUsers() {
  const box = $('adminUsers');
  if (!box) return;
  const q = ($('adminUserSearch') && $('adminUserSearch').value.trim()) || '';
  try {
    let url = '/api/admin/users?limit=50';
    if (q) url += '&q=' + encodeURIComponent(q);
    const data = await api(url);
    box.innerHTML = '';
    if (!data.users || !data.users.length) {
      box.innerHTML = '<div class="empty-state" style="padding:16px"><p>لا مستخدمين</p></div>';
      return;
    }
    data.users.forEach(u => {
      const div = document.createElement('div');
      div.className = 'card admin-user-card';
      div.style.margin = '0 0 8px';
      const badges = [];
      if (u.is_admin) badges.push('<span class="badge verified">أدمن</span>');
      if (u.is_restricted) badges.push('<span class="badge" style="background:rgba(239,68,68,.2);color:var(--red)">مقيّد</span>');
      div.innerHTML = `
        <div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap">
          <div>
            <strong>${esc(u.name || 'مستخدم')}</strong> ${badges.join(' ')}
            <div class="phone">${esc(u.phone || '—')}</div>
            <div style="color:var(--text2);font-size:11px">${esc(u.public_id||'')} · ${timeAgo(u.created_at)}</div>
          </div>
          <div style="display:flex;flex-direction:column;gap:4px">
            <button class="btn-sm btn-ghost" onclick="adminRestrict('${u.id}', ${u.is_restricted ? 'false' : 'true'})">${u.is_restricted ? 'رفع القيد' : 'تقييد'}</button>
            <button class="btn-sm btn-danger" onclick="adminDeleteUser('${u.id}','${esc(u.name||'')}')">حذف</button>
            <button class="btn-sm btn-primary" onclick="openDM('${u.id}','${esc(u.name||'مستخدم')}')">رسالة</button>
          </div>
        </div>
      `;
      box.appendChild(div);
    });
  } catch(e) {
    box.innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
  }
}

async function adminRestrict(uid, restrict) {
  const fd = new FormData();
  fd.append('restrict', restrict ? 'true' : 'false');
  try {
    await api('/api/admin/restrict/' + uid, { method: 'POST', body: fd });
    toast(restrict ? 'تم التقييد' : 'تم رفع القيد');
    loadAdminUsers();
  } catch(e) { toast(e.message); }
}

async function adminDeleteUser(uid, name) {
  if (!confirm('حذف حساب «' + (name||'') + '» نهائيًا؟ لا يمكن التراجع.')) return;
  try {
    await api('/api/admin/users/' + uid, { method: 'DELETE' });
    toast('تم حذف الحساب');
    loadAdminUsers();
  } catch(e) { toast(e.message); }
}

async function loadAdminAlerts() {
  const box = $('adminAlerts');
  if (!box) return;
  try {
    const data = await api('/api/admin/alerts');
    if (!data.count) { box.style.display = 'none'; return; }
    box.style.display = 'block';
    box.innerHTML = `<div class="card" style="margin:0;border-color:var(--red);background:rgba(239,68,68,.1)">
      <strong style="color:var(--red)">${data.count} بلاغ جديد يحتاج مراجعة</strong>
      <p style="font-size:12px;color:var(--text2);margin-top:4px">راجع القائمة بالأسفل للتفاصيل</p>
    </div>`;
  } catch(e) { box.style.display = 'none'; }
}

async function loadAdminReports() {
  const box = $('adminReports');
  if (!box) return;
  try {
    const reps = await api('/api/admin/reports');
    if (!reps.reports || !reps.reports.length) {
      box.innerHTML = '<div class="empty-state" style="padding:20px"><p>لا بلاغات</p></div>';
      return;
    }
    box.innerHTML = '';
    reps.reports.forEach(r => {
      const reporter = r.users || {};
      const div = document.createElement('div');
      div.className = 'card';
      div.style.margin = '0 0 10px';
      div.innerHTML = `
        <div style="font-size:12px;color:var(--text2)">${timeAgo(r.created_at)} · <span style="color:var(--orange)">${esc(r.status)}</span></div>
        <div style="margin-top:4px"><strong>${esc(r.reason)}</strong></div>
        <div style="font-size:13px;margin-top:4px">${esc(r.details || '—')}</div>
        <div style="font-size:12px;color:var(--text2);margin-top:6px">
          المبلّغ: ${esc(reporter.name || '—')} ${reporter.phone ? '· <span class="phone" style="color:var(--orange)">'+esc(reporter.phone)+'</span>' : ''}
        </div>
        <div style="font-size:11px;color:var(--text2)">منشور: ${esc(r.post_id || '—')} ${r.message_id ? '· رسالة: '+esc(r.message_id) : ''}</div>
        <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap">
          <button class="btn-sm btn-ghost" onclick="updateReport('${r.id}','قيد المراجعة')">قيد المراجعة</button>
          <button class="btn-sm btn-primary" onclick="resolveReport('${r.id}','delete_post')">قبول + حذف المنشور</button>
          <button class="btn-sm btn-ghost" onclick="resolveReport('${r.id}','restrict_24h')">قبول + تقييد 24س</button>
          <button class="btn-sm btn-danger" onclick="resolveReport('${r.id}','delete_user')">قبول + حذف الحساب</button>
          <button class="btn-sm btn-ghost" onclick="updateReport('${r.id}','رُفض البلاغ')">رفض البلاغ</button>
        </div>
      `;
      box.appendChild(div);
    });
  } catch(e) {
    box.innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
  }
}

async function updateReport(id, status) {
  const fd = new FormData();
  fd.append('status', status);
  try {
    await api(`/api/admin/reports/${id}`, { method: 'PUT', body: fd });
    toast('تم التحديث');
    loadAdmin();
  } catch(e) { toast(e.message); }
}

async function resolveReport(id, action) {
  const labels = {
    delete_post: 'قبول البلاغ وحذف المنشور؟',
    restrict_24h: 'قبول البلاغ وتقييد صاحب المنشور 24 ساعة؟',
    delete_user: 'قبول البلاغ وحذف حساب صاحب المنشور نهائيًا؟',
  };
  if (!confirm(labels[action] || 'تأكيد؟')) return;
  const fd = new FormData();
  fd.append('status', 'تمت المعالجة');
  fd.append('action', action);
  try {
    const r = await api(`/api/admin/reports/${id}`, { method: 'PUT', body: fd });
    toast(r.action_done ? 'تم تنفيذ الإجراء' : 'تم تحديث البلاغ');
    loadAdmin();
  } catch(e) { toast(e.message); }
}


// ====================== الأصدقاء ======================
async function searchFriends() {
  if (!state.user) { showPage('auth'); return; }
  const q = $('friendSearch').value.trim();
  if (!q) return;
  const box = $('friendSearchResults');
  box.innerHTML = '<div class="loading">جاري البحث...</div>';
  try {
    const data = await api('/api/users/search?q=' + encodeURIComponent(q));
    box.innerHTML = '';
    if (!data.users || !data.users.length) {
      box.innerHTML = '<div class="empty">لا نتائج</div>';
      return;
    }
    data.users.forEach(u => box.appendChild(renderUserRow(u)));
  } catch(e) { box.innerHTML = `<div class="error-box">${esc(e.message)}</div>`; }
}

function renderUserRow(u) {
  const div = document.createElement('div');
  div.className = 'user-row';
  let action = '';
  if (u.friend_status === 'friends') {
    action = `<button class="btn btn-primary btn-sm" onclick="openDM('${u.id}','${esc(u.name||'مستخدم')}')">رسالة</button>`;
  } else if (u.friend_status === 'outgoing') {
    action = `<span style="color:var(--text2);font-size:12px">بانتظار القبول</span>`;
  } else if (u.friend_status === 'incoming') {
    action = `<span style="color:var(--orange);font-size:12px">طلب وارد</span>`;
  } else {
    action = `<button class="btn btn-primary btn-sm" onclick="sendFriendReq('${u.id}', this)">إضافة</button>`;
  }
  div.innerHTML = `
    ${avatarHtml(u)}
    <div class="info">
      <div class="name">${esc(u.name || 'مستخدم')}</div>
      <div class="sub">${esc(u.public_id || '')}</div>
    </div>
    ${action}
  `;
  return div;
}

async function sendFriendReq(uid, btn) {
  try {
    await api('/api/friends/request/' + uid, { method: 'POST' });
    toast('تم إرسال طلب الصداقة');
    if (btn) { btn.disabled = true; btn.textContent = 'تم الإرسال'; }
    loadFriendRequests();
  } catch(e) { toast(e.message); }
}

async function loadFriendRequests() {
  if (!state.user) return;
  try {
    const data = await api('/api/friends/requests');
    const box = $('incomingRequests');
    const inc = data.incoming || [];
    if (!inc.length) { box.innerHTML = '<div class="empty">لا طلبات واردة</div>'; return; }
    box.innerHTML = '';
    inc.forEach(r => {
      const u = r.users || {};
      const div = document.createElement('div');
      div.className = 'user-row';
      div.innerHTML = `
        ${avatarHtml(u)}
        <div class="info">
          <div class="name">${esc(u.name || 'مستخدم')}</div>
          <div class="sub">${esc(u.public_id || '')}</div>
        </div>
        <button class="btn btn-primary btn-sm" onclick="acceptReq('${r.id}')">قبول</button>
        <button class="btn-ghost btn-sm" onclick="rejectReq('${r.id}')">رفض</button>
      `;
      box.appendChild(div);
    });
  } catch(e) {
    $('incomingRequests').innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
  }
}

async function acceptReq(id) {
  try {
    await api('/api/friends/accept/' + id, { method: 'POST' });
    toast('أصبحتما صديقين');
    loadFriendRequests();
    loadFriends();
  } catch(e) { toast(e.message); }
}

async function rejectReq(id) {
  try {
    await api('/api/friends/reject/' + id, { method: 'POST' });
    toast('تم الرفض');
    loadFriendRequests();
  } catch(e) { toast(e.message); }
}

async function loadFriends() {
  if (!state.user) return;
  const box = $('friendsList');
  try {
    const data = await api('/api/friends');
    box.innerHTML = '';
    if (!data.friends || !data.friends.length) {
      box.innerHTML = '<div class="empty">لا أصدقاء بعد — ابحث وأضف أصدقاء</div>';
      return;
    }
    data.friends.forEach(u => {
      u.friend_status = 'friends';
      box.appendChild(renderUserRow(u));
    });
  } catch(e) {
    box.innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
  }
}

// ====================== الرسائل الخاصة ======================
function showConvList() {
  $('convListView').style.display = 'block';
  $('dmView').style.display = 'none';
  state.dmOtherId = null;
  stopDMPoll();
}

async function loadConversations() {
  if (!state.user) { showPage('auth'); return; }
  const box = $('conversationsList');
  try {
    const data = await api('/api/messages/conversations');
    box.innerHTML = '';
    if (!data.conversations || !data.conversations.length) {
      box.innerHTML = '<div class="empty">لا محادثات — راسل أصدقاءك من صفحة الأصدقاء</div>';
      return;
    }
    data.conversations.forEach(c => {
      const o = c.other || {};
      const last = c.last_message;
      let preview = '';
      if (last) {
        if (last.media_type === 'image') preview = 'صورة';
        else if (last.media_type === 'audio') preview = 'رسالة صوتية';
        else preview = last.content || '';
      }
      const div = document.createElement('div');
      div.className = 'user-row';
      div.style.cursor = 'pointer';
      div.onclick = () => openDM(o.id, o.name || 'مستخدم');
      div.innerHTML = `
        ${avatarHtml(o)}
        <div class="info">
          <div class="name">${esc(o.name || 'مستخدم')}</div>
          <div class="sub">${esc(preview).slice(0, 60)}</div>
        </div>
        <span style="font-size:11px;color:var(--text2)">${timeAgo(c.last_message_at)}</span>
      `;
      box.appendChild(div);
    });
  } catch(e) {
    box.innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
  }
}

function openDM(otherId, name) {
  if (!otherId) { toast('تعذر فتح المحادثة'); return; }
  state.dmOtherId = otherId;
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  $('page-messages').classList.add('active');
  document.querySelectorAll('.nav-item').forEach(n => {
    n.classList.toggle('active', n.dataset.page === 'messages');
  });
  $('convListView').style.display = 'none';
  $('dmView').style.display = 'block';
  $('dmHeader').textContent = name || 'محادثة';
  document.body.classList.add('dm-open');
  if ($('bottomNav')) $('bottomNav').style.display = 'none';
  loadDM();
  startDMPoll();
  setTimeout(function() { setupRecButton('dmRecBtn', 'dm'); }, 100);
}

function backToConvs() {
  document.body.classList.remove('dm-open');
  document.body.classList.remove('chat-open');
  if ($('mainHeader')) $('mainHeader').style.display = 'block';
  if ($('bottomNav') && state.user) $('bottomNav').style.display = 'flex';
  showConvList();
  loadConversations();
}

async function loadDM() {
  if (!state.dmOtherId) return;
  const box = $('dmMessages');
  try {
    const data = await api('/api/messages/' + state.dmOtherId + '?limit=50');
    box.innerHTML = '';
    (data.messages || []).forEach(m => {
      const mine = state.user && m.sender_id === state.user.id;
      const div = document.createElement('div');
      div.className = 'dm-bubble ' + (mine ? 'mine' : 'theirs');
      let body = linkify(m.content || '');
      if (m.media_type === 'image' && m.media_url) {
        body += `<img src="${esc(m.media_url)}" alt="صورة" onclick="window.open(this.src)">`;
      }
      if (m.media_type === 'audio' && m.media_url) {
        body += `<audio controls src="${esc(m.media_url)}"></audio>`;
      }
      div.innerHTML = body + `<div class="dm-meta">${timeAgo(m.created_at)}</div>`;
      box.appendChild(div);
    });
    box.scrollTop = box.scrollHeight;
  } catch(e) {
    box.innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
  }
}

async function sendDM() {
  if (!state.dmOtherId || !state.user) return;
  const input = $('dmInput');
  const content = input.value.trim();
  if (!content) return;
  input.value = '';
  const fd = new FormData();
  fd.append('content', content);
  try {
    await api('/api/messages/' + state.dmOtherId, { method: 'POST', body: fd });
    loadDM();
  } catch(e) { toast(e.message); input.value = content; }
}

async function sendDMImage() {
  const f = $('dmImage').files[0];
  if (!f || !state.dmOtherId) return;
  const fd = new FormData();
  fd.append('image', f);
  try {
    await api('/api/messages/' + state.dmOtherId, { method: 'POST', body: fd });
    $('dmImage').value = '';
    loadDM();
    toast('تم إرسال الصورة');
  } catch(e) { toast(e.message); }
}

function startDMPoll() {
  stopDMPoll();
  state.dmPoll = setInterval(() => {
    if (state.dmOtherId && $('page-messages').classList.contains('active')) loadDM();
  }, 5000);
}
function stopDMPoll() {
  if (state.dmPoll) { clearInterval(state.dmPoll); state.dmPoll = null; }
}

// ====================== تسجيل صوت بالضغط المطوّل ======================
function setupRecButton(btnId, target) {
  const btn = $(btnId);
  if (!btn || btn._recBound) return;
  btn._recBound = true;

  const start = async (e) => {
    e.preventDefault();
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      toast('المتصفح لا يدعم التسجيل');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      state.audioChunks = [];
      const mime = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' :
                   MediaRecorder.isTypeSupported('audio/mp4') ? 'audio/mp4' : '';
      state.mediaRecorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      state.recordingFor = target;
      state.mediaRecorder.ondataavailable = (ev) => {
        if (ev.data && ev.data.size > 0) state.audioChunks.push(ev.data);
      };
      state.mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        btn.classList.remove('recording');
        const hint = target === 'dm' ? $('dmRecHint') : $('postRecHint');
        if (hint) hint.textContent = 'اضغط مطولاً على الميكروفون للتسجيل';
        if (!state.audioChunks.length) return;
        const blob = new Blob(state.audioChunks, { type: state.mediaRecorder.mimeType || 'audio/webm' });
        if (blob.size < 500) { toast('التسجيل قصير جداً'); return; }
        const file = new File([blob], 'voice.webm', { type: blob.type });
        if (target === 'dm' && state.dmOtherId) {
          const fd = new FormData();
          fd.append('audio', file);
          try {
            await api('/api/messages/' + state.dmOtherId, { method: 'POST', body: fd });
            loadDM();
            toast('تم إرسال الرسالة الصوتية');
          } catch(err) { toast(err.message); }
        } else if (target === 'post') {
          const dt = new DataTransfer();
          dt.items.add(file);
          const audioInput = $('postAudio');
          if (audioInput) {
            audioInput.files = dt.files;
            toast('تم تسجيل الصوت — اضغط نشر');
            const prev = $('previewBox');
            if (prev) {
              prev.style.display = 'block';
              prev.innerHTML = '<audio controls src="' + URL.createObjectURL(blob) + '"></audio>';
            }
          }
        }
      };
      state.mediaRecorder.start();
      btn.classList.add('recording');
      const hint = target === 'dm' ? $('dmRecHint') : $('postRecHint');
      if (hint) hint.textContent = 'جاري التسجيل... أفلت للإرسال';
    } catch(err) {
      toast('تعذر الوصول للميكروفون');
    }
  };

  const stop = (e) => {
    e.preventDefault();
    if (state.mediaRecorder && state.mediaRecorder.state === 'recording') {
      state.mediaRecorder.stop();
    }
  };

  btn.addEventListener('mousedown', start);
  btn.addEventListener('mouseup', stop);
  btn.addEventListener('mouseleave', stop);
  btn.addEventListener('touchstart', start, { passive: false });
  btn.addEventListener('touchend', stop);
  btn.addEventListener('touchcancel', stop);
}



// ====================== دعم المتابعين ======================
state.supportPlatform = null;

async function loadSupportStatus() {
  if (!state.user) { showPage('auth'); return; }
  const box = $('supportMyStats');
  if (!box) return;
  box.innerHTML = '<div class="loading">...</div>';
  try {
    const data = await api('/api/support/status');
    const lv = data.level || {};
    let profilesHtml = '';
    (data.profiles || []).forEach(p => {
      profilesHtml += `<div style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border);font-size:13px">
        <span class="badge">${esc(p.platform)}</span>
        <span>${intOr(p.points)} نقطة · ${intOr(p.coins)} عملة</span>
        <div><a href="${esc(p.profile_url)}" target="_blank" rel="noopener" style="font-size:12px;word-break:break-all">${esc(p.profile_url)}</a></div>
      </div>`;
    });
    box.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div>
          <div style="font-size:1.25rem"><span class="lvl-badge lvl-${esc(lv.key||'bronze')}">${esc(lv.name||'برونزي')}</span></div>
          <div style="color:var(--text2);font-size:13px;margin-top:4px">${intOr(data.total_points)} نقطة · ${intOr(data.total_coins)} عملة</div>
        </div>
      </div>
      ${profilesHtml || '<p style="margin-top:10px;color:var(--text2);font-size:13px">لم تسجّل أي منصة بعد</p>'}
    `;
  } catch(e) {
    box.innerHTML = `<div class="error-box" style="margin:0">${esc(e.message)}</div>`;
  }
}
function intOr(n) { return (parseInt(n,10)||0); }

function supportStartRegister() {
  if (!state.user) { showPage('auth'); return; }
  $('supportHome').style.display = 'none';
  $('supportRegisterFlow').style.display = 'block';
  $('supportStepExplain').style.display = 'block';
  $('supportStepPlatform').style.display = 'none';
  $('supportStepUrl').style.display = 'none';
  $('supportStepDone').style.display = 'none';
}
function supportCancelReg() {
  if ($('supportHome')) $('supportHome').style.display = 'block';
  if ($('supportRegisterFlow')) $('supportRegisterFlow').style.display = 'none';
  state.supportPlatform = null;
  loadSupportStatus();
}
function supportShowPlatforms() {
  $('supportStepExplain').style.display = 'none';
  $('supportStepPlatform').style.display = 'block';
  $('supportStepUrl').style.display = 'none';
}
function supportPickPlatform(p) {
  state.supportPlatform = p;
  document.querySelectorAll('.support-plat').forEach(b => {
    b.style.borderColor = b.dataset.p === p ? 'var(--blue)' : '';
    b.style.background = b.dataset.p === p ? 'rgba(59,130,246,.15)' : '';
  });
  const names = {facebook:'فيسبوك',instagram:'إنستغرام',tiktok:'تيك توك',youtube:'يوتيوب'};
  $('supportPlatName').textContent = names[p] || p;
  $('supportStepUrl').style.display = 'block';
}
async function supportSubmitRegister() {
  if (!state.supportPlatform) { toast('اختر منصة'); return; }
  const url = ($('supportUrl') && $('supportUrl').value.trim()) || '';
  if (!url) { toast('أدخل رابط الملف'); return; }
  const fd = new FormData();
  fd.append('platform', state.supportPlatform);
  fd.append('profile_url', url);
  try {
    const data = await api('/api/support/register', { method: 'POST', body: fd });
    $('supportStepPlatform').style.display = 'none';
    $('supportStepUrl').style.display = 'none';
    $('supportStepExplain').style.display = 'none';
    $('supportStepDone').style.display = 'block';
    $('supportDoneMsg').textContent = data.message || 'تم تسجيل ملفك في تطبيق الدعم';
    if ($('supportUrl')) $('supportUrl').value = '';
  } catch(e) { toast(e.message); }
}

async function loadSupportTasks() {
  const box = $('supportTasksBox');
  if (!box) return;
  box.innerHTML = '<div class="loading">جاري تحميل المهام...</div>';
  try {
    const data = await api('/api/support/tasks');
    const tasks = data.tasks || [];
    const note = data.phase_note ? `<p style="font-size:12px;color:var(--text2);margin-bottom:10px">${esc(data.phase_note)} (المستخدمون: ${intOr(data.users_count)})</p>` : '';
    if (!tasks.length) {
      box.innerHTML = note + '<div class="empty-state" style="padding:20px"><p>لا مهام متاحة الآن. سجّل ملفك وادعُ أصدقاءك.</p></div>';
      return;
    }
    box.innerHTML = '<h3 style="margin-bottom:10px">مهام المتابعة</h3>' + note;
    tasks.forEach(t => {
      const u = t.users || {};
      const lv = t.level || {};
      const div = document.createElement('div');
      div.className = 'card';
      div.style.margin = '0 0 10px';
      div.innerHTML = `
        <div style="display:flex;justify-content:space-between;gap:8px;align-items:flex-start">
          <div style="min-width:0">
            <strong>${esc(u.name||'مستخدم')}</strong>
            <span class="badge" style="margin-right:6px">${esc(t.platform)}</span>
            <div style="font-size:12px;color:var(--text2)"><span class="lvl-badge lvl-${esc(lv.key||'bronze')}">${esc(lv.name||'')}</span> · ${intOr(t.points)} نقطة</div>
            <a href="${esc(t.profile_url)}" target="_blank" rel="noopener" style="font-size:12px;word-break:break-all">${esc(t.profile_url)}</a>
          </div>
          <button class="btn btn-primary btn-sm" onclick="supportDoFollow('${t.id}', this)">تابعت (+2)</button>
        </div>`;
      box.appendChild(div);
    });
  } catch(e) {
    box.innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
  }
}

async function supportDoFollow(profileId, btn) {
  if (btn) btn.disabled = true;
  try {
    const data = await api('/api/support/follow/' + profileId, { method: 'POST' });
    toast(data.message || 'تم');
    if (data.open_url) {
      try { window.open(data.open_url, '_blank'); } catch(e) {}
    }
    loadSupportTasks();
    loadSupportStatus();
  } catch(e) {
    toast(e.message);
    if (btn) btn.disabled = false;
  }
}

async function loadSupportLeaders() {
  const box = $('supportLeadersBox');
  if (!box) return;
  box.innerHTML = '<div class="loading">...</div>';
  try {
    const data = await api('/api/support/leaderboard');
    const rows = data.leaders || [];
    if (!rows.length) {
      box.innerHTML = '<p style="color:var(--text2);font-size:13px">لا متصدرين بعد</p>';
      return;
    }
    box.innerHTML = '<h3 style="margin-bottom:10px">المتصدرون</h3>';
    rows.forEach((t, i) => {
      const u = t.users || {};
      const lv = t.level || {};
      const div = document.createElement('div');
      div.className = 'user-row';
      div.innerHTML = `
        <div style="width:28px;font-weight:700;color:var(--text2)">${i+1}</div>
        ${avatarHtml(u)}
        <div class="info">
          <div class="name">${esc(u.name||'مستخدم')} <span class="lvl-badge lvl-${esc(lv.key||'bronze')}">${esc(lv.name||'')}</span></div>
          <div class="sub">${esc(t.platform)} · ${intOr(t.points)} نقطة · ${intOr(t.coins)} عملة</div>
        </div>`;
      box.appendChild(div);
    });
  } catch(e) {
    box.innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
  }
}



// ====================== اكتشاف وتعارف ======================
async function runDiscover() {
  if (!state.user) { showPage('auth'); toast('سجّل الدخول أولًا'); return; }
  const modal = $('discoverModal');
  const body = $('discoverBody');
  if (!modal || !body) return;
  modal.style.display = 'flex';
  body.innerHTML = '<div class="loading">نبحث عن شخص متوافق مع اهتماماتك...</div>';
  try {
    const data = await api('/api/discover/random');
    if (!data.match) {
      body.innerHTML = `<p style="color:var(--text2)">${esc(data.message||'لا نتائج')}</p>
        <p style="margin-top:10px;font-size:13px">أكمل ملفك: الجنس والاهتمامات من «حسابي → تعديل الملف»</p>`;
      return;
    }
    const m = data.match;
    const common = (data.common_interests || []).map(x => `<span class="interest-tag">${esc(x)}</span>`).join('')
      || '<span style="color:var(--text2);font-size:12px">لا اهتمامات مشتركة بعد — أضف اهتماماتك في ملفك</span>';
    const ints = (m.interests || '').split(',').filter(Boolean).map(x => `<span class="interest-tag">${esc(x.trim())}</span>`).join(' ');
    body.innerHTML = `
      <div class="discover-card">
        ${avatarHtml(m)}
        <h3 style="margin:0 0 4px">${esc(m.name||'مستخدم')}</h3>
        <div style="color:var(--text2);font-size:13px">${esc(m.gender||'')} ${m.age? '· '+m.age+' سنة':''} ${m.origin? '· '+esc(m.origin):''}</div>
        ${m.bio ? `<p style="margin:10px 0;font-size:14px">${esc(m.bio)}</p>` : ''}
        <div style="margin:10px 0">${ints}</div>
        <div style="margin:12px 0;padding:10px;background:var(--bg3);border-radius:12px">
          <div style="font-size:12px;color:var(--text2);margin-bottom:6px">اهتمامات مشتركة</div>
          ${common}
        </div>
        <div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin-top:14px">
          <button class="btn btn-primary" onclick="sendFriendReq('${m.id}'); toast('تم إرسال طلب الصداقة');">طلب صداقة</button>
          <button class="btn-ghost" onclick="openDM('${m.id}','${esc(m.name||'مستخدم')}'); closeDiscover();">رسالة</button>
          <button class="btn-ghost" onclick="runDiscover()">شخص آخر</button>
        </div>
      </div>`;
  } catch(e) {
    body.innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
  }
}
function closeDiscover() {
  const m = $('discoverModal');
  if (m) m.style.display = 'none';
}

function setChatTheme(color) {
  document.body.classList.add('chat-themed');
  document.body.style.setProperty('--chat-theme', color);
  try { localStorage.setItem('dz_chat_theme', color); } catch(e) {}
  toast('تم تغيير لون المحادثة');
}

async function loadFriendSuggestions() {
  const box = $('friendSuggestions');
  if (!box) return;
  try {
    const data = await api('/api/friends/suggestions');
    const rows = data.suggestions || [];
    if (!rows.length) {
      box.innerHTML = '<p style="color:var(--text2);font-size:13px;padding:8px">لا اقتراحات الآن — أكمل الجنس والاهتمامات في ملفك</p>';
      return;
    }
    box.innerHTML = '<div class="section-title">اقتراحات لك</div>';
    rows.forEach(u => {
      const common = (u.common_interests || []).slice(0, 4).map(x => `<span class="interest-tag">${esc(x)}</span>`).join(' ');
      const div = document.createElement('div');
      div.className = 'user-row';
      div.innerHTML = `
        ${avatarHtml(u)}
        <div class="info">
          <div class="name">${esc(u.name||'مستخدم')} ${u.age? '· '+u.age:''}</div>
          <div class="sub">${esc(u.gender||'')} ${u.origin? '· '+esc(u.origin):''}</div>
          <div>${common}</div>
        </div>
        <button class="btn btn-primary btn-sm" onclick="sendFriendReq('${u.id}', this)">إضافة</button>`;
      box.appendChild(div);
    });
  } catch(e) {
    box.innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
  }
}


// ====================== بدء ======================
window.addEventListener('popstate', function(ev) {
  const page = (ev.state && ev.state.page) || (location.hash || '#home').replace('#','') || 'home';
  if (!state.user && page !== 'auth' && page !== 'privacy') {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    const a = $('page-auth');
    if (a) a.classList.add('active');
    return;
  }
  document.body.classList.remove('dm-open', 'chat-open');
  if ($('bottomNav') && state.user) $('bottomNav').style.display = 'flex';
  if ($('mainHeader') && state.user) $('mainHeader').style.display = 'block';
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  const el = $('page-' + page);
  if (el) {
    el.classList.add('active');
    document.querySelectorAll('.nav-item').forEach(n => {
      n.classList.toggle('active', n.dataset.page === page);
    });
    if (page === 'home') { state.page = 1; loadPosts(true); }
    if (page === 'profile') loadProfile();
    if (page === 'messages') { showConvList(); loadConversations(); }
    if (page === 'friends') { loadFriends(); loadFriendRequests(); }
    if (page === 'chat') { document.body.classList.add('chat-open'); loadChat(); startChatPoll(); }
    if (page === 'settings') {}
    if (page === 'admin' && state.user && state.user.is_developer) loadAdmin();
  } else if (state.user) {
    showPage('home');
  } else {
    showPage('auth');
  }
});

try {
  if (localStorage.getItem('dz_theme') === 'light') {
    document.body.classList.add('theme-light');
  }
  const ct = localStorage.getItem('dz_chat_theme');
  if (ct) {
    document.body.classList.add('chat-themed');
    document.body.style.setProperty('--chat-theme', ct);
  }
} catch(e) {}

init();
</script>
</body>
</html>
'''


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return HTMLResponse(APP_HTML)


@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page():
    return HTMLResponse(APP_HTML)  # نفس الواجهة، JS يفتح صفحة الخصوصية


# ====================== تشغيل محلي ======================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=PORT, reload=(APP_ENV == "development"))

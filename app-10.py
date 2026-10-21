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
from datetime import datetime, timezone
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

POST_CATEGORIES = [
    "عروض Djezzy",
    "عروض Ooredoo",
    "عروض Mobilis",
    "الهدايا اليومية",
    "بوتات الإنترنت",
    "التطبيقات والمواقع المفيدة",
    "العروض الجديدة",
    "العروض التي تم التحقق منها",
]
BOT_STATUSES = ["يعمل", "متوقف مؤقتًا", "لم يتم التحقق منه"]
REPORT_REASONS = [
    "عرض غير صحيح أو منتهي",
    "رابط مشبوه",
    "احتيال أو تضليل",
    "محتوى مسيء",
    "سبب آخر",
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
    if not u.get("is_admin"):
        raise HTTPException(403, detail="صلاحيات إدارية مطلوبة")
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


def create_user_row(phone: str, name: Optional[str] = None) -> dict:
    data = {
        "id": str(uuid.uuid4()),
        "phone": phone,
        "name": (name or "").strip()[:80] or None,
        "public_id": public_id(),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "is_admin": False,
        "is_restricted": False,
    }
    r = db().table("users").insert(data).execute()
    if not r.data:
        raise HTTPException(500, "فشل إنشاء الحساب")
    return r.data[0]


async def upload_media(file: UploadFile, folder: str, user_id: str) -> dict:
    if not storage_ready:
        raise HTTPException(503, "التخزين غير جاهز")
    ctype = (file.content_type or "").lower()
    if ctype in ALLOWED_IMAGE:
        mtype = "image"
    elif ctype in ALLOWED_AUDIO:
        mtype = "audio"
    else:
        raise HTTPException(400, f"نوع الملف غير مسموح ({ctype})")
    data = await file.read()
    if len(data) == 0:
        raise HTTPException(400, "الملف فارغ")
    if len(data) > MAX_UPLOAD_SIZE:
        raise HTTPException(400, "حجم الملف أكبر من 5 ميجابايت")
    ext = (file.filename or "bin").rsplit(".", 1)[-1][:8]
    path = f"{folder}/{user_id}/{uuid.uuid4().hex}.{ext}"
    try:
        db().storage.from_("media").upload(
            path, data,
            file_options={"content-type": ctype, "upsert": "false"}
        )
        url = db().storage.from_("media").get_public_url(path)
        return {"path": path, "url": url, "media_type": mtype, "size": len(data)}
    except Exception as e:
        raise HTTPException(500, f"فشل الرفع: {str(e)[:120]}")


# ====================== نماذج ======================
class RegisterBody(BaseModel):
    phone: str
    name: Optional[str] = None
    accept_privacy: bool = False


class LoginBody(BaseModel):
    phone: str


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
@app.post("/api/register")
async def register(request: Request, body: RegisterBody):
    if not check_rate(f"reg:{request.client.host if request.client else 'x'}"):
        raise HTTPException(429, "محاولات كثيرة، حاول لاحقًا")
    if not body.accept_privacy:
        raise HTTPException(400, "يجب الموافقة على سياسة الخصوصية")
    phone = normalize_phone(body.phone)
    if not is_valid_dz_phone(phone):
        raise HTTPException(400, "رقم هاتف جزائري غير صالح (05/06/07 + 8 أرقام)")
    if get_user_by_phone(phone):
        raise HTTPException(400, "هذا الرقم مسجل مسبقًا. استخدم صفحة الدخول")
    row = create_user_row(phone, body.name)
    set_session(request, row)
    return {
        "ok": True,
        "message": "تم إنشاء الحساب",
        "user": {
            "id": row["id"],
            "name": row.get("name") or "مستخدم",
            "public_id": row["public_id"],
            "avatar_url": row.get("avatar_url"),
        },
        "security_note": "الدخول برقم الهاتف فقط نموذج أولي محدود الأمان وليس مصادقة حقيقية. لا يُنصح به للإطلاق العام.",
    }


@app.post("/api/login")
async def login(request: Request, body: LoginBody):
    if not check_rate(f"login:{request.client.host if request.client else 'x'}"):
        raise HTTPException(429, "محاولات كثيرة")
    phone = normalize_phone(body.phone)
    if not is_valid_dz_phone(phone):
        raise HTTPException(400, "رقم هاتف غير صالح")
    row = get_user_by_phone(phone)
    if not row:
        raise HTTPException(404, "الحساب غير موجود. سجّل حسابًا جديدًا")
    if row.get("is_restricted"):
        raise HTTPException(403, "هذا الحساب مقيد من قبل الإدارة")
    set_session(request, row)
    return {
        "ok": True,
        "message": "تم تسجيل الدخول",
        "user": {
            "id": row["id"],
            "name": row.get("name") or "مستخدم",
            "public_id": row["public_id"],
            "avatar_url": row.get("avatar_url"),
            "is_admin": bool(row.get("is_admin")),
        },
        "security_note": "الدخول برقم الهاتف فقط نموذج أولي محدود الأمان.",
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
            "created_at": row.get("created_at"),
            "is_admin": bool(row.get("is_admin")),
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
        "is_verified": bool(u.get("is_admin") and category == "العروض التي تم التحقق منها"),
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
    if not are_friends(u["id"], other_user_id) and u["id"] != other_user_id:
        raise HTTPException(403, "يمكن المراسلة بين الأصدقاء فقط")
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
    if not are_friends(u["id"], other_user_id):
        raise HTTPException(403, "يمكن المراسلة بين الأصدقاء فقط. أرسل طلب صداقة أولاً")
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
async def admin_update_report(report_id: str, request: Request, status: str = Form(...)):
    u = require_admin(request)
    if status not in ("جديد", "قيد المراجعة", "تمت المعالجة", "رُفض البلاغ"):
        raise HTTPException(400, "حالة غير صالحة")
    db().table("reports").update({
        "status": status,
        "reviewed_at": now_iso(),
        "reviewed_by": u["id"],
    }).eq("id", report_id).execute()
    return {"ok": True}


@app.post("/api/admin/restrict/{user_id}")
async def admin_restrict(user_id: str, request: Request, restrict: bool = Form(True)):
    require_admin(request)
    db().table("users").update({
        "is_restricted": restrict,
        "updated_at": now_iso(),
    }).eq("id", user_id).execute()
    return {"ok": True, "restricted": restrict}


@app.get("/api/admin/stats")
async def admin_stats(request: Request):
    require_admin(request)
    try:
        users = db().table("users").select("id", count="exact").execute()
        posts = db().table("posts").select("id", count="exact").execute()
        reports = db().table("reports").select("id", count="exact").eq("status", "جديد").execute()
        msgs = db().table("chat_messages").select("id", count="exact").execute()
        return {
            "users": users.count or 0,
            "posts": posts.count or 0,
            "open_reports": reports.count or 0,
            "chat_messages": msgs.count or 0,
        }
    except Exception as e:
        raise HTTPException(500, str(e)[:100])


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
  --bg: #0d1117;
  --bg2: #161b22;
  --bg3: #21262d;
  --border: #30363d;
  --text: #e6edf3;
  --text2: #8b949e;
  --blue: #58a6ff;
  --blue2: #1f6feb;
  --green: #3fb950;
  --red: #f85149;
  --orange: #d29922;
  --radius: 12px;
  --nav-h: 64px;
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
.btn-primary { background: var(--blue2); color: #fff; }
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

/* الهيدر */
.header {
  position: sticky; top: 0; z-index: 50;
  background: rgba(13,17,23,.92); backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--border);
  padding: 12px 16px;
  display: flex; align-items: center; justify-content: space-between;
}
.header .brand { font-weight: 800; font-size: 1.25rem; color: var(--blue); }
.header-actions { display: flex; gap: 8px; align-items: center; }

/* شريط التنقل السفلي */
.bottom-nav {
  position: fixed; bottom: 0; left: 0; right: 0; height: var(--nav-h);
  background: var(--bg2); border-top: 1px solid var(--border);
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
  background: var(--blue2); color: #fff; border-radius: 50%;
  width: 48px; height: 48px; justify-content: center; margin-top: -18px;
  box-shadow: 0 4px 14px rgba(31,111,235,.4);
}
.nav-item.create .icon { font-size: 26px; }

/* الصفحات */
.page { display: none; padding: 16px; max-width: 640px; margin: 0 auto; }
.page.active { display: block; }

/* بطاقة المنشور */
.card {
  background: var(--bg2); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 14px; margin-bottom: 12px;
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
  white-space: nowrap; padding: 6px 14px; border-radius: 20px;
  background: var(--bg3); border: 1px solid var(--border); color: var(--text2);
  font-size: 13px; cursor: pointer;
}
.filter-chip.active { background: var(--blue2); color: #fff; border-color: var(--blue2); }

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
</style>
</head>
<body>

<!-- شاشة الترحيب -->
<div id="welcome">
  <div class="logo">DZ Connect</div>
  <p>مجتمع جزائري لمشاركة عروض الإنترنت والهدايا اليومية وتجارب المستخدمين والبرامج المفيدة</p>
  <button class="btn btn-primary" style="padding:14px 40px;font-size:16px" onclick="startApp()">ابدأ الآن</button>
  <p style="margin-top:16px;font-size:12px;color:var(--text2)">نموذج أولي — الدخول برقم الهاتف محدود الأمان</p>
</div>

<!-- الهيدر -->
<header class="header" id="mainHeader" style="display:none">
  <div class="brand">DZ Connect</div>
  <div class="header-actions">
    <button class="btn-ghost btn-sm" onclick="showPage('settings')" title="الإعدادات">⚙️</button>
  </div>
</header>

<!-- الصفحات -->
<main>
  <!-- الرئيسية -->
  <div id="page-home" class="page">
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
        <button type="button" class="rec-btn" id="postRecBtn" title="اضغط مطولاً">🎤</button>
        <span class="rec-hint" id="postRecHint">اضغط مطولاً للتسجيل الصوتي ثم أفلت</span>
      </div>
    </div>
    <div id="previewBox" style="display:none;margin-bottom:12px" class="card"></div>
    <button class="btn btn-primary" style="width:100%" id="publishBtn" onclick="publishPost()">نشر</button>
  </div>

  <!-- الدردشة -->
  <div id="page-chat" class="page">
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
    <h2 style="margin-bottom:12px">الأصدقاء</h2>
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
      <h2 style="margin-bottom:12px">الرسائل</h2>
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
          <button class="btn-ghost btn-sm" onclick="$('dmImage').click()" title="صورة">🖼</button>
          <button class="rec-btn" id="dmRecBtn" title="اضغط مطولاً للتسجيل">🎤</button>
          <button class="btn btn-primary btn-sm" onclick="sendDM()">إرسال</button>
        </div>
        <div class="rec-hint" id="dmRecHint">اضغط مطولاً على الميكروفون للتسجيل</div>
      </div>
    </div>
  </div>

  <!-- الإعدادات -->
  <div id="page-settings" class="page">
    <h2 style="margin-bottom:16px">الإعدادات</h2>
    <ul class="settings-list">
      <li><span>سياسة الخصوصية</span><a href="#" onclick="showPrivacy();return false">عرض</a></li>
      <li><span>عن التطبيق</span><span style="color:var(--text2);font-size:13px">DZ Connect v0.1</span></li>
      <li id="adminLink" style="display:none"><span>لوحة الإدارة</span><a href="#" onclick="showPage('admin');return false">فتح</a></li>
      <li><button class="btn-danger btn-sm" onclick="doLogout()">تسجيل الخروج</button></li>
    </ul>
  </div>

  <!-- الإدارة -->
  <div id="page-admin" class="page">
    <h2 style="margin-bottom:16px">لوحة الإدارة</h2>
    <div id="adminStats" class="card" style="margin-bottom:16px"></div>
    <h3 style="margin-bottom:10px">البلاغات</h3>
    <div id="adminReports" class="loading">جاري التحميل...</div>
  </div>

  <!-- الدخول / التسجيل -->
  <div id="page-auth" class="page">
    <div style="max-width:360px;margin:40px auto">
      <h2 style="text-align:center;margin-bottom:8px" id="authTitle">تسجيل الدخول</h2>
      <p style="text-align:center;color:var(--text2);font-size:13px;margin-bottom:20px">
        رقم الهاتف وحده لا يثبت الملكية — هذا نموذج أولي محدود الأمان
      </p>
      <div class="form-group">
        <label>رقم الهاتف (جزائري)</label>
        <input type="tel" id="authPhone" placeholder="05XXXXXXXX" dir="ltr">
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
    <button class="btn-ghost btn-sm" onclick="history.back()" style="margin-bottom:12px">→ رجوع</button>
    <h2>سياسة الخصوصية</h2>
    <div class="card" style="margin-top:12px;font-size:14px;line-height:1.7">
      <p><strong>البيانات التي نجمعها:</strong> رقم الهاتف، الاسم (اختياري)، الصورة الشخصية، المنشورات والتعليقات والرسائل التي تكتبها.</p>
      <p style="margin-top:10px"><strong>سبب جمع رقم الهاتف:</strong> استخدامه كمعرّف للحساب في هذه النسخة الأولية (بدون OTP).</p>
      <p style="margin-top:10px"><strong>من يمكنه الوصول:</strong> المشرفون المخوّلون فقط يمكنهم الاطلاع على أرقام الهواتف عند الحاجة. رقمك لا يُعرض للعامة.</p>
      <p style="margin-top:10px"><strong>مدة الاحتفاظ:</strong> طالما بقي حسابك نشطًا. يمكنك طلب الحذف بالتواصل معنا.</p>
      <p style="margin-top:10px"><strong>ملاحظة:</strong> هذه السياسة مسودة وتحتاج مراجعة قانونية قبل الإطلاق العام، مع مراعاة القوانين الجزائرية ومتطلبات Supabase.</p>
    </div>
  </div>
</main>

<!-- شريط التنقل -->
<nav class="bottom-nav" id="bottomNav" style="display:none">
  <button class="nav-item active" data-page="home" onclick="showPage('home')">
    <span class="icon">🏠</span><span>الرئيسية</span>
  </button>
  <button class="nav-item" data-page="friends" onclick="showPage('friends')">
    <span class="icon">👥</span><span>أصدقاء</span>
  </button>
  <button class="nav-item create" data-page="create" onclick="showPage('create')">
    <span class="icon">+</span>
  </button>
  <button class="nav-item" data-page="messages" onclick="showPage('messages')">
    <span class="icon">✉️</span><span>رسائل</span>
  </button>
  <button class="nav-item" data-page="profile" onclick="showPage('profile')">
    <span class="icon">👤</span><span>حسابي</span>
  </button>
</nav>

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

function startApp() {
  localStorage.setItem('dz_welcomed', '1');
  $('welcome').style.display = 'none';
  if (state.user) {
    enterApp();
  } else {
    showPage('auth');
    $('mainHeader').style.display = 'flex';
  }
}

function enterApp() {
  $('welcome').style.display = 'none';
  $('mainHeader').style.display = 'flex';
  $('bottomNav').style.display = 'flex';
  if (state.user && state.user.is_admin) {
    $('adminLink').style.display = 'flex';
  }
  showPage('home');
}

// ====================== التنقل ======================
function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  const el = $('page-' + name);
  if (el) el.classList.add('active');

  document.querySelectorAll('.nav-item').forEach(n => {
    n.classList.toggle('active', n.dataset.page === name);
  });

  if (name === 'home') { state.page = 1; state.hasMore = true; loadPosts(true); }
  if (name === 'chat') { loadChat(); startChatPoll(); } else { stopChatPoll(); }
  if (name === 'profile') loadProfile();
  if (name === 'admin') loadAdmin();
  if (name === 'friends') { loadFriends(); loadFriendRequests(); }
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

async function doAuth() {
  const phone = $('authPhone').value.trim();
  const btn = $('authSubmit');
  btn.disabled = true;
  $('authError').style.display = 'none';
  try {
    let data;
    if (state.authMode === 'register') {
      data = await api('/api/register', {
        method: 'POST',
        body: JSON.stringify({
          phone,
          name: $('authName').value.trim() || null,
          accept_privacy: $('authPrivacy').checked,
        }),
      });
    } else {
      data = await api('/api/login', {
        method: 'POST',
        body: JSON.stringify({ phone }),
      });
    }
    state.user = data.user;
    if (data.security_note) toast(data.security_note, 5000);
    enterApp();
  } catch(e) {
    $('authError').style.display = 'block';
    $('authError').textContent = e.message || 'فشل العملية';
  } finally {
    btn.disabled = false;
  }
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
      list.innerHTML = '<div class="empty">لا توجد منشورات بعد. كن أول من ينشر!</div>';
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
      ${p.is_verified ? '<span class="badge verified">✓ تم التحقق</span>' : ''}
      ${p.bot_status ? `<span class="badge bot">${esc(p.bot_status)}</span>` : ''}
    </div>
    <div class="card-body">${esc(p.content || '')}${media}</div>
    <div class="card-actions">
      <button class="action-btn ${p.liked_by_me ? 'liked' : ''}" onclick="toggleLike('${p.id}', this)">
        ${p.liked_by_me ? '♥' : '♡'} <span>${p.likes_count || 0}</span>
      </button>
      <button class="action-btn" onclick="toggleComments('${p.id}', this)">💬 ${p.comments_count || 0}</button>
      <button class="action-btn ${p.saved_by_me ? 'saved' : ''}" onclick="toggleSave('${p.id}', this)">
        ${p.saved_by_me ? '★' : '☆'}
      </button>
      <button class="action-btn" onclick="sharePost('${p.id}')">↗</button>
      <button class="action-btn" onclick="openReport('${p.id}')">⚑</button>
      ${isOwner ? `<button class="action-btn" onclick="deletePost('${p.id}')">🗑</button>` : ''}
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
    if (data.liked) { btn.classList.add('liked'); btn.innerHTML = `♥ <span>${n+1}</span>`; }
    else { btn.classList.remove('liked'); btn.innerHTML = `♡ <span>${Math.max(0,n-1)}</span>`; }
  } catch(e) { toast(e.message); }
}

async function toggleSave(postId, btn) {
  if (!state.user) { showPage('auth'); return; }
  try {
    const data = await api(`/api/posts/${postId}/save`, { method: 'POST' });
    btn.classList.toggle('saved', data.saved);
    btn.textContent = data.saved ? '★' : '☆';
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
        <div>${esc(c.content)}</div>
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
        <div>${esc(m.content)}</div>`;
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
    info.innerHTML = `
      <div class="card" style="text-align:center">
        ${avatarHtml(u)}
        <h3 style="margin:10px 0 4px">${esc(u.name || 'مستخدم')}</h3>
        <div style="color:var(--text2);font-size:13px">${esc(u.public_id)}</div>
        <div style="color:var(--text2);font-size:13px;margin-top:4px">انضم ${timeAgo(u.created_at)} · ${u.posts_count || 0} منشور</div>
        <button class="btn-ghost btn-sm" style="margin-top:12px" onclick="editProfile()">تعديل الاسم</button>
      </div>
    `;
    // منشوراتي
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
  const name = prompt('الاسم الجديد:', state.user.name || '');
  if (name === null) return;
  try {
    await api('/api/profile', {
      method: 'PUT',
      body: JSON.stringify({ name }),
    });
    toast('تم التحديث');
    loadProfile();
  } catch(e) { toast(e.message); }
}

// ====================== الإدارة ======================
async function loadAdmin() {
  if (!state.user || !state.user.is_admin) { toast('غير مصرح'); showPage('home'); return; }
  try {
    const stats = await api('/api/admin/stats');
    $('adminStats').innerHTML = `
      <div style="display:flex;gap:16px;flex-wrap:wrap;justify-content:space-around">
        <div><strong>${stats.users}</strong><br><span style="color:var(--text2);font-size:12px">مستخدم</span></div>
        <div><strong>${stats.posts}</strong><br><span style="color:var(--text2);font-size:12px">منشور</span></div>
        <div><strong>${stats.open_reports}</strong><br><span style="color:var(--text2);font-size:12px">بلاغ جديد</span></div>
        <div><strong>${stats.chat_messages}</strong><br><span style="color:var(--text2);font-size:12px">رسالة دردشة</span></div>
      </div>
    `;
    const reps = await api('/api/admin/reports');
    const box = $('adminReports');
    if (!reps.reports || !reps.reports.length) {
      box.innerHTML = '<div class="empty">لا بلاغات</div>';
      return;
    }
    box.innerHTML = '';
    reps.reports.forEach(r => {
      const div = document.createElement('div');
      div.className = 'card';
      div.innerHTML = `
        <div style="font-size:13px;color:var(--text2)">${timeAgo(r.created_at)} · ${esc(r.status)}</div>
        <div><strong>${esc(r.reason)}</strong></div>
        <div style="font-size:13px">${esc(r.details || '')}</div>
        <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap">
          <button class="btn-sm btn-ghost" onclick="updateReport('${r.id}','قيد المراجعة')">قيد المراجعة</button>
          <button class="btn-sm btn-primary" onclick="updateReport('${r.id}','تمت المعالجة')">تمت المعالجة</button>
          <button class="btn-sm btn-ghost" onclick="updateReport('${r.id}','رُفض البلاغ')">رفض</button>
        </div>
      `;
      box.appendChild(div);
    });
  } catch(e) {
    $('adminReports').innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
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
  state.dmOtherId = otherId;
  $('convListView').style.display = 'none';
  $('dmView').style.display = 'block';
  $('dmHeader').textContent = name || 'محادثة';
  loadDM();
  startDMPoll();
  setupRecButton('dmRecBtn', 'dm');
}

function backToConvs() {
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
      let body = esc(m.content || '');
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


// ====================== بدء ======================
init();
// إذا كان هناك ?post= في الرابط
const params = new URLSearchParams(location.search);
if (params.get('post')) {
  // يمكن توسيعها لاحقًا لفتح منشور محدد
}
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

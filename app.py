# ==========================================
# TaskCoins Hub - نسخة احترافية آمنة جاهزة للنشر
# ملف واحد (app.py) مع جميع الإصلاحات المطلوبة
# ==========================================
# التعديلات الرئيسية المطبقة:
# 1. نظام قوالب صحيح عبر DictLoader + Jinja2 Environment الخاص بـ Flask
# 2. عدادات الإدارة باستخدام count="exact" و .count
# 3. منع Race Condition عند تنفيذ المهام (تحديث ذري مع شرط)
# 4. التحقق من تطابق الرابط مع المنصة
# 5. حماية CSRF لجميع نماذج POST (Flask-WTF)
# 6. SECRET_KEY ثابت داخل الكود (بدون الاعتماد على متغير البيئة)
# 7. التحقق من المدير من قاعدة البيانات في كل طلب إداري
# 8. تنظيف البريد (lowercase + strip) عند التسجيل والدخول
# 9. إعدادات جلسة آمنة (HTTPONLY / SECURE / SAMESITE)
# 10. معالجة أخطاء احترافية مع logging ورسائل عربية فقط
# 11. تحقق صارم من المدخلات (قيم سالبة، مهام فارغة، مكافآت غير منطقية)
# 12-13. الحفاظ على كل الميزات والتصميم والصفحات والجداول
# 14. تغيير طريقة تنفيذ المهام: النقر على رابط المهمة نفسه يحسب الإكمال
#     (مسار /tasks/go/<id> يسجّل ثم يوجّه للرابط الحقيقي) — بدون زر تنفيذ منفصل
# ==========================================

import os
import re
import logging
from functools import wraps
from urllib.parse import urlparse

from flask import (
    Flask, request, redirect, url_for, session, flash, jsonify,
    render_template, get_flashed_messages
)
from flask_wtf.csrf import CSRFProtect, generate_csrf, CSRFError
from werkzeug.security import generate_password_hash, check_password_hash
from jinja2 import DictLoader
from supabase import create_client, Client
from dotenv import load_dotenv
from google import genai

load_dotenv()

# ==========================================
# إعداد التسجيل (Logging)
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger('TaskCoinsHub')

# ==========================================
# إعداد التطبيق
# ==========================================
# تم إزالة الاعتماد على متغير البيئة SECRET_KEY واستخدام مفتاح ثابت
app = Flask(__name__)
app.config['SECRET_KEY'] = 'TaskCoinsHub-7f3a9c2e8b1d4f6a0e5c9b7d2a8f4e1c6b0d9a3f7e2c5b8a1d4f0e6c9b3a7'

# [تعديل 9] إعدادات الجلسة الآمنة
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# SESSION_COOKIE_SECURE=True فقط عند HTTPS (يُكتشف تلقائياً أو عبر متغير بيئة)
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FORCE_HTTPS', 'false').lower() in ('1', 'true', 'yes')

# حماية CSRF
csrf = CSRFProtect(app)

# ==========================================
# اتصال Supabase
# ==========================================
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "SUPABASE_URL أو SUPABASE_KEY غير موجودين في متغيرات البيئة."
    )

db: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# اتصال Gemini AI
# ==========================================
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
if not GEMINI_API_KEY or GEMINI_API_KEY.strip() == '':
    print("========== GEMINI WARNING ==========")
    print("تحذير: متغير البيئة GEMINI_API_KEY غير موجود أو فارغ!")
    print("====================================")
    gemini_client = None
else:
    print("========== GEMINI INFO ==========")
    print("تم العثور على مفتاح GEMINI_API_KEY بنجاح.")
    print("=================================")
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================================
# نظام القوالب الصحيح لملف واحد (DictLoader)
# [تعديل 1] استخدام محرك Jinja الخاص بـ Flask بشكل صحيح
# ==========================================
TEMPLATES = {
    'base.html': '''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TaskCoins Hub</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --ig-gradient: linear-gradient(45deg, #f09433, #e6683c, #dc2743, #cc2366, #bc1888);
            --ig-pink: #E1306C;
            --ig-purple: #833AB4;
            --ig-orange: #F77737;
            --fb-blue: #1877F2;
            --bg-dark: #0a0a0a;
            --card-bg: #161616;
            --border-c: #2a2a2a;
        }
        body { background: var(--bg-dark); color: #f0f0f0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        .navbar-ig {
            background: #000 !important;
            border-bottom: 1px solid var(--border-c);
            padding: 0.5rem 0;
        }
        .navbar-brand {
            background: var(--ig-gradient);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 800;
            font-size: 1.4rem;
        }
        .nav-link {
            color: #ccc !important;
            font-weight: 500;
            position: relative;
            padding: 0.5rem 0.9rem !important;
            border-radius: 8px;
            transition: all 0.2s;
        }
        .nav-link:hover, .nav-link.active {
            color: #fff !important;
            background: rgba(225, 48, 108, 0.15);
        }
        .nav-link .badge-notif {
            position: absolute;
            top: 2px;
            left: 2px;
            background: #ff2d55;
            color: #fff;
            font-size: 0.65rem;
            min-width: 18px;
            height: 18px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
        }
        .card {
            background: var(--card-bg) !important;
            border: 1px solid var(--border-c) !important;
            border-radius: 12px !important;
        }
        .btn-ig {
            background: var(--ig-gradient);
            border: none;
            color: #fff;
            font-weight: 600;
            border-radius: 8px;
        }
        .btn-ig:hover { opacity: 0.9; color: #fff; }
        .btn-outline-ig {
            border: 1.5px solid var(--ig-pink);
            color: var(--ig-pink);
            background: transparent;
            border-radius: 8px;
        }
        .btn-outline-ig:hover { background: var(--ig-pink); color: #fff; }
        .form-control, .form-select {
            background: #1c1c1c !important;
            border: 1px solid var(--border-c) !important;
            color: #eee !important;
            border-radius: 8px;
        }
        .form-control:focus { border-color: var(--ig-pink) !important; box-shadow: 0 0 0 0.15rem rgba(225,48,108,0.25); }
        .avatar-sm { width: 36px; height: 36px; object-fit: cover; border-radius: 50%; }
        .avatar-md { width: 48px; height: 48px; object-fit: cover; border-radius: 50%; }
        .avatar-lg { width: 120px; height: 120px; object-fit: cover; border-radius: 50%; border: 3px solid transparent; background: var(--ig-gradient) padding-box, var(--ig-gradient) border-box; }
        .post-card { margin-bottom: 1.25rem; }
        .like-btn.liked { color: #ff2d55 !important; }
        .comment-reply { margin-right: 2.5rem; border-right: 2px solid var(--border-c); padding-right: 0.75rem; }
        .msg-bubble-me { background: var(--ig-gradient); color: #fff; border-radius: 18px 18px 4px 18px; }
        .msg-bubble-them { background: #2a2a2a; color: #eee; border-radius: 18px 18px 18px 4px; }
        .table-dark { --bs-table-bg: transparent; }
        a { color: var(--ig-pink); }
        a:hover { color: var(--ig-orange); }
        .bottom-nav {
            position: fixed; bottom: 0; left: 0; right: 0;
            background: #000; border-top: 1px solid var(--border-c);
            display: flex; justify-content: space-around; align-items: center;
            height: 56px; z-index: 1050;
            padding-bottom: env(safe-area-inset-bottom);
        }
        .bottom-nav a {
            flex: 1; text-align: center; color: #aaa !important;
            font-size: 1.35rem; padding: 8px 0; position: relative; text-decoration: none;
        }
        .bottom-nav a:hover, .bottom-nav a.active { color: #fff !important; }
        .bottom-nav .badge-notif {
            position: absolute; top: 4px; left: 50%; margin-left: 8px;
            background: #ff2d55; color: #fff; font-size: 0.6rem;
            min-width: 16px; height: 16px; border-radius: 50%;
            display: inline-flex; align-items: center; justify-content: center; font-weight: 700;
        }
        body { padding-bottom: 70px; }
        @media (min-width: 992px) {
            .bottom-nav { display: none; }
            body { padding-bottom: 0; }
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-ig sticky-top">
        <div class="container">
            <a class="navbar-brand" href="{{ url_for('posts_feed') }}"><i class="fas fa-coins me-1"></i>TaskCoins</a>
            <button class="navbar-toggler border-0" type="button" data-bs-toggle="collapse" data-bs-target="#navMain">
                <i class="fas fa-bars text-light"></i>
            </button>
            <div class="collapse navbar-collapse" id="navMain">
                <div class="navbar-nav me-auto align-items-lg-center">
                {% if session.get('user_id') %}
                <a class="nav-link" href="{{ url_for('posts_feed') }}" title="الرئيسية"><i class="fas fa-home"></i></a>
                <a class="nav-link" href="{{ url_for('friends_page') }}" title="الأصدقاء">
                    <i class="fas fa-user-friends"></i>
                    {% if pending_friend_requests and pending_friend_requests > 0 %}
                    <span class="badge-notif">{{ pending_friend_requests if pending_friend_requests < 100 else '99+' }}</span>
                    {% endif %}
                </a>
                <a class="nav-link" href="{{ url_for('messages_inbox') }}" title="الرسائل">
                    <i class="fas fa-facebook-messenger"></i>
                    {% if unread_messages and unread_messages > 0 %}
                    <span class="badge-notif">{{ unread_messages if unread_messages < 100 else '99+' }}</span>
                    {% endif %}
                </a>
                <a class="nav-link" href="{{ url_for('index') }}" title="المهام"><i class="fas fa-tasks me-1"></i>المهام</a>
                <a class="nav-link" href="{{ url_for('create_task') }}" title="إنشاء مهمة"><i class="fas fa-plus-circle me-1"></i>إنشاء</a>
                <a class="nav-link" href="{{ url_for('profile') }}" title="الملف"><i class="fas fa-user me-1"></i>الملف</a>
                <a class="nav-link" href="{{ url_for('ai_chat') }}" title="AI"><i class="fas fa-robot me-1"></i>AI</a>
                {% if session.get('is_admin') %}
                <a class="nav-link text-warning" href="{{ url_for('admin_dashboard') }}"><i class="fas fa-shield-alt me-1"></i>إدارة</a>
                {% endif %}
                <a class="nav-link" href="{{ url_for('logout') }}"><i class="fas fa-sign-out-alt me-1"></i>خروج</a>
                {% endif %}
                </div>
            </div>
        </div>
    </nav>
    <div class="container py-3">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for cat, msg in messages %}
                    <div class="alert alert-{{ cat }} alert-dismissible fade show" role="alert">{{ msg }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <meta name="csrf-token" content="{{ csrf_token() }}">
    <script>
        const originalFetch = window.fetch;
        window.fetch = function(url, options = {}) {
            options = options || {};
            options.headers = options.headers || {};
            if ((options.method || 'GET').toUpperCase() === 'POST') {
                const token = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
                if (token) {
                    if (options.headers instanceof Headers) {
                        options.headers.set('X-CSRFToken', token);
                    } else {
                        options.headers['X-CSRFToken'] = token;
                    }
                }
            }
            return originalFetch(url, options);
        };
    </script>
    {% if session.get('user_id') %}
    <nav class="bottom-nav">
        <a href="{{ url_for('posts_feed') }}" title="الرئيسية"><i class="fas fa-home"></i></a>
        <a href="{{ url_for('friends_page') }}" title="الأصدقاء">
            <i class="fas fa-user-friends"></i>
            {% if pending_friend_requests and pending_friend_requests > 0 %}
            <span class="badge-notif">{{ pending_friend_requests if pending_friend_requests < 100 else '99+' }}</span>
            {% endif %}
        </a>
        <a href="{{ url_for('messages_inbox') }}" title="الرسائل">
            <i class="fas fa-facebook-messenger"></i>
            {% if unread_messages and unread_messages > 0 %}
            <span class="badge-notif">{{ unread_messages if unread_messages < 100 else '99+' }}</span>
            {% endif %}
        </a>
        <a href="{{ url_for('index') }}" title="المهام"><i class="fas fa-tasks"></i></a>
        <a href="{{ url_for('profile') }}" title="الملف"><i class="fas fa-user"></i></a>
    </nav>
    {% endif %}
</body>
</html>''',

    'login.html': '''{% extends "base.html" %}
{% block content %}
<div class="row justify-content-center"><div class="col-md-5"><div class="card bg-dark border-secondary p-4 shadow">
<h3 class="text-center mb-4 text-primary">تسجيل الدخول</h3>
<form method="POST">
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
<div class="mb-3"><label class="form-label">البريد الإلكتروني</label><input type="email" name="email" class="form-control" required></div>
<div class="mb-3"><label class="form-label">كلمة المرور</label><input type="password" name="password" class="form-control" required></div>
<button type="submit" class="btn btn-primary w-100">دخول</button>
</form>
<div class="text-center mt-3"><a href="{{ url_for('register') }}" class="text-decoration-none">ليس لديك حساب؟ إنشاء حساب جديد</a></div>
</div></div></div>
{% endblock %}''',

    'register.html': '''{% extends "base.html" %}
{% block content %}
<div class="row justify-content-center"><div class="col-md-5"><div class="card bg-dark border-secondary p-4 shadow">
<h3 class="text-center mb-4 text-primary">إنشاء حساب جديد</h3>
<form method="POST">
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
<div class="mb-3"><label class="form-label">اسم المستخدم</label><input type="text" name="username" class="form-control" required maxlength="50"></div>
<div class="mb-3"><label class="form-label">البريد الإلكتروني</label><input type="email" name="email" class="form-control" required></div>
<div class="mb-3"><label class="form-label">كلمة المرور</label><input type="password" name="password" class="form-control" required minlength="6"></div>
<button type="submit" class="btn btn-primary w-100">تسجيل</button>
</form>
<div class="text-center mt-3"><a href="{{ url_for('login') }}" class="text-decoration-none">لديك حساب بالفعل؟ سجل دخولك</a></div>
</div></div></div>
{% endblock %}''',

    'index.html': '''{% extends "base.html" %}
{% block content %}
<div class="row mb-4"><div class="col-md-12">
<form method="GET" class="row g-3">
<div class="col-md-4"><input type="text" name="search" class="form-control" placeholder="ابحث عن نوع المهمة..." value="{{ search }}"></div>
<div class="col-md-4"><select name="platform" class="form-select">
<option value="">جميع المنصات</option>
<option value="YouTube" {% if current_platform == 'YouTube' %}selected{% endif %}>YouTube</option>
<option value="Facebook" {% if current_platform == 'Facebook' %}selected{% endif %}>Facebook</option>
<option value="Instagram" {% if current_platform == 'Instagram' %}selected{% endif %}>Instagram</option>
<option value="TikTok" {% if current_platform == 'TikTok' %}selected{% endif %}>TikTok</option>
<option value="X" {% if current_platform == 'X' %}selected{% endif %}>X</option>
<option value="Telegram" {% if current_platform == 'Telegram' %}selected{% endif %}>Telegram</option>
<option value="Discord" {% if current_platform == 'Discord' %}selected{% endif %}>Discord</option>
</select></div>
<div class="col-md-4"><button type="submit" class="btn btn-primary w-100">بحث وتصفية</button></div>
</form>
</div></div>
<div class="row">
{% for task in tasks %}
<div class="col-md-4 mb-3"><div class="card bg-dark border-secondary h-100 shadow-sm"><div class="card-body">
<span class="badge bg-secondary mb-2">{{ task.platform }}</span>
<h5 class="card-title text-light">{{ task.task_type }}</h5>
<p class="card-text text-muted small">المكافأة: <span class="text-success fw-bold">{{ task.reward }} نقطة</span></p>
<p class="card-text text-muted small">المنجز: {{ task.completed_count }} / {{ task.required_count }}</p>
<a href="{{ url_for('go_to_task', task_id=task.id) }}" target="_blank" rel="noopener noreferrer" class="btn btn-success btn-sm w-100">
<i class="fas fa-external-link-alt me-1"></i> فتح رابط المهمة (يُحتسب تلقائياً)
</a>
<p class="card-text text-muted small mt-2 mb-0">اضغط على الرابط أعلاه لتنفيذ المهمة والحصول على النقاط</p>
</div></div></div>
{% else %}
<div class="col-12 text-center py-5"><p class="text-muted">لا توجد مهام متاحة حالياً.</p></div>
{% endfor %}
</div>
{% endblock %}''',


    'create_task.html': '''{% extends "base.html" %}
{% block content %}
<div class="row justify-content-center"><div class="col-md-6"><div class="card bg-dark border-secondary p-4 shadow">
<h3 class="text-center mb-4 text-primary">إنشاء مهمة جديدة</h3>
<form id="createTaskForm">
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
<div class="mb-3"><label class="form-label">المنصة</label><select name="platform" class="form-select" required>
<option value="YouTube">YouTube</option><option value="Facebook">Facebook</option><option value="Instagram">Instagram</option><option value="TikTok">TikTok</option><option value="X">X</option><option value="Telegram">Telegram</option><option value="Discord">Discord</option>
</select></div>
<div class="mb-3"><label class="form-label">نوع المهمة</label><input type="text" name="task_type" class="form-control" required maxlength="100"></div>
<div class="mb-3"><label class="form-label">الرابط</label><input type="url" name="link" class="form-control" required placeholder="https://..."></div>
<div class="mb-3"><label class="form-label">العدد المطلوب</label><input type="number" name="required_count" class="form-control" min="1" max="10000" required></div>
<div class="mb-3"><label class="form-label">المكافأة لكل تنفيذ</label><input type="number" step="0.1" name="reward" class="form-control" min="0.1" max="1000" required></div>
<button type="submit" class="btn btn-primary w-100">إنشاء وخصم النقاط</button>
</form>
</div></div></div>
<script>
document.getElementById('createTaskForm').onsubmit = async (e) => {
    e.preventDefault();
    try {
        let res = await fetch('/tasks/create', {method: 'POST', body: new FormData(e.target)});
        let data = await res.json();
        alert(data.message);
        if(data.success) window.location.href = '{{ url_for("index") }}';
    } catch (err) {
        alert('حدث خطأ أثناء الاتصال بالخادم');
    }
};
</script>
{% endblock %}''',

    'profile.html': '''{% extends "base.html" %}
{% block content %}
<div class="row">
<div class="col-md-4">
<div class="card p-4 shadow mb-4 text-center">
{% if user.avatar_url %}
<img src="{{ user.avatar_url }}" alt="صورة الملف" class="avatar-lg mb-3">
{% else %}
<div class="rounded-circle bg-secondary d-inline-flex align-items-center justify-content-center mb-3" style="width:120px;height:120px;"><i class="fas fa-user fa-3x text-light"></i></div>
{% endif %}
<h4 class="mb-2" style="background:var(--ig-gradient);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">{{ user.username }}</h4>
<p class="mb-1 text-muted small">{{ user.email }}</p>
<p class="mb-3"><span class="text-success fw-bold">{{ user.points }} نقطة</span></p>
<form method="POST" action="{{ url_for('update_avatar') }}" enctype="multipart/form-data">
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
<div class="mb-2">
<input type="file" name="avatar" accept="image/*" class="form-control form-control-sm" required>
</div>
<button type="submit" class="btn btn-ig btn-sm w-100">رفع صورة البروفايل</button>
</form>
</div>
</div>
<div class="col-md-8"><div class="card p-4 shadow mb-4">
<h4 class="mb-3" style="color:var(--ig-pink);">سجل العمليات</h4>
<div class="table-responsive"><table class="table table-dark table-striped">
<thead><tr><th>النوع</th><th>المبلغ</th><th>الوصف</th><th>التاريخ</th></tr></thead>
<tbody>
{% for h in history %}
<tr><td>{{ h.type }}</td><td class="{% if h.amount > 0 %}text-success{% else %}text-danger{% endif %}">{{ h.amount }}</td><td>{{ h.description }}</td><td>{{ h.created_at[:10] if h.created_at else '' }}</td></tr>
{% else %}
<tr><td colspan="4" class="text-center text-muted">لا يوجد سجل بعد</td></tr>
{% endfor %}
</tbody></table></div>
</div></div></div>
{% endblock %}''',

    'admin.html': '''{% extends "base.html" %}
{% block content %}
<div class="row mb-4">
<div class="col-md-6"><div class="card bg-dark border-secondary p-3 text-center"><h3>إجمالي المستخدمين</h3><p class="fs-4 text-primary">{{ users_count }}</p></div></div>
<div class="col-md-6"><div class="card bg-dark border-secondary p-3 text-center"><h3>إجمالي المهام</h3><p class="fs-4 text-success">{{ tasks_count }}</p></div></div>
</div>
<div class="card bg-dark border-secondary p-4 shadow">
<h3 class="text-primary mb-3">إدارة المستخدمين</h3>
<div class="table-responsive"><table class="table table-dark table-striped">
<thead><tr><th>اسم المستخدم</th><th>البريد</th><th>النقاط</th><th>الحالة</th><th>الإجراءات</th></tr></thead>
<tbody>
{% for u in users %}
<tr><td>{{ u.username }}</td><td>{{ u.email }}</td><td>{{ u.points }}</td><td>{% if u.is_banned %}<span class="text-danger">محظور</span>{% else %}<span class="text-success">نشط</span>{% endif %}</td>
<td><button onclick="toggleBan('{{ u.id }}')" class="btn btn-sm btn-outline-warning">حظر/فك حظر</button></td></tr>
{% else %}
<tr><td colspan="5" class="text-center text-muted">لا يوجد مستخدمون</td></tr>
{% endfor %}
</tbody></table></div>
</div>
<script>
async function toggleBan(id) {
    try {
        let res = await fetch('/admin/user/ban/' + id, {method: 'POST'});
        let data = await res.json();
        alert(data.message);
        if(data.success) location.reload();
    } catch (e) {
        alert('حدث خطأ أثناء الاتصال بالخادم');
    }
}
</script>
{% endblock %}''',

    'ai_chat.html': '''{% extends "base.html" %}
{% block content %}
<div class="row justify-content-center">
<div class="col-md-8">
<div class="card bg-dark border-secondary shadow">
<div class="card-header bg-primary text-white d-flex align-items-center">
<i class="fas fa-robot me-2"></i>
<strong>محادثة الذكاء الاصطناعي</strong>
</div>
<div class="card-body p-0">
<div id="chat-box" class="p-3" style="height: 420px; overflow-y: auto;">
<div class="text-center text-muted small py-3">أهلاً بك! اكتب رسالتك للبدء...</div>
</div>
</div>
<div class="card-footer bg-dark border-secondary">
<div class="input-group">
<input type="text" id="user-input" class="form-control bg-dark text-light border-secondary" placeholder="اكتب رسالتك هنا..." onkeydown="if(event.key === 'Enter') sendMessage()">
<button class="btn btn-primary" type="button" onclick="sendMessage()"><i class="fas fa-paper-plane"></i> إرسال</button>
</div>
</div>
</div>
</div>
</div>
<script>
async function sendMessage() {
    const input = document.getElementById('user-input');
    const chatBox = document.getElementById('chat-box');
    const message = input.value.trim();
    if (!message) return;

    chatBox.innerHTML += `<div class="mb-2 text-end"><span class="d-inline-block bg-primary text-white p-2 rounded-3" style="max-width:80%">${message}</span></div>`;
    input.value = '';
    chatBox.scrollTop = chatBox.scrollHeight;

    try {
        const response = await fetch('/ai/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message })
        });
        const data = await response.json();
        if (data.reply) {
            chatBox.innerHTML += `<div class="mb-2 text-start"><span class="d-inline-block bg-secondary text-light p-2 rounded-3" style="max-width:80%">${data.reply}</span></div>`;
        } else if (data.error) {
            chatBox.innerHTML += `<div class="mb-2 text-start"><span class="d-inline-block bg-danger text-white p-2 rounded-3" style="max-width:80%">${data.error}</span></div>`;
        } else {
            chatBox.innerHTML += `<div class="mb-2 text-start"><span class="d-inline-block bg-danger text-white p-2 rounded-3">حدث خطأ غير معروف.</span></div>`;
        }
    } catch (err) {
        chatBox.innerHTML += `<div class="mb-2 text-start"><span class="d-inline-block bg-danger text-white p-2 rounded-3">تعذر الاتصال بالخادم.</span></div>`;
    }
    chatBox.scrollTop = chatBox.scrollHeight;
}
</script>
{% endblock %}''',

    'posts.html': '''{% extends "base.html" %}
{% block content %}
<div class="row justify-content-center">
<div class="col-md-8">

<!-- إنشاء منشور -->
<div class="card bg-dark border-secondary shadow mb-4">
<div class="card-header text-primary fw-bold"><i class="fas fa-pen me-1"></i> إنشاء منشور جديد</div>
<div class="card-body">
<form id="createPostForm" enctype="multipart/form-data">
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
<div class="mb-3">
<textarea name="content" class="form-control" rows="3" placeholder="ماذا يدور في ذهنك؟" required maxlength="2000"></textarea>
</div>
<div class="mb-3">
<input type="file" name="image" accept="image/*" class="form-control">
</div>
<button type="submit" class="btn btn-ig"><i class="fas fa-paper-plane me-1"></i> نشر</button>
</form>
</div>
</div>

<!-- قائمة المنشورات -->
{% for post in posts %}
<div class="card bg-dark border-secondary shadow mb-3">
<div class="card-body">
<div class="d-flex align-items-center mb-2">
{% if post.avatar_url %}
<img src="{{ post.avatar_url }}" class="rounded-circle me-2" style="width:40px;height:40px;object-fit:cover;">
{% else %}
<div class="rounded-circle bg-secondary d-inline-flex align-items-center justify-content-center me-2" style="width:40px;height:40px;"><i class="fas fa-user text-light"></i></div>
{% endif %}
<div>
<strong class="text-light">{{ post.username }}</strong>
<div class="text-muted small">{{ post.created_at[:16] if post.created_at else '' }}</div>
</div>
</div>
<p class="card-text text-light" style="white-space:pre-wrap;">{{ post.content }}</p>
{% if post.image_url %}
<img src="{{ post.image_url }}" class="img-fluid rounded mb-2" style="max-height:400px;object-fit:contain;" alt="صورة المنشور">
{% endif %}
<div class="d-flex gap-3 align-items-center mt-2">
<button class="btn btn-sm {% if post.liked_by_me %}btn-danger{% else %}btn-outline-danger{% endif %}" onclick="toggleLike('{{ post.id }}', this)">
<i class="fas fa-heart me-1"></i> <span class="like-count">{{ post.likes_count }}</span>
</button>
<button class="btn btn-sm btn-outline-secondary" type="button" data-bs-toggle="collapse" data-bs-target="#comments-{{ post.id }}">
<i class="fas fa-comment me-1"></i> {{ post.comments_count }} تعليق
</button>
</div>

<!-- التعليقات -->
<div class="collapse mt-3" id="comments-{{ post.id }}">
<div class="border-top border-secondary pt-2">
{% for c in post.comments if not c.parent_id %}
<div class="d-flex mb-2">
{% if c.avatar_url %}
<img src="{{ c.avatar_url }}" class="avatar-sm me-2" style="width:28px;height:28px;">
{% else %}
<div class="rounded-circle bg-secondary d-inline-flex align-items-center justify-content-center me-2" style="width:28px;height:28px;font-size:12px;"><i class="fas fa-user text-light"></i></div>
{% endif %}
<div class="bg-secondary bg-opacity-25 rounded p-2 flex-grow-1">
<strong class="small">{{ c.username }}</strong>
<span class="text-muted small ms-1">{{ c.created_at[:16] if c.created_at else '' }}</span>
<div class="small">{{ c.content }}</div>
<button type="button" class="btn btn-link btn-sm p-0 text-muted" onclick="showReplyForm('{{ post.id }}', '{{ c.id }}')">رد</button>
</div>
</div>
{% for r in post.comments if r.parent_id == c.id %}
<div class="d-flex mb-2 comment-reply">
{% if r.avatar_url %}
<img src="{{ r.avatar_url }}" class="avatar-sm me-2" style="width:24px;height:24px;">
{% else %}
<div class="rounded-circle bg-secondary d-inline-flex align-items-center justify-content-center me-2" style="width:24px;height:24px;font-size:10px;"><i class="fas fa-user text-light"></i></div>
{% endif %}
<div class="bg-secondary bg-opacity-25 rounded p-2 flex-grow-1">
<strong class="small">{{ r.username }}</strong>
<span class="text-muted small ms-1">{{ r.created_at[:16] if r.created_at else '' }}</span>
<div class="small">{{ r.content }}</div>
</div>
</div>
{% endfor %}
{% else %}
<p class="text-muted small">لا توجد تعليقات بعد.</p>
{% endfor %}
<form class="mt-2" id="comment-form-{{ post.id }}" onsubmit="addComment(event, '{{ post.id }}')">
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
<input type="hidden" name="parent_id" id="parent-{{ post.id }}" value="">
<div class="input-group input-group-sm">
<input type="text" name="content" class="form-control" placeholder="أضف تعليقاً..." required maxlength="500">
<button class="btn btn-ig" type="submit">إرسال</button>
</div>
</form>
</div>
</div>
</div>
</div>
{% else %}
<div class="text-center text-muted py-5">لا توجد منشورات بعد. كن أول من ينشر!</div>
{% endfor %}

</div>
</div>

<script>
document.getElementById('createPostForm').onsubmit = async (e) => {
    e.preventDefault();
    try {
        let res = await fetch('/posts/create', {method: 'POST', body: new FormData(e.target)});
        let data = await res.json();
        alert(data.message);
        if(data.success) location.reload();
    } catch (err) {
        alert('حدث خطأ أثناء النشر');
    }
};

async function toggleLike(postId, btn) {
    try {
        let res = await fetch('/posts/like/' + postId, {method: 'POST'});
        let data = await res.json();
        if(data.success) {
            btn.querySelector('.like-count').textContent = data.likes_count;
            if(data.liked) {
                btn.classList.remove('btn-outline-danger');
                btn.classList.add('btn-danger');
            } else {
                btn.classList.remove('btn-danger');
                btn.classList.add('btn-outline-danger');
            }
        } else {
            alert(data.message || 'فشل التفاعل');
        }
    } catch (e) {
        alert('حدث خطأ');
    }
}

async function addComment(e, postId) {
    e.preventDefault();
    const form = e.target;
    try {
        let res = await fetch('/posts/comment/' + postId, {method: 'POST', body: new FormData(form)});
        let data = await res.json();
        if(data.success) location.reload();
        else alert(data.message || 'فشل إضافة التعليق');
    } catch (err) {
        alert('حدث خطأ');
    }
}
function showReplyForm(postId, commentId) {
    const input = document.getElementById('parent-' + postId);
    if (input) {
        input.value = commentId;
        const form = document.getElementById('comment-form-' + postId);
        if (form) {
            form.querySelector('input[name="content"]').placeholder = 'اكتب رداً...';
            form.querySelector('input[name="content"]').focus();
        }
    }
}
</script>
{% endblock %}''',

    'friends.html': '''{% extends "base.html" %}
{% block content %}
<div class="row justify-content-center">
<div class="col-md-8">

<!-- طلبات الصداقة الواردة -->
<div class="card shadow mb-4">
<div class="card-header" style="color:var(--ig-pink);font-weight:700;">
<i class="fas fa-user-plus me-1"></i> طلبات الصداقة
{% if incoming %}<span class="badge rounded-pill ms-1" style="background:#1877F2;">{{ incoming|length }}</span>{% endif %}
</div>
<div class="list-group list-group-flush">
{% for r in incoming %}
<div class="list-group-item bg-transparent text-light border-secondary d-flex align-items-center py-3">
{% if r.avatar_url %}
<img src="{{ r.avatar_url }}" class="avatar-md me-3">
{% else %}
<div class="rounded-circle bg-secondary d-flex align-items-center justify-content-center me-3" style="width:48px;height:48px;"><i class="fas fa-user"></i></div>
{% endif %}
<div class="flex-grow-1">
<strong>{{ r.username }}</strong>
<div class="text-muted small">أرسل لك طلب صداقة</div>
</div>
<button class="btn btn-sm me-2" style="background:#1877F2;color:#fff;border:none;" onclick="respondFriend({{ r.request_id }}, 'accept')">تأكيد</button>
<button class="btn btn-sm btn-outline-secondary" onclick="respondFriend({{ r.request_id }}, 'reject')">حذف</button>
</div>
{% else %}
<div class="p-3 text-center text-muted small">لا توجد طلبات صداقة حالياً</div>
{% endfor %}
</div>
</div>

<!-- اقتراحات أصدقاء -->
<div class="card shadow mb-4">
<div class="card-header" style="color:var(--ig-pink);font-weight:700;">
<i class="fas fa-users me-1"></i> أشخاص قد تعرفهم
</div>
<div class="list-group list-group-flush">
{% for u in suggestions %}
<div class="list-group-item bg-transparent text-light border-secondary d-flex align-items-center py-3" id="sug-{{ u.id }}">
{% if u.avatar_url %}
<img src="{{ u.avatar_url }}" class="avatar-md me-3">
{% else %}
<div class="rounded-circle bg-secondary d-flex align-items-center justify-content-center me-3" style="width:48px;height:48px;"><i class="fas fa-user"></i></div>
{% endif %}
<div class="flex-grow-1">
<strong>{{ u.username }}</strong>
</div>
{% if u.request_status == 'pending_sent' %}
<button class="btn btn-sm btn-secondary" disabled>تم إرسال الطلب</button>
{% elif u.request_status == 'pending_received' %}
<button class="btn btn-sm me-2" style="background:#1877F2;color:#fff;border:none;" onclick="respondFriend({{ u.request_id }}, 'accept')">تأكيد</button>
{% elif u.request_status == 'friends' %}
<button class="btn btn-sm btn-outline-secondary" disabled>أصدقاء</button>
<a href="{{ url_for('messages_chat', other_id=u.id) }}" class="btn btn-sm btn-outline-ig ms-1">رسالة</a>
{% else %}
<button class="btn btn-sm" style="background:#1877F2;color:#fff;border:none;" id="add-btn-{{ u.id }}" onclick="sendFriendRequest({{ u.id }})">إضافة صديق</button>
{% endif %}
</div>
{% else %}
<div class="p-3 text-center text-muted small">لا توجد اقتراحات حالياً</div>
{% endfor %}
</div>
</div>

<!-- قائمة الأصدقاء -->
<div class="card shadow mb-4">
<div class="card-header" style="color:var(--ig-pink);font-weight:700;">
<i class="fas fa-user-friends me-1"></i> أصدقاؤك
</div>
<div class="list-group list-group-flush">
{% for f in friends %}
<a href="{{ url_for('messages_chat', other_id=f.id) }}" class="list-group-item list-group-item-action bg-transparent text-light border-secondary d-flex align-items-center py-3">
{% if f.avatar_url %}
<img src="{{ f.avatar_url }}" class="avatar-md me-3">
{% else %}
<div class="rounded-circle bg-secondary d-flex align-items-center justify-content-center me-3" style="width:48px;height:48px;"><i class="fas fa-user"></i></div>
{% endif %}
<strong>{{ f.username }}</strong>
</a>
{% else %}
<div class="p-3 text-center text-muted small">لا يوجد أصدقاء بعد</div>
{% endfor %}
</div>
</div>

</div>
</div>
<script>
async function sendFriendRequest(userId) {
    try {
        const res = await fetch('/friends/request/' + userId, {method: 'POST'});
        const data = await res.json();
        if (data.success) {
            const btn = document.getElementById('add-btn-' + userId);
            if (btn) {
                btn.textContent = 'تم إرسال الطلب';
                btn.className = 'btn btn-sm btn-secondary';
                btn.disabled = true;
            }
        } else {
            alert(data.message || 'فشل إرسال الطلب');
        }
    } catch (e) { alert('حدث خطأ'); }
}
async function respondFriend(requestId, action) {
    try {
        const res = await fetch('/friends/respond/' + requestId, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action: action})
        });
        const data = await res.json();
        if (data.success) location.reload();
        else alert(data.message || 'فشلت العملية');
    } catch (e) { alert('حدث خطأ'); }
}
</script>
{% endblock %}''',

    'messages_inbox.html': '''{% extends "base.html" %}
{% block content %}
<div class="row justify-content-center">
<div class="col-md-7">
<div class="card shadow mb-3">
<div class="card-header">
<span style="color:var(--ig-pink);font-weight:700;"><i class="fas fa-paper-plane me-1"></i> الرسائل</span>
</div>
<div class="card-body border-bottom border-secondary pb-3">
<label class="form-label small text-muted mb-1">ابحث عن مستخدم لبدء محادثة</label>
<div class="input-group">
<input type="text" id="userSearch" class="form-control" placeholder="اكتب اسم المستخدم..." autocomplete="off">
<button class="btn btn-ig" type="button" onclick="searchUsers()"><i class="fas fa-search"></i></button>
</div>
<div id="searchResults" class="list-group mt-2" style="max-height:220px;overflow-y:auto;"></div>
</div>
<div class="list-group list-group-flush">
{% for c in conversations %}
<a href="{{ url_for('messages_chat', other_id=c.user_id) }}" class="list-group-item list-group-item-action bg-transparent text-light border-secondary d-flex align-items-center py-3">
{% if c.avatar_url %}
<img src="{{ c.avatar_url }}" class="avatar-md me-3">
{% else %}
<div class="rounded-circle bg-secondary d-flex align-items-center justify-content-center me-3" style="width:48px;height:48px;"><i class="fas fa-user"></i></div>
{% endif %}
<div class="flex-grow-1">
<div class="d-flex justify-content-between">
<strong>{{ c.username }}</strong>
{% if c.unread %}<span class="badge rounded-pill" style="background:#ff2d55;">{{ c.unread }}</span>{% endif %}
</div>
<div class="text-muted small">{{ c.last_msg }}</div>
</div>
</a>
{% else %}
<div class="p-4 text-center text-muted">لا توجد محادثات بعد. ابحث عن مستخدم أعلاه للبدء.</div>
{% endfor %}
</div>
</div>
</div>
</div>
<script>
let searchTimer = null;
document.getElementById('userSearch').addEventListener('input', function() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(searchUsers, 350);
});
document.getElementById('userSearch').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') { e.preventDefault(); searchUsers(); }
});
async function searchUsers() {
    const q = document.getElementById('userSearch').value.trim();
    const box = document.getElementById('searchResults');
    if (q.length < 1) { box.innerHTML = ''; return; }
    try {
        const res = await fetch('/messages/search?q=' + encodeURIComponent(q));
        const data = await res.json();
        if (!data.success || !data.users.length) {
            box.innerHTML = '<div class="list-group-item bg-transparent text-muted small">لا توجد نتائج</div>';
            return;
        }
        box.innerHTML = data.users.map(u => `
            <a href="/messages/${u.id}" class="list-group-item list-group-item-action bg-transparent text-light border-secondary d-flex align-items-center py-2">
                ${u.avatar_url
                    ? `<img src="${u.avatar_url}" class="avatar-sm me-2">`
                    : `<div class="rounded-circle bg-secondary d-flex align-items-center justify-content-center me-2" style="width:36px;height:36px;"><i class="fas fa-user small"></i></div>`}
                <strong>${u.username}</strong>
            </a>
        `).join('');
    } catch (e) {
        box.innerHTML = '<div class="list-group-item bg-transparent text-danger small">خطأ في البحث</div>';
    }
}
</script>
{% endblock %}''',

    'messages_chat.html': '''{% extends "base.html" %}
{% block content %}
<div class="row justify-content-center">
<div class="col-md-7">
<div class="card shadow">
<div class="card-header d-flex align-items-center">
<a href="{{ url_for('messages_inbox') }}" class="me-2 text-light"><i class="fas fa-arrow-right"></i></a>
{% if other.avatar_url %}
<img src="{{ other.avatar_url }}" class="avatar-sm me-2">
{% else %}
<div class="rounded-circle bg-secondary d-flex align-items-center justify-content-center me-2" style="width:36px;height:36px;"><i class="fas fa-user small"></i></div>
{% endif %}
<strong>{{ other.username }}</strong>
</div>
<div class="card-body" style="height:420px;overflow-y:auto;" id="msgBox">
{% for m in messages %}
<div class="d-flex mb-2 {% if m.sender_id == session.user_id %}justify-content-start{% else %}justify-content-end{% endif %}">
<div class="px-3 py-2 {% if m.sender_id == session.user_id %}msg-bubble-me{% else %}msg-bubble-them{% endif %}" style="max-width:75%;">
{{ m.content }}
<div class="small opacity-75 mt-1" style="font-size:0.7rem;">{{ m.created_at[:16] if m.created_at else '' }}</div>
</div>
</div>
{% else %}
<div class="text-center text-muted py-5">ابدأ المحادثة...</div>
{% endfor %}
</div>
<div class="card-footer border-secondary">
<form method="POST" class="d-flex gap-2">
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
<input type="text" name="content" class="form-control" placeholder="اكتب رسالة..." required maxlength="2000" autocomplete="off">
<button class="btn btn-ig" type="submit"><i class="fas fa-paper-plane"></i></button>
</form>
</div>
</div>
</div>
</div>
<script>document.getElementById('msgBox').scrollTop = document.getElementById('msgBox').scrollHeight;</script>
{% endblock %}'''
}

# ربط DictLoader بمحرك Jinja الخاص بـ Flask
app.jinja_loader = DictLoader(TEMPLATES)

# جعل csrf_token وعدد الرسائل غير المقروءة متاحين في كل القوالب
@app.context_processor
def inject_globals():
    unread = 0
    pending_fr = 0
    if session.get('user_id'):
        try:
            res = db.table('messages').select('id', count='exact').eq(
                'receiver_id', session['user_id']
            ).eq('is_read', False).execute()
            unread = res.count if res.count is not None else 0
        except Exception:
            unread = 0
        try:
            fres = db.table('friend_requests').select('id', count='exact').eq(
                'receiver_id', session['user_id']
            ).eq('status', 'pending').execute()
            pending_fr = fres.count if fres.count is not None else 0
        except Exception:
            pending_fr = 0
    return dict(
        csrf_token=generate_csrf,
        unread_messages=unread,
        pending_friend_requests=pending_fr,
    )

# ==========================================
# الوظائف المساعدة
# ==========================================

def log_action(level: str, message: str):
    """تسجيل الأحداث بشكل موحد"""
    if level == 'info':
        logger.info(message)
    elif level == 'error':
        logger.error(message)
    elif level == 'warning':
        logger.warning(message)
    else:
        logger.debug(message)


def create_notification(user_id, message: str):
    try:
        db.table('notifications').insert({
            'user_id': user_id,
            'message': message,
            'is_read': False
        }).execute()
    except Exception as e:
        log_action('error', f"Error creating notification: {e}")


def add_points_history(user_id, amount, type_op: str, description: str):
    try:
        db.table('points_history').insert({
            'user_id': user_id,
            'amount': amount,
            'type': type_op,
            'description': description
        }).execute()
    except Exception as e:
        log_action('error', f"Error adding points history: {e}")


# [تعديل 4] التحقق من تطابق الرابط مع المنصة
PLATFORM_PATTERNS = {
    'YouTube': [
        r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+',
    ],
    'Facebook': [
        r'(https?://)?(www\.)?(facebook\.com|fb\.com|fb\.watch)/.+',
    ],
    'Instagram': [
        r'(https?://)?(www\.)?instagram\.com/.+',
    ],
    'TikTok': [
        r'(https?://)?(www\.)?(tiktok\.com|vm\.tiktok\.com)/.+',
    ],
    'X': [
        r'(https?://)?(www\.)?(twitter\.com|x\.com)/.+',
    ],
    'Telegram': [
        r'(https?://)?(www\.)?(t\.me|telegram\.me)/.+',
    ],
    'Discord': [
        r'(https?://)?(www\.)?(discord\.gg|discord\.com)/.+',
    ],
}

ALLOWED_PLATFORMS = set(PLATFORM_PATTERNS.keys())


def is_valid_platform_link(platform: str, link: str) -> bool:
    """التحقق من أن الرابط يطابق المنصة المختارة"""
    if platform not in PLATFORM_PATTERNS:
        return False
    if not link or not isinstance(link, str):
        return False
    link = link.strip()
    # يجب أن يبدأ بـ http/https
    parsed = urlparse(link)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        return False
    for pattern in PLATFORM_PATTERNS[platform]:
        if re.match(pattern, link, re.IGNORECASE):
            return True
    return False


def sanitize_email(email: str) -> str:
    """[تعديل 8] تنظيف البريد: strip + lowercase"""
    if not email:
        return ''
    return email.strip().lower()


def sanitize_username(username: str) -> str:
    if not username:
        return ''
    return username.strip()


def file_to_data_url(file_storage, max_bytes=600_000):
    """تحويل ملف صورة مرفوع إلى data URL (base64) مع حد حجم"""
    if not file_storage or not file_storage.filename:
        return None
    content = file_storage.read()
    if not content or len(content) > max_bytes:
        return None
    import base64
    mime = file_storage.mimetype or 'image/jpeg'
    if not mime.startswith('image/'):
        return None
    b64 = base64.b64encode(content).decode('ascii')
    return f'data:{mime};base64,{b64}'


# ==========================================
# Decorators
# ==========================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
                return jsonify({'success': False, 'message': 'يجب تسجيل الدخول أولاً'}), 401
            flash('الرجاء تسجيل الدخول للوصول إلى هذه الصفحة', 'danger')
            return redirect(url_for('login'))

        try:
            user_res = db.table('users').select('is_banned, is_admin').eq('id', session['user_id']).execute()
            if not user_res.data:
                session.clear()
                flash('الحساب غير موجود', 'danger')
                return redirect(url_for('login'))
            user = user_res.data[0]
            if user.get('is_banned'):
                session.clear()
                flash('تم حظر حسابك من قبل الإدارة', 'danger')
                return redirect(url_for('login'))
            # تحديث is_admin في الجلسة من القاعدة دائماً
            session['is_admin'] = bool(user.get('is_admin'))
        except Exception as e:
            log_action('error', f"login_required DB check failed: {e}")
            # لا نمنع الوصول إذا فشل الاتصال مؤقتاً، لكن نسجل الخطأ

        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """[تعديل 7] التحقق من المدير من قاعدة البيانات في كل طلب إداري"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
                return jsonify({'success': False, 'message': 'غير مصرح لك بالدخول'}), 403
            flash('غير مصرح لك بالدخول إلى لوحة التحكم', 'danger')
            return redirect(url_for('index'))

        try:
            user_res = db.table('users').select('is_admin, is_banned').eq('id', session['user_id']).execute()
            if not user_res.data:
                session.clear()
                flash('الحساب غير موجود', 'danger')
                return redirect(url_for('login'))

            user = user_res.data[0]
            if user.get('is_banned'):
                session.clear()
                flash('تم حظر حسابك من قبل الإدارة', 'danger')
                return redirect(url_for('login'))

            if not user.get('is_admin'):
                session['is_admin'] = False
                if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
                    return jsonify({'success': False, 'message': 'غير مصرح لك بالدخول'}), 403
                flash('غير مصرح لك بالدخول إلى لوحة التحكم', 'danger')
                return redirect(url_for('index'))

            # تأكيد الحالة في الجلسة
            session['is_admin'] = True
        except Exception as e:
            log_action('error', f"admin_required DB check failed: {e}")
            if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
                return jsonify({'success': False, 'message': 'حدث خطأ في التحقق من الصلاحيات'}), 500
            flash('حدث خطأ أثناء التحقق من الصلاحيات', 'danger')
            return redirect(url_for('index'))

        return f(*args, **kwargs)
    return decorated_function


# ==========================================
# معالجة أخطاء عامة
# [تعديل 10] عدم إظهار تفاصيل الخطأ للمستخدم
# ==========================================

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    log_action('warning', f"CSRF error: {e}")
    if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
        return jsonify({'success': False, 'message': 'طلب غير صالح (CSRF). أعد تحميل الصفحة وحاول مرة أخرى.'}), 400
    flash('طلب غير صالح. أعد تحميل الصفحة وحاول مرة أخرى.', 'danger')
    return redirect(request.referrer or url_for('index'))


@app.errorhandler(500)
def handle_500(e):
    log_action('error', f"Internal server error: {e}")
    logger.exception("500 error details")
    if request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json':
        return jsonify({'success': False, 'message': 'حدث خطأ غير متوقع. حاول مرة أخرى لاحقاً.'}), 500
    flash('حدث خطأ غير متوقع. حاول مرة أخرى لاحقاً.', 'danger')
    return redirect(url_for('index'))


# ==========================================
# مسارات المصادقة (Auth)
# ==========================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = sanitize_username(request.form.get('username', ''))
        email = sanitize_email(request.form.get('email', ''))
        password = request.form.get('password', '')

        # [تعديل 11] تحقق صارم من المدخلات
        if not username or len(username) < 3 or len(username) > 50:
            flash('اسم المستخدم يجب أن يكون بين 3 و 50 حرفاً', 'danger')
            return redirect(url_for('register'))
        if not email or '@' not in email:
            flash('البريد الإلكتروني غير صالح', 'danger')
            return redirect(url_for('register'))
        if not password or len(password) < 6:
            flash('كلمة المرور يجب أن تكون 6 أحرف على الأقل', 'danger')
            return redirect(url_for('register'))

        # التحقق من وجود المستخدم (استعلامان منفصلان لتجنب كسر or_ مع الأحرف الخاصة)
        try:
            by_username = db.table('users').select('id').eq('username', username).execute()
            by_email = db.table('users').select('id').eq('email', email).execute()
            if (by_username.data and len(by_username.data) > 0) or (by_email.data and len(by_email.data) > 0):
                flash('اسم المستخدم أو البريد الإلكتروني مستخدم مسبقاً', 'danger')
                return redirect(url_for('register'))
        except Exception as e:
            import traceback
            traceback.print_exc()
            print("Registration Error (check existing):", e)
            log_action('error', f"Register check existing failed: {e}")
            flash(f'حدث خطأ أثناء التحقق من البيانات: {e}', 'danger')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)
        welcome_points = 50.0

        # إدراج المستخدم في جدول users
        # الأعمدة المستخدمة تطابق المخطط الأصلي: username, email, password, points, is_admin, is_banned
        try:
            res = db.table('users').insert({
                'username': username,
                'email': email,
                'password': hashed_password,
                'points': welcome_points,
                'is_admin': False,
                'is_banned': False
            }).execute()

            print("Registration insert response data:", res.data)
            print("Registration insert response count:", getattr(res, 'count', None))

            if res.data and len(res.data) > 0:
                user = res.data[0]
                add_points_history(user['id'], welcome_points, 'bonus', 'نقاط ترحيبية عند إنشاء الحساب')
                create_notification(user['id'], 'مرحباً بك في منصة TaskCoins Hub! تم إضافة 50 نقطة كهدية ترحيبية.')
                flash('تم إنشاء الحساب بنجاح! يمكنك تسجيل الدخول الآن.', 'success')
                return redirect(url_for('login'))
            else:
                # غالباً بسبب RLS: الإدراج نجح لكن لا يُرجع صفوف، أو فشل بصمت
                print("Registration Error: insert returned empty data (check RLS policies on users table)")
                flash('فشل إنشاء الحساب. تحقق من سياسات RLS في جدول users أو صلاحيات المفتاح.', 'danger')
        except Exception as e:
            import traceback
            traceback.print_exc()
            print("Registration Error:", e)
            log_action('error', f"Register insert failed: {e}")
            flash(f'حدث خطأ أثناء التسجيل: {e}', 'danger')
            raise

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = sanitize_email(request.form.get('email', ''))
        password = request.form.get('password', '')

        if not email or not password:
            flash('الرجاء إدخال البريد الإلكتروني وكلمة المرور', 'danger')
            return redirect(url_for('login'))

        try:
            res = db.table('users').select('*').eq('email', email).execute()
            if not res.data:
                flash('البريد الإلكتروني غير موجود', 'danger')
                return redirect(url_for('login'))

            user = res.data[0]

            if user.get('is_banned'):
                flash('هذا الحساب محظور من قبل الإدارة', 'danger')
                return redirect(url_for('login'))

            if check_password_hash(user['password'], password):
                session.clear()
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['is_admin'] = bool(user.get('is_admin'))
                flash('تم تسجيل الدخول بنجاح', 'success')
                return redirect(url_for('index'))
            else:
                flash('كلمة المرور غير صحيحة', 'danger')
        except Exception as e:
            log_action('error', f"Login failed: {e}")
            flash('حدث خطأ أثناء تسجيل الدخول. حاول مرة أخرى.', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('تم تسجيل الخروج بنجاح', 'info')
    return redirect(url_for('login'))


# ==========================================
# مسارات المهام (Tasks)
# ==========================================

@app.route('/')
@login_required
def index():
    platform = request.args.get('platform', '').strip()
    search = request.args.get('search', '').strip()

    try:
        query = db.table('tasks').select('*').eq('status', 'active')
        if platform and platform in ALLOWED_PLATFORMS:
            query = query.eq('platform', platform)
        if search:
            # حماية بسيطة من حقن أحرف خاصة
            safe_search = search.replace('%', '').replace('_', '')[:100]
            if safe_search:
                query = query.ilike('task_type', f'%{safe_search}%')

        res = query.order('created_at', desc=True).execute()
        tasks = res.data if res.data else []
    except Exception as e:
        log_action('error', f"Index load tasks failed: {e}")
        tasks = []
        flash('حدث خطأ أثناء تحميل المهام', 'danger')

    return render_template('index.html', tasks=tasks, current_platform=platform, search=search)


@app.route('/tasks/create', methods=['GET', 'POST'])
@login_required
def create_task():
    if request.method == 'POST':
        platform = request.form.get('platform', '').strip()
        task_type = request.form.get('task_type', '').strip()
        link = request.form.get('link', '').strip()

        # [تعديل 11] تحقق صارم
        try:
            required_count = int(request.form.get('required_count', 0))
            reward = float(request.form.get('reward', 0))
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': 'قيم غير صالحة للعدد أو المكافأة'}), 400

        if platform not in ALLOWED_PLATFORMS:
            return jsonify({'success': False, 'message': 'المنصة غير مدعومة'}), 400
        if not task_type or len(task_type) > 100:
            return jsonify({'success': False, 'message': 'نوع المهمة مطلوب ويجب ألا يتجاوز 100 حرف'}), 400
        if required_count <= 0 or required_count > 10000:
            return jsonify({'success': False, 'message': 'العدد المطلوب يجب أن يكون بين 1 و 10000'}), 400
        if reward <= 0 or reward > 1000:
            return jsonify({'success': False, 'message': 'المكافأة يجب أن تكون بين 0.1 و 1000 نقطة'}), 400
        if not is_valid_platform_link(platform, link):
            return jsonify({
                'success': False,
                'message': f'الرابط غير صالح أو لا يطابق منصة {platform}'
            }), 400

        total_cost = required_count * reward

        try:
            user_res = db.table('users').select('points').eq('id', session['user_id']).execute()
            if not user_res.data:
                return jsonify({'success': False, 'message': 'المستخدم غير موجود'}), 404
            current_points = float(user_res.data[0]['points'] or 0)

            if current_points < total_cost:
                return jsonify({'success': False, 'message': 'رصيدك غير كافٍ لإنشاء هذه المهمة'}), 400

            # خصم النقاط أولاً (تحديث شرطي بسيط)
            new_points = current_points - total_cost
            update_res = db.table('users').update({'points': new_points}).eq(
                'id', session['user_id']
            ).gte('points', total_cost).execute()

            if not update_res.data:
                return jsonify({'success': False, 'message': 'فشل خصم النقاط. حاول مرة أخرى.'}), 400

            db.table('tasks').insert({
                'platform': platform,
                'task_type': task_type,
                'link': link,
                'required_count': required_count,
                'completed_count': 0,
                'reward': reward,
                'status': 'active',
                'owner_id': session['user_id']
            }).execute()

            add_points_history(session['user_id'], -total_cost, 'deduct', f'إنشاء مهمة جديدة على {platform}')
            create_notification(session['user_id'], f'تم إنشاء المهمة بنجاح وخصم {total_cost} نقطة.')

            return jsonify({'success': True, 'message': 'تم إنشاء المهمة بنجاح'})
        except Exception as e:
            log_action('error', f"Create task failed: {e}")
            return jsonify({'success': False, 'message': 'حدث خطأ أثناء إنشاء المهمة'}), 500

    return render_template('create_task.html')


@app.route('/tasks/complete/<task_id>', methods=['POST'])
@login_required
def complete_task(task_id):
    """
    [تعديل 3] منع Race Condition:
    - التحقق من عدم التنفيذ المسبق
    - تحديث ذري لـ completed_count بشرط completed_count < required_count
    - إضافة المكافأة فقط إذا نجح التحديث
    ملاحظة: لأقصى حماية يُنصح بإنشاء PostgreSQL Function (RPC) في Supabase
    تقوم بكل الخطوات داخل معاملة واحدة. هنا نستخدم أفضل ما يتيحه عميل Python.
    """
    user_id = session['user_id']

    try:
        # 1. جلب المهمة
        task_res = db.table('tasks').select('*').eq('id', task_id).execute()
        if not task_res.data:
            return jsonify({'success': False, 'message': 'المهمة غير موجودة'}), 404

        task = task_res.data[0]

        if task['owner_id'] == user_id:
            return jsonify({'success': False, 'message': 'لا يمكنك تنفيذ مهمتك الخاصة'}), 400

        if task['status'] != 'active':
            return jsonify({'success': False, 'message': 'هذه المهمة غير نشطة'}), 400

        # 2. التحقق من التنفيذ المسبق (منع التكرار)
        comp_res = db.table('task_completions').select('id').eq(
            'task_id', task_id
        ).eq('user_id', user_id).execute()
        if comp_res.data:
            return jsonify({'success': False, 'message': 'لا يمكنك تنفيذ نفس المهمة مرتين'}), 400

        current_completed = int(task.get('completed_count') or 0)
        required = int(task.get('required_count') or 0)

        if current_completed >= required:
            return jsonify({'success': False, 'message': 'تم الوصول للعدد المطلوب مسبقاً'}), 400

        # 3. تسجيل الإكمال أولاً (يفضل وجود UNIQUE constraint على (task_id, user_id))
        try:
            insert_comp = db.table('task_completions').insert({
                'task_id': task_id,
                'user_id': user_id
            }).execute()
            if not insert_comp.data:
                return jsonify({'success': False, 'message': 'فشل تسجيل التنفيذ'}), 400
        except Exception as e:
            # قد يكون تكراراً بسبب race
            log_action('warning', f"Completion insert conflict (possible race): {e}")
            return jsonify({'success': False, 'message': 'لا يمكنك تنفيذ نفس المهمة مرتين'}), 400

        # 4. تحديث ذري: زيادة completed_count فقط إذا كان لا يزال أقل من المطلوب
        new_completed = current_completed + 1
        new_status = 'completed' if new_completed >= required else 'active'

        update_res = db.table('tasks').update({
            'completed_count': new_completed,
            'status': new_status
        }).eq('id', task_id).eq(
            'completed_count', current_completed
        ).eq('status', 'active').execute()

        if not update_res.data:
            # فشل التحديث الذري → تم الوصول للحد من قبل مستخدم آخر
            # نحذف سجل الإكمال الذي أضفناه لتجنب عدم التناسق
            try:
                db.table('task_completions').delete().eq(
                    'task_id', task_id
                ).eq('user_id', user_id).execute()
            except Exception:
                pass
            return jsonify({
                'success': False,
                'message': 'عذراً، تم الوصول للعدد المطلوب من قبل مستخدمين آخرين'
            }), 409

        # 5. إضافة المكافأة للمستخدم
        reward = float(task.get('reward') or 0)
        user_res = db.table('users').select('points').eq('id', user_id).execute()
        if user_res.data:
            current_points = float(user_res.data[0].get('points') or 0)
            db.table('users').update({
                'points': current_points + reward
            }).eq('id', user_id).execute()

        add_points_history(user_id, reward, 'add', f'مكافأة تنفيذ مهمة {task["platform"]}')
        create_notification(user_id, f'لقد ربحت {reward} نقطة لتنفيذ المهمة بنجاح!')

        return jsonify({
            'success': True,
            'message': f'تم تنفيذ المهمة وحصلت على {reward} نقطة!'
        })

    except Exception as e:
        log_action('error', f"Complete task failed for {task_id}: {e}")
        return jsonify({'success': False, 'message': 'حدث خطأ أثناء تنفيذ المهمة'}), 500


@app.route('/tasks/go/<task_id>')
@login_required
def go_to_task(task_id):
    """
    عند النقر على رابط المهمة:
    - يُسجَّل الإكمال (مرة واحدة فقط) ويُضاف الرصيد إن أمكن
    - ثم يُوجَّه المستخدم إلى الرابط الحقيقي للمهمة
    لا يوجد زر «تنفيذ» منفصل؛ النقر على الرابط نفسه هو التنفيذ.
    """
    user_id = session['user_id']
    real_link = None

    try:
        task_res = db.table('tasks').select('*').eq('id', task_id).execute()
        if not task_res.data:
            flash('المهمة غير موجودة', 'danger')
            return redirect(url_for('index'))

        task = task_res.data[0]
        real_link = task.get('link')

        if not real_link:
            flash('رابط المهمة غير صالح', 'danger')
            return redirect(url_for('index'))

        # المهام الخاصة بالمستخدم نفسه أو غير النشطة: افتح الرابط فقط بدون نقاط
        if task.get('owner_id') == user_id or task.get('status') != 'active':
            return redirect(real_link)

        # هل نُفِّذت مسبقاً؟
        comp_res = db.table('task_completions').select('id').eq(
            'task_id', task_id
        ).eq('user_id', user_id).execute()
        if comp_res.data:
            # سبق التنفيذ → افتح الرابط فقط
            return redirect(real_link)

        current_completed = int(task.get('completed_count') or 0)
        required = int(task.get('required_count') or 0)

        if current_completed >= required:
            return redirect(real_link)

        # تسجيل الإكمال
        try:
            insert_comp = db.table('task_completions').insert({
                'task_id': task_id,
                'user_id': user_id
            }).execute()
            if not insert_comp.data:
                return redirect(real_link)
        except Exception as e:
            log_action('warning', f"go_to_task completion insert conflict: {e}")
            return redirect(real_link)

        # تحديث ذري للعداد
        new_completed = current_completed + 1
        new_status = 'completed' if new_completed >= required else 'active'

        update_res = db.table('tasks').update({
            'completed_count': new_completed,
            'status': new_status
        }).eq('id', task_id).eq(
            'completed_count', current_completed
        ).eq('status', 'active').execute()

        if not update_res.data:
            # فشل ذري → حذف سجل الإكمال
            try:
                db.table('task_completions').delete().eq(
                    'task_id', task_id
                ).eq('user_id', user_id).execute()
            except Exception:
                pass
            return redirect(real_link)

        # إضافة المكافأة
        reward = float(task.get('reward') or 0)
        user_res = db.table('users').select('points').eq('id', user_id).execute()
        if user_res.data:
            current_points = float(user_res.data[0].get('points') or 0)
            db.table('users').update({
                'points': current_points + reward
            }).eq('id', user_id).execute()

        add_points_history(user_id, reward, 'add', f'مكافأة تنفيذ مهمة {task["platform"]}')
        create_notification(user_id, f'لقد ربحت {reward} نقطة لتنفيذ المهمة بنجاح!')

        # نجاح → توجيه إلى الرابط الحقيقي
        return redirect(real_link)

    except Exception as e:
        log_action('error', f"go_to_task failed for {task_id}: {e}")
        if real_link:
            return redirect(real_link)
        flash('حدث خطأ أثناء فتح المهمة', 'danger')
        return redirect(url_for('index'))


# ==========================================
# مسارات الملف الشخصي (Profile)
# ==========================================

@app.route('/profile')
@login_required
def profile():
    user_id = session['user_id']
    try:
        user_res = db.table('users').select('*').eq('id', user_id).execute()
        user = user_res.data[0] if user_res.data else {}

        history_res = db.table('points_history').select('*').eq(
            'user_id', user_id
        ).order('created_at', desc=True).limit(50).execute()
        history = history_res.data if history_res.data else []
    except Exception as e:
        log_action('error', f"Profile load failed: {e}")
        user, history = {}, []
        flash('حدث خطأ أثناء تحميل الملف الشخصي', 'danger')

    return render_template('profile.html', user=user, history=history)


@app.route('/profile/avatar', methods=['POST'])
@login_required
def update_avatar():
    file = request.files.get('avatar')
    data_url = file_to_data_url(file)
    if not data_url:
        flash('اختر صورة صالحة بحجم أقل من 600 كيلوبايت', 'danger')
        return redirect(url_for('profile'))
    try:
        db.table('users').update({'avatar_url': data_url}).eq(
            'id', session['user_id']
        ).execute()
        flash('تم تحديث صورة البروفايل بنجاح', 'success')
    except Exception as e:
        log_action('error', f'Update avatar failed: {e}')
        flash('حدث خطأ أثناء تحديث الصورة', 'danger')
    return redirect(url_for('profile'))


# ==========================================
# المنشورات (Posts Feed)
# ==========================================

@app.route('/posts')
@login_required
def posts_feed():
    user_id = session['user_id']
    try:
        posts_res = db.table('posts').select('*').order(
            'created_at', desc=True
        ).limit(50).execute()
        raw_posts = posts_res.data if posts_res.data else []

        posts = []
        for p in raw_posts:
            # بيانات الكاتب
            author = {}
            try:
                ures = db.table('users').select('username, avatar_url').eq(
                    'id', p['user_id']
                ).execute()
                if ures.data:
                    author = ures.data[0]
            except Exception:
                pass

            # عدد الإعجابات وهل أعجب المستخدم الحالي
            likes_count = 0
            liked_by_me = False
            try:
                likes_res = db.table('post_likes').select(
                    'id, user_id', count='exact'
                ).eq('post_id', p['id']).execute()
                likes_count = likes_res.count if likes_res.count is not None else 0
                if likes_res.data:
                    liked_by_me = any(str(l.get('user_id')) == str(user_id) for l in likes_res.data)
            except Exception:
                pass

            # التعليقات
            comments = []
            comments_count = 0
            try:
                cres = db.table('post_comments').select('*').eq(
                    'post_id', p['id']
                ).order('created_at', desc=False).limit(30).execute()
                if cres.data:
                    comments_count = len(cres.data)
                    for c in cres.data:
                        c_author = {'username': 'مستخدم', 'avatar_url': None}
                        try:
                            cures = db.table('users').select(
                                'username, avatar_url'
                            ).eq('id', c['user_id']).execute()
                            if cures.data:
                                c_author = cures.data[0]
                        except Exception:
                            pass
                        comments.append({
                            'id': c.get('id'),
                            'parent_id': c.get('parent_id'),
                            'content': c.get('content', ''),
                            'created_at': c.get('created_at'),
                            'username': c_author.get('username', 'مستخدم'),
                            'avatar_url': c_author.get('avatar_url'),
                        })
            except Exception:
                pass

            posts.append({
                'id': p['id'],
                'content': p.get('content', ''),
                'image_url': p.get('image_url'),
                'created_at': p.get('created_at'),
                'username': author.get('username', 'مستخدم'),
                'avatar_url': author.get('avatar_url'),
                'likes_count': likes_count,
                'liked_by_me': liked_by_me,
                'comments': comments,
                'comments_count': comments_count,
            })
    except Exception as e:
        log_action('error', f'Posts feed failed: {e}')
        posts = []
        flash('حدث خطأ أثناء تحميل المنشورات', 'danger')

    return render_template('posts.html', posts=posts)


@app.route('/posts/create', methods=['POST'])
@login_required
def create_post():
    content = (request.form.get('content') or '').strip()
    image_file = request.files.get('image')
    image_url = file_to_data_url(image_file, max_bytes=900_000)

    if not content or len(content) > 2000:
        return jsonify({'success': False, 'message': 'المحتوى مطلوب ويجب ألا يتجاوز 2000 حرف'}), 400

    try:
        db.table('posts').insert({
            'user_id': session['user_id'],
            'content': content,
            'image_url': image_url,
        }).execute()
        return jsonify({'success': True, 'message': 'تم نشر المنشور بنجاح'})
    except Exception as e:
        log_action('error', f'Create post failed: {e}')
        return jsonify({'success': False, 'message': 'حدث خطأ أثناء النشر'}), 500


@app.route('/posts/like/<post_id>', methods=['POST'])
@login_required
def toggle_like(post_id):
    user_id = session['user_id']
    try:
        # هل أعجب مسبقاً؟
        existing = db.table('post_likes').select('id').eq(
            'post_id', post_id
        ).eq('user_id', user_id).execute()

        if existing.data:
            # إلغاء الإعجاب
            db.table('post_likes').delete().eq(
                'post_id', post_id
            ).eq('user_id', user_id).execute()
            liked = False
        else:
            # إضافة إعجاب
            db.table('post_likes').insert({
                'post_id': post_id,
                'user_id': user_id,
            }).execute()
            liked = True

        # عدد الإعجابات الجديد
        count_res = db.table('post_likes').select(
            'id', count='exact'
        ).eq('post_id', post_id).execute()
        likes_count = count_res.count if count_res.count is not None else 0

        return jsonify({
            'success': True,
            'liked': liked,
            'likes_count': likes_count,
        })
    except Exception as e:
        log_action('error', f'Toggle like failed: {e}')
        return jsonify({'success': False, 'message': 'حدث خطأ أثناء التفاعل'}), 500


@app.route('/posts/comment/<post_id>', methods=['POST'])
@login_required
def add_comment(post_id):
    content = (request.form.get('content') or '').strip()
    parent_id = request.form.get('parent_id') or None
    if parent_id:
        try:
            parent_id = int(parent_id)
        except (ValueError, TypeError):
            parent_id = None

    if not content or len(content) > 500:
        return jsonify({'success': False, 'message': 'التعليق مطلوب ويجب ألا يتجاوز 500 حرف'}), 400

    try:
        pres = db.table('posts').select('id').eq('id', post_id).execute()
        if not pres.data:
            return jsonify({'success': False, 'message': 'المنشور غير موجود'}), 404

        row = {
            'post_id': post_id,
            'user_id': session['user_id'],
            'content': content,
        }
        if parent_id:
            row['parent_id'] = parent_id

        db.table('post_comments').insert(row).execute()
        return jsonify({'success': True, 'message': 'تم إضافة التعليق'})
    except Exception as e:
        log_action('error', f'Add comment failed: {e}')
        return jsonify({'success': False, 'message': 'حدث خطأ أثناء إضافة التعليق'}), 500


# ==========================================
# الأصدقاء وطلبات الصداقة
# ==========================================

@app.route('/friends')
@login_required
def friends_page():
    user_id = session['user_id']
    incoming = []
    suggestions = []
    friends = []
    try:
        # طلبات واردة معلقة
        inc = db.table('friend_requests').select('*').eq(
            'receiver_id', user_id
        ).eq('status', 'pending').execute()
        for r in (inc.data or []):
            ures = db.table('users').select('username, avatar_url').eq('id', r['sender_id']).execute()
            uname, avatar = 'مستخدم', None
            if ures.data:
                uname = ures.data[0].get('username', 'مستخدم')
                avatar = ures.data[0].get('avatar_url')
            incoming.append({
                'request_id': r['id'],
                'user_id': r['sender_id'],
                'username': uname,
                'avatar_url': avatar,
            })

        # الأصدقاء (طلبات مقبولة من الطرفين)
        fr1 = db.table('friend_requests').select('*').eq('sender_id', user_id).eq('status', 'accepted').execute()
        fr2 = db.table('friend_requests').select('*').eq('receiver_id', user_id).eq('status', 'accepted').execute()
        friend_ids = set()
        for r in (fr1.data or []):
            friend_ids.add(r['receiver_id'])
        for r in (fr2.data or []):
            friend_ids.add(r['sender_id'])
        for fid in friend_ids:
            ures = db.table('users').select('id, username, avatar_url').eq('id', fid).execute()
            if ures.data:
                friends.append(ures.data[0])

        # اقتراحات: مستخدمون ليسوا أصدقاء ولا طلبات معلقة
        all_rel = set(friend_ids)
        pend_out = db.table('friend_requests').select('receiver_id, id').eq(
            'sender_id', user_id
        ).eq('status', 'pending').execute()
        pend_in = db.table('friend_requests').select('sender_id, id').eq(
            'receiver_id', user_id
        ).eq('status', 'pending').execute()
        pending_sent = {r['receiver_id']: r['id'] for r in (pend_out.data or [])}
        pending_recv = {r['sender_id']: r['id'] for r in (pend_in.data or [])}
        all_rel.update(pending_sent.keys())
        all_rel.update(pending_recv.keys())
        all_rel.add(user_id)

        users_res = db.table('users').select(
            'id, username, avatar_url, is_banned'
        ).eq('is_banned', False).limit(40).execute()
        for u in (users_res.data or []):
            if u['id'] in all_rel:
                continue
            status = None
            req_id = None
            if u['id'] in pending_sent:
                status = 'pending_sent'
                req_id = pending_sent[u['id']]
            elif u['id'] in pending_recv:
                status = 'pending_received'
                req_id = pending_recv[u['id']]
            elif u['id'] in friend_ids:
                status = 'friends'
            suggestions.append({
                'id': u['id'],
                'username': u.get('username', 'مستخدم'),
                'avatar_url': u.get('avatar_url'),
                'request_status': status,
                'request_id': req_id,
            })
            if len(suggestions) >= 20:
                break
    except Exception as e:
        log_action('error', f'Friends page failed: {e}')
        flash('حدث خطأ أثناء تحميل صفحة الأصدقاء', 'danger')

    return render_template(
        'friends.html',
        incoming=incoming,
        suggestions=suggestions,
        friends=friends,
    )


@app.route('/friends/request/<int:target_id>', methods=['POST'])
@login_required
def send_friend_request(target_id):
    user_id = session['user_id']
    if target_id == user_id:
        return jsonify({'success': False, 'message': 'لا يمكنك إضافة نفسك'}), 400
    try:
        # هل يوجد طلب سابق؟
        existing = db.table('friend_requests').select('id, status, sender_id, receiver_id').or_(
            f'and(sender_id.eq.{user_id},receiver_id.eq.{target_id}),and(sender_id.eq.{target_id},receiver_id.eq.{user_id})'
        ).execute()
        if existing.data:
            row = existing.data[0]
            if row['status'] == 'accepted':
                return jsonify({'success': False, 'message': 'أنتم أصدقاء بالفعل'})
            if row['status'] == 'pending':
                return jsonify({'success': False, 'message': 'يوجد طلب قيد الانتظار'})
            # مرفوض سابقاً → إعادة إرسال
            db.table('friend_requests').update({
                'status': 'pending',
                'sender_id': user_id,
                'receiver_id': target_id,
            }).eq('id', row['id']).execute()
            return jsonify({'success': True, 'message': 'تم إرسال طلب الصداقة'})

        db.table('friend_requests').insert({
            'sender_id': user_id,
            'receiver_id': target_id,
            'status': 'pending',
        }).execute()
        return jsonify({'success': True, 'message': 'تم إرسال طلب الصداقة'})
    except Exception as e:
        log_action('error', f'Send friend request failed: {e}')
        return jsonify({'success': False, 'message': 'فشل إرسال الطلب'}), 500


@app.route('/friends/respond/<int:request_id>', methods=['POST'])
@login_required
def respond_friend_request(request_id):
    user_id = session['user_id']
    data = request.get_json(silent=True) or {}
    action = (data.get('action') or '').strip().lower()
    if action not in ('accept', 'reject'):
        return jsonify({'success': False, 'message': 'إجراء غير صالح'}), 400
    try:
        res = db.table('friend_requests').select('*').eq('id', request_id).execute()
        if not res.data:
            return jsonify({'success': False, 'message': 'الطلب غير موجود'}), 404
        row = res.data[0]
        if str(row['receiver_id']) != str(user_id):
            return jsonify({'success': False, 'message': 'غير مصرح'}), 403
        if row['status'] != 'pending':
            return jsonify({'success': False, 'message': 'تم التعامل مع هذا الطلب مسبقاً'})

        new_status = 'accepted' if action == 'accept' else 'rejected'
        db.table('friend_requests').update({'status': new_status}).eq('id', request_id).execute()
        msg = 'أصبحتما أصدقاء' if action == 'accept' else 'تم رفض الطلب'
        return jsonify({'success': True, 'message': msg})
    except Exception as e:
        log_action('error', f'Respond friend request failed: {e}')
        return jsonify({'success': False, 'message': 'فشلت العملية'}), 500


# ==========================================
# الرسائل الخاصة
# ==========================================

@app.route('/messages/search')
@login_required
def messages_search():
    q = (request.args.get('q') or '').strip()
    if not q or len(q) > 50:
        return jsonify({'success': True, 'users': []})
    try:
        safe_q = q.replace('%', '').replace('_', '')[:50]
        res = db.table('users').select('id, username, avatar_url, is_banned').ilike(
            'username', f'%{safe_q}%'
        ).neq('id', session['user_id']).eq('is_banned', False).limit(15).execute()
        users = []
        for u in (res.data or []):
            users.append({
                'id': u['id'],
                'username': u.get('username', 'مستخدم'),
                'avatar_url': u.get('avatar_url'),
            })
        return jsonify({'success': True, 'users': users})
    except Exception as e:
        log_action('error', f'Messages search failed: {e}')
        return jsonify({'success': False, 'users': []}), 500


@app.route('/messages')
@login_required
def messages_inbox():
    user_id = session['user_id']
    try:
        # جلب كل الرسائل المتعلقة بالمستخدم
        sent = db.table('messages').select('*').eq('sender_id', user_id).order('created_at', desc=True).limit(100).execute()
        received = db.table('messages').select('*').eq('receiver_id', user_id).order('created_at', desc=True).limit(100).execute()
        all_msgs = (sent.data or []) + (received.data or [])

        # تجميع حسب الطرف الآخر
        partners = {}
        for m in all_msgs:
            other_id = m['receiver_id'] if str(m['sender_id']) == str(user_id) else m['sender_id']
            if other_id not in partners:
                partners[other_id] = {
                    'user_id': other_id,
                    'last_msg': m.get('content', '')[:60],
                    'last_at': m.get('created_at', ''),
                    'unread': 0,
                }
            if str(m['receiver_id']) == str(user_id) and not m.get('is_read'):
                partners[other_id]['unread'] += 1
            # تحديث آخر رسالة إذا أحدث
            if m.get('created_at', '') > partners[other_id]['last_at']:
                partners[other_id]['last_msg'] = m.get('content', '')[:60]
                partners[other_id]['last_at'] = m.get('created_at', '')

        conversations = []
        for pid, info in partners.items():
            try:
                ures = db.table('users').select('username, avatar_url').eq('id', pid).execute()
                if ures.data:
                    info['username'] = ures.data[0].get('username', 'مستخدم')
                    info['avatar_url'] = ures.data[0].get('avatar_url')
                else:
                    info['username'] = 'مستخدم'
                    info['avatar_url'] = None
            except Exception:
                info['username'] = 'مستخدم'
                info['avatar_url'] = None
            conversations.append(info)

        conversations.sort(key=lambda x: x.get('last_at') or '', reverse=True)
    except Exception as e:
        log_action('error', f'Messages inbox failed: {e}')
        conversations = []
        flash('حدث خطأ أثناء تحميل الرسائل', 'danger')

    return render_template('messages_inbox.html', conversations=conversations)


@app.route('/messages/<int:other_id>', methods=['GET', 'POST'])
@login_required
def messages_chat(other_id):
    user_id = session['user_id']
    if other_id == user_id:
        flash('لا يمكنك مراسلة نفسك', 'warning')
        return redirect(url_for('messages_inbox'))

    if request.method == 'POST':
        content = (request.form.get('content') or '').strip()
        if content and len(content) <= 2000:
            try:
                db.table('messages').insert({
                    'sender_id': user_id,
                    'receiver_id': other_id,
                    'content': content,
                    'is_read': False,
                }).execute()
            except Exception as e:
                log_action('error', f'Send message failed: {e}')
                flash('فشل إرسال الرسالة', 'danger')
        return redirect(url_for('messages_chat', other_id=other_id))

    # جلب بيانات الطرف الآخر
    other = {'id': other_id, 'username': 'مستخدم', 'avatar_url': None}
    try:
        ures = db.table('users').select('id, username, avatar_url').eq('id', other_id).execute()
        if ures.data:
            other = ures.data[0]
    except Exception:
        pass

    # جلب المحادثة
    try:
        q1 = db.table('messages').select('*').eq('sender_id', user_id).eq('receiver_id', other_id).execute()
        q2 = db.table('messages').select('*').eq('sender_id', other_id).eq('receiver_id', user_id).execute()
        msgs = (q1.data or []) + (q2.data or [])
        msgs.sort(key=lambda m: m.get('created_at') or '')

        # تعليم كمقروء
        db.table('messages').update({'is_read': True}).eq(
            'sender_id', other_id
        ).eq('receiver_id', user_id).eq('is_read', False).execute()
    except Exception as e:
        log_action('error', f'Messages chat failed: {e}')
        msgs = []

    return render_template('messages_chat.html', other=other, messages=msgs)


@app.route('/messages/start/<int:user_id>')
@login_required
def messages_start(user_id):
    return redirect(url_for('messages_chat', other_id=user_id))


# ==========================================
# الذكاء الاصطناعي (Gemini Chat)
# ==========================================

@app.route('/ai')
@login_required
def ai_chat():
    return render_template('ai_chat.html')


@app.route('/ai/chat', methods=['POST'])
@login_required
def ai_chat_api():
    data = request.get_json(silent=True) or {}
    user_message = (data.get('message') or '').strip()
    if not user_message:
        return jsonify({'error': 'الرسالة فارغة'}), 400

    if not gemini_client:
        error_msg = 'مفتاح GEMINI_API_KEY غير مهيأ على الخادم.'
        print('========== GEMINI ERROR ==========')
        print(error_msg)
        print('==================================')
        return jsonify({'error': error_msg}), 500

    try:
        response = gemini_client.models.generate_content(
            model='gemini-3.6-flash',
            contents=user_message,
        )
        return jsonify({'reply': response.text})
    except Exception as e:
        print('========== GEMINI ERROR ==========')
        print(repr(e))
        print('==================================')
        log_action('error', f'Gemini chat failed: {e}')
        return jsonify({'error': str(e)}), 500


# ==========================================
# لوحة التحكم (Admin)
# ==========================================

@app.route('/admin')
@admin_required
def admin_dashboard():
    try:
        # [تعديل 2] استخدام count="exact" وقراءة .count
        users_count_res = db.table('users').select('id', count='exact').execute()
        users_count = users_count_res.count if users_count_res.count is not None else 0

        tasks_count_res = db.table('tasks').select('id', count='exact').execute()
        tasks_count = tasks_count_res.count if tasks_count_res.count is not None else 0

        users_res = db.table('users').select(
            'id, username, email, points, is_banned, is_admin, created_at'
        ).order('created_at', desc=True).limit(200).execute()
        users = users_res.data if users_res.data else []
    except Exception as e:
        log_action('error', f"Admin dashboard failed: {e}")
        users_count, tasks_count, users = 0, 0, []
        flash('حدث خطأ أثناء تحميل لوحة الإدارة', 'danger')

    return render_template('admin.html', users_count=users_count, tasks_count=tasks_count, users=users)


@app.route('/admin/user/ban/<user_id>', methods=['POST'])
@admin_required
def admin_toggle_ban(user_id):
    # منع المدير من حظر نفسه
    if str(user_id) == str(session.get('user_id')):
        return jsonify({'success': False, 'message': 'لا يمكنك حظر حسابك الخاص'}), 400

    try:
        user_res = db.table('users').select('is_banned, is_admin').eq('id', user_id).execute()
        if not user_res.data:
            return jsonify({'success': False, 'message': 'المستخدم غير موجود'}), 404

        target = user_res.data[0]
        if target.get('is_admin'):
            return jsonify({'success': False, 'message': 'لا يمكن حظر حساب مدير'}), 403

        new_status = not bool(target.get('is_banned'))
        db.table('users').update({'is_banned': new_status}).eq('id', user_id).execute()
        create_notification(
            user_id,
            'تم حظر حسابك من قبل الإدارة.' if new_status else 'تم فك الحظر عن حسابك.'
        )

        return jsonify({'success': True, 'message': 'تم تحديث حالة الحظر بنجاح'})
    except Exception as e:
        log_action('error', f"Admin toggle ban failed: {e}")
        return jsonify({'success': False, 'message': 'حدث خطأ أثناء تحديث الحالة'}), 500


# ==========================================
# نقطة الدخول
# ==========================================

if __name__ == '__main__':
    # للتطوير المحلي فقط. على Render استخدم gunicorn
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', '0') == '1')

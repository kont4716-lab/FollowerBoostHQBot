# ==========================================
# TaskCoins Hub - الكود الكامل والجاهز للتشغيل (app.py)
# النسخة المعدلة والمحسنة بالكامل (متوافقة مع Python 3.12, Render, Supabase, و google-genai)
# ==========================================

import os
import re
import logging
from functools import wraps
from urllib.parse import urlparse

from flask import (
    Flask, request, redirect, url_for, session, flash, jsonify,
    render_template
)
from flask_wtf.csrf import CSRFProtect, generate_csrf, CSRFError
from werkzeug.security import generate_password_hash, check_password_hash
from jinja2 import DictLoader
from supabase import create_client, Client
from dotenv import load_dotenv

# استيراد مكتبة Gemini الرسمية الحديثة
from google import genai
from google.genai import errors as genai_errors

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
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get(
    'SECRET_KEY',
    'TaskCoinsHub-7f3a9c2e8b1d4f6a0e5c9b7d2a8f4e1c6b0d9a3f7e2c5b8a1d4f0e6c9b3a7'
)

app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
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
# إعداد عميل Google Gemini AI والنماذج الاحتياطية
# ==========================================
gemini_api_key = os.environ.get('GEMINI_API_KEY')
ai_client = None
if gemini_api_key:
    try:
        ai_client = genai.Client(api_key=gemini_api_key)
    except Exception as e:
        logger.error(f"Failed to initialize Gemini client: {e}")

# قائمة النماذج المرتبة حسب الأولوية لتجربتها تلقائياً في حال فشل أحدها
GEMINI_MODELS = [
    'gemini-2.5-flash',
    'gemini-2.0-flash',
    'gemini-1.5-flash',
    'gemini-1.5-pro'
]

# ==========================================
# نظام القوالب (DictLoader)
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
    <style>body { background-color: #121212; color: #e0e0e0; }</style>
</head>
<body data-bs-theme="dark">
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark border-bottom border-secondary mb-4">
        <div class="container">
            <a class="navbar-brand fw-bold text-primary" href="{{ url_for('index') }}"><i class="fas fa-coins me-2"></i>TaskCoins Hub</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav" aria-controls="navbarNav" aria-expanded="false" aria-label="Toggle navigation">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <div class="navbar-nav me-auto">
                    {% if session.get('user_id') %}
                    <a class="nav-link" href="{{ url_for('index') }}">المهام</a>
                    <a class="nav-link" href="{{ url_for('create_task') }}">إنشاء مهمة</a>
                    <a class="nav-link" href="{{ url_for('profile') }}">الملف الشخصي</a>
                    {% if session.get('is_admin') %}
                    <a class="nav-link text-warning" href="{{ url_for('admin_dashboard') }}">لوحة الإدارة</a>
                    {% endif %}
                    <a class="nav-link text-danger" href="{{ url_for('logout') }}">تسجيل الخروج</a>
                    {% endif %}
                </div>
            </div>
        </div>
    </nav>
    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for cat, msg in messages %}
                    <div class="alert alert-{{ cat }} alert-dismissible fade show" role="alert">{{ msg }}<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button></div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </div>

    <!-- زر اسأل الذكاء الاصطناعي العائم -->
    {% if session.get('user_id') %}
    <button type="button" class="btn btn-primary rounded-circle shadow-lg position-fixed bottom-0 end-0 m-4 d-flex align-items-center justify-content-center" style="width: 60px; height: 60px; z-index: 1050;" data-bs-toggle="modal" data-bs-target="#aiModal" title="اسأل الذكاء الاصطناعي">
        <i class="fas fa-robot fs-4"></i>
    </button>

    <!-- نافذة المحادثة (Modal) -->
    <div class="modal fade" id="aiModal" tabindex="-1" aria-labelledby="aiModalLabel" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered modal-lg">
            <div class="modal-content bg-dark border-secondary text-light shadow-lg">
                <div class="modal-header border-secondary">
                    <h5 class="modal-title text-primary" id="aiModalLabel"><i class="fas fa-robot me-2"></i>مساعد الذكاء الاصطناعي Gemini</h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="إغلاق"></button>
                </div>
                <div class="modal-body d-flex flex-column" style="height: 450px;">
                    <div id="aiChatMessages" class="flex-grow-1 overflow-auto p-3 mb-3 border border-secondary rounded bg-black" style="scroll-behavior: smooth;">
                        <div class="text-muted text-center my-auto">مرحباً بك! كيف يمكنني مساعدتك اليوم؟</div>
                    </div>
                    <form id="aiChatForm" class="d-flex gap-2">
                        <input type="text" id="aiUserInput" class="form-control bg-dark text-light border-secondary" placeholder="اكتب سؤالك هنا..." autocomplete="off" required>
                        <button type="submit" class="btn btn-primary px-4" id="aiSendBtn">
                            <i class="fas fa-paper-plane"></i>
                        </button>
                    </form>
                </div>
            </div>
        </div>
    </div>
    {% endif %}

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <meta name="csrf-token" content="{{ csrf_token() }}">
    <script>
        const originalFetch = window.fetch;
        window.fetch = function(url, options = {}) {
            options = options || {};
            options.headers = options.headers || {};
            const method = (options.method || 'GET').toUpperCase();
            if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
                const token = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
                if (token) {
                    if (options.headers instanceof Headers) {
                        options.headers.set('X-CSRFToken', token);
                    } else if (Array.isArray(options.headers)) {
                        options.headers.push(['X-CSRFToken', token]);
                    } else {
                        options.headers['X-CSRFToken'] = token;
                    }
                }
            }
            return originalFetch(url, options);
        };

        const aiForm = document.getElementById('aiChatForm');
        if(aiForm) {
            aiForm.onsubmit = async function(e) {
                e.preventDefault();
                const inputField = document.getElementById('aiUserInput');
                const messagesContainer = document.getElementById('aiChatMessages');
                const sendBtn = document.getElementById('aiSendBtn');
                const message = inputField.value.trim();
                
                if (!message) return;

                if (messagesContainer.querySelector('.text-muted.text-center')) {
                    messagesContainer.innerHTML = '';
                }

                messagesContainer.innerHTML += `
                    <div class="d-flex justify-content-end mb-3">
                        <div class="bg-primary text-white p-3 rounded-3 shadow-sm" style="max-width: 75%; word-break: break-word;">
                            <strong>أنت:</strong><br>${escapeHtml(message)}
                        </div>
                    </div>`;
                
                inputField.value = '';
                inputField.disabled = true;
                sendBtn.disabled = true;
                messagesContainer.scrollTop = messagesContainer.scrollHeight;

                const loadingId = 'loading-' + Date.now();
                messagesContainer.innerHTML += `
                    <div id="${loadingId}" class="d-flex justify-content-start mb-3">
                        <div class="bg-secondary text-light p-3 rounded-3 shadow-sm" style="max-width: 75%;">
                            <strong>الذكاء الاصطناعي:</strong><br><i class="fas fa-spinner fa-spin me-2"></i>جارٍ التفكير...
                        </div>
                    </div>`;
                messagesContainer.scrollTop = messagesContainer.scrollHeight;

                try {
                    let res = await fetch('/ai', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: message })
                    });
                    let data = await res.json();
                    
                    const loadingElement = document.getElementById(loadingId);
                    if (loadingElement) loadingElement.remove();

                    messagesContainer.innerHTML += `
                        <div class="d-flex justify-content-start mb-3">
                            <div class="bg-secondary text-light p-3 rounded-3 shadow-sm" style="max-width: 75%; word-break: break-word; white-space: pre-wrap;">
                                <strong>الذكاء الاصطناعي:</strong><br>${escapeHtml(data.reply || 'لم يتم استلام رد.')}
                            </div>
                        </div>`;
                } catch (err) {
                    const loadingElement = document.getElementById(loadingId);
                    if (loadingElement) loadingElement.remove();
                    messagesContainer.innerHTML += `
                        <div class="d-flex justify-content-start mb-3">
                            <div class="bg-danger text-white p-3 rounded-3 shadow-sm" style="max-width: 75%;">
                                <strong>خطأ:</strong><br>حدث خطأ في الاتصال بالخادم.
                            </div>
                        </div>`;
                } finally {
                    inputField.disabled = false;
                    sendBtn.disabled = false;
                    inputField.focus();
                    messagesContainer.scrollTop = messagesContainer.scrollHeight;
                }
            };
        }

        function escapeHtml(text) {
            if (!text) return '';
            return text
                .toString()
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        }
    </script>
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
<a href="{{ task.link }}" target="_blank" rel="noopener noreferrer" class="btn btn-outline-info btn-sm mb-2 w-100">رابط المهمة</a>
<button onclick="completeTask('{{ task.id }}')" class="btn btn-success btn-sm w-100">تنفيذ المهمة</button>
</div></div></div>
{% else %}
<div class="col-12 text-center py-5"><p class="text-muted">لا توجد مهام متاحة حالياً.</p></div>
{% endfor %}
</div>
<script>
async function completeTask(id) {
    try {
        let res = await fetch('/tasks/complete/' + id, { method: 'POST' });
        let data = await res.json();
        alert(data.message);
        if(data.success) location.reload();
    } catch (e) {
        alert('حدث خطأ أثناء الاتصال بالخادم');
    }
}
</script>
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
        let res = await fetch('/tasks/create', { method: 'POST', body: new FormData(e.target) });
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
<div class="col-md-4"><div class="card bg-dark border-secondary p-4 shadow mb-4">
<h4 class="text-primary mb-3">الملف الشخصي</h4>
<p><strong>اسم المستخدم:</strong> {{ user.username }}</p>
<p><strong>البريد الإلكتروني:</strong> {{ user.email }}</p>
<p><strong>الرصيد الحالي:</strong> <span class="text-success fw-bold">{{ user.points }} نقطة</span></p>
</div></div>
<div class="col-md-8"><div class="card bg-dark border-secondary p-4 shadow mb-4">
<h4 class="text-primary mb-3">سجل العمليات</h4>
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
        let res = await fetch('/admin/user/ban/' + id, { method: 'POST' });
        let data = await res.json();
        alert(data.message);
        if(data.success) location.reload();
    } catch (e) {
        alert('حدث خطأ أثناء الاتصال بالخادم');
    }
}
</script>
{% endblock %}'''
}

app.jinja_loader = DictLoader(TEMPLATES)


@app.context_processor
def inject_csrf():
    return dict(csrf_token=generate_csrf)


# ==========================================
# الوظائف المساعدة (Helper Functions)
# ==========================================

def log_action(level: str, message: str):
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


PLATFORM_PATTERNS = {
    'YouTube': [r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+'],
    'Facebook': [r'(https?://)?(www\.)?(facebook\.com|fb\.com|fb\.watch)/.+'],
    'Instagram': [r'(https?://)?(www\.)?instagram\.com/.+'],
    'TikTok': [r'(https?://)?(www\.)?(tiktok\.com|vm\.tiktok\.com)/.+'],
    'X': [r'(https?://)?(www\.)?(twitter\.com|x\.com)/.+'],
    'Telegram': [r'(https?://)?(www\.)?(t\.me|telegram\.me)/.+'],
    'Discord': [r'(https?://)?(www\.)?(discord\.gg|discord\.com)/.+'],
}

ALLOWED_PLATFORMS = set(PLATFORM_PATTERNS.keys())


def is_valid_platform_link(platform: str, link: str) -> bool:
    if platform not in PLATFORM_PATTERNS:
        return False
    if not link or not isinstance(link, str):
        return False
    link = link.strip()
    parsed = urlparse(link)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        return False
    for pattern in PLATFORM_PATTERNS[platform]:
        if re.match(pattern, link, re.IGNORECASE):
            return True
    return False


def sanitize_email(email: str) -> str:
    if not email:
        return ''
    return email.strip().lower()


def sanitize_username(username: str) -> str:
    if not username:
        return ''
    return username.strip()


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
            session['is_admin'] = bool(user.get('is_admin'))
        except Exception as e:
            log_action('error', f"login_required DB check failed: {e}")

        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
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
# معالجة الأخطاء العامة (Error Handlers)
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
# مسار الذكاء الاصطناعي (POST /ai) مع نظام التبديل التلقائي للاحتياط
# ==========================================

@app.route('/ai', methods=['POST'])
@login_required
def ask_ai():
    if not ai_client:
        return jsonify({
            'reply': 'عذراً، مفتاح Gemini API غير متوفر في متغيرات البيئة (GEMINI_API_KEY).'
        }), 500

    data = request.get_json(silent=True) or {}
    message = data.get('message', '').strip()

    if not message:
        return jsonify({'reply': 'الرجاء إدخال سؤال أو رسالة صحيحة.'}), 400

    response = None
    last_error = None

    # محاولة تجربة النماذج بترتيب الأولوية تلقائياً
    for model_name in GEMINI_MODELS:
        try:
            response = ai_client.models.generate_content(
                model=model_name,
                contents=message,
            )
            if response and response.text:
                break
        except genai_errors.APIError as e:
            last_error = e
            log_action('warning', f"Model {model_name} failed with APIError: {e}")
            continue
        except Exception as e:
            last_error = e
            log_action('warning', f"Model {model_name} failed with unexpected error: {e}")
            continue

    if response and response.text:
        return jsonify({'reply': response.text})
    
    # في حال فشل جميع النماذج المتاحة
    log_action('error', f"All Gemini models failed. Last error: {last_error}")
    return jsonify({
        'reply': 'عذراً، نماذج الذكاء الاصطناعي غير متاحة حالياً أو حدث خطأ في الاتصال بخدمة Gemini. يرجى المحاولة لاحقاً.'
    }), 500


# ==========================================
# مسارات المصادقة (Auth Routes)
# ==========================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = sanitize_username(request.form.get('username', ''))
        email = sanitize_email(request.form.get('email', ''))
        password = request.form.get('password', '')

        if not username or len(username) < 3 or len(username) > 50:
            flash('اسم المستخدم يجب أن يكون بين 3 و 50 حرفاً', 'danger')
            return redirect(url_for('register'))
        if not email or '@' not in email:
            flash('البريد الإلكتروني غير صالح', 'danger')
            return redirect(url_for('register'))
        if not password or len(password) < 6:
            flash('كلمة المرور يجب أن تكون 6 أحرف على الأقل', 'danger')
            return redirect(url_for('register'))

        try:
            by_username = db.table('users').select('id').eq('username', username).execute()
            by_email = db.table('users').select('id').eq('email', email).execute()
            if (by_username.data and len(by_username.data) > 0) or (by_email.data and len(by_email.data) > 0):
                flash('اسم المستخدم أو البريد الإلكتروني مستخدم مسبقاً', 'danger')
                return redirect(url_for('register'))
        except Exception as e:
            log_action('error', f"Register check existing failed: {e}")
            flash('حدث خطأ أثناء التحقق من البيانات', 'danger')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)
        welcome_points = 50.0

        try:
            res = db.table('users').insert({
                'username': username,
                'email': email,
                'password': hashed_password,
                'points': welcome_points,
                'is_admin': False,
                'is_banned': False
            }).execute()

            if res.data and len(res.data) > 0:
                user = res.data[0]
                add_points_history(user['id'], welcome_points, 'bonus', 'نقاط ترحيبية عند إنشاء الحساب')
                create_notification(user['id'], 'مرحباً بك في منصة TaskCoins Hub! تم إضافة 50 نقطة كهدية ترحيبية.')
                flash('تم إنشاء الحساب بنجاح! يمكنك تسجيل الدخول الآن.', 'success')
                return redirect(url_for('login'))
            else:
                flash('فشل إنشاء الحساب.', 'danger')
        except Exception as e:
            log_action('error', f"Register insert failed: {e}")
            flash('حدث خطأ أثناء التسجيل', 'danger')
            return redirect(url_for('register'))

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
# مسارات المهام (Task Routes)
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
    user_id = session['user_id']

    try:
        task_res = db.table('tasks').select('*').eq('id', task_id).execute()
        if not task_res.data:
            return jsonify({'success': False, 'message': 'المهمة غير موجودة'}), 404

        task = task_res.data[0]

        if task['owner_id'] == user_id:
            return jsonify({'success': False, 'message': 'لا يمكنك تنفيذ مهمتك الخاصة'}), 400

        if task['status'] != 'active':
            return jsonify({'success': False, 'message': 'هذه المهمة غير نشطة'}), 400

        comp_res = db.table('task_completions').select('id').eq(
            'task_id', task_id
        ).eq('user_id', user_id).execute()
        if comp_res.data:
            return jsonify({'success': False, 'message': 'لا يمكنك تنفيذ نفس المهمة مرتين'}), 400

        current_completed = int(task.get('completed_count') or 0)
        required = int(task.get('required_count') or 0)

        if current_completed >= required:
            return jsonify({'success': False, 'message': 'تم الوصول للعدد المطلوب مسبقاً'}), 400

        try:
            insert_comp = db.table('task_completions').insert({
                'task_id': task_id,
                'user_id': user_id
            }).execute()
            if not insert_comp.data:
                return jsonify({'success': False, 'message': 'فشل تسجيل التنفيذ'}), 400
        except Exception as e:
            log_action('warning', f"Completion insert conflict: {e}")
            return jsonify({'success': False, 'message': 'لا يمكنك تنفيذ نفس المهمة مرتين'}), 400

        new_completed = current_completed + 1
        new_status = 'completed' if new_completed >= required else 'active'

        update_res = db.table('tasks').update({
            'completed_count': new_completed,
            'status': new_status
        }).eq('id', task_id).eq(
            'completed_count', current_completed
        ).eq('status', 'active').execute()

        if not update_res.data:
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


# ==========================================
# مسارات الملف الشخصي (Profile Route)
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


# ==========================================
# لوحة التحكم (Admin Routes)
# ==========================================

@app.route('/admin')
@admin_required
def admin_dashboard():
    try:
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
# نقطة الدخول (Entry Point)
# ==========================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', '0') == '1')

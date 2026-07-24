import os
import re
import logging
from functools import wraps
from flask import (
    Flask, request, session, redirect, url_for,
    jsonify, render_template_string, make_response
)
from werkzeug.security import generate_password_hash, check_password_hash
from supabase import create_client, Client

# =========================================================
# Logging Configuration
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("TaskApp")

# =========================================================
# Flask & Supabase Initialization
# =========================================================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super-secret-key-change-this-in-production")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.warning("SUPABASE_URL or SUPABASE_KEY environment variables are missing!")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if (SUPABASE_URL and SUPABASE_KEY) else None

# =========================================================
# Security & Helper Decorators
# =========================================================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        # Check if user is banned
        res = supabase.table("accounts").select("is_banned").eq("id", session['user_id']).execute()
        if res.data and res.data[0]['is_banned']:
            session.clear()
            return render_template_string(BASE_LAYOUT, title="مظور", content="""
                <div class="card p-4 text-center border-danger">
                    <h3 class="text-danger">تم حظر حسابك</h3>
                    <p class="text-muted">لقد تم حظر حسابك لمخالفة الشروط والأحكام. تواصل مع الدعم الفني للمزيد.</p>
                    <a href="/login" class="btn btn-primary">العودة لتسجيل الدخول</a>
                </div>
            """)
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if not session.get('is_admin', False):
            return render_template_string(BASE_LAYOUT, title="غير مصرح", content="""
                <div class="card p-4 text-center border-warning">
                    <h3 class="text-warning">غير مصرح لك بالوصول</h3>
                    <p class="text-muted">هذه الصفحة خاصة بمديري النظام فقط.</p>
                    <a href="/dashboard" class="btn btn-primary">الرئيسية</a>
                </div>
            """), 403
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    if 'user_id' in session:
        res = supabase.table("accounts").select("*").eq("id", session['user_id']).execute()
        if res.data:
            return res.data[0]
    return None

def log_coin_transaction(user_id, amount, action, description):
    """تسجيل أي حركة نقاط في القاعدة"""
    supabase.table("coin_history").insert({
        "user_id": user_id,
        "amount": amount,
        "action": action,
        "description": description
    }).execute()

def create_notification(user_id, title, message):
    """إرسال إشعار للمستخدم"""
    supabase.table("notifications").insert({
        "user_id": user_id,
        "title": title,
        "message": message
    }).execute()

# =========================================================
# HTML Templates (Single-File Architecture)
# =========================================================

BASE_LAYOUT = """
<!DOCTYPE html>
<html lang="ar" dir="rtl" data-bs-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} - TaskCoins Hub</title>
    <!-- Bootstrap 5 RTL CSS -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.rtl.min.css">
    <!-- Font Awesome Icons -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
    <style>
        :root {
            --bg-primary: #0f172a;
            --bg-card: #1e293b;
            --accent: #6366f1;
            --accent-hover: #4f46e5;
        }
        body {
            background-color: var(--bg-primary);
            color: #f8fafc;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .card {
            background-color: var(--bg-card);
            border: 1px solid #334155;
            border-radius: 12px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }
        .navbar {
            background-color: var(--bg-card);
            border-bottom: 1px solid #334155;
        }
        .btn-primary {
            background-color: var(--accent);
            border-color: var(--accent);
        }
        .btn-primary:hover {
            background-color: var(--accent-hover);
            border-color: var(--accent-hover);
        }
        .coin-badge {
            background: linear-gradient(135deg, #f59e0b, #d97706);
            color: #fff;
            padding: 6px 14px;
            border-radius: 20px;
            font-weight: bold;
        }
        .nav-link {
            color: #94a3b8;
        }
        .nav-link:hover, .nav-link.active {
            color: #ffffff;
        }
        .toast-container {
            position: fixed;
            top: 20px;
            left: 20px;
            z-index: 1060;
        }
    </style>
</head>
<body>

    <!-- Dynamic Navbar -->
    <nav class="navbar navbar-expand-lg sticky-top">
        <div class="container">
            <a class="navbar-brand fw-bold text-primary" href="/dashboard">
                <i class="fa-solid fa-coins me-2"></i>TaskCoins
            </a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                {% if session.get('user_id') %}
                <ul class="navbar-nav me-auto mb-2 mb-lg-0">
                    <li class="nav-item"><a class="nav-link" href="/dashboard"><i class="fa-solid fa-house me-1"></i> الرئيسية</a></li>
                    <li class="nav-item"><a class="nav-link" href="/tasks/create"><i class="fa-solid fa-plus-circle me-1"></i> إضافة مهمة</a></li>
                    <li class="nav-item"><a class="nav-link" href="/my-tasks"><i class="fa-solid fa-list-check me-1"></i> مهامي</a></li>
                    <li class="nav-item"><a class="nav-link" href="/history"><i class="fa-solid fa-history me-1"></i> السجل</a></li>
                    <li class="nav-item"><a class="nav-link" href="/notifications"><i class="fa-solid fa-bell me-1"></i> الإشعارات</a></li>
                    {% if session.get('is_admin') %}
                    <li class="nav-item"><a class="nav-link text-warning" href="/admin"><i class="fa-solid fa-user-shield me-1"></i> لوحة الإدارة</a></li>
                    {% endif %}
                </ul>
                <div class="d-flex align-items-center gap-3">
                    <span class="coin-badge">
                        <i class="fa-solid fa-coins me-1"></i><span id="user-coins-display">{{ user_coins if user_coins is not none else 0 }}</span>
                    </span>
                    <div class="dropdown">
                        <a href="#" class="d-flex align-items-center text-white text-decoration-none dropdown-toggle" data-bs-toggle="dropdown">
                            <img src="{{ profile_photo or 'https://via.placeholder.com/150' }}" width="32" height="32" class="rounded-circle me-2">
                            <strong>{{ username }}</strong>
                        </a>
                        <ul class="dropdown-menu dropdown-menu-dark text-small shadow">
                            <li><a class="dropdown-item" href="/profile"><i class="fa-solid fa-user me-2"></i> الملف الشخصي</a></li>
                            <li><a class="dropdown-item" href="/report"><i class="fa-solid fa-flag me-2"></i> تقديم بلاغ</a></li>
                            <li><hr class="dropdown-divider"></li>
                            <li><a class="dropdown-item text-danger" href="/logout"><i class="fa-solid fa-right-from-bracket me-2"></i> تسجيل الخروج</a></li>
                        </ul>
                    </div>
                </div>
                {% else %}
                <div class="ms-auto">
                    <a href="/login" class="btn btn-outline-light me-2">تسجيل الدخول</a>
                    <a href="/register" class="btn btn-primary">إنشاء حساب</a>
                </div>
                {% endif %}
            </div>
        </div>
    </nav>

    <!-- Main Content Container -->
    <main class="container my-4 flex-grow-1">
        <div id="alert-zone"></div>
        {{ content | safe }}
    </main>

    <!-- Footer -->
    <footer class="footer mt-auto py-3 bg-dark text-center text-muted border-top border-secondary">
        <div class="container">
            <small>&copy; 2026 TaskCoins Hub - جميع الحقوق محفوظة.</small>
        </div>
    </footer>

    <!-- Bootstrap JS + Popper -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
    
    <!-- Custom Application AJAX Scripts -->
    <script>
        // System Alert Helper
        function showAlert(message, type = 'success') {
            const alertZone = document.getElementById('alert-zone');
            const alertHtml = `
                <div class="alert alert-${type} alert-dismissible fade show" role="alert">
                    ${message}
                    <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                </div>
            `;
            alertZone.innerHTML = alertHtml;
            setTimeout(() => { alertZone.innerHTML = ''; }, 5000);
        }

        // Global AJAX Executor
        async function apiCall(url, method = 'GET', data = null) {
            try {
                const options = {
                    method: method,
                    headers: { 'Content-Type': 'application/json' }
                };
                if (data) options.body = JSON.stringify(data);
                
                const response = await fetch(url, options);
                const result = await response.json();
                
                if (!response.ok) {
                    throw new Error(result.error || 'حدث خطأ غير متوقع');
                }
                return result;
            } catch (err) {
                showAlert(err.message, 'danger');
                return null;
            }
        }
    </script>
</body>
</html>
"""

# =========================================================
# Authentication Routes
# =========================================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        content = """
        <div class="row justify-content-center">
            <div class="col-md-5">
                <div class="card p-4">
                    <h3 class="text-center mb-4"><i class="fa-solid fa-user-plus text-primary me-2"></i>إنشاء حساب جديد</h3>
                    <form id="register-form">
                        <div class="mb-3">
                            <label class="form-label">اسم المستخدم</label>
                            <input type="text" id="username" class="form-control" required placeholder="مثال: ahmed123">
                        </div>
                        <div class="mb-3">
                            <label class="form-label">البريد الإلكتروني</label>
                            <input type="email" id="email" class="form-control" required placeholder="user@domain.com">
                        </div>
                        <div class="mb-3">
                            <label class="form-label">كلمة المرور</label>
                            <input type="password" id="password" class="form-control" required placeholder="******">
                        </div>
                        <button type="submit" class="btn btn-primary w-100 mb-3">تسجيل الحساب</button>
                    </form>
                    <div class="text-center">
                        <small>لديك حساب بالفعل؟ <a href="/login">تسجيل الدخول</a></small>
                    </div>
                </div>
            </div>
        </div>
        <script>
            document.getElementById('register-form').addEventListener('submit', async (e) => {
                e.preventDefault();
                const username = document.getElementById('username').value.trim();
                const email = document.getElementById('email').value.trim();
                const password = document.getElementById('password').value;

                const res = await apiCall('/api/auth/register', 'POST', { username, email, password });
                if(res && res.success) {
                    showAlert('تم إنشاء الحساب بنجاح! جاري تحويلك...', 'success');
                    setTimeout(() => window.location.href = '/dashboard', 1500);
                }
            });
        </script>
        """
        return render_template_string(BASE_LAYOUT, title="تسجيل حساب", content=content)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        content = """
        <div class="row justify-content-center">
            <div class="col-md-5">
                <div class="card p-4">
                    <h3 class="text-center mb-4"><i class="fa-solid fa-right-to-bracket text-primary me-2"></i>تسجيل الدخول</h3>
                    <form id="login-form">
                        <div class="mb-3">
                            <label class="form-label">اسم المستخدم أو البريد</label>
                            <input type="text" id="identity" class="form-control" required>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">كلمة المرور</label>
                            <input type="password" id="password" class="form-control" required>
                        </div>
                        <button type="submit" class="btn btn-primary w-100 mb-3">دخول</button>
                    </form>
                    <div class="text-center">
                        <small>ليس لديك حساب؟ <a href="/register">إنشاء حساب</a></small>
                    </div>
                </div>
            </div>
        </div>
        <script>
            document.getElementById('login-form').addEventListener('submit', async (e) => {
                e.preventDefault();
                const identity = document.getElementById('identity').value.trim();
                const password = document.getElementById('password').value;

                const res = await apiCall('/api/auth/login', 'POST', { identity, password });
                if(res && res.success) {
                    window.location.href = '/dashboard';
                }
            });
        </script>
        """
        return render_template_string(BASE_LAYOUT, title="تسجيل الدخول", content=content)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# =========================================================
# Main User Dashboard & App Pages
# =========================================================

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    user = get_current_user()
    content = f"""
    <div class="row mb-4">
        <div class="col-md-8">
            <h2>مرحباً بك، {user['username']}! 👋</h2>
            <p class="text-muted">قم بإكمال المهام المتاحة لجمع النقاط، أو أنشئ مهامك الخاصة لزيادة المتابعين والتفاعلات.</p>
        </div>
        <div class="col-md-4 text-start">
            <div class="card p-3 bg-primary bg-gradient text-white">
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <h6 class="mb-0">رصيد النقاط الحالي</h6>
                        <h2 class="fw-bold mb-0">{user['coins']}</h2>
                    </div>
                    <i class="fa-solid fa-coins fa-2x opacity-75"></i>
                </div>
            </div>
        </div>
    </div>

    <!-- Filters & Search -->
    <div class="card p-3 mb-4">
        <div class="row g-3">
            <div class="col-md-6">
                <input type="text" id="search-input" class="form-control" placeholder="بحث عن مهمة...">
            </div>
            <div class="col-md-4">
                <select id="platform-filter" class="form-select">
                    <option value="">جميع المنصات</option>
                    <option value="YouTube">YouTube</option>
                    <option value="Facebook">Facebook</option>
                    <option value="TikTok">TikTok</option>
                    <option value="Instagram">Instagram</option>
                    <option value="X">X (Twitter)</option>
                    <option value="Other">منصات أخرى</option>
                </select>
            </div>
            <div class="col-md-2">
                <button onclick="loadTasks()" class="btn btn-primary w-100"><i class="fa-solid fa-filter me-1"></i>تصفية</button>
            </div>
        </div>
    </div>

    <!-- Available Tasks Grid -->
    <h4 class="mb-3"><i class="fa-solid fa-tasks me-2"></i>المهام المتاحة</h4>
    <div class="row" id="tasks-container">
        <!-- JS injected content -->
    </div>

    <script>
        async function loadTasks() {{
            const search = document.getElementById('search-input').value;
            const platform = document.getElementById('platform-filter').value;
            const queryParams = new URLSearchParams({{ search, platform }}).toString();
            
            const container = document.getElementById('tasks-container');
            container.innerHTML = '<div class="text-center my-5"><div class="spinner-border text-primary"></div></div>';

            const tasks = await apiCall('/api/tasks?' + queryParams, 'GET');
            if(!tasks) return;

            if(tasks.length === 0) {{
                container.innerHTML = '<div class="col-12 text-center my-5 text-muted">لا توجد مهام متاحة حالياً.</div>';
                return;
            }}

            container.innerHTML = tasks.map(t => `
                <div class="col-md-4 mb-4">
                    <div class="card h-100">
                        <div class="card-body">
                            <div class="d-flex justify-content-between align-items-center mb-2">
                                <span class="badge bg-secondary">${{t.platform}}</span>
                                <span class="badge bg-warning text-dark"><i class="fa-solid fa-coins me-1"></i>+${{t.reward}}</span>
                            </div>
                            <h5 class="card-title">${{t.task_type}}</h5>
                            <p class="card-text text-truncate"><a href="${{t.target_url}}" target="_blank" class="text-info">${{t.target_url}}</a></p>
                            <div class="progress mb-3" style="height: 10px;">
                                <div class="progress-bar bg-success" style="width: ${(t.completed_count / t.required_count) * 100}%"></div>
                            </div>
                            <small class="text-muted d-block mb-3">المكتمل: ${{t.completed_count}} من ${{t.required_count}}</small>
                            <button onclick="executeTask(${{t.id}}, '${{t.target_url}}')" class="btn btn-outline-primary w-100">
                                <i class="fa-solid fa-external-link me-1"></i>تنفيذ المهمة
                            </button>
                        </div>
                    </div>
                </div>
            `).join('');
        }}

        async function executeTask(taskId, targetUrl) {{
            // Open target in new tab first
            window.open(targetUrl, '_blank');
            
            // Send claim points request
            const res = await apiCall(`/api/tasks/${{taskId}}/complete`, 'POST');
            if(res && res.success) {{
                showAlert(`تم إكمال المهمة بنجاح! حصلت على ${res.reward} نقطة.`, 'success');
                document.getElementById('user-coins-display').innerText = res.new_balance;
                loadTasks();
            }}
        }}

        // Initial Load
        loadTasks();
    </script>
    """
    return render_template_string(
        BASE_LAYOUT, title="الرئيسية", content=content,
        user_coins=user['coins'], username=user['username'], profile_photo=user['profile_photo']
    )

@app.route('/tasks/create', methods=['GET'])
@login_required
def create_task_page():
    user = get_current_user()
    content = """
    <div class="row justify-content-center">
        <div class="col-md-8">
            <div class="card p-4">
                <h3 class="mb-4"><i class="fa-solid fa-plus-circle text-primary me-2"></i>إنشاء مهمة جديدة</h3>
                <form id="create-task-form">
                    <div class="mb-3">
                        <label class="form-label">المنصة</label>
                        <select id="platform" class="form-select" required>
                            <option value="YouTube">YouTube</option>
                            <option value="Facebook">Facebook</option>
                            <option value="TikTok">TikTok</option>
                            <option value="Instagram">Instagram</option>
                            <option value="X">X (Twitter)</option>
                            <option value="Other">منصة أخرى</option>
                        </select>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">نوع المهمة</label>
                        <input type="text" id="task_type" class="form-control" placeholder="مثال: اشتراك بالقناة، إعجاب بالفيديو..." required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">الرابط المستهدف</label>
                        <input type="url" id="target_url" class="form-control" placeholder="https://..." required>
                    </div>
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">المكافأة لكل شخص (نقاط)</label>
                            <input type="number" id="reward" class="form-control" min="1" value="5" required>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">العدد المطلوب</label>
                            <input type="number" id="required_count" class="form-control" min="1" value="10" required>
                        </div>
                    </div>
                    <div class="alert alert-info">
                        <strong>التكلفة الإجمالية: </strong><span id="total-cost">50</span> نقطة.
                    </div>
                    <button type="submit" class="btn btn-primary w-100">نشر المهمة خصماً من الرصيد</button>
                </form>
            </div>
        </div>
    </div>
    <script>
        const rewardInput = document.getElementById('reward');
        const countInput = document.getElementById('required_count');
        const totalCostSpan = document.getElementById('total-cost');

        function updateTotal() {
            const reward = parseInt(rewardInput.value) || 0;
            const count = parseInt(countInput.value) || 0;
            totalCostSpan.innerText = reward * count;
        }

        rewardInput.addEventListener('input', updateTotal);
        countInput.addEventListener('input', updateTotal);

        document.getElementById('create-task-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const data = {
                platform: document.getElementById('platform').value,
                task_type: document.getElementById('task_type').value.trim(),
                target_url: document.getElementById('target_url').value.trim(),
                reward: parseInt(rewardInput.value),
                required_count: parseInt(countInput.value)
            };

            const res = await apiCall('/api/tasks', 'POST', data);
            if(res && res.success) {
                showAlert('تم إضافة المهمة وخصم النقاط بنجاح!', 'success');
                setTimeout(() => window.location.href = '/my-tasks', 1500);
            }
        });
    </script>
    """
    return render_template_string(
        BASE_LAYOUT, title="إضافة مهمة", content=content,
        user_coins=user['coins'], username=user['username'], profile_photo=user['profile_photo']
    )

@app.route('/my-tasks')
@login_required
def my_tasks_page():
    user = get_current_user()
    content = """
    <h3 class="mb-4"><i class="fa-solid fa-list-check me-2"></i>إدارة مهامي</h3>
    <div class="table-responsive">
        <table class="table table-dark table-striped align-middle">
            <thead>
                <tr>
                    <th>المنصة</th>
                    <th>النوع</th>
                    <th>الرابط</th>
                    <th>المكافأة</th>
                    <th>الإنجاز</th>
                    <th>الحالة</th>
                    <th>الإجراءات</th>
                </tr>
            </thead>
            <tbody id="my-tasks-table">
                <!-- JS populated -->
            </tbody>
        </table>
    </div>

    <script>
        async function loadMyTasks() {
            const tasks = await apiCall('/api/my-tasks', 'GET');
            const tbody = document.getElementById('my-tasks-table');
            if(!tasks) return;

            if(tasks.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">لم تقم بإنشاء أي مهام بعد.</td></tr>';
                return;
            }

            tbody.innerHTML = tasks.map(t => `
                <tr>
                    <td><span class="badge bg-secondary">${t.platform}</span></td>
                    <td>${t.task_type}</td>
                    <td><a href="${t.target_url}" target="_blank" class="text-info">رابط</a></td>
                    <td>${t.reward}</td>
                    <td>${t.completed_count} / ${t.required_count}</td>
                    <td><span class="badge bg-${t.status === 'active' ? 'success' : 'danger'}">${t.status}</span></td>
                    <td>
                        <button onclick="deleteTask(${t.id})" class="btn btn-sm btn-outline-danger"><i class="fa-solid fa-trash"></i></button>
                    </td>
                </tr>
            `).join('');
        }

        async function deleteTask(id) {
            if(!confirm('هل أنت تأكد من إيقاف/حذف هذه المهمة؟')) return;
            const res = await apiCall(`/api/tasks/${id}`, 'DELETE');
            if(res && res.success) {
                showAlert('تم حذف المهمة بنجاح.', 'success');
                loadMyTasks();
            }
        }

        loadMyTasks();
    </script>
    """
    return render_template_string(
        BASE_LAYOUT, title="مهامي", content=content,
        user_coins=user['coins'], username=user['username'], profile_photo=user['profile_photo']
    )

@app.route('/history')
@login_required
def history_page():
    user = get_current_user()
    content = """
    <h3 class="mb-4"><i class="fa-solid fa-history me-2"></i>سجل المعاملات والنقاط</h3>
    <div class="card p-3">
        <div class="table-responsive">
            <table class="table table-dark align-middle">
                <thead>
                    <tr>
                        <th>التاريخ</th>
                        <th>العملية</th>
                        <th>المبلغ</th>
                        <th>الوصف</th>
                    </tr>
                </thead>
                <tbody id="history-table"></tbody>
            </table>
        </div>
    </div>
    <script>
        async function loadHistory() {
            const data = await apiCall('/api/user/history', 'GET');
            const tbody = document.getElementById('history-table');
            if(!data) return;

            if(data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">لا يوجد سجل معاملات حتى الآن.</td></tr>';
                return;
            }

            tbody.innerHTML = data.map(h => `
                <tr>
                    <td>${new Date(h.created_at).toLocaleString('ar')}</td>
                    <td><span class="badge bg-${h.amount >= 0 ? 'success' : 'danger'}">${h.action}</span></td>
                    <td class="${h.amount >= 0 ? 'text-success' : 'text-danger'} fw-bold">${h.amount > 0 ? '+' : ''}${h.amount}</td>
                    <td>${h.description || '-'}</td>
                </tr>
            `).join('');
        }
        loadHistory();
    </script>
    """
    return render_template_string(
        BASE_LAYOUT, title="السجل", content=content,
        user_coins=user['coins'], username=user['username'], profile_photo=user['profile_photo']
    )

@app.route('/notifications')
@login_required
def notifications_page():
    user = get_current_user()
    content = """
    <h3 class="mb-4"><i class="fa-solid fa-bell me-2"></i>الإشعارات</h3>
    <div class="row justify-content-center">
        <div class="col-md-10" id="notifications-list"></div>
    </div>
    <script>
        async function loadNotifications() {
            const data = await apiCall('/api/user/notifications', 'GET');
            const list = document.getElementById('notifications-list');
            if(!data) return;

            if(data.length === 0) {
                list.innerHTML = '<div class="text-center text-muted card p-4">لا توجد إشعارات جديدة.</div>';
                return;
            }

            list.innerHTML = data.map(n => `
                <div class="card p-3 mb-3 border-start border-4 border-info">
                    <div class="d-flex justify-content-between">
                        <h5 class="mb-1">${n.title}</h5>
                        <small class="text-muted">${new Date(n.created_at).toLocaleString('ar')}</small>
                    </div>
                    <p class="mb-0 text-slate-300">${n.message}</p>
                </div>
            `).join('');
        }
        loadNotifications();
    </script>
    """
    return render_template_string(
        BASE_LAYOUT, title="الإشعارات", content=content,
        user_coins=user['coins'], username=user['username'], profile_photo=user['profile_photo']
    )

@app.route('/profile', methods=['GET'])
@login_required
def profile_page():
    user = get_current_user()
    content = f"""
    <div class="row justify-content-center">
        <div class="col-md-6">
            <div class="card p-4 mb-4">
                <h4 class="mb-3"><i class="fa-solid fa-user-gear me-2"></i>الملف الشخصي</h4>
                <form id="profile-form">
                    <div class="mb-3 text-center">
                        <img src="{user['profile_photo']}" width="100" height="100" class="rounded-circle mb-2">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">اسم المستخدم</label>
                        <input type="text" class="form-control" value="{user['username']}" disabled>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">البريد الإلكتروني</label>
                        <input type="email" id="email" class="form-control" value="{user['email']}" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">رابط الصورة الشخصية</label>
                        <input type="url" id="profile_photo" class="form-control" value="{user['profile_photo']}">
                    </div>
                    <button type="submit" class="btn btn-primary w-100">حفظ التغييرات</button>
                </form>
            </div>

            <div class="card p-4">
                <h4 class="mb-3"><i class="fa-solid fa-key me-2"></i>تغيير كلمة المرور</h4>
                <form id="password-form">
                    <div class="mb-3">
                        <label class="form-label">كلمة المرور الحالية</label>
                        <input type="password" id="current_password" class="form-control" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">كلمة المرور الجديدة</label>
                        <input type="password" id="new_password" class="form-control" required>
                    </div>
                    <button type="submit" class="btn btn-warning w-100">تحديث كلمة المرور</button>
                </form>
            </div>
        </div>
    </div>
    <script>
        document.getElementById('profile-form').addEventListener('submit', async (e) => {{
            e.preventDefault();
            const res = await apiCall('/api/user/profile', 'PUT', {{
                email: document.getElementById('email').value,
                profile_photo: document.getElementById('profile_photo').value
            }});
            if(res && res.success) showAlert('تم تحديث البيانات بنجاح', 'success');
        }});

        document.getElementById('password-form').addEventListener('submit', async (e) => {{
            e.preventDefault();
            const res = await apiCall('/api/user/password', 'PUT', {{
                current_password: document.getElementById('current_password').value,
                new_password: document.getElementById('new_password').value
            }});
            if(res && res.success) showAlert('تم تغيير كلمة المرور بنجاح', 'success');
        }});
    </script>
    """
    return render_template_string(
        BASE_LAYOUT, title="الملف الشخصي", content=content,
        user_coins=user['coins'], username=user['username'], profile_photo=user['profile_photo']
    )

@app.route('/report', methods=['GET'])
@login_required
def report_page():
    user = get_current_user()
    content = """
    <div class="row justify-content-center">
        <div class="col-md-6">
            <div class="card p-4">
                <h4 class="mb-3"><i class="fa-solid fa-flag text-danger me-2"></i>تقديم بلاغ أو شكوى</h4>
                <form id="report-form">
                    <div class="mb-3">
                        <label class="form-label">معرف/اسم المستخدم المبلغ عنه (اختياري)</label>
                        <input type="text" id="reported_user" class="form-control" placeholder="اسم المستخدم أو اتركه فارغاً">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">سبب البلاغ / تفاصيل المشكلة</label>
                        <textarea id="reason" class="form-control" rows="4" required></textarea>
                    </div>
                    <button type="submit" class="btn btn-danger w-100">إرسال البلاغ</button>
                </form>
            </div>
        </div>
    </div>
    <script>
        document.getElementById('report-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const res = await apiCall('/api/reports', 'POST', {
                reported_user: document.getElementById('reported_user').value.trim(),
                reason: document.getElementById('reason').value.trim()
            });
            if(res && res.success) {
                showAlert('تم تقديم البلاغ بنجاح وسوف تقوم الإدارة بمراجعته.', 'success');
                document.getElementById('report-form').reset();
            }
        });
    </script>
    """
    return render_template_string(
        BASE_LAYOUT, title="تقديم بلاغ", content=content,
        user_coins=user['coins'], username=user['username'], profile_photo=user['profile_photo']
    )

# =========================================================
# Admin Panel Route
# =========================================================

@app.route('/admin')
@admin_required
def admin_panel():
    user = get_current_user()
    content = """
    <h2 class="mb-4 text-warning"><i class="fa-solid fa-user-shield me-2"></i>لوحة التحكم الإدارية</h2>

    <!-- System Stats -->
    <div class="row mb-4" id="stats-zone">
        <div class="col-md-3"><div class="card p-3 text-center"><h5>المستخدمين</h5><h3 id="stat-users">-</h3></div></div>
        <div class="col-md-3"><div class="card p-3 text-center"><h5>المهام النشطة</h5><h3 id="stat-tasks">-</h3></div></div>
        <div class="col-md-3"><div class="card p-3 text-center"><h5>إجمالي النقاط</h5><h3 id="stat-coins">-</h3></div></div>
        <div class="col-md-3"><div class="card p-3 text-center"><h5>البلاغات</h5><h3 id="stat-reports">-</h3></div></div>
    </div>

    <!-- Admin Tabs -->
    <ul class="nav nav-tabs mb-3" id="adminTabs">
        <li class="nav-item"><a class="nav-link active" data-bs-toggle="tab" href="#users-tab">المستخدمين</a></li>
        <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#reports-tab">البلاغات</a></li>
    </ul>

    <div class="tab-content">
        <!-- Users Management Tab -->
        <div class="tab-pane fade show active" id="users-tab">
            <div class="card p-3">
                <div class="table-responsive">
                    <table class="table table-dark align-middle">
                        <thead>
                            <tr>
                                <th>المعرف</th>
                                <th>اسم المستخدم</th>
                                <th>البريد</th>
                                <th>النقاط</th>
                                <th>الحالة</th>
                                <th>الإجراءات</th>
                            </tr>
                        </thead>
                        <tbody id="admin-users-table"></tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- Reports Tab -->
        <div class="tab-pane fade" id="reports-tab">
            <div class="card p-3">
                <div class="table-responsive">
                    <table class="table table-dark align-middle">
                        <thead>
                            <tr>
                                <th>المُبلّغ</th>
                                <th>السبب</th>
                                <th>التاريخ</th>
                                <th>الحالة</th>
                            </tr>
                        </thead>
                        <tbody id="admin-reports-table"></tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <script>
        async function loadAdminData() {
            const data = await apiCall('/api/admin/overview', 'GET');
            if(!data) return;

            document.getElementById('stat-users').innerText = data.stats.total_users;
            document.getElementById('stat-tasks').innerText = data.stats.active_tasks;
            document.getElementById('stat-coins').innerText = data.stats.total_coins;
            document.getElementById('stat-reports').innerText = data.stats.pending_reports;

            // Render Users Table
            document.getElementById('admin-users-table').innerHTML = data.users.map(u => `
                <tr>
                    <td>${u.id}</td>
                    <td>${u.username}</td>
                    <td>${u.email}</td>
                    <td>${u.coins}</td>
                    <td><span class="badge bg-${u.is_banned ? 'danger' : 'success'}">${u.is_banned ? 'محظور' : 'نشط'}</span></td>
                    <td>
                        <button onclick="toggleBan(${u.id}, ${!u.is_banned})" class="btn btn-sm btn-${u.is_banned ? 'success' : 'warning'}">
                            ${u.is_banned ? 'إلغاء الحظر' : 'حظر'}
                        </button>
                    </td>
                </tr>
            `).join('');

            // Render Reports
            document.getElementById('admin-reports-table').innerHTML = data.reports.map(r => `
                <tr>
                    <td>${r.reporter_id}</td>
                    <td>${r.reason}</td>
                    <td>${new Date(r.created_at).toLocaleDateString('ar')}</td>
                    <td><span class="badge bg-info">${r.status}</span></td>
                </tr>
            `).join('');
        }

        async function toggleBan(userId, banState) {
            const res = await apiCall(`/api/admin/users/${userId}/ban`, 'POST', { ban: banState });
            if(res && res.success) {
                showAlert('تم تحديث حالة المستخدم بنجاح', 'success');
                loadAdminData();
            }
        }

        loadAdminData();
    </script>
    """
    return render_template_string(
        BASE_LAYOUT, title="لوحة الإدارة", content=content,
        user_coins=user['coins'], username=user['username'], profile_photo=user['profile_photo']
    )

# =========================================================
# Internal REST APIs (JSON responses with input validation)
# =========================================================

@app.route('/api/auth/register', methods=['POST'])
def api_register():
    data = request.json or {}
    username = data.get('username', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not username or not email or not password:
        return jsonify({"error": "جميع الحقول مطلوبة"}), 400

    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return jsonify({"error": "البريد الإلكتروني غير صحيح"}), 400

    # Check existence
    existing = supabase.table("accounts").select("id").or_(f"username.eq.{username},email.eq.{email}").execute()
    if existing.data:
        return jsonify({"error": "اسم المستخدم أو البريد المستعمل موجود بالفعل"}), 400

    hashed_pw = generate_password_hash(password)
    
    # Get initial balance setting
    settings = supabase.table("app_settings").select("setting_value").eq("setting_key", "welcome_bonus").execute()
    welcome_coins = int(settings.data[0]['setting_value']) if settings.data else 100

    res = supabase.table("accounts").insert({
        "username": username,
        "email": email,
        "password_hash": hashed_pw,
        "coins": welcome_coins,
        "total_earned": welcome_coins
    }).execute()

    if res.data:
        new_user = res.data[0]
        session['user_id'] = new_user['id']
        session['username'] = new_user['username']
        session['is_admin'] = new_user['is_admin']

        log_coin_transaction(new_user['id'], welcome_coins, "BONUS", "مكافأة التسجيل الجديد")
        create_notification(new_user['id'], "مرحباً بك!", f"لقد حصلت على {welcome_coins} نقطة هدية التسجيل.")

        return jsonify({"success": True})
    
    return jsonify({"error": "فشل إنشاء الحساب"}), 500

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.json or {}
    identity = data.get('identity', '').strip()
    password = data.get('password', '')

    if not identity or not password:
        return jsonify({"error": "يرجى كتابة كافة البيانات"}), 400

    res = supabase.table("accounts").select("*").or_(f"username.eq.{identity},email.eq.{identity}").execute()
    
    if not res.data:
        return jsonify({"error": "بيانات الدخول غير صحيحة"}), 400

    user = res.data[0]
    
    if user['is_banned']:
        return jsonify({"error": "هذا الحساب محظور من الاستخدام"}), 403

    if check_password_hash(user['password_hash'], password):
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['is_admin'] = user['is_admin']
        return jsonify({"success": True})
    
    return jsonify({"error": "بيانات الدخول غير صحيحة"}), 400

@app.route('/api/tasks', methods=['GET'])
@login_required
def api_get_tasks():
    current_uid = session['user_id']
    platform = request.args.get('platform')
    search = request.args.get('search')

    # Query active tasks excluding user's own tasks
    query = supabase.table("tasks").select("*").eq("status", "active").neq("owner_id", current_uid)
    
    if platform:
        query = query.eq("platform", platform)
    if search:
        query = query.ilike("task_type", f"%{search}%")

    tasks_res = query.order("created_at", desc=True).execute()
    
    # Get list of task IDs user has already completed
    completed_res = supabase.table("completed_tasks").select("task_id").eq("user_id", current_uid).execute()
    completed_ids = {c['task_id'] for c in completed_res.data} if completed_res.data else set()

    # Filter out already executed tasks
    available_tasks = [t for t in tasks_res.data if t['id'] not in completed_ids]

    return jsonify(available_tasks)

@app.route('/api/tasks', methods=['POST'])
@login_required
def api_create_task():
    user = get_current_user()
    data = request.json or {}

    platform = data.get('platform')
    task_type = data.get('task_type')
    target_url = data.get('target_url')
    reward = int(data.get('reward', 0))
    required_count = int(data.get('required_count', 0))

    if not all([platform, task_type, target_url]) or reward <= 0 or required_count <= 0:
        return jsonify({"error": "مدخلات غير صالحة"}), 400

    total_cost = reward * required_count

    if user['coins'] < total_cost:
        return jsonify({"error": f"رصيدك غير كافي. تحتاج إلى {total_cost} نقطة."}), 400

    # Deduct coins from owner
    new_balance = user['coins'] - total_cost
    supabase.table("accounts").update({
        "coins": new_balance,
        "total_spent": user['total_spent'] + total_cost
    }).eq("id", user['id']).execute()

    # Create task
    task_res = supabase.table("tasks").insert({
        "owner_id": user['id'],
        "platform": platform,
        "task_type": task_type,
        "target_url": target_url,
        "reward": reward,
        "required_count": required_count,
        "status": "active"
    }).execute()

    log_coin_transaction(user['id'], -total_cost, "SPENT", f"إنشاء مهمة {platform}")

    return jsonify({"success": True, "new_balance": new_balance})

@app.route('/api/tasks/<int:task_id>/complete', methods=['POST'])
@login_required
def api_complete_task(task_id):
    user_id = session['user_id']
    
    # Check task existence
    task_res = supabase.table("tasks").select("*").eq("id", task_id).execute()
    if not task_res.data:
        return jsonify({"error": "المهمة غير موجودة"}), 404

    task = task_res.data[0]

    if task['owner_id'] == user_id:
        return jsonify({"error": "لا يمكنك تنفيذ مهمتك الخاصة"}), 400

    if task['status'] != 'active' or task['completed_count'] >= task['required_count']:
        return jsonify({"error": "هذه المهمة مكتملة أو غير نشطة"}), 400

    # Prevent duplicate completion
    check_done = supabase.table("completed_tasks").select("id").eq("task_id", task_id).eq("user_id", user_id).execute()
    if check_done.data:
        return jsonify({"error": "لقد قمت بتنفيذ هذه المهمة من قبل"}), 400

    # 1. Insert completion record
    supabase.table("completed_tasks").insert({
        "task_id": task_id,
        "user_id": user_id,
        "rewarded": task['reward']
    }).execute()

    # 2. Update Task Count
    new_completed = task['completed_count'] + 1
    new_status = 'completed' if new_completed >= task['required_count'] else 'active'
    
    supabase.table("tasks").update({
        "completed_count": new_completed,
        "status": new_status
    }).eq("id", task_id).execute()

    # 3. Add rewards to worker
    worker = get_current_user()
    new_coins = worker['coins'] + task['reward']
    
    supabase.table("accounts").update({
        "coins": new_coins,
        "total_earned": worker['total_earned'] + task['reward']
    }).eq("id", user_id).execute()

    log_coin_transaction(user_id, task['reward'], "EARNED", f"إكمال مهمة #{task_id}")
    create_notification(user_id, "تم كسب نقاط!", f"حصلت على {task['reward']} نقطة لقاء إكمال مهمة {task['platform']}.")

    return jsonify({"success": True, "reward": task['reward'], "new_balance": new_coins})

@app.route('/api/my-tasks', methods=['GET'])
@login_required
def api_my_tasks():
    res = supabase.table("tasks").select("*").eq("owner_id", session['user_id']).order("created_at", desc=True).execute()
    return jsonify(res.data)

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
@login_required
def api_delete_task(task_id):
    # Ensure owner is executing
    res = supabase.table("tasks").select("*").eq("id", task_id).eq("owner_id", session['user_id']).execute()
    if not res.data:
        return jsonify({"error": "المهمة غير موجودة أو غير مملوكة لك"}), 404

    supabase.table("tasks").delete().eq("id", task_id).execute()
    return jsonify({"success": True})

@app.route('/api/user/history', methods=['GET'])
@login_required
def api_user_history():
    res = supabase.table("coin_history").select("*").eq("user_id", session['user_id']).order("created_at", desc=True).execute()
    return jsonify(res.data)

@app.route('/api/user/notifications', methods=['GET'])
@login_required
def api_user_notifications():
    res = supabase.table("notifications").select("*").eq("user_id", session['user_id']).order("created_at", desc=True).execute()
    return jsonify(res.data)

@app.route('/api/user/profile', methods=['

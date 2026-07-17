from flask import Flask, request, redirect, url_for, session, render_template_string
import os
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = "change_this_secret_key"

USERS_FILE = "users.json"
POSTS_FILE = "posts.json"

def load_data(file):
    if not os.path.exists(file):
        return []
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_data(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_users():
    return load_data(USERS_FILE)

def get_posts():
    return load_data(POSTS_FILE)

style = """
<style>
body {font-family: Arial, sans-serif; background:#f2f2f2; margin:0; padding:0; transition: background 0.3s;}
body.dark {background:#121212; color:white;}
.container {width:90%; max-width:600px; margin:40px auto; background:white; padding:20px; border-radius:15px; box-shadow:0 0 10px #ccc; transition: background 0.3s;}
body.dark .container {background:#1e1e1e;}
h1 {text-align:center;}
input, textarea {width:100%; padding:12px; margin:8px 0; border:1px solid #ccc; border-radius:8px; box-sizing:border-box;}
button {width:100%; padding:12px; background:#1976d2; color:white; border:none; border-radius:8px; cursor:pointer;}
button:hover {background:#125aa0;}
.post {background:#fafafa; padding:15px; margin:15px 0; border-radius:10px; border:1px solid #ddd;}
body.dark .post {background:#2a2a2a;}
.name {font-weight:bold; color:#1976d2;}
.time {font-size:12px; color:#777;}
</style>
"""

home_page = """
<!DOCTYPE html>
<html><head><title>Posts</title>""" + style + """</head><body>
<div class="container">
<a href="/settings" style="float:right; padding:10px;">⚙️ الإعدادات</a>
<h1>المنشورات</h1>
<form method="post" action="/post">
<textarea name="content" placeholder="اكتب منشورك" required></textarea>
<button>نشر</button>
</form>
<hr>
{% for p in posts %}
<div class="post">
<div class="name">{{ p.get("user", "") }}</div>
<p>{{ p.get("content", "") }}</p>
<div class="time">{{ p.get("time", "") }}</div>
<p>❤️ {{ p.get("likes", 0) }}</p>
</div>
{% endfor %}
<a href="/logout">تسجيل خروج</a>
</div>
<script>
if (localStorage.getItem('darkMode') === 'true') document.body.classList.add('dark');
</script>
</body></html>
"""

settings_page = """
<!DOCTYPE html>
<html><head><title>Settings</title>""" + style + """</head><body>
<div class="container">
<h1>الإعدادات</h1>
<button onclick="toggleDarkMode()">🌙 تفعيل الوضع المظلم</button>
<br><br>
<a href="/home">العودة للرئيسية</a>
</div>
<script>
function toggleDarkMode() {
    document.body.classList.toggle('dark');
    localStorage.setItem('darkMode', document.body.classList.contains('dark'));
}
</script>
</body></html>
"""

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username:
            users = get_users()
            for u in users:
                if u.get("name") == username and u.get("password") == password:
                    session["user"] = username
                    return redirect(url_for("home"))
            users.append({"name": username, "password": password or "", "created": str(datetime.now())})
            save_data(USERS_FILE, users)
            session["user"] = username
            return redirect(url_for("home"))
    return render_template_string(login_page)

@app.route("/register", methods=["GET", "POST"])
def register():
    return login()

@app.route("/home")
def home():
    if "user" not in session:
        return redirect(url_for("login"))
    posts = get_posts()
    posts.reverse()
    return render_template_string(home_page, posts=posts)

@app.route("/settings")
def settings():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template_string(settings_page)

@app.route("/post", methods=["POST"])
def create_post():
    if "user" not in session:
        return redirect(url_for("login"))
    content = request.form.get("content")
    if content:
        posts = get_posts()
        posts.append({
            "user": session["user"],
            "content": content,
            "time": str(datetime.now()),
            "likes": 0
        })
        save_data(POSTS_FILE, posts)
    return redirect(url_for("home"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

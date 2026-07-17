from flask import Flask, request, redirect, url_for, session, render_template_string
import os
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = "change_this_secret_key"

USERS_FILE = "users.json"
POSTS_FILE = "posts.json"
FOLLOWERS_FILE = "followers.json"

def load_data(file):
    if not os.path.exists(file):
        return [] if 'users' in file or 'posts' in file else {}
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return [] if 'users' in file or 'posts' in file else {}

def save_data(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_users():
    return load_data(USERS_FILE)

def get_posts():
    return load_data(POSTS_FILE)

def get_followers_data():
    data = load_data(FOLLOWERS_FILE)
    return data if isinstance(data, dict) else {}

style = """
<style>
body {font-family: Arial, sans-serif; background:#f2f2f2; margin:0; padding:0;}
.container {width:90%; max-width:600px; margin:40px auto; background:white; padding:20px; border-radius:15px; box-shadow:0 0 10px #ccc;}
h1 {text-align:center;}
input, textarea {width:100%; padding:12px; margin:8px 0; border:1px solid #ccc; border-radius:8px; box-sizing:border-box;}
button {width:100%; padding:12px; background:#1976d2; color:white; border:none; border-radius:8px; cursor:pointer;}
button:hover {background:#125aa0;}
.post {background:#fafafa; padding:15px; margin:15px 0; border-radius:10px; border:1px solid #ddd;}
.name {font-weight:bold; color:#1976d2;}
.time {font-size:12px; color:#777;}
</style>
"""

login_page = """
<!DOCTYPE html>
<html><head><title>Login</title>""" + style + """</head><body>
<div class="container">
<h1>الدخول</h1>
<form method="post">
<input name="username" placeholder="اسم المستخدم" required>
<input name="password" type="password" placeholder="كلمة المرور" required>
<button type="submit">دخول</button>
</form>
<a href="/register">تسجيل حساب جديد</a>
</div></body></html>
"""

home_page = """
<!DOCTYPE html>
<html><head><title>Posts</title>""" + style + """</head><body>
<div class="container">
<h1>المنشورات - مرحبا {{current_user}}</h1>
<form method="post" action="/post">
<textarea name="content" placeholder="اكتب منشورك" required></textarea>
<button>نشر</button>
</form>
<hr>
{% for p in posts %}
<div class="post">
<div class="name">{{p["user"]}}</div>
<p>{{p["content"]}}</p>
<div class="time">{{p["time"]}}</div>
<p>❤️ {{p.get("likes", 0)}} | تعليقات: {{len(p.get("comments", []))}}</p>
</div>
{% endfor %}
<a href="/profile">ملفي الشخصي</a>
</div></body></html>
"""

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        users = get_users()
        for user in users:
            if user.get("name") == username and user.get("password") == password:
                session["user"] = username
                return redirect(url_for("home"))
        return "اسم المستخدم أو كلمة المرور خاطئة!"
    return render_template_string(login_page)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username and password:
            users = get_users()
            if not any(u["name"] == username for u in users):
                users.append({"name": username, "password": password, "created": str(datetime.now())})
                save_data(USERS_FILE, users)
                session["user"] = username
                return redirect(url_for("home"))
    return render_template_string(login_page)

@app.route("/home")
def home():
    if "user" not in session:
        return redirect(url_for("login"))
    posts = get_posts()
    posts.reverse()
    return render_template_string(home_page, posts=posts, current_user=session["user"])

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
            "likes": 0,
            "comments": []
        })
        save_data(POSTS_FILE, posts)
    return redirect(url_for("home"))

@app.route("/profile")
def profile():
    if "user" not in session:
        return redirect(url_for("login"))
    # يمكن توسيعها لعرض عدد المتابعين
    return f"<h1>ملف {session['user']}</h1><p>عدد المتابعين: 0 (جاري التطوير)</p><a href='/home'>العودة</a>"

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

from flask import Flask, render_template_string, request
from playwright.sync_api import sync_playwright
import base64
import os

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>Login Tester</title>
    <style>
        body { font-family: Arial; max-width: 600px; margin: 40px auto; padding: 20px; background: #f5f5f5; }
        input, button { width: 100%; padding: 12px; margin: 8px 0; font-size: 16px; }
        button { background: #2563eb; color: white; border: none; cursor: pointer; }
        button:hover { background: #1d4ed8; }
        .result { background: white; padding: 15px; margin-top: 20px; border-radius: 8px; }
        img { max-width: 100%; border: 1px solid #ddd; }
    </style>
</head>
<body>
    <h2>مختبر تسجيل الدخول (لموقعك فقط)</h2>
    <form method="POST">
        <input type="url" name="url" placeholder="رابط صفحة تسجيل الدخول" required value="{{ url or '' }}">
        <input type="text" name="username" placeholder="الرقم أو اسم المستخدم" required value="{{ username or '' }}">
        <input type="password" name="password" placeholder="كلمة المرور" required>
        <button type="submit">ابدأ التجربة</button>
    </form>

    {% if error %}
        <div class="result" style="color: red;">{{ error }}</div>
    {% endif %}

    {% if success %}
        <div class="result">
            <p><strong>النتيجة:</strong> {{ success }}</p>
            <p><strong>الرابط الحالي:</strong> {{ current_url }}</p>
            {% if screenshot %}
                <p><strong>لقطة الشاشة:</strong></p>
                <img src="data:image/png;base64,{{ screenshot }}">
            {% endif %}
        </div>
    {% endif %}
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template_string(HTML)

    url = request.form.get("url", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    if not url or not username or not password:
        return render_template_string(HTML, error="يجب ملء كل الحقول")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=30000)

            # غيّر هذه الـ selectors حسب موقعك
            page.fill('input[name="username"]', username)      # ← عدّل هنا
            page.fill('input[name="password"]', password)      # ← عدّل هنا
            page.click('button[type="submit"]')                 # ← عدّل هنا

            page.wait_for_timeout(3000)

            current_url = page.url
            screenshot_bytes = page.screenshot()
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode()

            browser.close()

        return render_template_string(
            HTML,
            success="تمت العملية بنجاح",
            current_url=current_url,
            screenshot=screenshot_b64,
            url=url,
            username=username
        )

    except Exception as e:
        return render_template_string(HTML, error=f"خطأ: {str(e)}", url=url, username=username)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

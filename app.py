from flask import Flask, request, render_template_string, send_file
from playwright.sync_api import sync_playwright
import os
import uuid
import subprocess
import traceback


app = Flask(__name__)


# تثبيت Chromium عند التشغيل
try:
    subprocess.run(
        ["playwright", "install", "chromium"],
        check=False
    )
    print("Chromium installed successfully")
except Exception as e:
    print("Chromium install error:", e)


SCREENSHOT_FOLDER = "screenshots"
os.makedirs(SCREENSHOT_FOLDER, exist_ok=True)


# مهلات قصيرة لتقليل استهلاك الموارد ومنع تعليق العمال
GOTO_TIMEOUT = 30000      # 30 ثانية
ACTION_TIMEOUT = 5000     # 5 ثوانٍ للنقر/الكتابة
WAIT_AFTER_CLICK = 800    # انتظار قصير بعد النقر


HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>

<meta charset="UTF-8">
<title>مساعد المواقع</title>

<style>

body{
font-family:Arial;
background:#f2f2f2;
text-align:center;
padding:40px;
}

.box{
background:white;
padding:30px;
border-radius:15px;
max-width:600px;
margin:auto;
}

input{
width:90%;
padding:12px;
margin:10px;
border-radius:8px;
border:1px solid #ccc;
}

button{
padding:12px 25px;
background:#007bff;
color:white;
border:0;
border-radius:8px;
}

img{
width:100%;
margin-top:20px;
}

.error{
color:red;
white-space:pre-wrap;
text-align:left;
direction:ltr;
font-size:13px;
}

</style>

</head>


<body>

<div class="box">

<h2>🌐 مساعد المواقع</h2>


<form method="POST">


<input 
type="url"
name="url"
placeholder="رابط الموقع"
required>


<input
name="click_text"
placeholder="الكلمة التي تريد النقر عليها">


<input
name="write_text"
placeholder="النص المراد كتابته">


<button>
تشغيل
</button>


</form>


{% if result %}
<h3>{{result}}</h3>
{% endif %}


{% if image %}
<h3>الصورة:</h3>
<img src="/image/{{image}}">
{% endif %}


{% if error %}
<p class="error">{{error}}</p>
{% endif %}


</div>

</body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
def home():

    image = None
    result = None
    error = None

    if request.method == "POST":

        url = request.form.get("url")
        click_text = request.form.get("click_text")
        write_text = request.form.get("write_text")

        filename = str(uuid.uuid4()) + ".png"
        path = os.path.join(SCREENSHOT_FOLDER, filename)

        browser = None
        page = None

        try:
            with sync_playwright() as p:

                # إعدادات Chromium منخفضة الاستهلاك للذاكرة (مناسبة لـ Render المجاني)
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-software-rasterizer",
                        "--disable-extensions",
                        "--disable-background-networking",
                        "--disable-default-apps",
                        "--disable-sync",
                        "--no-first-run",
                        "--disable-translate",
                        "--mute-audio",
                        "--hide-scrollbars",
                        "--disable-features=TranslateUI",
                        "--disable-ipc-flooding-protection",
                        "--single-process",
                        "--renderer-process-limit=1",
                    ]
                )

                page = browser.new_page(
                    viewport={"width": 1280, "height": 900}
                )

                # فتح الصفحة بمهلة معقولة
                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=GOTO_TIMEOUT
                )

                # ---------- النقر على الكلمة ----------
                if click_text:
                    try:
                        element = page.get_by_text(click_text, exact=False)
                        count = element.count()

                        if count > 0:
                            clicked = False
                            last_error = None

                            # 1) جرب العناصر الظاهرة أولاً (حتى 5 عناصر لتجنب التأخير)
                            for i in range(min(count, 5)):
                                try:
                                    loc = element.nth(i)
                                    if loc.is_visible(timeout=800):
                                        loc.scroll_into_view_if_needed(timeout=1500)
                                        loc.click(timeout=ACTION_TIMEOUT)
                                        page.wait_for_timeout(WAIT_AFTER_CLICK)
                                        result = "✅ تم النقر على الكلمة"
                                        clicked = True
                                        break
                                except Exception as e:
                                    last_error = e
                                    continue

                            # 2) إذا لم ينجح → جرب force click على أول عنصر
                            if not clicked:
                                try:
                                    element.first.scroll_into_view_if_needed(timeout=1500)
                                    element.first.click(timeout=3000, force=True)
                                    page.wait_for_timeout(WAIT_AFTER_CLICK)
                                    result = "✅ تم النقر على الكلمة (force)"
                                    clicked = True
                                except Exception as e:
                                    last_error = e

                            if not clicked:
                                result = "⚠️ الكلمة موجودة لكن النقر فشل: " + str(last_error)
                        else:
                            result = "❌ لم يتم العثور على الكلمة"
                    except Exception as e:
                        result = "⚠️ خطأ أثناء البحث عن الكلمة: " + str(e)

                # ---------- الكتابة في أول خانة ----------
                if write_text:
                    try:
                        inputs = page.locator("input:visible")

                        if inputs.count() == 0:
                            # fallback: أي input
                            inputs = page.locator("input")

                        if inputs.count() > 0:
                            try:
                                target = inputs.first
                                target.scroll_into_view_if_needed(timeout=1500)
                                target.fill(write_text, timeout=ACTION_TIMEOUT)
                                result = "✅ تم إدخال النص"
                            except Exception as e:
                                # محاولة force
                                try:
                                    inputs.first.fill(write_text, timeout=3000, force=True)
                                    result = "✅ تم إدخال النص (force)"
                                except Exception as e2:
                                    result = "⚠️ فشل إدخال النص: " + str(e2)
                        else:
                            result = "❌ لم توجد خانة كتابة"
                    except Exception as e:
                        result = "⚠️ خطأ أثناء البحث عن خانة الكتابة: " + str(e)

                # التقاط صورة في الحالة العادية
                try:
                    page.screenshot(path=path, full_page=True)
                    image = filename
                except Exception:
                    pass

        except Exception:
            # أي خطأ غير متوقع → عرض الـ traceback الكامل
            error = traceback.format_exc()
            print(error)

            # محاولة التقاط لقطة شاشة إن أمكن قبل الإغلاق
            if page is not None:
                try:
                    page.screenshot(path=path, full_page=True)
                    image = filename
                except Exception:
                    pass

        finally:
            # إغلاق المتصفح دائماً
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass

    return render_template_string(
        HTML,
        result=result,
        image=image,
        error=error
    )


@app.route("/image/<name>")
def image(name):
    return send_file(
        os.path.join(SCREENSHOT_FOLDER, name)
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000
)

from flask import Flask, request, render_template_string, send_file
from playwright.sync_api import sync_playwright
import os
import uuid
import subprocess
import traceback
import gc


app = Flask(__name__)


# تثبيت Chromium مرة واحدة فقط
try:
    subprocess.run(
        ["playwright", "install", "chromium"],
        check=False,
        timeout=120
    )
    print("Chromium installed successfully")
except Exception as e:
    print("Chromium install error:", e)


SCREENSHOT_FOLDER = "screenshots"
os.makedirs(SCREENSHOT_FOLDER, exist_ok=True)


GOTO_TIMEOUT = 25000
ACTION_TIMEOUT = 4000
WAIT_AFTER_CLICK = 600


HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<title>مساعد المواقع</title>
<style>
body{font-family:Arial;background:#f2f2f2;text-align:center;padding:40px;}
.box{background:white;padding:30px;border-radius:15px;max-width:600px;margin:auto;}
input{width:90%;padding:12px;margin:10px;border-radius:8px;border:1px solid #ccc;}
button{padding:12px 25px;background:#007bff;color:white;border:0;border-radius:8px;}
img{width:100%;margin-top:20px;}
.error{color:red;white-space:pre-wrap;text-align:left;direction:ltr;font-size:13px;}
</style>
</head>
<body>
<div class="box">
<h2>🌐 مساعد المواقع</h2>
<form method="POST">
<input type="url" name="url" placeholder="رابط الموقع" required>
<input name="click_text" placeholder="الكلمة التي تريد النقر عليها">
<input name="write_text" placeholder="النص المراد كتابته">
<button>تشغيل</button>
</form>
{% if result %}<h3>{{result}}</h3>{% endif %}
{% if image %}<h3>الصورة:</h3><img src="/image/{{image}}">{% endif %}
{% if error %}<p class="error">{{error}}</p>{% endif %}
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
                        "--mute-audio",
                        "--hide-scrollbars",
                        "--single-process",
                        "--renderer-process-limit=1",
                        "--disable-features=VizDisplayCompositor",
                        "--memory-pressure-off",
                    ]
                )

                page = browser.new_page(
                    viewport={"width": 1024, "height": 768}  # أصغر لتوفير الذاكرة
                )

                page.goto(url, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT)

                # ---------- النقر ----------
                if click_text:
                    try:
                        element = page.get_by_text(click_text, exact=False)
                        count = element.count()

                        if count > 0:
                            clicked = False
                            last_error = None

                            for i in range(min(count, 3)):  # أقل عدد لتقليل الوقت
                                try:
                                    loc = element.nth(i)
                                    if loc.is_visible(timeout=800):
                                        try:
                                            loc.scroll_into_view_if_needed(timeout=2000)
                                        except Exception:
                                            pass
                                        loc.click(timeout=ACTION_TIMEOUT)
                                        page.wait_for_timeout(WAIT_AFTER_CLICK)
                                        result = "✅ تم النقر على الكلمة"
                                        clicked = True
                                        break
                                except Exception as e:
                                    last_error = e
                                    continue

                            if not clicked:
                                try:
                                    element.first.click(timeout=2500, force=True)
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

                # ---------- الكتابة ----------
                if write_text:
                    try:
                        inputs = page.locator("input:visible")
                        if inputs.count() == 0:
                            inputs = page.locator("input")

                        if inputs.count() > 0:
                            try:
                                target = inputs.first
                                try:
                                    target.scroll_into_view_if_needed(timeout=2000)
                                except Exception:
                                    pass
                                target.fill(write_text, timeout=ACTION_TIMEOUT)
                                result = "✅ تم إدخال النص"
                            except Exception as e:
                                try:
                                    inputs.first.fill(write_text, timeout=2500, force=True)
                                    result = "✅ تم إدخال النص (force)"
                                except Exception as e2:
                                    result = "⚠️ فشل إدخال النص: " + str(e2)
                        else:
                            result = "❌ لم توجد خانة كتابة"
                    except Exception as e:
                        result = "⚠️ خطأ أثناء البحث عن خانة الكتابة: " + str(e)

                # التقاط صورة
                try:
                    page.screenshot(path=path, full_page=False)  # full_page=False لتوفير الذاكرة
                    image = filename
                except Exception:
                    pass

        except Exception:
            error = traceback.format_exc()
            print(error)

            if page is not None:
                try:
                    page.screenshot(path=path, full_page=False)
                    image = filename
                except Exception:
                    pass

        finally:
            if page is not None:
                try:
                    page.close()
                except Exception:
                    pass
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass
            gc.collect()  # تنظيف الذاكرة

    return render_template_string(HTML, result=result, image=image, error=error)


@app.route("/image/<name>")
def image(name):
    return send_file(os.path.join(SCREENSHOT_FOLDER, name))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

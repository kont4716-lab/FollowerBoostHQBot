from flask import Flask, request, render_template_string, send_file
from playwright.sync_api import sync_playwright
import os
import uuid
import subprocess
import traceback
import gc


app = Flask(__name__)


try:
    subprocess.run(["playwright", "install", "chromium"], check=False, timeout=90)
    print("Chromium installed successfully")
except Exception as e:
    print("Chromium install error:", e)


SCREENSHOT_FOLDER = "screenshots"
os.makedirs(SCREENSHOT_FOLDER, exist_ok=True)


GOTO_TIMEOUT = 20000
ACTION_TIMEOUT = 3500
WAIT_AFTER_CLICK = 1200


HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<title>مساعد المواقع</title>
<style>
body{font-family:Arial;background:#f2f2f2;text-align:center;padding:40px;}
.box{background:white;padding:30px;border-radius:15px;max-width:650px;margin:auto;}
input{width:90%;padding:12px;margin:10px;border-radius:8px;border:1px solid #ccc;}
button{padding:12px 25px;background:#007bff;color:white;border:0;border-radius:8px;}
img{width:100%;margin-top:20px;}
.error{color:red;white-space:pre-wrap;text-align:left;direction:ltr;font-size:13px;}
.info{background:#e8f4fd;padding:12px;border-radius:8px;margin:10px 0;text-align:right;font-size:14px;}
</style>
</head>
<body>
<div class="box">
<h2>🌐 مساعد المواقع</h2>
<form method="POST">
<input type="url" name="url" placeholder="رابط الموقع" required>
<input name="click_text" placeholder="الكلمة التي تريد النقر عليها (اختياري)">
<input name="write_text1" placeholder="النص الأول (إيميل أو رقم هاتف)">
<input name="write_text2" placeholder="النص الثاني (كلمة المرور)">
<button>تشغيل</button>
</form>
{% if result %}<div class="info">{{result|safe}}</div>{% endif %}
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
        write_text1 = request.form.get("write_text1")
        write_text2 = request.form.get("write_text2")

        filename = str(uuid.uuid4()) + ".png"
        path = os.path.join(SCREENSHOT_FOLDER, filename)

        browser = None
        page = None
        messages = []

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-software-rasterizer",
                        "--single-process",
                        "--renderer-process-limit=1",
                        "--disable-extensions",
                        "--mute-audio",
                        "--hide-scrollbars",
                        "--disable-background-networking",
                        "--memory-pressure-off",
                    ]
                )

                page = browser.new_page(viewport={"width": 1024, "height": 720})
                page.goto(url, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT)

                # ========== اكتشاف الأزرار وخانات الكتابة ==========
                try:
                    # الأزرار
                    clickables = []
                    buttons = page.get_by_role("button").all()
                    for btn in buttons[:12]:
                        try:
                            txt = btn.inner_text().strip()
                            if txt and 1 < len(txt) < 40:
                                clickables.append(txt)
                        except:
                            pass

                    # روابط وأزرار إضافية بالنص
                    links = page.locator("a:visible, [role='button']:visible").all()
                    for link in links[:8]:
                        try:
                            txt = link.inner_text().strip()
                            if txt and 1 < len(txt) < 40 and txt not in clickables:
                                clickables.append(txt)
                        except:
                            pass

                    # إزالة التكرار
                    clickables = list(dict.fromkeys(clickables))

                    if clickables:
                        messages.append("<b>الأزرار المتاحة للنقر:</b><br>" + " | ".join(clickables[:10]))
                    else:
                        messages.append("لم يتم العثور على أزرار واضحة")
                except Exception as e:
                    messages.append("خطأ في اكتشاف الأزرار: " + str(e))

                try:
                    # خانات الكتابة
                    inputs_info = []
                    inputs = page.locator("input:visible").all()
                    for i, inp in enumerate(inputs[:8]):
                        try:
                            placeholder = inp.get_attribute("placeholder") or ""
                            name = inp.get_attribute("name") or ""
                            typ = inp.get_attribute("type") or "text"
                            label = placeholder or name or f"خانة {i+1}"
                            inputs_info.append(f"{label} ({typ})")
                        except:
                            pass

                    if inputs_info:
                        messages.append("<b>خانات الكتابة المتاحة:</b><br>" + " | ".join(inputs_info))
                    else:
                        messages.append("لم يتم العثور على خانات كتابة")
                except Exception as e:
                    messages.append("خطأ في اكتشاف الخانات: " + str(e))

                # ========== تنفيذ النقر ==========
                if click_text and click_text.strip():
                    try:
                        clicked = False

                        # 1) جرب كـ button
                        try:
                            btn = page.get_by_role("button", name=click_text.strip(), exact=False)
                            if btn.count() > 0:
                                try:
                                    btn.first.click(timeout=ACTION_TIMEOUT, no_wait_after=True)
                                    page.wait_for_timeout(WAIT_AFTER_CLICK)
                                    messages.append("✅ تم النقر على الزر: " + click_text)
                                    clicked = True
                                except Exception:
                                    btn.first.click(timeout=2500, force=True, no_wait_after=True)
                                    page.wait_for_timeout(WAIT_AFTER_CLICK)
                                    messages.append("✅ تم النقر (force) على الزر: " + click_text)
                                    clicked = True
                        except Exception:
                            pass

                        # 2) جرب بالنص
                        if not clicked:
                            element = page.get_by_text(click_text.strip(), exact=False)
                            if element.count() > 0:
                                try:
                                    element.first.click(timeout=ACTION_TIMEOUT, no_wait_after=True)
                                    page.wait_for_timeout(WAIT_AFTER_CLICK)
                                    messages.append("✅ تم النقر على: " + click_text)
                                    clicked = True
                                except Exception:
                                    try:
                                        element.first.click(timeout=2500, force=True, no_wait_after=True)
                                        page.wait_for_timeout(WAIT_AFTER_CLICK)
                                        messages.append("✅ تم النقر (force) على: " + click_text)
                                        clicked = True
                                    except Exception as e:
                                        if "navigated to" in str(e).lower():
                                            messages.append("✅ تم النقر والانتقال: " + click_text)
                                            clicked = True
                                        else:
                                            messages.append("⚠️ فشل النقر: " + str(e))
                            else:
                                messages.append("❌ لم يتم العثور على: " + click_text)
                    except Exception as e:
                        messages.append("⚠️ خطأ في النقر: " + str(e))

                # ========== النص الأول ==========
                if write_text1 and write_text1.strip():
                    try:
                        inputs = page.locator('input:visible:not([type="password"]):not([type="hidden"]):not([type="submit"])')
                        if inputs.count() == 0:
                            inputs = page.locator('input:not([type="password"]):not([type="hidden"])')

                        if inputs.count() > 0:
                            try:
                                inputs.first.fill(write_text1.strip(), timeout=ACTION_TIMEOUT)
                                messages.append("✅ تم كتابة النص الأول")
                            except Exception:
                                try:
                                    inputs.first.fill(write_text1.strip(), timeout=2500, force=True)
                                    messages.append("✅ تم كتابة النص الأول (force)")
                                except Exception as e:
                                    messages.append("⚠️ فشل النص الأول: " + str(e))
                        else:
                            messages.append("❌ لم توجد خانة للنص الأول")
                    except Exception as e:
                        messages.append("⚠️ خطأ في النص الأول: " + str(e))

                # ========== النص الثاني (باسورد) ==========
                if write_text2 and write_text2.strip():
                    try:
                        password = page.locator('input[type="password"]')
                        if password.count() > 0:
                            target = password.first
                        else:
                            inputs = page.locator('input:visible:not([type="hidden"]):not([type="submit"])')
                            target = inputs.nth(1) if inputs.count() > 1 else inputs.first

                        if target.count() > 0:
                            try:
                                target.fill(write_text2.strip(), timeout=ACTION_TIMEOUT)
                                messages.append("✅ تم كتابة النص الثاني (باسورد)")
                            except Exception:
                                try:
                                    target.fill(write_text2.strip(), timeout=2500, force=True)
                                    messages.append("✅ تم كتابة النص الثاني (force)")
                                except Exception as e:
                                    messages.append("⚠️ فشل النص الثاني: " + str(e))
                        else:
                            messages.append("❌ لم توجد خانة للنص الثاني")
                    except Exception as e:
                        messages.append("⚠️ خطأ في النص الثاني: " + str(e))

                result = "<br>".join(messages) if messages else None

                try:
                    page.screenshot(path=path, full_page=False)
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
            gc.collect()

    return render_template_string(HTML, result=result, image=image, error=error)


@app.route("/image/<name>")
def image(name):
    return send_file(os.path.join(SCREENSHOT_FOLDER, name))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

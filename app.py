from flask import Flask, request, render_template_string, send_file
from playwright.sync_api import sync_playwright
import os
import uuid
import glob
import traceback

app = Flask(__name__)

SCREENSHOT_FOLDER = "screenshots"
os.makedirs(SCREENSHOT_FOLDER, exist_ok=True)


HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<title>لقطة شاشة المواقع</title>
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
    max-width:500px;
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
    margin-top:20px;
}
</style>
</head>

<body>

<div class="box">

<h2>📸 التقاط صورة موقع</h2>

<form method="POST">

<input 
type="url"
name="url"
placeholder="ضع رابط الموقع هنا"
required>

<br>

<button>
التقاط الصورة
</button>

</form>


{% if image %}
<h3>النتيجة:</h3>
<img src="/image/{{image}}">
{% endif %}


{% if error %}
<div class="error">
{{error}}
</div>
{% endif %}

</div>

</body>
</html>
"""


@app.route("/", methods=["GET","POST"])
def home():

    image = None
    error = None


    if request.method == "POST":

        url = request.form.get("url")

        try:

            filename = str(uuid.uuid4()) + ".png"

            path = os.path.join(
                SCREENSHOT_FOLDER,
                filename
            )


            with sync_playwright() as p:

                # البحث عن Chromium المثبت في Render
                chromium = glob.glob(
                    "/opt/render/.cache/ms-playwright/chromium-*/chrome-linux/chrome"
                )


                if chromium:
                    browser = p.chromium.launch(
                        executable_path=chromium[0],
                        headless=True,
                        args=[
                            "--no-sandbox",
                            "--disable-dev-shm-usage"
                        ]
                    )

                else:
                    browser = p.chromium.launch(
                        headless=True,
                        args=[
                            "--no-sandbox",
                            "--disable-dev-shm-usage"
                        ]
                    )


                page = browser.new_page(
                    viewport={
                        "width":1280,
                        "height":900
                    }
                )


                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=60000
                )


                page.screenshot(
                    path=path,
                    full_page=True
                )


                browser.close()


            image = filename


        except Exception as e:

            error = str(e)
            print(traceback.format_exc())


    return render_template_string(
        HTML,
        image=image,
        error=error
    )



@app.route("/image/<name>")
def get_image(name):

    return send_file(
        os.path.join(
            SCREENSHOT_FOLDER,
            name
        )
    )



if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000
                    )

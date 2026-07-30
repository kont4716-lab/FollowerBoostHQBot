from flask import Flask, request, render_template_string, send_file
from playwright.sync_api import sync_playwright
import os
import uuid

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
    font-family: Arial;
    background:#f2f2f2;
    text-align:center;
    padding:50px;
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
}
button{
    padding:12px 25px;
    background:#007bff;
    color:white;
    border:0;
    border-radius:8px;
    cursor:pointer;
}
img{
    max-width:90%;
    margin-top:20px;
}
</style>
</head>

<body>

<div class="box">

<h2>📸 التقاط صورة موقع</h2>

<form method="POST">
<input name="url" placeholder="ضع رابط الموقع هنا" required>
<br>
<button>
التقاط الصورة
</button>
</form>

{% if image %}
<h3>النتيجة:</h3>
<img src="/image/{{image}}">
{% endif %}

</div>

</body>
</html>
"""


@app.route("/", methods=["GET","POST"])
def home():

    image = None

    if request.method == "POST":

        url = request.form["url"]

        filename = str(uuid.uuid4()) + ".png"
        path = os.path.join(
            SCREENSHOT_FOLDER,
            filename
        )

        with sync_playwright() as p:

            browser = p.chromium.launch(
                headless=True
            )

            page = browser.new_page(
                viewport={
                    "width":1280,
                    "height":900
                }
            )

            page.goto(
                url,
                wait_until="networkidle",
                timeout=60000
            )

            page.screenshot(
                path=path,
                full_page=True
            )

            browser.close()

        image = filename


    return render_template_string(
        HTML,
        image=image
    )


@app.route("/image/<name>")
def image(name):
    return send_file(
        os.path.join(
            SCREENSHOT_FOLDER,
            name
        )
    )


if __name__=="__main__":
    app.run(
        host="0.0.0.0",
        port=5000
    )

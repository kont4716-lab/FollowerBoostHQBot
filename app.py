from flask import Flask, request, render_template_string, send_file
from playwright.sync_api import sync_playwright
import os
import uuid
import traceback

app = Flask(__name__)

SCREENSHOT_FOLDER = "screenshots"
os.makedirs(SCREENSHOT_FOLDER, exist_ok=True)


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
padding:25px;
border-radius:15px;
max-width:600px;
margin:auto;
}

input,button{
width:90%;
padding:12px;
margin:8px;
}

button{
background:#007bff;
color:white;
border:0;
border-radius:8px;
}

img{
width:100%;
margin-top:20px;
}
</style>

</head>

<body>

<div class="box">

<h2>🌐 مساعد المواقع</h2>

<form method="POST">

<input name="url" placeholder="رابط الموقع" required>

<input name="click_text" placeholder="الكلمة التي تريد النقر عليها">

<input name="write_text" placeholder="النص المراد كتابته">

<button>
تشغيل
</button>

</form>


{% if image %}
<h3>الصورة:</h3>
<img src="/image/{{image}}">
{% endif %}


{% if result %}
<p>{{result}}</p>
{% endif %}


</div>

</body>
</html>
"""


@app.route("/", methods=["GET","POST"])
def home():

    image=None
    result=None


    if request.method=="POST":

        url=request.form.get("url")
        click_text=request.form.get("click_text")
        write_text=request.form.get("write_text")


        try:

            filename=str(uuid.uuid4())+".png"
            path=os.path.join(
                SCREENSHOT_FOLDER,
                filename
            )


            with sync_playwright() as p:

                browser=p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox"
                    ]
                )


                page=browser.new_page(
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


                # البحث عن كلمة والنقر عليها
                if click_text:

                    locator=page.get_by_text(
                        click_text,
                        exact=False
                    )

                    if locator.count()>0:
                        locator.first.click()
                        result="✅ تم النقر على: "+click_text
                    else:
                        result="❌ لم يتم العثور على الكلمة"


                # البحث عن خانة وكتابة النص
                if write_text:

                    inputs=page.locator("input")

                    if inputs.count()>0:
                        inputs.first.fill(write_text)
                        result="✅ تم إدخال النص"
                    else:
                        result="❌ لم توجد خانة كتابة"


                page.screenshot(
                    path=path,
                    full_page=True
                )


                browser.close()


            image=filename


        except Exception as e:

            result=str(e)
            print(traceback.format_exc())


    return render_template_string(
        HTML,
        image=image,
        result=result
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

import os
from flask import Flask, request, redirect, url_for, send_from_directory

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp"
}


def allowed_file(filename):
    return (
        "." in filename and
        filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


@app.route("/", methods=["GET", "POST"])
def home():

    message = ""

    if request.method == "POST":

        if "image" not in request.files:
            message = "❌ لم يتم اختيار صورة."

        else:

            file = request.files["image"]

            if file.filename == "":
                message = "❌ اختر صورة أولاً."

            elif allowed_file(file.filename):

                filename = file.filename

                path = os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    filename
                )

                file.save(path)

                message = "✅ تم رفع الصورة بنجاح."

            else:
                message = "❌ هذا النوع غير مسموح."

    files = os.listdir(app.config["UPLOAD_FOLDER"])

    html = f"""
<!DOCTYPE html>
<html lang="ar">

<head>

<meta charset="UTF-8">

<title>رفع الصور</title>

<style>

body{{
font-family:Arial;
background:#f4f4f4;
text-align:center;
padding:30px;
}}

.container{{
background:white;
max-width:700px;
margin:auto;
padding:20px;
border-radius:10px;
box-shadow:0 0 10px #ccc;
}}

button{{
padding:10px 20px;
font-size:16px;
cursor:pointer;
}}

img{{
width:180px;
margin:10px;
border-radius:10px;
}}

.success{{
color:green;
font-weight:bold;
}}

.error{{
color:red;
font-weight:bold;
}}

</style>

</head>

<body>

<div class="container">

<h1>📤 رفع صورة</h1>

<form method="POST" enctype="multipart/form-data">

<input type="file" name="image">

<br><br>

<button type="submit">

رفع الصورة

</button>

</form>

<p>{message}</p>

<hr>

<h2>الصور المرفوعة</h2>
"""    for file in files:

        html += f"""
        <div>
            <img src="/uploads/{file}">
            <br>
            {file}
            <hr>
        </div>
        """

    html += """
</div>

</body>

</html>
"""

    return html


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )

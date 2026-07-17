from flask import Flask, request, redirect, url_for, send_from_directory, render_template_string
import os
import uuid

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"mp4", "mov", "avi", "mkv", "webm"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mini TikTok</title>
    <style>
        body {
            margin: 0;
            background: #000;
            font-family: Arial;
            overflow-y: scroll;
            scroll-snap-type: y mandatory;
            height: 100vh;
        }

        .video {
            height: 100vh;
            scroll-snap-align: start;
            display: flex;
            justify-content: center;
            align-items: center;
            background: black;
        }

        video {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .upload {
            position: fixed;
            top: 15px;
            left: 15px;
            z-index: 999;
            background: white;
            padding: 10px;
            border-radius: 10px;
        }

        button {
            padding: 10px;
            font-size: 16px;
        }
    </style>
</head>
<body>

    <div class="upload">
        <form action="/upload" method="post" enctype="multipart/form-data">
            <input type="file" name="video" accept="video/*">
            <button type="submit">رفع الفيديو</button>
        </form>
    </div>

    {% for video in videos %}
    <div class="video">
        <video controls autoplay muted loop playsinline>
            <source src="/uploads/{{ video }}">
        </video>
    </div>
    {% endfor %}

</body>
</html>
"""


@app.route("/")
def index():
    videos = []
    if os.path.exists(app.config["UPLOAD_FOLDER"]):
        videos = sorted(os.listdir(app.config["UPLOAD_FOLDER"]), reverse=True)
    return render_template_string(HTML, videos=videos)


@app.route("/upload", methods=["POST"])
def upload():
    if "video" not in request.files:
        return redirect(url_for("index"))

    file = request.files["video"]

    if file.filename == "":
        return redirect(url_for("index"))

    if file and allowed_file(file.filename):
        ext = file.filename.rsplit(".", 1)[1].lower()
        filename = f"{uuid.uuid4().hex}.{ext}"
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

    return redirect(url_for("index"))


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

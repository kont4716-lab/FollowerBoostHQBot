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


def get_videos():
    if not os.path.exists(UPLOAD_FOLDER):
        return []
    videos = []
    for f in os.listdir(UPLOAD_FOLDER):
        if f == ".gitkeep":
            continue
        if allowed_file(f):
            videos.append(f)
    return sorted(videos, reverse=True)


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
            font-family: Arial, sans-serif;
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
            background: rgba(255,255,255,0.95);
            padding: 12px;
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.3);
        }
        .info {
            position: fixed;
            bottom: 15px;
            left: 15px;
            background: rgba(0,0,0,0.7);
            color: white;
            padding: 8px 12px;
            border-radius: 8px;
            font-size: 14px;
            z-index: 999;
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

    <div class="info">
        عدد الفيديوهات: {{ videos|length }}
    </div>

    {% for video in videos %}
    <div class="video">
        <video controls autoplay muted loop playsinline>
            <source src="/uploads/{{ video }}">
        </video>
    </div>
    {% else %}
    <div style="height:100vh;display:flex;align-items:center;justify-content:center;color:white;font-size:18px;">
        لا توجد فيديوهات بعد. ارفع أول فيديو!
    </div>
    {% endfor %}

</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML, videos=get_videos())


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
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        print(f"✅ Video uploaded: {filename}")  # للـ logs

    return redirect(url_for("index"))


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    if filename == ".gitkeep":
        return "Not found", 404
    return send_from_directory(UPLOAD_FOLDER, filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

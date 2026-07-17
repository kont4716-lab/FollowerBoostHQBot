import os
from flask import Flask, request, redirect, url_for, send_from_directory, render_template_string

app = Flask(__name__)

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload size

# Create uploads folder
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def home():
    files = [f for f in os.listdir(app.config["UPLOAD_FOLDER"]) 
             if os.path.isfile(os.path.join(app.config["UPLOAD_FOLDER"], f))]
    
    html = """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>معرض الصور</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 20px;
                background: #f4f4f4;
            }
            h1 { text-align: center; color: #333; }
            .gallery {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
                gap: 15px;
                max-width: 1200px;
                margin: 0 auto;
            }
            .image-card {
                background: white;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                text-align: center;
            }
            .image-card img {
                max-width: 100%;
                height: 200px;
                object-fit: cover;
            }
            .image-card p {
                margin: 10px 0;
                font-size: 0.9em;
                color: #555;
            }
            .upload-form {
                text-align: center;
                margin: 20px 0;
                padding: 20px;
                background: white;
                border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }
            input[type="submit"] {
                padding: 10px 20px;
                background: #007bff;
                color: white;
                border: none;
                border-radius: 5px;
                cursor: pointer;
            }
        </style>
    </head>
    <body>
        <h1>📸 معرض رفع و عرض الصور</h1>
        
        <div class="upload-form">
            <form action="/upload" method="post" enctype="multipart/form-data">
                <input type="file" name="file" accept="image/*" required>
                <input type="submit" value="رفع الصورة">
            </form>
        </div>

        <div class="gallery">
    """

    if not files:
        html += "<p style='grid-column: 1/-1; text-align:center; color:#888;'>لا توجد صور مرفوعة بعد.</p>"
    else:
        for file in files:
            html += f"""
            <div class="image-card">
                <img src="/uploads/{file}" alt="{file}">
                <p>{file}</p>
            </div>
            """

    html += """
        </div>
    </body>
    </html>
    """

    return render_template_string(html)


@app.route("/upload", methods=["POST"])
def upload_file():
    if 'file' not in request.files:
        return redirect(url_for('home'))

    file = request.files['file']

    if file.filename == '':
        return redirect(url_for('home'))

    if file and allowed_file(file.filename):
        filename = file.filename
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return redirect(url_for('home'))

    return "نوع الملف غير مسموح به", 400


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
)

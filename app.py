from flask import Flask, request, render_template_string, jsonify, send_from_directory
import os
import uuid

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 1GB

ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'mp4', 'mov', 'avi', 'mkv', 'webm'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>رفع ملفات</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600&display=swap');
        body { font-family:'Cairo',sans-serif; background:linear-gradient(135deg,#667eea,#764ba2); margin:0; padding:0; min-height:100vh; color:#333; }
        .container { background:white; border-radius:20px; box-shadow:0 20px 40px rgba(0,0,0,0.2); width:90%; max-width:520px; margin:40px auto; padding:30px; text-align:center; }
        h1 { margin-bottom:30px; }
        .upload-area { border:3px dashed #667eea; border-radius:15px; padding:40px 20px; margin:20px 0; cursor:pointer; }
        .upload-area:hover { background:#f8f9ff; }
        .btn { background:#667eea; color:white; border:none; padding:14px 40px; font-size:18px; border-radius:50px; margin:15px 5px; cursor:pointer; font-weight:600; }
        #progress-container { margin:25px 0; display:none; }
        .progress-bar { height:12px; background:#e0e0e0; border-radius:20px; overflow:hidden; }
        .progress { height:100%; background:linear-gradient(90deg,#667eea,#764ba2); width:0%; transition:width 0.4s; }
        .tiktok-container { margin-top:30px; max-height:500px; overflow-y:auto; border:1px solid #ddd; border-radius:10px; }
        .media-slide { height:400px; display:flex; align-items:center; justify-content:center; background:#000; position:relative; margin:10px 0; }
        .media-slide video { max-height:100%; max-width:100%; }
        .controls { position:absolute; bottom:10px; left:50%; transform:translateX(-50%); background:rgba(0,0,0,0.6); padding:5px 15px; border-radius:20px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>رفع صورة أو فيديو</h1>
        
        <div class="upload-area" id="drop-area">
            <p>اسحب الملف هنا أو</p>
            <button class="btn" onclick="document.getElementById('file-input').click()">اختر ملف</button>
            <input type="file" id="file-input" accept="image/*,video/*" style="display:none;">
        </div>
        
        <button class="btn" id="upload-btn" onclick="uploadFile()" disabled>رفع الملف</button>
        
        <div id="progress-container">
            <div class="progress-bar"><div class="progress" id="progress"></div></div>
            <div id="status">جاري الرفع...</div>
        </div>
        
        <div class="tiktok-container" id="feed"></div>
    </div>

    <script>
        let selectedFile = null;

        // رفع الملف
        function uploadFile() {
            if (!selectedFile) return;
            const progressContainer = document.getElementById('progress-container');
            const progressBar = document.getElementById('progress');
            const status = document.getElementById('status');

            progressContainer.style.display = 'block';
            status.textContent = 'جاري الرفع...';

            const formData = new FormData();
            formData.append('file', selectedFile);

            const xhr = new XMLHttpRequest();
            xhr.open('POST', '/upload', true);

            xhr.upload.onprogress = (e) => {
                if (e.lengthComputable) {
                    const percent = Math.round((e.loaded / e.total) * 100);
                    progressBar.style.width = percent + '%';
                    status.textContent = `جاري الرفع... ${percent}%`;
                }
            };

            xhr.onload = () => {
                progressContainer.style.display = 'none';
                if (xhr.status === 200) {
                    status.innerHTML = '<span style="color:green">✅ تم الرفع بنجاح</span>';
                    loadFeed();
                    setTimeout(() => location.reload(), 1500);
                } else {
                    status.innerHTML = '<span style="color:red">❌ فشل الرفع</span>';
                }
            };

            xhr.send(formData);
        }

        // تحميل الفيديوهات والصور
        async function loadFeed() {
            const res = await fetch('/files');
            const files = await res.json();
            const feed = document.getElementById('feed');
            feed.innerHTML = '';

            files.forEach(file => {
                const isVideo = /\.(mp4|mov|webm|avi|mkv)$/i.test(file);
                const slide = document.createElement('div');
                slide.className = 'media-slide';
                
                if (isVideo) {
                    slide.innerHTML = `
                        <video src="/uploads/${file}" loop playsinline controls></video>
                    `;
                } else {
                    slide.innerHTML = `<img src="/uploads/${file}" alt="">`;
                }
                feed.appendChild(slide);
            });
        }

        // اختيار الملف
        document.getElementById('file-input').addEventListener('change', (e) => {
            selectedFile = e.target.files[0];
            document.getElementById('upload-btn').disabled = false;
        });

        window.onload = loadFeed;
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/upload', methods=['POST'])
def upload():
    try:
        if 'file' not in request.files:
            return jsonify({'message': 'لم يتم اختيار ملف'}), 400
        
        file = request.files['file']
        if file.filename == '' or not allowed_file(file.filename):
            return jsonify({'message': 'نوع الملف غير مدعوم'}), 400

        ext = file.filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4()}.{ext}"
        filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
        
        file.save(filepath)
        return jsonify({'message': 'تم الرفع بنجاح'})
    
    except Exception as e:
        return jsonify({'message': str(e)}), 500

@app.route('/files')
def get_files():
    files = [f for f in os.listdir(UPLOAD_FOLDER) if os.path.isfile(os.path.join(UPLOAD_FOLDER, f))]
    files.sort(key=lambda x: os.path.getmtime(os.path.join(UPLOAD_FOLDER, x)), reverse=True)
    return jsonify(files)

@app.route('/uploads/<filename>')
def serve_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)

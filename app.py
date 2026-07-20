from flask import Flask, request, render_template_string, jsonify, send_from_directory
import os
import uuid
import time

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
    <title>Boost Feed</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family:'Cairo',sans-serif; background:#000; color:white; overflow:hidden; height:100vh; }
        .header { position:fixed; top:0; left:0; right:0; background:rgba(0,0,0,0.8); padding:15px; text-align:center; font-size:20px; z-index:100; }
        .tiktok-container { height:100vh; overflow-y:scroll; scroll-snap-type:y mandatory; }
        .media-slide { height:100vh; scroll-snap-align:start; display:flex; align-items:center; justify-content:center; background:#000; position:relative; }
        .media-slide img, .media-slide video { max-height:100%; max-width:100%; object-fit:contain; }
        .upload-overlay { position:fixed; bottom:30px; left:50%; transform:translateX(-50%); z-index:200; background:rgba(0,0,0,0.85); padding:12px 30px; border-radius:50px; }
        .btn { background:#ff0050; color:white; border:none; padding:14px 32px; border-radius:50px; font-size:17px; font-weight:600; cursor:pointer; }
        #progress-container { position:fixed; bottom:100px; left:50%; transform:translateX(-50%); background:rgba(0,0,0,0.9); padding:15px 25px; border-radius:30px; display:none; z-index:300; width:80%; max-width:400px; }
        .success-msg { position:fixed; top:80px; left:50%; transform:translateX(-50%); background:#4caf50; padding:12px 30px; border-radius:50px; z-index:400; display:none; }
    </style>
</head>
<body>
    <div class="header">FollowerBoost Feed</div>
    <div class="tiktok-container" id="feed"></div>

    <div class="upload-overlay">
        <button class="btn" onclick="document.getElementById('file-input').click()">رفع صورة أو فيديو</button>
        <input type="file" id="file-input" accept="image/*,video/*" style="display:none;">
    </div>

    <div id="progress-container">
        <div style="margin-bottom:10px;">جاري رفع الفيديو... <span id="percent">0%</span></div>
        <div style="height:8px;background:#333;border-radius:10px;overflow:hidden;">
            <div id="progress" style="height:100%;width:0%;background:linear-gradient(90deg,#ff0050,#ff8a00);transition:width 0.4s ease;"></div>
        </div>
        <div id="status" style="font-size:14px;margin-top:8px;color:#ccc;">0 MB / 0 MB</div>
    </div>

    <div class="success-msg" id="success-msg"></div>

    <script>
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
                    slide.innerHTML = `<video src="/uploads/${file}" loop muted playsinline></video>`;
                } else {
                    slide.innerHTML = `<img src="/uploads/${file}" alt="">`;
                }
                feed.appendChild(slide);
            });
        }

        document.getElementById('file-input').addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            const progressContainer = document.getElementById('progress-container');
            const progressBar = document.getElementById('progress');
            const percentText = document.getElementById('percent');
            const status = document.getElementById('status');
            const successMsg = document.getElementById('success-msg');

            progressContainer.style.display = 'block';

            const formData = new FormData();
            formData.append('file', file);

            const xhr = new XMLHttpRequest();
            xhr.open('POST', '/upload', true);

            xhr.upload.onprogress = (e) => {
                if (e.lengthComputable) {
                    const percent = Math.round((e.loaded / e.total) * 100);
                    progressBar.style.width = percent + '%';
                    percentText.textContent = percent + '%';
                    
                    const loadedMB = (e.loaded / (1024*1024)).toFixed(1);
                    const totalMB = (e.total / (1024*1024)).toFixed(1);
                    status.textContent = `${loadedMB} MB / ${totalMB} MB`;
                }
            };

            xhr.onload = () => {
                progressContainer.style.display = 'none';
                if (xhr.status === 200) {
                    successMsg.textContent = '✅ تم رفع الفيديو بنجاح!';
                    successMsg.style.display = 'block';
                    setTimeout(() => successMsg.style.display = 'none', 3000);
                    loadFeed();
                } else {
                    alert('حدث خطأ أثناء الرفع: ' + xhr.responseText);
                }
            };

            xhr.onerror = () => alert('خطأ في الاتصال');
            xhr.send(formData);
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
        
        return jsonify({'message': 'تم الرفع بنجاح', 'filename': unique_filename})
    
    except Exception as e:
        return jsonify({'message': f'خطأ: {str(e)}'}), 500

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

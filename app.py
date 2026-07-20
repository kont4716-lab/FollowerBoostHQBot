from flask import Flask, request, render_template_string, jsonify, send_from_directory
import os
import uuid

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024

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
        .header { position:fixed; top:0; left:0; right:0; background:rgba(0,0,0,0.9); padding:15px; text-align:center; font-size:21px; font-weight:700; z-index:100; }
        .tiktok-container { height:100vh; overflow-y:scroll; scroll-snap-type:y mandatory; -webkit-overflow-scrolling:touch; }
        .media-slide { 
            height:100vh; scroll-snap-align:start; display:flex; align-items:center; justify-content:center; 
            background:#111; position:relative; 
        }
        .media-slide img, .media-slide video { 
            max-height:100%; max-width:100%; object-fit:contain; 
        }
        .controls {
            position: absolute;
            bottom: 30px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0,0,0,0.7);
            padding: 8px 20px;
            border-radius: 30px;
            display: none;
            z-index: 10;
        }
        .media-slide:hover .controls { display: flex; gap: 15px; }
        .btn-control {
            background: rgba(255,255,255,0.2);
            color: white;
            border: none;
            padding: 10px 16px;
            border-radius: 20px;
            cursor: pointer;
            font-size: 14px;
        }
        .upload-overlay { 
            position:fixed; bottom:30px; left:50%; transform:translateX(-50%); z-index:200; 
            background:rgba(0,0,0,0.9); padding:12px 35px; border-radius:50px; box-shadow:0 5px 20px rgba(0,0,0,0.5);
        }
        .btn { background:#ff0050; color:white; border:none; padding:15px 35px; border-radius:50px; font-size:17px; font-weight:700; cursor:pointer; }
    </style>
</head>
<body>
    <div class="header">FollowerBoost Feed</div>
    <div class="tiktok-container" id="feed"></div>

    <div class="upload-overlay">
        <button class="btn" onclick="document.getElementById('file-input').click()">📤 رفع صورة أو فيديو</button>
        <input type="file" id="file-input" accept="image/*,video/*" style="display:none;">
    </div>

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
                    slide.innerHTML = `
                        <video src="/uploads/${file}" loop playsinline></video>
                        <div class="controls">
                            <button class="btn-control" onclick="toggleMute(this)">🔊</button>
                            <button class="btn-control" onclick="togglePlay(this)">⏸️</button>
                        </div>
                    `;
                } else {
                    slide.innerHTML = `<img src="/uploads/${file}" alt="">`;
                }
                feed.appendChild(slide);
            });
        }

        function toggleMute(btn) {
            const video = btn.parentElement.parentElement.querySelector('video');
            video.muted = !video.muted;
            btn.textContent = video.muted ? '🔇' : '🔊';
        }

        function togglePlay(btn) {
            const video = btn.parentElement.parentElement.querySelector('video');
            if (video.paused) {
                video.play();
                btn.textContent = '⏸️';
            } else {
                video.pause();
                btn.textContent = '▶️';
            }
        }

        // Auto play when scrolling
        document.getElementById('feed').addEventListener('scroll', () => {
            const videos = document.querySelectorAll('video');
            const scrollPos = document.getElementById('feed').scrollTop;
            
            videos.forEach(video => {
                const rect = video.getBoundingClientRect();
                if (rect.top < window.innerHeight * 0.6 && rect.bottom > window.innerHeight * 0.4) {
                    video.play().catch(() => {});
                } else {
                    video.pause();
                }
            });
        });

        document.getElementById('file-input').addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (!file) return;

            const formData = new FormData();
            formData.append('file', file);

            const xhr = new XMLHttpRequest();
            xhr.open('POST', '/upload', true);

            xhr.upload.onprogress = (e) => {
                if (e.lengthComputable) {
                    const percent = Math.round((e.loaded / e.total) * 100);
                    console.log(`Progress: ${percent}%`);
                }
            };

            xhr.onload = () => {
                if (xhr.status === 200) {
                    alert('✅ تم رفع الفيديو بنجاح!');
                    loadFeed();
                } else {
                    alert('❌ فشل الرفع');
                }
            };

            xhr.send(formData);
        });

        window.onload = loadFeed;
    </script>
</body>
</html>
'''

# باقي الكود (Routes) بدون تغيير
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

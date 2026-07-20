from flask import Flask, request, render_template_string, jsonify, send_from_directory
import os
import uuid

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

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
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Cairo', sans-serif;
            background: #000;
            color: white;
            overflow: hidden;
            height: 100vh;
        }
        
        .header {
            position: fixed;
            top: 0; left: 0; right: 0;
            background: rgba(0,0,0,0.7);
            padding: 15px;
            z-index: 100;
            text-align: center;
            font-size: 20px;
            font-weight: 700;
        }

        .tiktok-container {
            height: 100vh;
            overflow-y: scroll;
            scroll-snap-type: y mandatory;
            -webkit-overflow-scrolling: touch;
        }

        .media-slide {
            height: 100vh;
            width: 100%;
            scroll-snap-align: start;
            position: relative;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #000;
        }

        .media-slide img, .media-slide video {
            max-height: 100%;
            max-width: 100%;
            object-fit: contain;
        }

        .media-slide video {
            width: 100%;
        }

        .upload-overlay {
            position: fixed;
            bottom: 30px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 200;
            background: rgba(0,0,0,0.8);
            padding: 12px 30px;
            border-radius: 50px;
            display: flex;
            gap: 15px;
        }

        .btn {
            background: #ff0050;
            color: white;
            border: none;
            padding: 14px 28px;
            border-radius: 50px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
        }

        #progress-container {
            position: fixed;
            bottom: 100px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0,0,0,0.8);
            padding: 10px 20px;
            border-radius: 30px;
            display: none;
            z-index: 300;
        }

        .success-msg {
            position: fixed;
            top: 80px;
            left: 50%;
            transform: translateX(-50%);
            background: #4caf50;
            color: white;
            padding: 12px 25px;
            border-radius: 50px;
            z-index: 400;
            display: none;
        }
    </style>
</head>
<body>
    <div class="header">FollowerBoost Feed</div>

    <div class="tiktok-container" id="feed">
        <!-- Media will be loaded here by JS -->
    </div>

    <div class="upload-overlay">
        <button class="btn" onclick="document.getElementById('file-input').click()">رفع صورة/فيديو</button>
        <input type="file" id="file-input" accept="image/*,video/*" style="display:none">
    </div>

    <div id="progress-container">
        <div style="color:white; margin-bottom:8px;">جاري الرفع...</div>
        <div style="height:6px; background:#333; border-radius:10px; overflow:hidden;">
            <div id="progress" style="height:100%; width:0%; background:#ff0050; transition:width 0.3s;"></div>
        </div>
    </div>

    <div class="success-msg" id="success-msg"></div>

    <script>
        let currentFiles = [];

        async function loadFeed() {
            const res = await fetch('/files');
            currentFiles = await res.json();
            
            const feed = document.getElementById('feed');
            feed.innerHTML = '';

            currentFiles.forEach(file => {
                const isVideo = file.endsWith('.mp4') || file.endsWith('.mov') || 
                               file.endsWith('.webm') || file.endsWith('.avi') || file.endsWith('.mkv');
                
                const slide = document.createElement('div');
                slide.className = 'media-slide';
                
                if (isVideo) {
                    slide.innerHTML = `
                        <video src="/uploads/${file}" loop muted playsinline></video>
                    `;
                } else {
                    slide.innerHTML = `
                        <img src="/uploads/${file}" alt="media">
                    `;
                }
                feed.appendChild(slide);
            });
        }

        // TikTok-like auto play
        const feed = document.getElementById('feed');
        feed.addEventListener('scroll', () => {
            const videos = feed.querySelectorAll('video');
            const scrollPos = feed.scrollTop;
            const slideHeight = window.innerHeight;

            videos.forEach(video => {
                const slide = video.parentElement;
                const slideTop = slide.offsetTop;
                if (scrollPos >= slideTop - 100 && scrollPos <= slideTop + 100) {
                    video.play();
                } else {
                    video.pause();
                }
            });
        });

        // Upload
        document.getElementById('file-input').addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            const progressContainer = document.getElementById('progress-container');
            const progressBar = document.getElementById('progress');
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
                }
            };

            xhr.onload = () => {
                progressContainer.style.display = 'none';
                if (xhr.status === 200) {
                    successMsg.textContent = '✅ تم الرفع بنجاح!';
                    successMsg.style.display = 'block';
                    setTimeout(() => successMsg.style.display = 'none', 2500);
                    loadFeed();
                }
            };

            xhr.send(formData);
        });

        // Initial load
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
    if 'file' not in request.files:
        return jsonify({'message': 'لم يتم اختيار ملف'}), 400
    
    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'message': 'ملف غير صالح'}), 400
    
    ext = file.filename.rsplit('.', 1)[1].lower()
    unique_filename = f"{uuid.uuid4()}.{ext}"
    
    filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
    file.save(filepath)
    
    return jsonify({'message': 'تم الرفع بنجاح', 'filename': unique_filename})

@app.route('/files')
def get_files():
    files = [f for f in os.listdir(UPLOAD_FOLDER) if os.path.isfile(os.path.join(UPLOAD_FOLDER, f))]
    return jsonify(files)

@app.route('/uploads/<filename>')
def serve_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)

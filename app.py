from flask import Flask, request, render_template_string, jsonify
import os
import uuid
import json
from supabase import create_client, Client

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # الحد الأقصى لحجم الملف 1 جيجابايت

ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'mp4', 'mov', 'avi', 'mkv', 'webm'}
LIKE_FILE = 'likes.json'
BUCKET_NAME = 'uploads'

# إعداد Supabase باستخدام متغيرات البيئة (تعمل تلقائيًا في Render)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase = None
    print("تنبيه: لم يتم العثور على متغيرات بيئة Supabase.")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# تحميل وتجهيز ملف الإعجابات
if os.path.exists(LIKE_FILE):
    with open(LIKE_FILE, 'r', encoding='utf-8') as f:
        likes_data = json.load(f)
else:
    likes_data = {}

def save_likes():
    with open(LIKE_FILE, 'w', encoding='utf-8') as f:
        json.dump(likes_data, f, ensure_ascii=False, indent=2)

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
        .header { position:fixed; top:0; left:0; right:0; background:rgba(0,0,0,0.85); padding:15px; text-align:center; z-index:100; font-size:20px; font-weight:700; }
        .tiktok-container { height:100vh; overflow-y:scroll; scroll-snap-type:y mandatory; scroll-behavior:smooth; }
        .media-slide { height:100vh; scroll-snap-align:start; display:flex; align-items:center; justify-content:center; background:#111; position:relative; }
        .media-slide video, .media-slide img { max-height:100%; max-width:100%; object-fit:contain; }
        .like-btn {
            position:absolute; bottom:80px; right:20px; background:rgba(0,0,0,0.7); 
            width:65px; height:65px; border-radius:50%; display:flex; align-items:center; 
            justify-content:center; font-size:32px; cursor:pointer; z-index:10; transition:0.3s;
        }
        .like-btn.liked { color:#ff0050; transform:scale(1.4); }
        .like-count { font-size:14px; margin-top:3px; }
        .upload-btn {
            position:fixed; bottom:30px; left:50%; transform:translateX(-50%);
            background:#ff0050; color:white; border:none; padding:15px 30px; 
            border-radius:50px; font-size:17px; font-weight:700; z-index:200;
        }
        #progress-container { 
            position:fixed; bottom:100px; left:50%; transform:translateX(-50%);
            background:rgba(0,0,0,0.9); padding:12px 25px; border-radius:30px; display:none; z-index:300;
        }
    </style>
</head>
<body>
    <div class="header">FollowerBoost Feed</div>
    <div class="tiktok-container" id="feed"></div>

    <button class="upload-btn" onclick="document.getElementById('file-input').click()">📤 رفع</button>
    <input type="file" id="file-input" accept="image/*,video/*" style="display:none;">

    <div id="progress-container">
        <div style="margin-bottom:8px;">جاري الرفع... <span id="percent">0%</span></div>
        <div style="height:8px; background:#333; border-radius:10px; width:300px; overflow:hidden;">
            <div id="progress" style="height:100%; width:0%; background:#ff0050; transition:width 0.3s;"></div>
        </div>
    </div>

    <script>
        let username = localStorage.getItem('username');
        if (!username) {
            username = prompt("أدخل اسمك ليتم حفظ اللايكات:");
            if (!username) username = "مستخدم" + Math.floor(Math.random()*9999);
            localStorage.setItem('username', username);
        }

        async function loadFeed() {
            const res = await fetch('/files');
            const filesData = await res.json();
            const likesRes = await fetch('/likes');
            const likes = await likesRes.json();

            const feed = document.getElementById('feed');
            feed.innerHTML = '';

            filesData.forEach(fileObj => {
                const fileName = fileObj.name;
                const fileUrl = fileObj.url;
                const isVideo = /\.(mp4|mov|webm|avi|mkv)$/i.test(fileName);
                const slide = document.createElement('div');
                slide.className = 'media-slide';

                const likeInfo = likes[fileName] || {count: 0, users: []};
                const isLiked = likeInfo.users.includes(username);

                if (isVideo) {
                    slide.innerHTML = `
                        <video src="${fileUrl}" loop playsinline preload="metadata"></video>
                        <div class="like-btn ${isLiked ? 'liked' : ''}" data-file="${fileName}" onclick="toggleLike(this)">
                            ❤️ <span class="like-count">${likeInfo.count}</span>
                        </div>
                    `;
                } else {
                    slide.innerHTML = `
                        <img src="${fileUrl}" alt="">
                        <div class="like-btn ${isLiked ? 'liked' : ''}" data-file="${fileName}" onclick="toggleLike(this)">
                            ❤️ <span class="like-count">${likeInfo.count}</span>
                        </div>
                    `;
                }
                feed.appendChild(slide);
            });
        }

        async function toggleLike(btn) {
            const file = btn.dataset.file;
            const res = await fetch('/like', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({file: file, username: localStorage.getItem('username')})
            });
            const data = await res.json();
            if (data.success) {
                btn.classList.toggle('liked', data.liked);
                btn.querySelector('.like-count').textContent = data.count;
            }
        }

        // تشغيل الفيديو عند ظهوره في الشاشة
        document.getElementById('feed').addEventListener('scroll', () => {
            document.querySelectorAll('video').forEach(video => {
                const rect = video.getBoundingClientRect();
                if (rect.top < window.innerHeight * 0.7 && rect.bottom > window.innerHeight * 0.3) {
                    video.play().catch(() => {});
                } else {
                    video.pause();
                }
            });
        });

        document.getElementById('file-input').addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (!file) return;

            const progressContainer = document.getElementById('progress-container');
            const progressBar = document.getElementById('progress');
            const percentText = document.getElementById('percent');

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
                }
            };

            xhr.onload = () => {
                progressContainer.style.display = 'none';
                if (xhr.status === 200) {
                    loadFeed();
                } else {
                    alert("حدث خطأ أثناء الرفع، راجع السجلات");
                }
            };

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
    if not supabase:
        return jsonify({'message': 'إعدادات Supabase غير متوفرة'}), 500
        
    try:
        if 'file' not in request.files:
            return jsonify({'message': 'لم يتم اختيار ملف'}), 400
        file = request.files['file']
        if file.filename == '' or not allowed_file(file.filename):
            return jsonify({'message': 'نوع الملف غير مدعوم'}), 400

        ext = file.filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4()}.{ext}"
        
        # قراءة الملف من الذاكرة ورفعه مباشرة إلى Supabase
        file_bytes = file.read()
        res = supabase.storage.from_(BUCKET_NAME).upload(
            path=unique_filename,
            file=file_bytes,
            file_options={"content-type": file.content_type}
        )
        
        return jsonify({'message': 'تم الرفع بنجاح'})
    except Exception as e:
        print("Upload Error:", e)
        return jsonify({'message': str(e)}), 500

@app.route('/files')
def get_files():
    if not supabase:
        return jsonify([])
        
    try:
        # جلب قائمة الملفات من Supabase
        res = supabase.storage.from_(BUCKET_NAME).list()
        
        # تصفية الملفات وإزالة العناصر الفارغة، وترتيبها من الأحدث للأقدم
        valid_files = [f for f in res if f.get('name') and f['name'] != '.emptyFolderPlaceholder']
        valid_files.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        file_list = []
        for f in valid_files:
            filename = f['name']
            # استخراج الرابط العام المباشر وعرضه في الواجهة
            public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(filename)
            file_list.append({
                "name": filename,
                "url": public_url
            })
            
        return jsonify(file_list)
    except Exception as e:
        print("Error fetching files:", e)
        return jsonify([])

@app.route('/likes')
def get_likes():
    return jsonify(likes_data)

@app.route('/like', methods=['POST'])
def like():
    data = request.json
    file = data.get('file')
    user = data.get('username')

    if file not in likes_data:
        likes_data[file] = {"count": 0, "users": []}

    if user not in likes_data[file]["users"]:
        likes_data[file]["users"].append(user)
        likes_data[file]["count"] += 1
        save_likes()
        return jsonify({"success": True, "count": likes_data[file]["count"], "liked": True})
    else:
        likes_data[file]["users"].remove(user)
        likes_data[file]["count"] -= 1
        save_likes()
        return jsonify({"success": True, "count": likes_data[file]["count"], "liked": False})

if __name__ == '__main__':
    # يعمل محليًا بهذا الشكل، ولكن في Render سيقوم gunicorn بالتعامل مع app
    app.run(host='0.0.0.0', port=5000, debug=False)

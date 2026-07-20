from flask import Flask, request, render_template_string, jsonify
import os
import uuid
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max upload

# Allowed extensions
ALLOWED_EXTENSIONS = {
    'jpg', 'jpeg', 'png', 'gif', 'webp',
    'mp4', 'mov', 'avi', 'mkv', 'webm'
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Create uploads directory
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
        
        body {
            font-family: 'Cairo', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            padding: 0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #333;
        }
        
        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.2);
            width: 90%;
            max-width: 500px;
            padding: 40px 30px;
            text-align: center;
        }
        
        h1 {
            color: #4a4a4a;
            margin-bottom: 30px;
            font-size: 28px;
        }
        
        .upload-area {
            border: 3px dashed #667eea;
            border-radius: 15px;
            padding: 40px 20px;
            margin: 20px 0;
            transition: all 0.3s ease;
            cursor: pointer;
        }
        
        .upload-area:hover {
            background: #f8f9ff;
            border-color: #4a4a4a;
        }
        
        .upload-area.dragover {
            background: #e3f2fd;
            border-color: #2196f3;
        }
        
        input[type="file"] {
            display: none;
        }
        
        .btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 14px 40px;
            font-size: 18px;
            border-radius: 50px;
            cursor: pointer;
            margin: 15px 5px;
            transition: all 0.3s ease;
            font-weight: 600;
        }
        
        .btn:hover {
            background: #5a67d8;
            transform: translateY(-3px);
        }
        
        .btn:disabled {
            background: #a0a0a0;
            cursor: not-allowed;
            transform: none;
        }
        
        #progress-container {
            margin: 25px 0;
            display: none;
        }
        
        .progress-bar {
            height: 12px;
            background: #e0e0e0;
            border-radius: 20px;
            overflow: hidden;
            margin-bottom: 10px;
        }
        
        .progress {
            height: 100%;
            background: linear-gradient(90deg, #667eea, #764ba2);
            width: 0%;
            transition: width 0.3s ease;
            border-radius: 20px;
        }
        
        #status {
            font-size: 16px;
            margin: 15px 0;
            min-height: 24px;
        }
        
        .success {
            color: #4caf50;
            font-weight: 600;
        }
        
        .error {
            color: #f44336;
            font-weight: 600;
        }
        
        .file-info {
            margin: 15px 0;
            font-size: 14px;
            color: #666;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>رفع صورة أو فيديو</h1>
        
        <div class="upload-area" id="drop-area">
            <p>اسحب الملف هنا أو</p>
            <button class="btn" onclick="document.getElementById('file-input').click()">اختر ملف</button>
            <input type="file" id="file-input" accept="image/*,video/*">
            <div class="file-info" id="file-name"></div>
        </div>
        
        <button class="btn" id="upload-btn" onclick="uploadFile()" disabled>رفع الملف</button>
        
        <div id="progress-container">
            <div class="progress-bar">
                <div class="progress" id="progress"></div>
            </div>
            <div id="status"></div>
        </div>
        
        <div id="result"></div>
    </div>

    <script>
        let selectedFile = null;
        
        const dropArea = document.getElementById('drop-area');
        const fileInput = document.getElementById('file-input');
        const uploadBtn = document.getElementById('upload-btn');
        const fileNameDisplay = document.getElementById('file-name');
        
        // Drag and drop handlers
        dropArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropArea.classList.add('dragover');
        });
        
        dropArea.addEventListener('dragleave', () => {
            dropArea.classList.remove('dragover');
        });
        
        dropArea.addEventListener('drop', (e) => {
            e.preventDefault();
            dropArea.classList.remove('dragover');
            const file = e.dataTransfer.files[0];
            handleFile(file);
        });
        
        fileInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            handleFile(file);
        });
        
        function handleFile(file) {
            if (!file) return;
            
            const ext = file.name.split('.').pop().toLowerCase();
            const allowed = ['jpg','jpeg','png','gif','webp','mp4','mov','avi','mkv','webm'];
            
            if (!allowed.includes(ext)) {
                alert('نوع الملف غير مدعوم. يرجى اختيار صورة أو فيديو.');
                return;
            }
            
            selectedFile = file;
            fileNameDisplay.textContent = `الملف المختار: \( {file.name} ( \){(file.size / (1024*1024)).toFixed(2)} MB)`;
            uploadBtn.disabled = false;
        }
        
        function uploadFile() {
            if (!selectedFile) return;
            
            const progressContainer = document.getElementById('progress-container');
            const progressBar = document.getElementById('progress');
            const status = document.getElementById('status');
            const result = document.getElementById('result');
            
            progressContainer.style.display = 'block';
            uploadBtn.disabled = true;
            result.innerHTML = '';
            status.textContent = 'جاري الرفع...';
            
            const formData = new FormData();
            formData.append('file', selectedFile);
            
            const xhr = new XMLHttpRequest();
            
            xhr.open('POST', '/upload', true);
            
            xhr.upload.onprogress = function(e) {
                if (e.lengthComputable) {
                    const percent = Math.round((e.loaded / e.total) * 100);
                    progressBar.style.width = percent + '%';
                    status.textContent = `جاري الرفع... ${percent}%`;
                }
            };
            
            xhr.onload = function() {
                if (xhr.status === 200) {
                    const response = JSON.parse(xhr.responseText);
                    progressBar.style.width = '100%';
                    status.innerHTML = `<span class="success">✅ ${response.message}</span>`;
                    result.innerHTML = `<p style="color:#4caf50; margin-top:20px;">تم حفظ الملف بنجاح!</p>`;
                    
                    // Reset form after 3 seconds
                    setTimeout(() => {
                        resetForm();
                    }, 3000);
                } else {
                    const errorMsg = xhr.responseText || 'حدث خطأ أثناء الرفع';
                    status.innerHTML = `<span class="error">❌ ${errorMsg}</span>`;
                    uploadBtn.disabled = false;
                }
            };
            
            xhr.onerror = function() {
                status.innerHTML = `<span class="error">❌ خطأ في الاتصال</span>`;
                uploadBtn.disabled = false;
            };
            
            xhr.send(formData);
        }
        
        function resetForm() {
            selectedFile = null;
            fileNameDisplay.textContent = '';
            document.getElementById('file-input').value = '';
            document.getElementById('progress-container').style.display = 'none';
            document.getElementById('progress').style.width = '0%';
            document.getElementById('upload-btn').disabled = true;
            document.getElementById('result').innerHTML = '';
        }
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
    
    if file.filename == '':
        return jsonify({'message': 'لم يتم اختيار ملف'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'message': 'نوع الملف غير مسموح به'}), 400
    
    # Generate unique filename
    ext = file.filename.rsplit('.', 1)[1].lower()
    unique_filename = f"{uuid.uuid4()}.{ext}"
    
    filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
    file.save(filepath)
    
    return jsonify({
        'message': 'تم الرفع بنجاح',
        'filename': unique_filename
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)

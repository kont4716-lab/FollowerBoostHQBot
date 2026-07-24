from flask import Flask, request, render_template_string, jsonify
import os
import uuid
from supabase import create_client, Client

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # الحد الأقصى لحجم الملف 1 جيجابايت

ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'mp4', 'mov', 'avi', 'mkv', 'webm'}
BUCKET_NAME = 'uploads'

# إعداد Supabase من متغيرات البيئة
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase = None
    print("تنبيه: لم يتم العثور على متغيرات بيئة Supabase.")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
        
        .header { 
            position:fixed; top:0; left:0; right:0; 
            background:rgba(0,0,0,0.85); padding:15px; 
            text-align:center; z-index:100; font-size:20px; font-weight:700; 
            display:flex; justify-content:center; align-items:center;
        }
        
        .chat-btn-header {
            position:absolute; left:15px; top:50%; transform:translateY(-50%);
            background:#ff0050; color:white; border:none; padding:6px 14px;
            border-radius:20px; font-size:13px; font-family:'Cairo', sans-serif;
            font-weight:bold; cursor:pointer; display:flex; align-items:center; gap:5px;
        }

        .tiktok-container { height:100vh; overflow-y:scroll; scroll-snap-type:y mandatory; scroll-behavior:smooth; }
        .media-slide { height:100vh; scroll-snap-align:start; display:flex; align-items:center; justify-content:center; background:#111; position:relative; }
        .media-slide video, .media-slide img { max-height:100%; max-width:100%; object-fit:contain; }
        
        /* شريط الإجراءات الجانبي */
        .action-bar {
            position:absolute; bottom:80px; right:20px; 
            display:flex; flex-direction:column; gap:18px; 
            align-items:center; z-index:10;
        }
        .action-btn {
            background:rgba(0,0,0,0.7); 
            width:60px; height:60px; border-radius:50%; 
            display:flex; flex-direction:column; align-items:center; 
            justify-content:center; font-size:26px; cursor:pointer; 
            transition:0.3s; color:white; border:none;
        }
        .like-btn.liked { color:#ff0050; transform:scale(1.15); }
        .action-count { font-size:12px; margin-top:2px; font-weight:600; }

        .upload-btn {
            position:fixed; bottom:25px; left:50%; transform:translateX(-50%);
            background:#ff0050; color:white; border:none; padding:12px 30px; 
            border-radius:50px; font-size:16px; font-weight:700; z-index:200; cursor:pointer;
        }
        #progress-container { 
            position:fixed; bottom:90px; left:50%; transform:translateX(-50%);
            background:rgba(0,0,0,0.9); padding:12px 25px; border-radius:30px; display:none; z-index:300;
        }

        /* نافذة التعليقات المنزلقة */
        .comments-modal {
            position:fixed; bottom:-100%; left:0; right:0;
            height:55vh; background:#181818; border-top-left-radius:20px; border-top-right-radius:20px;
            z-index:500; transition:bottom 0.3s ease-in-out; display:flex; flex-direction:column;
            box-shadow:0 -5px 25px rgba(0,0,0,0.8);
        }
        .comments-modal.active { bottom:0; }
        .comments-header {
            padding:15px; text-align:center; font-weight:bold; border-bottom:1px solid #333; position:relative;
        }
        .close-comments {
            position:absolute; left:15px; top:12px; cursor:pointer; font-size:20px; color:#888;
        }
        .comments-list {
            flex:1; overflow-y:auto; padding:15px;
        }
        .comment-item {
            margin-bottom:12px; background:#222; padding:10px 14px; border-radius:12px;
        }
        .comment-user {
            font-size:12px; color:#ff0050; font-weight:bold; margin-bottom:3px;
        }
        .comment-text {
            font-size:14px; word-break:break-word; color:#eee;
        }
        .comment-input-area {
            display:flex; padding:10px 15px; border-top:1px solid #333; background:#111;
        }
        .comment-input {
            flex:1; background:#222; border:1px solid #444; color:white;
            padding:10px 15px; border-radius:25px; outline:none; font-family:'Cairo', sans-serif;
        }
        .send-comment-btn {
            background:#ff0050; color:white; border:none; padding:0 18px;
            margin-right:8px; border-radius:25px; font-weight:bold; cursor:pointer;
        }

        /* نافذة الرسائل الخاصة */
        .messaging-modal {
            position:fixed; bottom:-100%; left:0; right:0;
            height:80vh; background:#181818; border-top-left-radius:20px; border-top-right-radius:20px;
            z-index:600; transition:bottom 0.3s ease-in-out; display:flex; flex-direction:column;
            box-shadow:0 -5px 25px rgba(0,0,0,0.8);
        }
        .messaging-modal.active { bottom:0; }
        
        .messaging-header {
            padding:15px; text-align:center; font-weight:bold; border-bottom:1px solid #333; 
            position:relative; display:flex; align-items:center; justify-content:center;
        }
        .close-messaging { position:absolute; left:15px; cursor:pointer; font-size:18px; color:#888; }
        .back-messaging { position:absolute; right:15px; cursor:pointer; font-size:18px; color:#888; display:none; }

        /* منطقة البحث عن مستخدمين */
        .search-area { padding:12px 15px; border-bottom:1px solid #222; }
        .search-input {
            width:100%; background:#222; border:1px solid #444; color:white;
            padding:10px 15px; border-radius:20px; outline:none; font-family:'Cairo', sans-serif;
        }

        .user-list { flex:1; overflow-y:auto; padding:10px 15px; }
        .user-item {
            display:flex; align-items:center; justify-content:space-between;
            padding:12px 15px; background:#222; border-radius:12px; margin-bottom:8px; cursor:pointer; transition:0.2s;
        }
        .user-item:hover { background:#2a2a2a; }
        .user-item-name { font-weight:bold; color:#fff; }
        .user-item-action { font-size:12px; color:#ff0050; font-weight:bold; }

        /* منطقة المحادثة النشطة */
        .chat-view { display:none; flex-direction:column; flex:1; overflow:hidden; }
        .chat-messages { flex:1; overflow-y:auto; padding:15px; display:flex; flex-direction:column; gap:10px; }
        
        .msg-bubble {
            max-width:75%; padding:10px 14px; border-radius:16px; font-size:14px; word-break:break-word; line-height:1.4;
        }
        .msg-sent {
            align-self:flex-start; background:#ff0050; color:white; border-bottom-right-radius:4px;
        }
        .msg-received {
            align-self:flex-end; background:#2c2c2e; color:white; border-bottom-left-radius:4px;
        }
        .msg-sender { font-size:10px; opacity:0.7; margin-bottom:2px; font-weight:bold; }

        .chat-input-area {
            display:flex; padding:10px 15px; border-top:1px solid #333; background:#111;
        }
        .chat-input {
            flex:1; background:#222; border:1px solid #444; color:white;
            padding:10px 15px; border-radius:25px; outline:none; font-family:'Cairo', sans-serif;
        }
        .send-msg-btn {
            background:#ff0050; color:white; border:none; padding:0 18px;
            margin-right:8px; border-radius:25px; font-weight:bold; cursor:pointer;
        }
    </style>
</head>
<body>
    <div class="header">
        <span>FollowerBoost Feed</span>
        <button class="chat-btn-header" onclick="openMessagingModal()">💬 الرسائل</button>
    </div>
    
    <div class="tiktok-container" id="feed"></div>

    <button class="upload-btn" onclick="document.getElementById('file-input').click()">📤 رفع</button>
    <input type="file" id="file-input" accept="image/*,video/*" style="display:none;">

    <div id="progress-container">
        <div style="margin-bottom:8px;">جاري الرفع... <span id="percent">0%</span></div>
        <div style="height:8px; background:#333; border-radius:10px; width:300px; overflow:hidden;">
            <div id="progress" style="height:100%; width:0%; background:#ff0050; transition:width 0.3s;"></div>
        </div>
    </div>

    <!-- نافذة التعليقات -->
    <div class="comments-modal" id="comments-modal">
        <div class="comments-header">
            <span>التعليقات</span>
            <span class="close-comments" onclick="closeComments()">✕</span>
        </div>
        <div class="comments-list" id="comments-list"></div>
        <div class="comment-input-area">
            <input type="text" id="comment-input" class="comment-input" placeholder="اكتب تعليقاً..." onkeypress="if(event.key==='Enter') sendComment()">
            <button class="send-comment-btn" onclick="sendComment()">إرسال</button>
        </div>
    </div>

    <!-- نافذة الرسائل الخاصة -->
    <div class="messaging-modal" id="messaging-modal">
        <div class="messaging-header">
            <span class="back-messaging" id="back-messaging-btn" onclick="backToUserSearch()">➔</span>
            <span id="messaging-title">المحادثات الخاصة</span>
            <span class="close-messaging" onclick="closeMessagingModal()">✕</span>
        </div>

        <!-- عرض البحث والقائمة -->
        <div id="search-view" style="display:flex; flex-direction:column; flex:1; overflow:hidden;">
            <div class="search-area">
                <input type="text" id="user-search-input" class="search-input" placeholder="ابحث عن اسم مستخدم للمراسلة..." oninput="handleUserSearch()">
            </div>
            <div class="user-list" id="user-results-list">
                <div style="text-align:center; color:#777; margin-top:20px;">اكتب اسم المستخدم للبحث والبدء في المحادثة</div>
            </div>
        </div>

        <!-- عرض المحادثة النشطة -->
        <div class="chat-view" id="chat-view">
            <div class="chat-messages" id="chat-messages"></div>
            <div class="chat-input-area">
                <input type="text" id="chat-input" class="chat-input" placeholder="اكتب رسالة..." onkeypress="if(event.key==='Enter') sendChatMessage()">
                <button class="send-msg-btn" onclick="sendChatMessage()">إرسال</button>
            </div>
        </div>
    </div>

    <script>
        let currentPostId = null;
        let postsCache = {};
        
        // متغيرات حالة نظام الرسائل
        let activeConversationId = null;
        let activeTargetUsername = null;
        let chatPollInterval = null;

        async function initUser() {
            let username = localStorage.getItem('username');
            
            if (username) {
                const res = await fetch('/verify_user', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username: username})
                });
                const data = await res.json();
                if (!data.exists) {
                    username = null;
                    localStorage.removeItem('username');
                }
            }

            while (!username) {
                username = prompt("أدخل اسم مستخدم جديد لإنشاء حسابك:");
                if (!username || !username.trim()) continue;
                username = username.trim();

                const res = await fetch('/register', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username: username})
                });
                const data = await res.json();

                if (data.success) {
                    localStorage.setItem('username', username);
                    alert("تم تسجيل اسمك بنجاح!");
                } else {
                    alert(data.message || "اسم المستخدم غير متاح، يرجى اختيار اسم آخر.");
                    username = null;
                }
            }
        }

        async function loadFeed() {
            try {
                const res = await fetch('/feed');
                const posts = await res.json();
                const username = localStorage.getItem('username');

                const feed = document.getElementById('feed');
                feed.innerHTML = '';
                postsCache = {};

                posts.forEach(post => {
                    postsCache[post.id] = post;
                    const isVideo = /\.(mp4|mov|webm|avi|mkv)$/i.test(post.media_url);
                    const slide = document.createElement('div');
                    slide.className = 'media-slide';

                    const isLiked = post.liked_users.includes(username);

                    const actionHtml = `
                        <div class="action-bar">
                            <button class="action-btn like-btn ${isLiked ? 'liked' : ''}" onclick="toggleLike('${post.id}', this)">
                                ❤️ <span class="action-count">${post.likes_count}</span>
                            </button>
                            <button class="action-btn" onclick="openComments('${post.id}')">
                                💬 <span class="action-count" id="comment-count-${post.id}">${post.comments.length}</span>
                            </button>
                        </div>
                    `;

                    if (isVideo) {
                        slide.innerHTML = `
                            <video src="${post.media_url}" loop playsinline preload="metadata"></video>
                            ${actionHtml}
                        `;
                    } else {
                        slide.innerHTML = `
                            <img src="${post.media_url}" alt="Media">
                            ${actionHtml}
                        `;
                    }
                    feed.appendChild(slide);
                });
                
                const firstVideo = feed.querySelector('video');
                if(firstVideo) firstVideo.play().catch(() => {});
                
            } catch (error) {
                console.error("خطأ في تحميل المنشورات:", error);
            }
        }

        async function toggleLike(postId, btn) {
            const username = localStorage.getItem('username');
            const res = await fetch('/like', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({post_id: postId, username: username})
            });
            const data = await res.json();
            if (data.success) {
                btn.classList.toggle('liked', data.liked);
                btn.querySelector('.action-count').textContent = data.count;
            }
        }

        function openComments(postId) {
            currentPostId = postId;
            const post = postsCache[postId];
            if (!post) return;

            renderCommentsList(post.comments || []);
            document.getElementById('comments-modal').classList.add('active');
        }

        function closeComments() {
            document.getElementById('comments-modal').classList.remove('active');
            currentPostId = null;
        }

        function renderCommentsList(comments) {
            const listEl = document.getElementById('comments-list');
            listEl.innerHTML = '';

            if (comments.length === 0) {
                listEl.innerHTML = '<div style="text-align:center; color:#777; margin-top:20px;">لا توجد تعليقات بعد. كن أول من يعلق!</div>';
                return;
            }

            comments.forEach(c => {
                const item = document.createElement('div');
                item.className = 'comment-item';
                item.innerHTML = `
                    <div class="comment-user">@${escapeHtml(c.username)}</div>
                    <div class="comment-text">${escapeHtml(c.content)}</div>
                `;
                listEl.appendChild(item);
            });
            listEl.scrollTop = listEl.scrollHeight;
        }

        async function sendComment() {
            const input = document.getElementById('comment-input');
            const content = input.value.trim();
            const username = localStorage.getItem('username');

            if (!content || !currentPostId) return;

            const res = await fetch('/comment', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    post_id: currentPostId,
                    username: username,
                    content: content
                })
            });

            const data = await res.json();
            if (data.success) {
                input.value = '';
                if (postsCache[currentPostId]) {
                    postsCache[currentPostId].comments = data.comments;
                }
                renderCommentsList(data.comments);
                const countSpan = document.getElementById(`comment-count-${currentPostId}`);
                if (countSpan) countSpan.textContent = data.count;
            } else {
                alert(data.message || "حدث خطأ أثناء إضافة التعليق");
            }
        }

        /* ----- وظائف نظام الرسائل الخاصة ----- */

        function openMessagingModal() {
            document.getElementById('messaging-modal').classList.add('active');
            backToUserSearch();
        }

        function closeMessagingModal() {
            document.getElementById('messaging-modal').classList.remove('active');
            stopChatPolling();
        }

        async function handleUserSearch() {
            const query = document.getElementById('user-search-input').value.trim();
            const username = localStorage.getItem('username');
            const listEl = document.getElementById('user-results-list');

            if (!query) {
                listEl.innerHTML = '<div style="text-align:center; color:#777; margin-top:20px;">اكتب اسم المستخدم للبحث والبدء في المحادثة</div>';
                return;
            }

            try {
                const res = await fetch('/search_users', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({query: query, username: username})
                });
                const users = await res.json();

                listEl.innerHTML = '';
                if (users.length === 0) {
                    listEl.innerHTML = '<div style="text-align:center; color:#777; margin-top:20px;">لم يتم العثور على مستخدمين مطبقين</div>';
                    return;
                }

                users.forEach(u => {
                    const item = document.createElement('div');
                    item.className = 'user-item';
                    item.onclick = () => startChatWith(u.username);
                    item.innerHTML = `
                        <span class="user-item-name">@${escapeHtml(u.username)}</span>
                        <span class="user-item-action">مراسلة 💬</span>
                    `;
                    listEl.appendChild(item);
                });
            } catch (err) {
                console.error("خطأ أثناء البحث عن مستخدمين:", err);
            }
        }

        async function startChatWith(targetUsername) {
            const username = localStorage.getItem('username');
            try {
                const res = await fetch('/create_or_get_conversation', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username: username, target_username: targetUsername})
                });
                const data = await res.json();

                if (data.success) {
                    activeConversationId = data.conversation_id;
                    activeTargetUsername = targetUsername;

                    document.getElementById('search-view').style.display = 'none';
                    document.getElementById('chat-view').style.display = 'flex';
                    document.getElementById('back-messaging-btn').style.display = 'block';
                    document.getElementById('messaging-title').textContent = `@${targetUsername}`;

                    loadMessages();
                    startChatPolling();
                } else {
                    alert(data.message || "تعذر فتح المحادثة");
                }
            } catch (err) {
                console.error("خطأ في إنشاء أو جلب المحادثة:", err);
            }
        }

        function backToUserSearch() {
            stopChatPolling();
            activeConversationId = null;
            activeTargetUsername = null;

            document.getElementById('search-view').style.display = 'flex';
            document.getElementById('chat-view').style.display = 'none';
            document.getElementById('back-messaging-btn').style.display = 'none';
            document.getElementById('messaging-title').textContent = 'المحادثات الخاصة';
            document.getElementById('user-search-input').value = '';
            handleUserSearch();
        }

        async function loadMessages() {
            if (!activeConversationId) return;

            try {
                const res = await fetch('/get_messages', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({conversation_id: activeConversationId})
                });
                const messages = await res.json();
                renderMessages(messages);
            } catch (err) {
                console.error("خطأ أثناء جلب الرسائل:", err);
            }
        }

        function renderMessages(messages) {
            const container = document.getElementById('chat-messages');
            const currentUsername = localStorage.getItem('username');
            
            // التحقق من حالة التمرير الحالية لتجنب إزعاج المستخدم إذا كان يقرأ الرسائل العلوية
            const isScrolledToBottom = container.scrollHeight - container.clientHeight <= container.scrollTop + 50;

            container.innerHTML = '';

            if (messages.length === 0) {
                container.innerHTML = '<div style="text-align:center; color:#777; margin-top:20px;">لا توجد رسائل بعد. ابدأ المحادثة الآن!</div>';
                return;
            }

            messages.forEach(m => {
                const isMe = m.sender_username === currentUsername;
                const bubble = document.createElement('div');
                bubble.className = `msg-bubble ${isMe ? 'msg-sent' : 'msg-received'}`;
                bubble.innerHTML = `
                    <div class="msg-sender">${escapeHtml(m.sender_username)}</div>
                    <div>${escapeHtml(m.content)}</div>
                `;
                container.appendChild(bubble);
            });

            if (isScrolledToBottom) {
                container.scrollTop = container.scrollHeight;
            }
        }

        async function sendChatMessage() {
            const input = document.getElementById('chat-input');
            const content = input.value.trim();
            const username = localStorage.getItem('username');

            if (!content || !activeConversationId) return;

            input.value = '';

            try {
                const res = await fetch('/send_message', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        conversation_id: activeConversationId,
                        username: username,
                        content: content
                    })
                });

                const data = await res.json();
                if (data.success) {
                    await loadMessages();
                    const container = document.getElementById('chat-messages');
                    container.scrollTop = container.scrollHeight;
                } else {
                    alert(data.message || "فشل إرسال الرسالة");
                }
            } catch (err) {
                console.error("خطأ في إرسال الرسالة:", err);
            }
        }

        function startChatPolling() {
            stopChatPolling();
            chatPollInterval = setInterval(loadMessages, 2000);
        }

        function stopChatPolling() {
            if (chatPollInterval) {
                clearInterval(chatPollInterval);
                chatPollInterval = null;
            }
        }

        function escapeHtml(text) {
            if (!text) return '';
            return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
        }

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
            formData.append('username', localStorage.getItem('username'));

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
                    alert("حدث خطأ أثناء الرفع");
                }
                document.getElementById('file-input').value = '';
            };

            xhr.send(formData);
        });

        window.onload = async () => {
            await initUser();
            await loadFeed();
        };
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/verify_user', methods=['POST'])
def verify_user():
    data = request.json or {}
    username = data.get('username', '').strip()
    if not username or not supabase:
        return jsonify({'exists': False})
    
    try:
        res = supabase.table('accounts').select('id').eq('username', username).execute()
        return jsonify({'exists': bool(res.data and len(res.data) > 0)})
    except Exception as e:
        print("Verify User Error:", e)
        return jsonify({'exists': False})

@app.route('/register', methods=['POST'])
def register():
    data = request.json or {}
    username = data.get('username', '').strip()

    if not username or not supabase:
        return jsonify({"success": False, "message": "اسم المستخدم مطلوب"}), 400

    try:
        check_res = supabase.table('accounts').select('id').eq('username', username).execute()
        if check_res.data and len(check_res.data) > 0:
            return jsonify({"success": False, "message": "اسم المستخدم مستخدم بالفعل، اختر اسماً آخر"})

        new_user = supabase.table('accounts').insert({'username': username}).execute()
        return jsonify({"success": True, "username": username, "user_id": new_user.data[0]['id']})
    except Exception as e:
        print("Register Error:", e)
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/upload', methods=['POST'])
def upload():
    if not supabase:
        return jsonify({'message': 'إعدادات Supabase غير متوفرة'}), 500
        
    try:
        if 'file' not in request.files:
            return jsonify({'message': 'لم يتم اختيار ملف'}), 400
        file = request.files['file']
        username = request.form.get('username', '').strip()
        
        if file.filename == '' or not allowed_file(file.filename):
            return jsonify({'message': 'نوع الملف غير مدعوم'}), 400

        user_res = supabase.table('accounts').select('id').eq('username', username).execute()
        if not user_res.data:
            return jsonify({'message': 'المستخدم غير موجود'}), 400
        user_id = user_res.data[0]['id']

        ext = file.filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4()}.{ext}"
        
        file_bytes = file.read()
        supabase.storage.from_(BUCKET_NAME).upload(
            path=unique_filename,
            file=file_bytes,
            file_options={"content-type": file.content_type}
        )
        
        public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(unique_filename)
        
        supabase.table('posts').insert({
            'user_id': user_id,
            'media_url': public_url
        }).execute()
        
        return jsonify({'message': 'تم الرفع بنجاح'})
    except Exception as e:
        print("Upload Error:", e)
        return jsonify({'message': str(e)}), 500

@app.route('/feed')
def get_feed():
    if not supabase:
        return jsonify([])
        
    try:
        posts = supabase.table('posts').select('id, user_id, media_url, created_at, accounts(username)').order('created_at', desc=True).execute().data
        likes = supabase.table('likes').select('post_id, user_id, accounts(username)').execute().data
        comments = supabase.table('comments').select('id, post_id, content, created_at, accounts(username)').order('created_at', desc=False).execute().data

        likes_map = {}
        for l in likes:
            pid = l['post_id']
            uname = l.get('accounts', {}).get('username') if isinstance(l.get('accounts'), dict) else None
            if pid not in likes_map:
                likes_map[pid] = []
            if uname:
                likes_map[pid].append(uname)

        comments_map = {}
        for c in comments:
            pid = c['post_id']
            uname = c.get('accounts', {}).get('username') if isinstance(c.get('accounts'), dict) else 'مستخدم'
            if pid not in comments_map:
                comments_map[pid] = []
            comments_map[pid].append({
                'id': c['id'],
                'username': uname,
                'content': c['content'],
                'created_at': c.get('created_at')
            })

        formatted_posts = []
        for p in posts:
            pid = p['id']
            publisher = p.get('accounts', {}).get('username') if isinstance(p.get('accounts'), dict) else 'مستخدم'
            liked_users = likes_map.get(pid, [])
            post_comments = comments_map.get(pid, [])
            
            formatted_posts.append({
                'id': pid,
                'media_url': p['media_url'],
                'publisher': publisher,
                'likes_count': len(liked_users),
                'liked_users': liked_users,
                'comments': post_comments
            })

        return jsonify(formatted_posts)
    except Exception as e:
        print("Error fetching feed:", e)
        return jsonify([])

@app.route('/like', methods=['POST'])
def like():
    data = request.json or {}
    post_id = data.get('post_id')
    username = data.get('username')

    if not post_id or not username or not supabase:
        return jsonify({"success": False, "message": "بيانات ناقصة"}), 400

    try:
        user_res = supabase.table('accounts').select('id').eq('username', username).execute()
        if not user_res.data:
            return jsonify({"success": False, "message": "المستخدم غير موجود"}), 404
        user_id = user_res.data[0]['id']

        existing_like = supabase.table('likes').select('id').eq('user_id', user_id).eq('post_id', post_id).execute()

        if existing_like.data and len(existing_like.data) > 0:
            supabase.table('likes').delete().eq('user_id', user_id).eq('post_id', post_id).execute()
            liked = False
        else:
            supabase.table('likes').insert({'user_id': user_id, 'post_id': post_id}).execute()
            liked = True

        count_res = supabase.table('likes').select('id', count='exact').eq('post_id', post_id).execute()
        new_count = count_res.count if count_res.count is not None else len(count_res.data)

        return jsonify({"success": True, "count": new_count, "liked": liked})
    except Exception as e:
        print("Like Error:", e)
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/comment', methods=['POST'])
def add_comment():
    data = request.json or {}
    post_id = data.get('post_id')
    username = data.get('username')
    content = data.get('content', '').strip()

    if not post_id or not username or not content or not supabase:
        return jsonify({"success": False, "message": "التعليق لا يمكن أن يكون فارغاً"}), 400

    try:
        user_res = supabase.table('accounts').select('id').eq('username', username).execute()
        if not user_res.data:
            return jsonify({"success": False, "message": "المستخدم غير موجود"}), 404
        user_id = user_res.data[0]['id']

        supabase.table('comments').insert({
            'user_id': user_id,
            'post_id': post_id,
            'content': content
        }).execute()

        comments_res = supabase.table('comments').select('id, content, created_at, accounts(username)').eq('post_id', post_id).order('created_at', desc=False).execute()
        
        formatted_comments = []
        for c in comments_res.data:
            uname = c.get('accounts', {}).get('username') if isinstance(c.get('accounts'), dict) else 'مستخدم'
            formatted_comments.append({
                'id': c['id'],
                'username': uname,
                'content': c['content'],
                'created_at': c.get('created_at')
            })

        return jsonify({"success": True, "comments": formatted_comments, "count": len(formatted_comments)})
    except Exception as e:
        print("Comment Error:", e)
        return jsonify({"success": False, "message": str(e)}), 500

# -------------------------------------------------------------
# مسارات نظام الرسائل الخاصة الجديدة
# -------------------------------------------------------------

@app.route('/search_users', methods=['POST'])
def search_users():
    data = request.json or {}
    query = data.get('query', '').strip()
    current_username = data.get('username', '').strip()

    if not query or not supabase:
        return jsonify([])

    try:
        # البحث في جدول accounts باستثناء الحساب الحالي
        res = supabase.table('accounts').select('id, username')\
            .ilike('username', f'%{query}%')\
            .neq('username', current_username)\
            .limit(10).execute()
        return jsonify(res.data or [])
    except Exception as e:
        print("Search Users Error:", e)
        return jsonify([])

@app.route('/create_or_get_conversation', methods=['POST'])
def create_or_get_conversation():
    data = request.json or {}
    username = data.get('username', '').strip()
    target_username = data.get('target_username', '').strip()

    if not username or not target_username or username == target_username or not supabase:
        return jsonify({'success': False, 'message': 'طلب غير صالح'}), 400

    try:
        u1_res = supabase.table('accounts').select('id').eq('username', username).execute()
        u2_res = supabase.table('accounts').select('id').eq('username', target_username).execute()

        if not u1_res.data or not u2_res.data:
            return jsonify({'success': False, 'message': 'المستخدم غير موجود'}), 404

        u1_id = u1_res.data[0]['id']
        u2_id = u2_res.data[0]['id']

        # البحث عن محادثة سابقة بالاتجاهين
        conv1 = supabase.table('conversations').select('id')\
            .eq('user1_id', u1_id).eq('user2_id', u2_id).execute()
        
        if conv1.data and len(conv1.data) > 0:
            return jsonify({'success': True, 'conversation_id': conv1.data[0]['id']})

        conv2 = supabase.table('conversations').select('id')\
            .eq('user1_id', u2_id).eq('user2_id', u1_id).execute()

        if conv2.data and len(conv2.data) > 0:
            return jsonify({'success': True, 'conversation_id': conv2.data[0]['id']})

        # إنشاء محادثة جديدة إذا لم تكن موجودة
        new_conv = supabase.table('conversations').insert({
            'user1_id': u1_id,
            'user2_id': u2_id
        }).execute()

        return jsonify({'success': True, 'conversation_id': new_conv.data[0]['id']})
    except Exception as e:
        print("Conversation Error:", e)
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/get_messages', methods=['POST'])
def get_messages():
    data = request.json or {}
    conversation_id = data.get('conversation_id')

    if not conversation_id or not supabase:
        return jsonify([])

    try:
        res = supabase.table('messages')\
            .select('id, conversation_id, sender_id, content, created_at, accounts(username)')\
            .eq('conversation_id', conversation_id)\
            .order('created_at', desc=False).execute()

        messages = []
        for m in res.data or []:
            uname = m.get('accounts', {}).get('username') if isinstance(m.get('accounts'), dict) else 'مستخدم'
            messages.append({
                'id': m['id'],
                'sender_id': m['sender_id'],
                'sender_username': uname,
                'content': m['content'],
                'created_at': m.get('created_at')
            })

        return jsonify(messages)
    except Exception as e:
        print("Get Messages Error:", e)
        return jsonify([])

@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.json or {}
    conversation_id = data.get('conversation_id')
    username = data.get('username')
    content = data.get('content', '').strip()

    if not conversation_id or not username or not content or not supabase:
        return jsonify({'success': False, 'message': 'بيانات ناقصة'}), 400

    try:
        user_res = supabase.table('accounts').select('id').eq('username', username).execute()
        if not user_res.data:
            return jsonify({'success': False, 'message': 'المستخدم غير موجود'}), 404
        sender_id = user_res.data[0]['id']

        supabase.table('messages').insert({
            'conversation_id': conversation_id,
            'sender_id': sender_id,
            'content': content
        }).execute()

        return jsonify({'success': True})
    except Exception as e:
        print("Send Message Error:", e)
        return jsonify({'success': False, 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)

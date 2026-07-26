from flask import Flask, render_template_string, request, jsonify
import os
from google import genai

app = Flask(__name__)

# 5. التحقق من وجود مفتاح GEMINI_API_KEY عند بدء التطبيق وطباعة الحالة في السجل
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key or api_key.strip() == "":
    print("========== GEMINI WARNING ==========")
    print("تحذير: متغير البيئة GEMINI_API_KEY غير موجود أو فارغ!")
    print("====================================")
    client = None
else:
    print("========== GEMINI INFO ==========")
    print("تم العثور على مفتاح GEMINI_API_KEY بنجاح.")
    print("=================================")
    # تهيئة عميل الذكاء الاصطناعي
    client = genai.Client(api_key=api_key)

# واجهة المستخدم (التصميم الأصلي كما هو تماماً دون تغيير)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>محادثة الذكاء الاصطناعي</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 h-screen flex flex-col justify-between">
    <header class="bg-blue-600 text-white p-4 text-center font-bold text-lg">
        موقع المحادثة البسيط
    </header>

    <div id="chat-box" class="flex-1 overflow-y-auto p-4 space-y-3 max-w-2xl mx-auto w-full">
        <div class="text-center text-gray-400 text-sm">أهلاً بك! اكتب رسالتك للبدء...</div>
    </div>

    <div class="bg-white p-4 shadow-md max-w-2xl mx-auto w-full flex gap-2">
        <input type="text" id="user-input" placeholder="اكتب رسالتك هنا..." 
               class="flex-1 border rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
               onkeydown="if(event.key === 'Enter') sendMessage()">
        <button onclick="sendMessage()" class="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700">إرسال</button>
    </div>

    <script>
        async function sendMessage() {
            const input = document.getElementById('user-input');
            const chatBox = document.getElementById('chat-box');
            const message = input.value.trim();
            if (!message) return;

            // إضافة رسالة المستخدم
            chatBox.innerHTML += `<div class="text-left"><span class="inline-block bg-blue-100 text-blue-900 p-3 rounded-lg max-w-lg">${message}</span></div>`;
            input.value = '';
            chatBox.scrollTop = chatBox.scrollHeight;

            try {
                // إرسال الطلب للخلفية
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: message })
                });

                const data = await response.json();
                
                // إضافة رد الذكاء الاصطناعي أو عرض سبب الخطأ الحقيقي القادم من الخادم
                if (data.reply) {
                    chatBox.innerHTML += `<div class="text-right"><span class="inline-block bg-white text-gray-800 p-3 rounded-lg shadow max-w-lg">${data.reply}</span></div>`;
                } else if (data.error) {
                    chatBox.innerHTML += `<div class="text-right"><span class="inline-block bg-red-100 text-red-800 p-3 rounded-lg shadow max-w-lg">${data.error}</span></div>`;
                } else {
                    chatBox.innerHTML += `<div class="text-right"><span class="inline-block bg-red-100 text-red-800 p-3 rounded-lg">حدث خطأ غير معروف.</span></div>`;
                }
            } catch (err) {
                chatBox.innerHTML += `<div class="text-right"><span class="inline-block bg-red-100 text-red-800 p-3 rounded-lg">تعذر الاتصال بالخادم.</span></div>`;
            }
            chatBox.scrollTop = chatBox.scrollHeight;
        }
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/chat", methods=["POST"])
def chat():
    user_message = request.json.get("message")
    if not user_message:
        return jsonify({"error": "الرسالة فارغة"}), 400

    if not client:
        error_msg = "مفتاح GEMINI_API_KEY غير مهيأ على الخادم."
        print("========== GEMINI ERROR ==========")
        print(error_msg)
        print("==================================")
        return jsonify({"error": error_msg}), 500

    try:
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=user_message,
        )
        return jsonify({"reply": response.text})
    except Exception as e:
        # 2. تسجيل الخطأ كاملاً في سجل Render بالإضافة إلى إرجاعه بصيغة JSON
        print("========== GEMINI ERROR ==========")
        print(repr(e))
        print("==================================")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)

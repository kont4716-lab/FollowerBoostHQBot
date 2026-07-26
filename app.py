import os
from flask import Flask, jsonify
from google import genai

app = Flask(__name__)

# ============================================
# إعداد المفاتيح حسب Environment Variables في Render
# GEMINI_API_KEY | SUPABASE_KEY | SUPABASE_URL
# ============================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")

ai_client = None

if GEMINI_API_KEY:
    try:
        ai_client = genai.Client(api_key=GEMINI_API_KEY)
        print("✅ ai_client تم إنشاؤه بنجاح باستخدام GEMINI_API_KEY")
    except Exception as e:
        print(f"❌ خطأ في إنشاء ai_client: {e}")
        ai_client = None
else:
    print("⚠️ لم يتم العثور على GEMINI_API_KEY")


# ============================================
# Route تشخيصي مؤقت - /test-models
# يعرض جميع نماذج Gemini المتاحة
# ============================================
@app.route('/test-models')
def test_models():
    if not ai_client:
        return jsonify({"error": "No API Key"}), 400

    try:
        models = []
        for m in ai_client.models.list():
            models.append(m.name)

        return jsonify({
            "status": "success",
            "total_models": len(models),
            "models": models
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# ============================================
# صفحة رئيسية بسيطة
# ============================================
@app.route('/')
def home():
    return '''
    <html dir="rtl">
    <head>
        <title>تشخيص نماذج Gemini</title>
        <style>
            body { font-family: Arial, sans-serif; padding: 40px; background: #f5f5f5; }
            .box { background: white; padding: 30px; border-radius: 10px; max-width: 600px; margin: auto; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            a { display: inline-block; margin-top: 20px; padding: 12px 24px; background: #4285f4; color: white; text-decoration: none; border-radius: 6px; }
            a:hover { background: #3367d6; }
        </style>
    </head>
    <body>
        <div class="box">
            <h2>تشخيص نماذج Google Gemini</h2>
            <p>اضغط على الزر أدناه لعرض جميع النماذج المتاحة لمفتاح API الحالي.</p>
            <a href="/test-models">عرض النماذج المتاحة</a>
        </div>
    </body>
    </html>
    '''


if __name__ == '__main__':
    port = int(os.getenv("PORT", 5001))
    app.run(debug=False, host='0.0.0.0', port=port)

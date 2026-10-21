# DZ Connect

منصة تواصل جزائرية لعروض الإنترنت والهدايا اليومية وتجارب المستخدمين.

## الملفات

| الملف | الوصف |
|-------|--------|
| `app.py` | التطبيق الكامل (خادم + واجهة) في ملف واحد |
| `requirements.txt` | المكتبات المطلوبة |
| `supabase_schema.sql` | جداول وسياسات قاعدة البيانات |

## إعداد Supabase

1. أنشئ مشروعًا جديدًا على [supabase.com](https://supabase.com).
2. اذهب إلى **SQL Editor** → New query.
3. انسخ محتوى `supabase_schema.sql` كاملًا والصقه ثم اضغط **Run**.
4. اذهب إلى **Storage** → New bucket:
   - الاسم: `media`
   - Public bucket: **نعم** (للحصول على روابط عامة للصور والتسجيلات).
5. (اختياري) بعد أول تسجيل، امنح نفسك صلاحية أدمن:
   ```sql
   UPDATE users SET is_admin = TRUE WHERE phone = '05XXXXXXXX';
   ```

## متغيرات البيئة (Render أو محلي)

| المتغير | مطلوب؟ | الوصف |
|---------|--------|--------|
| `SUPABASE_URL` | نعم | رابط مشروع Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | نعم | مفتاح Service Role (من Settings → API) — **لا تضعه في الواجهة** |
| `SUPABASE_ANON_KEY` | لا | اختياري (للتوسع لاحقًا) |
| `SECRET_KEY` | مُفضّل | مفتاح توقيع الجلسات (سلسلة عشوائية طويلة) |
| `APP_ENV` | لا | `production` أو `development` (افتراضي) |
| `PORT` | تلقائي على Render | المنفذ (افتراضي 8000) |

> **تحذير أمني:** رقم الهاتف وحده لا يثبت ملكية الحساب. هذا نموذج أولي محدود الأمان. أضف OTP قبل الإطلاق العام.

## التشغيل المحلي

```bash
python -m venv venv
source venv/bin/activate   # أو venv\Scripts\activate على Windows
pip install -r requirements.txt

export SUPABASE_URL="https://xxxx.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="eyJ..."
export SECRET_KEY="غيّر-هذا-إلى-سلسلة-عشوائية-طويلة"
export APP_ENV="development"

uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

افتح: http://localhost:8000

## النشر على Render

1. ارفع الملفات إلى مستودع GitHub.
2. أنشئ Web Service جديد على Render واربط المستودع.
3. الإعدادات:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app:app --host 0.0.0.0 --port $PORT`
   - **Environment:** أضف المتغيرات المذكورة أعلاه.
4. بعد النشر، تحقق من `/health`.

## الميزات المنفذة

- تسجيل ودخول برقم هاتف جزائري (تطبيع 05/06/07)
- جلسات Cookie (HttpOnly + Secure في الإنتاج)
- منشورات: نص / صورة / صوت + تصنيفات + حالة البوتات
- إعجابات، تعليقات، حفظ، مشاركة رابط، إبلاغ
- دردشة عامة (تحديث دوري كل 8 ثوانٍ)
- ملف شخصي + تعديل الاسم
- لوحة إدارة (إحصاءات + مراجعة بلاغات + تقييد مستخدمين)
- واجهة عربية RTL متجاوبة مع شريط تنقل سفلي
- رفع وسائط إلى Supabase Storage
- رسائل خطأ واضحة عند غياب الإعدادات أو الجداول

## ما يحتاج إعدادًا يدويًا

1. تنفيذ `supabase_schema.sql`
2. إنشاء bucket اسمه `media`
3. تعيين متغيرات البيئة
4. منح `is_admin = true` لحسابك
5. (مستقبلاً) إضافة تحقق OTP حقيقي

## خطة اختبار سريعة

1. `/health` → يجب أن يعيد `db_ready: true` بعد إعداد SQL
2. التسجيل برقم جديد
3. منع تكرار نفس الرقم
4. إنشاء منشور نصي ثم بصورة
5. إعجاب / تعليق / حفظ / بلاغ
6. إرسال رسالة في الدردشة
7. تسجيل الخروج ثم الدخول مجددًا
8. كأدمن: مراجعة بلاغ وتغيير حالته

## ملاحظات

- الدردشة ليست WebSocket حقيقيًا؛ تعتمد على polling كل 8 ثوانٍ (مناسب للنسخة الأولية).
- لا تُعرض أرقام الهواتف في الواجهة أو المنشورات أو الدردشة.
- لا تضع `SERVICE_ROLE_KEY` في أي كود واجهة أمامية.
'''
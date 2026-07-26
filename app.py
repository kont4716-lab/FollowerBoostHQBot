# ==========================================
# التعديل الخاص بنظام الذكاء الاصطناعي (Gemini)
# ==========================================

# جلب النماذج المدعومة ديناميكياً والتأكد من توافق الأسماء (مع دعم التبديل التلقائي وتسجيل الأخطاء)
GEMINI_MODELS = []
if ai_client:
    try:
        # استعراض النماذج المتاحة من العميل مباشرة حسب أحدث إصدار لمكتبة google-genai
        for m in ai_client.models.list():
            # نقوم بالبحث عن النماذج التي تدعم توليد المحتوى (generateContent)
            supported_actions = getattr(m, 'supported_generation_methods', [])
            model_name = getattr(m, 'name', '')
            if model_name and ('generateContent' in supported_actions or not supported_actions):
                # تنظيف اسم النموذج من بادئة "models/" إذا وجدت لتجنب أخطاء التوافق، أو الاحتفاظ بالاسم النقي
                clean_name = model_name.replace('models/', '')
                if clean_name not in GEMINI_MODELS:
                    GEMINI_MODELS.append(clean_name)
    except Exception as e:
        logger.warning(f"Could not list models dynamically: {e}")

# إذا لم يتم جلب أي نموذج تلقائياً، نضع قائمة احتياطية افتراضية مستقرة
if not GEMINI_MODELS:
    GEMINI_MODELS = ['gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-1.5-pro']


@app.route('/ai', methods=['POST'])
@login_required
def ask_ai():
    if not ai_client:
        return jsonify({
            'reply': 'عذراً، مفتاح Gemini API غير متوفر في متغيرات البيئة (GEMINI_API_KEY).'
        }), 500

    data = request.get_json(silent=True) or {}
    message = data.get('message', '').strip()

    if not message:
        return jsonify({'reply': 'الرجاء إدخال سؤال أو رسالة صحيحة.'}), 400

    response = None
    last_error_message = ""
    successful_model = ""

    # تجربة النماذج المتاحة تباعاً مع معالجة البادئة تلقائياً
    for base_model_name in GEMINI_MODELS:
        # اختبار الاحتمالين (مع بادئة models/ أو بدونها) لضمان التوافق التام مع أحدث إصدار
        models_to_try = [base_model_name, f"models/{base_model_name}"] if not base_model_name.startswith("models/") else [base_model_name, base_model_name.replace("models/", "")]
        
        for model_to_test in models_to_try:
            try:
                logger.info(f"جرب استخدام النموذج: {model_to_test}")
                response = ai_client.models.generate_content(
                    model=model_to_test,
                    contents=message,
                )
                if response and response.text:
                    successful_model = model_to_test
                    logger.info(f"نجح النموذج في توليد الرد: {successful_model}")
                    break
            except genai_errors.APIError as e:
                last_error_message = str(e)
                logger.error(f"خطأ API حقيقي من Gemini للنموذج {model_to_test}: {last_error_message}")
                continue
            except Exception as e:
                last_error_message = str(e)
                logger.error(f"خطأ غير متوقع للنموذج {model_to_test}: {last_error_message}")
                continue
        
        if response and response.text:
            break

    if response and response.text:
        return jsonify({'reply': response.text})
    
    # في حال فشل جميع النماذج، يتم إرجاع رسالة واضحة تحتوي على تفاصيل الخطأ الحقيقي دون تعطل التطبيق
    return jsonify({
        'reply': f'عذراً، تعذر الحصول على رد من نماذج الذكاء الاصطناعي. تفاصيل الخطأ: {last_error_message or "النماذج غير متاحة حالياً"}'
    }), 500

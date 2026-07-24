import os
from flask import Flask, request, jsonify
from supabase import create_client, Client

app = Flask(__name__)

# ==========================================
# 1. إعداد الاتصال بـ Supabase
# ==========================================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "ضع_رابط_سوبابيز_هنا")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "ضع_مفتاح_سوبابيز_هنا")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print("Error initializing Supabase client:", e)


# ==========================================
# 2. مسار البحث عن المستخدمين (/search_users)
# ==========================================
@app.route('/search_users', methods=['POST'])
def search_users():
    data = request.json or {}
    query = str(data.get('query', '')).strip()
    current_username = str(data.get('username', '')).strip()

    if not query or not supabase:
        return jsonify([])

    try:
        # البحث في جدول الحسابات بالاسم مع استثناء المستخدم الحالي
        res = supabase.table('accounts')\
            .select('id, username')\
            .ilike('username', f'%{query}%')\
            .neq('username', current_username)\
            .limit(10)\
            .execute()
            
        return jsonify(res.data or [])
    except Exception as e:
        print("Search Users Error:", e)
        return jsonify([])


# ==========================================
# 3. مسار إنشاء أو جلب محادثة (/create_or_get_conversation)
# ==========================================
@app.route('/create_or_get_conversation', methods=['POST'])
def create_or_get_conversation():
    data = request.json or {}
    username = str(data.get('username', '')).strip()
    target_username = str(data.get('target_username', '')).strip()

    if not username or not target_username or username == target_username:
        return jsonify({'success': False, 'message': 'بيانات المستخدمين غير صالحة'}), 400

    if not supabase:
        return jsonify({'success': False, 'message': 'تعذر الاتصال بقاعدة البيانات'}), 500

    try:
        # 1. جلب ID المستخدمين
        u1_res = supabase.table('accounts').select('id').eq('username', username).execute()
        u2_res = supabase.table('accounts').select('id').eq('username', target_username).execute()

        if not u1_res.data or not u2_res.data:
            return jsonify({'success': False, 'message': 'أحد المستخدمين غير موجود'}), 404

        u1_id = u1_res.data[0]['id']
        u2_id = u2_res.data[0]['id']

        # 2. البحث عن محادثة قائمة بين الطرفين بالاتجاهين
        or_clause = f"and(user1_id.eq.{u1_id},user2_id.eq.{u2_id}),and(user1_id.eq.{u2_id},user2_id.eq.{u1_id})"
        conv_res = supabase.table('conversations').select('id').or_(or_clause).execute()

        if conv_res.data and len(conv_res.data) > 0:
            return jsonify({'success': True, 'conversation_id': conv_res.data[0]['id']})

        # 3. إنشاء محادثة جديدة في حال عدم وجودها
        new_conv = supabase.table('conversations').insert({
            'user1_id': u1_id,
            'user2_id': u2_id
        }).execute()

        if new_conv.data and len(new_conv.data) > 0:
            return jsonify({'success': True, 'conversation_id': new_conv.data[0]['id']})
        else:
            return jsonify({'success': False, 'message': 'فشل إنشاء المحادثة'}), 500

    except Exception as e:
        print("Create Conversation Error:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


# ==========================================
# 4. مسار جلب قائمة المحادثات (/get_conversations)
# ==========================================
@app.route('/get_conversations', methods=['POST'])
def get_conversations():
    data = request.json or {}
    username = str(data.get('username', '')).strip()

    if not username or not supabase:
        return jsonify([])

    try:
        # جلب ID المستخدم
        user_res = supabase.table('accounts').select('id').eq('username', username).execute()
        if not user_res.data:
            return jsonify([])
        user_id = user_res.data[0]['id']

        # جلب جميع المحادثات التي ينتمي لها المستخدم
        or_clause = f"user1_id.eq.{user_id},user2_id.eq.{user_id}"
        conv_res = supabase.table('conversations')\
            .select('id, user1_id, user2_id, created_at')\
            .or_(or_clause)\
            .order('created_at', desc=True)\
            .execute()

        conversations = []
        for conv in conv_res.data or []:
            conv_id = conv['id']
            target_id = conv['user2_id'] if conv['user1_id'] == user_id else conv['user1_id']

            # جلب اسم الطرف الآخر
            target_res = supabase.table('accounts').select('username').eq('id', target_id).execute()
            target_username = target_res.data[0]['username'] if target_res.data else 'مستخدم'

            # جلب آخر رسالة في المحادثة
            last_msg_res = supabase.table('messages')\
                .select('message, created_at')\
                .eq('conversation_id', conv_id)\
                .order('created_at', desc=True)\
                .limit(1)\
                .execute()

            if last_msg_res.data and len(last_msg_res.data) > 0:
                last_message = last_msg_res.data[0]['message']
                updated_at = last_msg_res.data[0]['created_at']
            else:
                last_message = 'لا توجد رسائل بعد'
                updated_at = conv['created_at']

            conversations.append({
                'conversation_id': conv_id,
                'target_username': target_username,
                'last_message': last_message,
                'updated_at': updated_at
            })

        return jsonify(conversations)

    except Exception as e:
        print("Get Conversations List Error:", e)
        return jsonify([])


# ==========================================
# 5. مسار جلب الرسائل (/get_messages)
# ==========================================
@app.route('/get_messages', methods=['POST'])
def get_messages():
    data = request.json or {}
    conversation_id = data.get('conversation_id')

    if not conversation_id or not supabase:
        return jsonify([])

    try:
        # جلب الرسائل مع اسم المستخدم عن طريق العلاقة المباشرة بين sender_id و accounts.id
        res = supabase.table('messages')\
            .select('id, conversation_id, sender_id, message, created_at, accounts!sender_id(username)')\
            .eq('conversation_id', conversation_id)\
            .order('created_at', desc=False)\
            .execute()

        messages = []
        for m in res.data or []:
            acc = m.get('accounts')
            uname = 'مستخدم'
            if isinstance(acc, dict) and 'username' in acc:
                uname = acc['username']
            elif isinstance(acc, list) and len(acc) > 0 and 'username' in acc[0]:
                uname = acc[0]['username']

            messages.append({
                'id': m['id'],
                'sender_id': m['sender_id'],
                'sender_username': uname,
                'message': m.get('message', ''),
                'content': m.get('message', ''),  # متوافق مع الواجهات التي تبحث عن المفتاح content
                'created_at': m.get('created_at')
            })

        return jsonify(messages)

    except Exception as e:
        print("Primary Get Messages Error:", e)
        # مسار إضافي حمايتي في حال حدوث أي خطأ في ربط الجداول
        try:
            res = supabase.table('messages')\
                .select('id, conversation_id, sender_id, message, created_at')\
                .eq('conversation_id', conversation_id)\
                .order('created_at', desc=False)\
                .execute()
            
            messages = []
            for m in res.data or []:
                messages.append({
                    'id': m['id'],
                    'sender_id': m['sender_id'],
                    'sender_username': 'مستخدم',
                    'message': m.get('message', ''),
                    'content': m.get('message', ''),
                    'created_at': m.get('created_at')
                })
            return jsonify(messages)
        except Exception as inner_e:
            print("Fallback Get Messages Error:", inner_e)
            return jsonify([])


# ==========================================
# 6. مسار إرسال الرسائل (/send_message)
# ==========================================
@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.json or {}
    conversation_id = data.get('conversation_id')
    username = str(data.get('username', '')).strip()
    
    # قراءة النص وتفريغه من المساحات الفارغة مع دعم المفتاحين (message و content)
    raw_msg = data.get('message') if data.get('message') is not None else data.get('content')
    message_text = str(raw_msg or '').strip()

    # التحقق من أن الرسالة والبيانات الأساسية موجودة وليست فارغة
    if not conversation_id or not username or not message_text:
        return jsonify({
            'success': False, 
            'message': 'جميع البيانات مطلوبة، ولا يمكن إرسال رسالة فارغة'
        }), 400

    if not supabase:
        return jsonify({'success': False, 'message': 'خطأ في الاتصال بقاعدة البيانات'}), 500

    try:
        # جلب ID المستخدم المرسل
        user_res = supabase.table('accounts').select('id').eq('username', username).execute()
        if not user_res.data:
            return jsonify({'success': False, 'message': 'المستخدم غير موجود'}), 404
        
        sender_id = user_res.data[0]['id']

        # إدخال الرسالة في Supabase داخل العمود message
        insert_res = supabase.table('messages').insert({
            'conversation_id': conversation_id,
            'sender_id': sender_id,
            'message': message_text
        }).execute()

        if insert_res.data and len(insert_res.data) > 0:
            return jsonify({
                'success': True, 
                'message': 'تم إرسال الرسالة بنجاح',
                'data': insert_res.data[0]
            })
        else:
            return jsonify({'success': False, 'message': 'فشل إدخال الرسالة'}), 500

    except Exception as e:
        print("Send Message Error:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

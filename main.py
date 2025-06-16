import telebot
from telebot import types
import subprocess
import os
import re
import zipfile
import uuid
import datetime
import time
import json
import shutil
import sys
import tempfile
from collections import defaultdict

TOKEN = '7987463096:AAHvEk0BHRW2ZWcnwAp2ui0CKY7ww9-Q33k'
bot = telebot.TeleBot(TOKEN)
admin_id = 7384683084  # ضع هنا آيدي المطور

# تخزين العمليات والملفات
user_files = {}  # {chat_id: {file_key: {'process': Popen, 'file_path': str, 'file_name': str}}}
banned_users = set()
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

# تخزين بيانات الأدمن
admin_users = {admin_id}  # مجموعة من آيدي الأدمن
user_activity = []  # سجل النشاطات
all_users = set()  # جميع المستخدمين الذين بدأوا البوت
user_stats = {  # إحصائيات البوت
    'total_users': 0,
    'total_files': 0,
    'running_bots': 0,
    'command_usage': defaultdict(int)
}
bot_locked = False  # حالة قفل البوت
live_monitoring = False  # حالة المراقبة المباشرة

# تخزين بيانات المستخدمين في ملف
DATA_FILE = "bot_data.json"

def save_data():
    """حفظ بيانات البوت في ملف"""
    data = {
        'banned_users': list(banned_users),
        'admin_users': list(admin_users),
        'all_users': list(all_users),
        'user_stats': user_stats,
        'bot_locked': bot_locked,
        'live_monitoring': live_monitoring
    }
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f)

def load_data():
    """تحميل بيانات البوت من ملف"""
    global banned_users, admin_users, all_users, user_stats, bot_locked, live_monitoring
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                banned_users = set(data.get('banned_users', []))
                admin_users = set(data.get('admin_users', [admin_id]))
                all_users = set(data.get('all_users', []))
                user_stats = data.get('user_stats', user_stats)
                bot_locked = data.get('bot_locked', False)
                live_monitoring = data.get('live_monitoring', False)
    except Exception as e:
        print(f"حدث خطأ أثناء تحميل البيانات: {e}")

def log_activity(user_id, action, details=""):
    """تسجيل نشاط في سجل النشاطات"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    activity = {
        'timestamp': timestamp,
        'user_id': user_id,
        'action': action,
        'details': details
    }
    user_activity.append(activity)
    # حفظ النشاط الأخير فقط (500 نشاط)
    if len(user_activity) > 500:
        user_activity.pop(0)

def get_welcome_message(user_name):
    now = datetime.datetime.now()
    current_time = now.strftime("%H:%M")
    return f"""
مرحباً، {user_name} | الوقت: {current_time}⏐! 👋
أهلاً بك في بوت رفع واستضافة بوتات بايثون!

🎯 مهمة البوت:
- رفع وتشغيل بوتاتك البرمجية.

🚀 كيفية الاستخدام:
1. استخدم الأزرار للتنقل.
2. ارفع ملفك مع الالتزام بالشروط
"""

def install_requirements(path):
    """تثبيت المتطلبات من ملف أو من الشفرة المصدرية"""
    try:
        # المحاولة الأولى: البحث عن ملف requirements.txt في نفس المجلد
        dir_path = os.path.dirname(path)
        requirements_path = os.path.join(dir_path, "requirements.txt")
        
        if os.path.exists(requirements_path):
            print(f"تم العثور على ملف المتطلبات: {requirements_path}")
            subprocess.call(['pip', 'install', '-r', requirements_path])
            return
        
        # المحاولة الثانية: تحليل الشفرة المصدرية لاكتشاف المتطلبات
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
            # البحث عن جميع أنواع الاستيرادات
            import_patterns = [
                r'import\s+(\w+)',                          # import module
                r'from\s+(\w+)\s+import',                    # from module import
                r'import\s+(\w+)\s+as',                      # import module as
                r'from\s+([\w.]+)\s+import\s+(\w+)',         # from module.sub import something
                r'install_requires\s*=\s*\[([^\]]+)\]',      # setup.py install_requires
            ]
            
            libraries = set()
            
            for pattern in import_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        # معالجة الحالات التي تحتوي على عدة مجموعات
                        for lib in match:
                            if lib:
                                # إزالة علامات الاقتباس والمسافات
                                clean_lib = lib.strip('"\'').split('.')[0].strip()
                                if clean_lib and len(clean_lib) > 1:
                                    libraries.add(clean_lib)
                    else:
                        clean_lib = match.strip('"\'').split('.')[0].strip()
                        if clean_lib and len(clean_lib) > 1:
                            libraries.add(clean_lib)
            
            # استبعاد المكاتب القياسية
            std_libs = sys.stdlib_module_names
            libraries = [lib for lib in libraries if lib not in std_libs]
            
            print(f"المكتبات المكتشفة: {libraries}")
            
            # تثبيت المكاتب المكتشفة
            for lib in libraries:
                try:
                    subprocess.call(['pip', 'install', lib])
                except Exception as e:
                    print(f"فشل تثبيت {lib}: {e}")
    
    except Exception as e:
        print(f"فشل التثبيت التلقائي: {e}")

def create_virtual_environment(env_path):
    """إنشاء بيئة افتراضية جديدة"""
    try:
        os.makedirs(env_path, exist_ok=True)
        subprocess.call([sys.executable, '-m', 'venv', env_path])
        return True
    except Exception as e:
        print(f"فشل إنشاء البيئة الافتراضية: {e}")
        return False

def get_virtualenv_python(env_path):
    """الحصول على مسار بايثون في البيئة الافتراضية"""
    if sys.platform == 'win32':
        return os.path.join(env_path, 'Scripts', 'python.exe')
    else:
        return os.path.join(env_path, 'bin', 'python')

@bot.message_handler(commands=['start'])
def start(message):
    if bot_locked:
        return bot.reply_to(message, "⛔ البوت تحت الصيانة حالياً. يرجى المحاولة لاحقاً.")
    
    if message.from_user.id in banned_users:
        return bot.reply_to(message, "❌ تم حظرك من استخدام البوت.")
    
    # إضافة المستخدم إلى الإحصائيات
    all_users.add(message.chat.id)
    user_stats['total_users'] = len(all_users)
    user_stats['command_usage']['/start'] += 1
    log_activity(message.chat.id, "بدء البوت")
    
    # الحصول على اسم المستخدم
    user_name = message.from_user.first_name or "عزيزي المستخدم"
    if message.from_user.last_name:
        user_name += " " + message.from_user.last_name
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton("رفع .py 📤", callback_data='upload_py'),
        types.InlineKeyboardButton("رفع .zip 📤", callback_data='upload_zip'),
        types.InlineKeyboardButton("ملفاتي 📂", callback_data='my_files'),
    ]
    markup.add(*buttons)
    
    # أزرار المساعدة والمطور في نفس السطر
    help_dev_buttons = [
        types.InlineKeyboardButton("المساعدة ❓", callback_data='help'),
        types.InlineKeyboardButton("المطور 👨‍💻", url="https://t.me/SSUU_R")
    ]
    markup.add(*help_dev_buttons)
    
    welcome = get_welcome_message(user_name)
    bot.send_message(message.chat.id, welcome, reply_markup=markup)
    save_data()

# ===== زر المساعدة الجديد =====
@bot.callback_query_handler(func=lambda call: call.data == 'help')
def show_help(call):
    help_text = """
📚 *دليل استخدام البوت*

🚀 كيفية رفع ملفاتك:
1. تأكد من أن ملف البوت الخاص بك يحتوي على جميع الملفات الضرورية
2. إذا كان بوتك يحتاج إلى مكتبات خارجية:
   - قم بإنشاء ملف `requirements.txt`
   - ضع فيه أسماء المكتبات المطلوبة (سطر لكل مكتبة)
3. قم بضغط ملف البوت (الملف .py) مع ملف `requirements.txt` في ملف zip واحد
4. قم برفع الملف المضغوط (zip) إلى البوت

💡 ملاحظات هامة:
- يمكنك رفع ملف .py مباشرة إذا لم يكن بحاجة إلى مكتبات خارجية
- عند الرفع كملف zip:
  • سيتم البحث عن ملف رئيسي (main.py, bot.py, ...)
  • سيتم تثبيت المكتبات من ملف requirements.txt تلقائيًا
- الحد الأقصى لحجم الملف: 100MB

📦 مثال لملف requirements.txt:
telebot
requests
python-dotenv
    """
    bot.send_message(call.message.chat.id, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    user_id = message.from_user.id
    if user_id not in admin_users:
        bot.reply_to(message, "⛔ ليس لديك صلاحية الوصول إلى لوحة الأدمن.")
        return
    
    log_activity(user_id, "فتح لوحة الأدمن")
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton("📢 إرسال إذاعة", callback_data='admin_broadcast'),
        types.InlineKeyboardButton("👥 عدد المستخدمين", callback_data='admin_user_count'),
        types.InlineKeyboardButton("🚫 حظر مستخدم", callback_data='admin_ban_user'),
        types.InlineKeyboardButton("✅ إلغاء الحظر", callback_data='admin_unban_user'),
        types.InlineKeyboardButton("🗂️ قائمة المحظورين", callback_data='admin_banned_list'),
        types.InlineKeyboardButton("🧪 اختبار بوت مستخدم", callback_data='admin_test_user_bot'),
        types.InlineKeyboardButton("🔁 إعادة تشغيل بوت مستخدم", callback_data='admin_restart_user_bot'),
        types.InlineKeyboardButton("❌ إيقاف بوت مستخدم", callback_data='admin_stop_user_bot'),
        types.InlineKeyboardButton("🔄 إعادة تشغيل كل البوتات", callback_data='admin_restart_all'),
        types.InlineKeyboardButton("📦 عرض ملفات مستخدم", callback_data='admin_view_user_files'),
        types.InlineKeyboardButton("🗑️ حذف ملف مستخدم", callback_data='admin_delete_user_file'),
        types.InlineKeyboardButton("✉️ التواصل مع مستخدم", callback_data='admin_contact_user'),
        types.InlineKeyboardButton("📝 سجل النشاط", callback_data='admin_activity_log'),
        types.InlineKeyboardButton("⚙️ إعدادات البوت", callback_data='admin_settings'),
        types.InlineKeyboardButton("🔍 بحث عن مستخدم", callback_data='admin_search_user'),
        types.InlineKeyboardButton("📊 إحصائيات عامة", callback_data='admin_stats'),
        types.InlineKeyboardButton("🔒 قفل البوت", callback_data='admin_lock_bot'),
        types.InlineKeyboardButton("👁️‍🗨️ مراقبة مباشرة", callback_data='admin_monitor')
    ]
    
    # إضافة الأزرار في مجموعات
    for i in range(0, len(buttons), 2):
        row = buttons[i:i+2]
        markup.add(*row)
    
    bot.send_message(message.chat.id, "👮‍♂️ *لوحة تحكم الأدمن*", parse_mode="Markdown", reply_markup=markup)

# ===== معالجات لوحة الأدمن =====
@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def handle_admin_callback(call):
    user_id = call.from_user.id
    if user_id not in admin_users:
        bot.answer_callback_query(call.id, "⛔ ليس لديك صلاحية!")
        return
    
    data = call.data
    chat_id = call.message.chat.id
    
    if data == 'admin_broadcast':
        msg = bot.send_message(chat_id, "📤 أرسل الرسالة التي تريد إذاعتها (نص, صورة, ملف):")
        bot.register_next_step_handler(msg, process_broadcast)
    
    elif data == 'admin_user_count':
        count = len(all_users)
        bot.answer_callback_query(call.id, f"👥 عدد المستخدمين: {count}")
    
    elif data == 'admin_ban_user':
        msg = bot.send_message(chat_id, "أرسل آيدي المستخدم الذي تريد حظره:")
        bot.register_next_step_handler(msg, process_ban_user)
    
    elif data == 'admin_unban_user':
        msg = bot.send_message(chat_id, "أرسل آيدي المستخدم الذي تريد إلغاء حظره:")
        bot.register_next_step_handler(msg, process_unban_user)
    
    elif data == 'admin_banned_list':
        if not banned_users:
            bot.answer_callback_query(call.id, "📭 لا يوجد مستخدمين محظورين")
        else:
            banned_list = "\n".join([f"- {uid}" for uid in banned_users])
            bot.send_message(chat_id, f"🚫 قائمة المحظورين:\n{banned_list}")
    
    elif data == 'admin_test_user_bot':
        msg = bot.send_message(chat_id, "أرسل آيدي المستخدم الذي تريد اختبار بوتاته:")
        bot.register_next_step_handler(msg, process_test_user_bot)
    
    elif data == 'admin_restart_user_bot':
        msg = bot.send_message(chat_id, "أرسل آيدي المستخدم الذي تريد إعادة تشغيل بوتاته:")
        bot.register_next_step_handler(msg, process_restart_user_bot)
    
    elif data == 'admin_stop_user_bot':
        msg = bot.send_message(chat_id, "أرسل آيدي المستخدم الذي تريد إيقاف بوتاته:")
        bot.register_next_step_handler(msg, process_stop_user_bot)
    
    elif data == 'admin_restart_all':
        restart_all_bots(chat_id)
    
    elif data == 'admin_view_user_files':
        msg = bot.send_message(chat_id, "أرسل آيدي المستخدم الذي تريد عرض ملفاته:")
        bot.register_next_step_handler(msg, process_view_user_files)
    
    elif data == 'admin_delete_user_file':
        msg = bot.send_message(chat_id, "أرسل آيدي المستخدم واسم الملف (مثال: 12345678 ملف.py):")
        bot.register_next_step_handler(msg, process_delete_user_file)
    
    elif data == 'admin_contact_user':
        msg = bot.send_message(chat_id, "أرسل آيدي المستخدم والرسالة (مثال: 12345678 مرحباً):")
        bot.register_next_step_handler(msg, process_contact_user)
    
    elif data == 'admin_activity_log':
        show_activity_log(chat_id)
    
    elif data == 'admin_settings':
        show_bot_settings(chat_id)
    
    elif data == 'admin_search_user':
        msg = bot.send_message(chat_id, "أرسل آيدي المستخدم الذي تريد البحث عنه:")
        bot.register_next_step_handler(msg, process_search_user)
    
    elif data == 'admin_stats':
        show_stats(chat_id)
    
    elif data == 'admin_lock_bot':
        toggle_bot_lock(chat_id)
    
    elif data == 'admin_monitor':
        toggle_live_monitoring(chat_id)
    
    # إضافة معالجة للزر العودة في لوحة الأدمن
    elif data == 'admin_back':
        admin_panel(call.message)

# ===== وظائف معالجة الأدمن =====
def process_broadcast(message):
    """معالجة عملية الإذاعة"""
    sent = 0
    failed = 0
    total = len(all_users)
    
    for user_id in all_users:
        try:
            # إرسال نفس الرسالة لكل مستخدم
            bot.copy_message(user_id, message.chat.id, message.message_id)
            sent += 1
        except:
            failed += 1
        time.sleep(0.1)  # تجنب حظر التليجرام
    
    bot.reply_to(message, f"✅ تمت الإذاعة بنجاح:\n- تم الإرسال: {sent}\n- فشل: {failed}\n- الإجمالي: {total}")
    log_activity(message.from_user.id, "إرسال إذاعة", f"تم الإرسال: {sent}, فشل: {failed}")

def process_ban_user(message):
    """حظر مستخدم"""
    try:
        user_id = int(message.text)
        banned_users.add(user_id)
        bot.reply_to(message, f"✅ تم حظر المستخدم {user_id}")
        log_activity(message.from_user.id, "حظر مستخدم", f"ID: {user_id}")
        save_data()
    except:
        bot.reply_to(message, "❌ آيدي غير صالح. يجب أن يكون رقمًا")

def process_unban_user(message):
    """إلغاء حظر مستخدم"""
    try:
        user_id = int(message.text)
        if user_id in banned_users:
            banned_users.remove(user_id)
            bot.reply_to(message, f"✅ تم إلغاء حظر المستخدم {user_id}")
            log_activity(message.from_user.id, "إلغاء حظر مستخدم", f"ID: {user_id}")
            save_data()
        else:
            bot.reply_to(message, "❌ هذا المستخدم غير محظور")
    except:
        bot.reply_to(message, "❌ آيدي غير صالح. يجب أن يكون رقمًا")

def process_test_user_bot(message):
    """اختبار بوتات مستخدم"""
    try:
        user_id = int(message.text)
        if user_id not in user_files or not user_files[user_id]:
            bot.reply_to(message, "❌ هذا المستخدم ليس لديه ملفات نشطة")
            return
        
        # تشغيل كل ملفات المستخدم
        for file_key, file_info in user_files[user_id].items():
            if file_info['file_name'].endswith('.py'):
                if file_info['process'] and file_info['process'].poll() is None:
                    file_info['process'].terminate()
                
                proc = subprocess.Popen(["python3", file_info['file_path']])
                file_info['process'] = proc
        
        bot.reply_to(message, f"✅ تم اختبار وإعادة تشغيل بوتات المستخدم {user_id}")
        log_activity(message.from_user.id, "اختبار بوت مستخدم", f"ID: {user_id}")
    except:
        bot.reply_to(message, "❌ آيدي غير صالح. يجب أن يكون رقمًا")

def process_restart_user_bot(message):
    """إعادة تشغيل بوتات مستخدم"""
    try:
        user_id = int(message.text)
        if user_id not in user_files or not user_files[user_id]:
            bot.reply_to(message, "❌ هذا المستخدم ليس لديه ملفات نشطة")
            return
        
        # إيقاف ثم تشغيل كل ملفات المستخدم
        for file_key, file_info in user_files[user_id].items():
            if file_info['file_name'].endswith('.py'):
                if file_info['process'] and file_info['process'].poll() is None:
                    file_info['process'].terminate()
                    time.sleep(1)
                
                proc = subprocess.Popen(["python3", file_info['file_path']])
                file_info['process'] = proc
        
        bot.reply_to(message, f"✅ تم إعادة تشغيل بوتات المستخدم {user_id}")
        log_activity(message.from_user.id, "إعادة تشغيل بوت مستخدم", f"ID: {user_id}")
    except:
        bot.reply_to(message, "❌ آيدي غير صالح. يجب أن يكون رقمًا")

def process_stop_user_bot(message):
    """إيقاف بوتات مستخدم"""
    try:
        user_id = int(message.text)
        if user_id not in user_files or not user_files[user_id]:
            bot.reply_to(message, "❌ هذا المستخدم ليس لديه ملفات نشطة")
            return
        
        # إيقاف كل ملفات المستخدم
        for file_key, file_info in user_files[user_id].items():
            if file_info['process'] and file_info['process'].poll() is None:
                file_info['process'].terminate()
        
        bot.reply_to(message, f"✅ تم إيقاف بوتات المستخدم {user_id}")
        log_activity(message.from_user.id, "إيقاف بوت مستخدم", f"ID: {user_id}")
    except:
        bot.reply_to(message, "❌ آيدي غير صالح. يجب أن يكون رقمًا")

def restart_all_bots(chat_id):
    """إعادة تشغيل جميع البوتات"""
    count = 0
    for user_id, files in user_files.items():
        for file_key, file_info in files.items():
            if file_info['file_name'].endswith('.py'):
                if file_info['process'] and file_info['process'].poll() is None:
                    file_info['process'].terminate()
                    time.sleep(1)
                
                proc = subprocess.Popen(["python3", file_info['file_path']])
                file_info['process'] = proc
                count += 1
    
    bot.send_message(chat_id, f"✅ تم إعادة تشغيل {count} بوت بنجاح")
    log_activity(chat_id, "إعادة تشغيل جميع البوتات", f"عدد: {count}")

def process_view_user_files(message):
    """عرض ملفات مستخدم"""
    try:
        user_id = int(message.text)
        if user_id not in user_files or not user_files[user_id]:
            bot.reply_to(message, "❌ هذا المستخدم ليس لديه ملفات")
            return
        
        files_info = []
        for file_key, file_info in user_files[user_id].items():
            status = "🟢 قيد التشغيل" if file_info.get('process') and file_info['process'].poll() is None else "🔴 متوقف"
            files_info.append(f"📄 {file_info['file_name']} - {status}")
        
        response = "\n".join(files_info)
        bot.reply_to(message, f"📂 ملفات المستخدم {user_id}:\n{response}")
    except:
        bot.reply_to(message, "❌ آيدي غير صالح. يجب أن يكون رقمًا")

def process_delete_user_file(message):
    """حذف ملف مستخدم"""
    try:
        parts = message.text.split(' ', 1)
        if len(parts) < 2:
            bot.reply_to(message, "❌ صيغة غير صحيحة. مثال: 12345678 ملف.py")
            return
        
        user_id = int(parts[0])
        file_name = parts[1]
        
        if user_id not in user_files or not user_files[user_id]:
            bot.reply_to(message, "❌ هذا المستخدم ليس لديه ملفات")
            return
        
        # البحث عن الملف وحذفه
        deleted = False
        for file_key, file_info in list(user_files[user_id].items()):
            if file_info['file_name'] == file_name:
                # إيقاف العملية إن كانت نشطة
                if file_info['process'] and file_info['process'].poll() is None:
                    file_info['process'].terminate()
                
                # حذف الملف
                try:
                    os.remove(file_info['file_path'])
                    # حذف مجلد فك الضغط إذا كان موجوداً
                    if 'extract_path' in file_info:
                        shutil.rmtree(file_info['extract_path'], ignore_errors=True)
                    # حذف البيئة الافتراضية إذا كانت موجودة
                    if 'env_path' in file_info and file_info['env_path']:
                        shutil.rmtree(file_info['env_path'], ignore_errors=True)
                except:
                    pass
                
                # حذف من التخزين
                del user_files[user_id][file_key]
                deleted = True
                break
        
        if deleted:
            bot.reply_to(message, f"✅ تم حذف الملف {file_name} للمستخدم {user_id}")
            log_activity(message.from_user.id, "حذف ملف مستخدم", f"ID: {user_id}, ملف: {file_name}")
        else:
            bot.reply_to(message, f"❌ لم يتم العثور على الملف {file_name} للمستخدم {user_id}")
    except:
        bot.reply_to(message, "❌ خطأ في المعالجة. تأكد من الصيغة")

def process_contact_user(message):
    """التواصل مع مستخدم"""
    try:
        parts = message.text.split(' ', 1)
        if len(parts) < 2:
            bot.reply_to(message, "❌ صيغة غير صحيحة. مثال: 12345678 مرحباً")
            return
        
        user_id = int(parts[0])
        user_message = parts[1]
        
        if user_id not in all_users:
            bot.reply_to(message, "❌ هذا المستخدم غير موجود في قاعدة البيانات")
            return
        
        try:
            bot.send_message(user_id, f"📬 رسالة من الأدمن:\n{user_message}")
            bot.reply_to(message, f"✅ تم إرسال الرسالة للمستخدم {user_id}")
            log_activity(message.from_user.id, "رسالة إلى مستخدم", f"ID: {user_id}, رسالة: {user_message[:20]}...")
        except:
            bot.reply_to(message, f"❌ فشل إرسال الرسالة للمستخدم {user_id}. قد يكون قام بحظر البوت")
    except:
        bot.reply_to(message, "❌ خطأ في المعالجة. تأكد من الصيغة")

def show_activity_log(chat_id):
    """عرض سجل النشاطات"""
    if not user_activity:
        bot.send_message(chat_id, "📭 سجل النشاطات فارغ")
        return
    
    # عرض آخر 10 نشاطات
    recent_activity = user_activity[-10:]
    activity_list = []
    
    for act in reversed(recent_activity):
        activity_list.append(
            f"⏱️ {act['timestamp']}\n👤 {act['user_id']}\n🔧 {act['action']}\nℹ️ {act['details']}\n"
        )
    
    response = "\n".join(activity_list)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("العودة ←", callback_data='admin_back'))
    bot.send_message(chat_id, f"📝 آخر 10 نشاطات:\n\n{response}", reply_markup=markup)

def show_bot_settings(chat_id):
    """عرض إعدادات البوت"""
    settings = f"""
⚙️ *إعدادات البوت الحالية*:

- 🔒 حالة القفل: {'مقفل' if bot_locked else 'مفتوح'}
- 👁️‍🗨️ المراقبة المباشرة: {'مفعلة' if live_monitoring else 'معطلة'}
- 📏 الحد الأقصى لحجم الملف: {MAX_FILE_SIZE // (1024*1024)} MB
- 👮 عدد الأدمن: {len(admin_users)}
- 🚫 عدد المحظورين: {len(banned_users)}
"""
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("تغيير حجم الملف", callback_data='change_file_size'))
    markup.add(types.InlineKeyboardButton("العودة ←", callback_data='admin_back'))
    bot.send_message(chat_id, settings, parse_mode="Markdown", reply_markup=markup)

def process_search_user(message):
    """البحث عن مستخدم"""
    try:
        user_id = int(message.text)
        is_banned = "نعم" if user_id in banned_users else "لا"
        num_files = len(user_files.get(user_id, {}))
        
        response = f"""
🔍 *معلومات المستخدم*:

- 🆔 الآيدي: `{user_id}`
- 🚫 محظور: {is_banned}
- 📂 عدد الملفات: {num_files}
- 📅 تاريخ الانضمام: {'غير معروف'}
"""
        bot.reply_to(message, response, parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ آيدي غير صالح. يجب أن يكون رقمًا")

def show_stats(chat_id):
    """عرض إحصائيات البوت"""
    running_bots = 0
    for user_id, files in user_files.items():
        for file_info in files.values():
            if file_info.get('process') and file_info['process'].poll() is None:
                running_bots += 1
    
    stats = f"""
📊 *إحصائيات البوت*:

- 👥 إجمالي المستخدمين: {user_stats['total_users']}
- 📂 إجمالي الملفات: {user_stats['total_files']}
- 🤖 البوتات النشطة: {running_bots}
- 📈 أكثر الأوامر استخداماً:
"""
    
    # ترتيب الأوامر الأكثر استخداماً
    sorted_commands = sorted(user_stats['command_usage'].items(), key=lambda x: x[1], reverse=True)[:5]
    for cmd, count in sorted_commands:
        stats += f"  - {cmd}: {count}\n"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("العودة ←", callback_data='admin_back'))
    bot.send_message(chat_id, stats, parse_mode="Markdown", reply_markup=markup)

def toggle_bot_lock(chat_id):
    """تبديل حالة قفل البوت"""
    global bot_locked
    bot_locked = not bot_locked
    status = "مقفل" if bot_locked else "مفتوح"
    bot.send_message(chat_id, f"🔒 تم {status} البوت بنجاح")
    log_activity(chat_id, "تبديل قفل البوت", f"الحالة: {status}")
    save_data()

def toggle_live_monitoring(chat_id):
    """تبديل حالة المراقبة المباشرة"""
    global live_monitoring
    live_monitoring = not live_monitoring
    status = "مفعلة" if live_monitoring else "معطلة"
    bot.send_message(chat_id, f"👁️‍🗨️ تم {status} المراقبة المباشرة بنجاح")
    log_activity(chat_id, "تبديل المراقبة", f"الحالة: {status}")
    save_data()

# ===== وظائف المراقبة المباشرة =====
def live_monitor_notify(action, user_id, details=""):
    """إرسال إشعارات المراقبة المباشرة للأدمن"""
    if not live_monitoring:
        return
    
    message = f"👁️‍🗨️ *مراقبة مباشرة*\n\n🔧 الإجراء: {action}\n👤 المستخدم: {user_id}"
    if details:
        message += f"\nℹ️ التفاصيل: {details}"
    
    for admin in admin_users:
        try:
            bot.send_message(admin, message, parse_mode="Markdown")
        except:
            pass

@bot.callback_query_handler(func=lambda call: call.data == 'change_file_size')
def change_file_size(call):
    chat_id = call.message.chat.id
    if call.from_user.id not in admin_users:
        bot.answer_callback_query(call.id, "⛔ ليس لديك صلاحية!")
        return
    
    msg = bot.send_message(chat_id, "أرسل الحد الأقصى الجديد لحجم الملف (بالـ MB):")
    bot.register_next_step_handler(msg, process_change_file_size)

def process_change_file_size(message):
    global MAX_FILE_SIZE
    try:
        new_size = int(message.text)
        if new_size < 1 or new_size > 100:
            bot.reply_to(message, "❌ الحجم يجب أن يكون بين 1 و 100 MB")
            return
        
        MAX_FILE_SIZE = new_size * 1024 * 1024
        bot.reply_to(message, f"✅ تم تحديث الحد الأقصى لحجم الملف إلى {new_size} MB")
        log_activity(message.from_user.id, "تغيير حجم الملف", f"الحجم الجديد: {new_size}MB")
    except:
        bot.reply_to(message, "❌ قيمة غير صحيحة. يجب أن يكون رقمًا")

@bot.message_handler(content_types=['document'])
def handle_file(message):
    if bot_locked:
        return bot.reply_to(message, "⛔ البوت تحت الصيانة حالياً. يرجى المحاولة لاحقاً.")
    
    if message.from_user.id in banned_users:
        return bot.reply_to(message, "❌ تم حظرك.")

    file_name = message.document.file_name
    file_id = message.document.file_id
    file_info = bot.get_file(file_id)
    file_size = file_info.file_size

    # إرسال رسالة الانتظار
    waiting_msg = bot.send_message(message.chat.id, f"⏳ جاري رفع وتشغيل الملف `{file_name}`...", parse_mode="Markdown")
    
    if file_size > MAX_FILE_SIZE:
        bot.edit_message_text(
            chat_id=waiting_msg.chat.id,
            message_id=waiting_msg.message_id,
            text=f"⚠️ الملف `{file_name}` يتجاوز الحجم المسموح ({MAX_FILE_SIZE//(1024*1024)}MB)."
        )
        return

    # إنشاء مجلد التحميلات
    os.makedirs("uploads", exist_ok=True)
    
    # إنشاء مفتاح فريد للملف
    file_key = str(uuid.uuid4())[:8]
    save_path = os.path.join("uploads", file_name)
    
    # تحميل الملف
    try:
        file_data = bot.download_file(file_info.file_path)
        with open(save_path, "wb") as f:
            f.write(file_data)
    except Exception as e:
        bot.edit_message_text(
            chat_id=waiting_msg.chat.id,
            message_id=waiting_msg.message_id,
            text=f"❌ فشل في رفع الملف `{file_name}`: {str(e)}"
        )
        return

    # إنشاء الأزرار
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(f"⏹️ ايقاف تشغيل {file_name}", callback_data=f'stop_{file_key}'),
        types.InlineKeyboardButton(f"🗑️ حذف {file_name}", callback_data=f'delete_{file_key}')
    )
    markup.add(types.InlineKeyboardButton("📂 عرض جميع ملفاتي", callback_data='my_files'))

    # معالجة الملف
    response = ""
    if file_name.endswith(".py"):
        # إنشاء بيئة افتراضية للملف
        env_path = os.path.join("venvs", f"env_{file_key}")
        env_created = create_virtual_environment(env_path)
        
        # تحديث رسالة الانتظار
        bot.edit_message_text(
            chat_id=waiting_msg.chat.id,
            message_id=waiting_msg.message_id,
            text=f"🔧 جاري إعداد البيئة وتثبيت المتطلبات...",
            parse_mode="Markdown"
        )
        
        try:
            # تثبيت المتطلبات
            install_requirements(save_path)
            
            # تشغيل الملف في البيئة الافتراضية
            if env_created:
                python_exec = get_virtualenv_python(env_path)
                command = [python_exec, save_path]
            else:
                command = ["python3", save_path]
            
            proc = subprocess.Popen(command)
            
            response = f"✅ تم تشغيل الملف `{file_name}` بنجاح."
            if env_created:
                response += "\n\n⚠️ تم إنشاء بيئة افتراضية خاصة للملف لتجنب تعارض المكاتب"
            
            # تخزين المعلومات
            if message.chat.id not in user_files:
                user_files[message.chat.id] = {}
            user_files[message.chat.id][file_key] = {
                'process': proc,
                'file_path': save_path,
                'file_name': file_name,
                'env_path': env_path if env_created else None
            }
            
            # تسجيل النشاط
            user_stats['total_files'] += 1
            log_activity(message.chat.id, "رفع وتشغيل ملف", f"ملف: {file_name}")
            
        except Exception as e:
            response = f"❌ فشل في تشغيل الملف `{file_name}`:\n{str(e)}"
        
    elif file_name.endswith(".zip"):
        try:
            extract_path = os.path.join("uploads", file_name.replace('.zip', ''))
            with zipfile.ZipFile(save_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            
            # البحث عن ملفات البايثون الرئيسية
            py_files = [f for f in os.listdir(extract_path) if f.endswith('.py')]
            main_file = None
            
            # محاولة العثور على ملف رئيسي
            for candidate in ['main.py', 'bot.py', 'start.py', 'app.py']:
                if candidate in py_files:
                    main_file = os.path.join(extract_path, candidate)
                    break
            
            # إذا لم يتم العثور، استخدام أول ملف بايثون
            if not main_file and py_files:
                main_file = os.path.join(extract_path, py_files[0])
            
            if main_file:
                # إنشاء بيئة افتراضية
                env_path = os.path.join("venvs", f"env_{file_key}")
                env_created = create_virtual_environment(env_path)
                
                # تثبيت المتطلبات
                install_requirements(main_file)
                
                # تشغيل الملف
                if env_created:
                    python_exec = get_virtualenv_python(env_path)
                    command = [python_exec, main_file]
                else:
                    command = ["python3", main_file]
                
                proc = subprocess.Popen(command)
                
                response = f"✅ تم تشغيل الملف الرئيسي `{os.path.basename(main_file)}` بنجاح."
                if env_created:
                    response += "\n\n⚠️ تم إنشاء بيئة افتراضية خاصة للملف لتجنب تعارض المكاتب"
                
                # تخزين المعلومات
                if message.chat.id not in user_files:
                    user_files[message.chat.id] = {}
                user_files[message.chat.id][file_key] = {
                    'process': proc,
                    'file_path': save_path,
                    'main_file': main_file,
                    'file_name': file_name,
                    'extract_path': extract_path,
                    'env_path': env_path if env_created else None
                }
            else:
                response = f"✅ تم فك الضغط في المجلد: `{extract_path}`\n\n⚠️ لم يتم العثور على ملف بايثون رئيسي للتشغيل"
            
            # تسجيل النشاط
            user_stats['total_files'] += 1
            log_activity(message.chat.id, "رفع ملف ZIP", f"ملف: {file_name}")
            
        except Exception as e:
            response = f"❌ فشل في فك ضغط أو تشغيل الملف `{file_name}`: {str(e)}"
        
    else:
        response = "❌ صيغة غير مدعومة. استخدم .py أو .zip فقط."

    # تحديث الرسالة النهائية
    bot.edit_message_text(
        chat_id=waiting_msg.chat.id,
        message_id=waiting_msg.message_id,
        text=response,
        parse_mode="Markdown",
        reply_markup=markup
    )
    
    # إرسال إشعار المراقبة المباشرة
    live_monitor_notify("رفع ملف", message.chat.id, f"ملف: {file_name}")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    data = call.data
    
    # معالجة طلبات الإيقاف
    if data.startswith('stop_'):
        file_key = data.split('_')[1]
        if chat_id in user_files and file_key in user_files[chat_id]:
            file_info = user_files[chat_id][file_key]
            if file_info['process'] and file_info['process'].poll() is None:
                file_info['process'].terminate()
                bot.answer_callback_query(call.id, f"⏹️ تم إيقاف {file_info['file_name']}")
                # تحديث الواجهة
                file_actions(call)
                log_activity(chat_id, "إيقاف ملف", f"ملف: {file_info['file_name']}")
            else:
                bot.answer_callback_query(call.id, "⚠️ الملف غير قيد التشغيل.")
        else:
            bot.answer_callback_query(call.id, "❌ الملف غير موجود أو تم حذفه مسبقاً.")

    # معالجة طلبات التشغيل
    elif data.startswith('run_'):
        file_key = data.split('_')[1]
        if chat_id in user_files and file_key in user_files[chat_id]:
            file_info = user_files[chat_id][file_key]
            if file_info['process'] is None or file_info['process'].poll() is not None:
                if file_info['file_name'].endswith('.py'):
                    # إعادة تشغيل ملف البايثون
                    if 'env_path' in file_info and file_info['env_path']:
                        python_exec = get_virtualenv_python(file_info['env_path'])
                        command = [python_exec, file_info['file_path']]
                    else:
                        command = ["python3", file_info['file_path']]
                    
                    proc = subprocess.Popen(command)
                    file_info['process'] = proc
                    bot.answer_callback_query(call.id, f"▶️ تم تشغيل {file_info['file_name']}")
                    # تحديث الواجهة
                    file_actions(call)
                    log_activity(chat_id, "تشغيل ملف", f"ملف: {file_info['file_name']}")
                else:
                    bot.answer_callback_query(call.id, "⚠️ لا يمكن تشغيل هذا النوع من الملفات.")
            else:
                bot.answer_callback_query(call.id, "⚠️ الملف قيد التشغيل بالفعل.")
        else:
            bot.answer_callback_query(call.id, "❌ الملف غير موجود.")

    # معالجة طلبات الحذف
    elif data.startswith('delete_'):
        file_key = data.split('_')[1]
        if chat_id in user_files and file_key in user_files[chat_id]:
            file_info = user_files[chat_id].pop(file_key)
            
            # إيقاف العملية إن كانت نشطة
            if file_info['process'] and file_info['process'].poll() is None:
                file_info['process'].terminate()
                
            # حذف الملف
            try:
                os.remove(file_info['file_path'])
                # حذف مجلد فك الضغط إذا كان موجوداً
                if 'extract_path' in file_info:
                    shutil.rmtree(file_info['extract_path'], ignore_errors=True)
                # حذف البيئة الافتراضية إذا كانت موجودة
                if 'env_path' in file_info and file_info['env_path']:
                    shutil.rmtree(file_info['env_path'], ignore_errors=True)
                bot.answer_callback_query(call.id, f"🗑️ تم حذف {file_info['file_name']}")
                # العودة لقائمة الملفات
                show_user_files(call)
                log_activity(chat_id, "حذف ملف", f"ملف: {file_info['file_name']}")
            except Exception as e:
                bot.answer_callback_query(call.id, f"❌ فشل الحذف: {str(e)}")
        else:
            bot.answer_callback_query(call.id, "❌ الملف غير موجود أو تم حذفه مسبقاً.")

    # معالجة طلبات التنزيل
    elif data.startswith('download_'):
        file_key = data.split('_')[1]
        if chat_id in user_files and file_key in user_files[chat_id]:
            file_info = user_files[chat_id][file_key]
            try:
                with open(file_info['file_path'], 'rb') as file:
                    bot.send_document(chat_id, file, caption=f"📥 {file_info['file_name']}")
                bot.answer_callback_query(call.id, "✅ تم إرسال الملف")
                log_activity(chat_id, "تنزيل ملف", f"ملف: {file_info['file_name']}")
            except Exception as e:
                bot.answer_callback_query(call.id, f"❌ فشل إرسال الملف: {str(e)}")
        else:
            bot.answer_callback_query(call.id, "❌ الملف غير موجود.")

    # معالجة الأزرار الأخرى
    elif data == "upload_py":
        bot.send_message(chat_id, "📤 أرسل الآن ملف `.py` لتشغيله.")
        log_activity(chat_id, "طلب رفع ملف .py")
    elif data == "upload_zip":
        bot.send_message(chat_id, "📤 أرسل الآن ملف `.zip` لفك ضغطه.")
        log_activity(chat_id, "طلب رفع ملف .zip")
    elif data == "my_files":
        show_user_files(call)
    elif data == "back_to_main":
        back_to_main(call)
    elif data.startswith("file_"):
        file_actions(call)
    elif data == "help":  # معالجة زر المساعدة من أي مكان
        show_help(call)

@bot.callback_query_handler(func=lambda call: call.data == 'my_files')
def show_user_files(call):
    chat_id = call.message.chat.id
    if chat_id not in user_files or not user_files[chat_id]:
        bot.answer_callback_query(call.id, "⚠️ ليس لديك أي ملفات مخزنة.")
        return
    
    markup = types.InlineKeyboardMarkup()
    for file_key, file_info in user_files[chat_id].items():
        file_name = file_info['file_name']
        status = "🟢 قيد التشغيل" if file_info['process'] and file_info['process'].poll() is None else "🔴 متوقف"
        
        markup.add(
            types.InlineKeyboardButton(
                f"{file_name} ({status})",
                callback_data=f"file_{file_key}"
            )
        )
    
    markup.add(types.InlineKeyboardButton("العودة ←", callback_data='back_to_main'))
    
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=call.message.message_id,
        text="📂 *ملفاتك المخزنة*:\nاختر ملفاً للتحكم به:",
        parse_mode="Markdown",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('file_'))
def file_actions(call):
    chat_id = call.message.chat.id
    file_key = call.data.split('_')[1]
    
    if chat_id not in user_files or file_key not in user_files[chat_id]:
        bot.answer_callback_query(call.id, "❌ الملف غير موجود.")
        return
    
    file_info = user_files[chat_id][file_key]
    file_name = file_info['file_name']
    status = "🟢 قيد التشغيل" if file_info['process'] and file_info['process'].poll() is None else "🔴 متوقف"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    # عرض خيارات التشغيل فقط لملفات البايثون
    if file_info['file_name'].endswith('.py'):
        if file_info['process'] and file_info['process'].poll() is None:
            markup.add(types.InlineKeyboardButton("⏹️ إيقاف التشغيل", callback_data=f"stop_{file_key}"))
        else:
            markup.add(types.InlineKeyboardButton("▶️ تشغيل الملف", callback_data=f"run_{file_key}"))
    
    markup.add(
        types.InlineKeyboardButton("🗑️ حذف الملف", callback_data=f"delete_{file_key}"),
        types.InlineKeyboardButton("📥 تنزيل الملف", callback_data=f"download_{file_key}"),
        types.InlineKeyboardButton("العودة ←", callback_data='my_files')
    )
    
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=call.message.message_id,
        text=f"⚙️ *تحكم في الملف*:\n"
             f"اسم الملف: `{file_name}`\n"
             f"الحالة: {status}\n"
             f"المسار: `{file_info['file_path']}`",
        parse_mode="Markdown",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == 'back_to_main')
def back_to_main(call):
    # الحصول على اسم المستخدم عند العودة للواجهة الرئيسية
    user = call.from_user
    user_name = user.first_name or "عزيزي المستخدم"
    if user.last_name:
        user_name += " " + user.last_name
        
    start_message = get_welcome_message(user_name)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("رفع .py 📤", callback_data='upload_py'),
        types.InlineKeyboardButton("رفع .zip 📤", callback_data='upload_zip'),
        types.InlineKeyboardButton("ملفاتي 📂", callback_data='my_files'),
    )
    
    # أزرار المساعدة والمطور في نفس السطر
    help_dev_buttons = [
        types.InlineKeyboardButton("المساعدة ❓", callback_data='help'),
        types.InlineKeyboardButton("المطور 👨‍💻", url="https://t.me/SSUU_R")
    ]
    markup.add(*help_dev_buttons)
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=start_message,
        reply_markup=markup
    )

# بدء البوت
if __name__ == "__main__":
    # إنشاء المجلدات اللازمة
    os.makedirs("venvs", exist_ok=True)
    os.makedirs("uploads", exist_ok=True)
    
    load_data()  # تحميل البيانات المحفوظة
    print("🚀 Bot is running...")
    bot.polling()

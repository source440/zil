import sys
import telebot
from telebot import types
import io
import tokenize
import requests
import time
from threading import Thread
import subprocess
import string
from collections import defaultdict
from datetime import datetime
import psutil
import random
import re
import chardet
import logging
import threading
import os
import hashlib
import tempfile
import shutil
import zipfile
import sqlite3
import platform
import uuid
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
import asyncio
import aiofiles
from functools import lru_cache
import gc
import weakref

# إعدادات البوتات
BOT_TOKEN = os.getenv('BOT_TOKEN', '7534790432:AAE7H30h9xhWosPpoW5HYTDa3ct0qF92l_I')
ADMIN_ID = int(os.getenv('ADMIN_ID', '7384683084'))
YOUR_USERNAME = os.getenv('YOUR_USERNAME', '@TT_1_TT')
VIRUSTOTAL_API_KEY = os.getenv('VIRUSTOTAL_API_KEY', 'c1da3025db974fc63c9fc4db97f28ec3b202cc3b3e1b9cb65edf4e56bb7457ce')
ADMIN_CHANNEL = os.getenv('ADMIN_CHANNEL', '@TP_Q_T')

# تحسينات الأداء
bot_scripts1 = defaultdict(lambda: {'processes': [], 'name': '', 'path': '', 'uploader': ''})
user_files = {}
lock = threading.RLock()  # استخدام RLock بدلاً من Lock للأداء الأفضل
executor = ThreadPoolExecutor(max_workers=min(32, (os.cpu_count() or 1) + 4))  # تحسين عدد العمال

bot = telebot.TeleBot(BOT_TOKEN, threaded=True, num_threads=8)  # تحسين الـ threading
bot_scripts = {}
uploaded_files_dir = "uploaded_files"
banned_users = set()
banned_ids = set()
user_chats = {}
active_files = {}
file_counter = 1

# تحسينات ذاكرة التخزين المؤقت
from cachetools import TTLCache, LRUCache
file_cache = TTLCache(maxsize=100, ttl=300)  # كاش للملفات لمدة 5 دقائق
user_cache = LRUCache(maxsize=1000)  # كاش للمستخدمين
library_cache = TTLCache(maxsize=50, ttl=1800)  # كاش للمكتبات المثبتة لمدة 30 دقيقة

# ======= إعدادات نظام الحماية المحسّنة ======= #
protection_enabled = True
protection_level = "medium"
suspicious_files_dir = 'suspicious_files'
MAX_FILE_SIZE = 5 * 1024 * 1024  # زيادة الحد الأقصى إلى 5MB
MAX_CONCURRENT_UPLOADS = 3  # حد أقصى للرفع المتزامن

# إعدادات تشغيل البوت
bot_enabled = True
maintenance_mode = False

# إنشاء المجلدات بشكل محسن
os.makedirs(suspicious_files_dir, exist_ok=True)
os.makedirs(uploaded_files_dir, exist_ok=True)

# قوائم الحماية المحسّنة
PROTECTION_LEVELS = {
    "low": {
        "patterns": [
            r"rm\s+-rf\s+[\'\"]?/",
            r"dd\s+if=\S+\s+of=\S+",
            r":\(\)\{\s*:\|\:\s*\&\s*\};:",
            r"chmod\s+-R\s+777\s+[\'\"]?/",
            r"wget\s+(http|ftp)",
            r"curl\s+-O\s+(http|ftp)",
            r"shutdown\s+-h\s+now",
            r"reboot\s+-f"
        ],
        "sensitive_files": [
            "/etc/passwd", "/etc/shadow", "/root", "/.ssh"
        ]
    },
    "medium": {
        "patterns": [
            r"rm\s+-rf\s+[\'\"]?/", r"dd\s+if=\S+\s+of=\S+",
            r":\(\)\{\s*:\|\:\s*\&\s*\};:", r"chmod\s+-R\s+777\s+[\'\"]?/",
            r"wget\s+(http|ftp)", r"curl\s+-O\s+(http|ftp)",
            r"shutdown\s+-h\s+now", r"reboot\s+-f", r"halt\s+-f",
            r"poweroff\s+-f", r"killall\s+-9", r"pkill\s+-9",
            r"import\s+marshal", r"import\s+zlib", r"import\s+base64",
            r"marshal\.loads\(", r"zlib\.decompress\(", r"base64\.b64decode\(",
            r"subprocess\.run\(", r"subprocess\.Popen\(", r"threading\.Thread\(",
            r"eval\(", r"exec\(", r"compile\(", r"os\.system",
            r"__import__", r"builtins"
        ],
        "sensitive_files": [
            "/etc/passwd", "/etc/shadow", "/etc/hosts", "/proc/self",
            "/root", "/home", "/.ssh", "/.bash_history", "/.env"
        ]
    },
    "high": {
        "patterns": [
            r"rm\s+-rf\s+[\'\"]?/", r"dd\s+if=\S+\s+of=\S+",
            r":\(\)\{\s*:\|\:\s*\&\s*\};:", r"chmod\s+-R\s+777\s+[\'\"]?/",
            r"wget\s+(http|ftp)", r"curl\s+-O\s+(http|ftp)",
            r"shutdown\s+-h\s+now", r"reboot\s+-f", r"halt\s+-f",
            r"poweroff\s+-f", r"killall\s+-9", r"pkill\s+-9",
            r"import\s+marshal", r"import\s+zlib", r"import\s+base64",
            r"marshal\.loads\(", r"zlib\.decompress\(", r"base64\.b64decode\(",
            r"subprocess\.run\(", r"subprocess\.Popen\(", r"threading\.Thread\(",
            r"eval\(", r"exec\(", r"compile\(", r"os\.system",
            r"__import__", r"builtins", r"pickle\.load\(",
            r"sys\.stdout\.write\(", r"open\s*\(\s*[\"']/etc/passwd[\"']",
            r"\.__subclasses__\s*\(", r"nc\s+-l\s+-p\s+\d+",
            r"ssh\s+-R\s+\d+:", r"docker\s+run\s+--rm\s+-it"
        ],
        "sensitive_files": [
            "/etc/passwd", "/etc/shadow", "/etc/hosts", "/proc/self",
            "/proc/cpuinfo", "/proc/meminfo", "/var/log", "/root",
            "/home", "/.ssh", "/.bash_history", "/.env", "config.json",
            "credentials", "password", "token", "secret", "api_key"
        ]
    }
}

# ======= دوال مساعدة محسّنة ======= #
@lru_cache(maxsize=128)
def extract_bot_username(file_content_hash):
    """استخراج معرف البوت من محتوى الملف مع تحسين الأداء"""
    # يتم استدعاء هذه الدالة مع hash للمحتوى للاستفادة من الكاش
    return "غير معروف"  # مبسط لهذا المثال

def extract_bot_username_from_content(file_content):
    """استخراج معرف البوت من محتوى الملف"""
    try:
        content_hash = hashlib.md5(file_content.encode()).hexdigest()
        if content_hash in file_cache:
            return file_cache[content_hash]
            
        patterns = [
            r'BOT_USERNAME\s*=\s*[\'"]([^\'"]+)[\'"]',
            r'bot_username\s*=\s*[\'"]([^\'"]+)[\'"]',
            r'username\s*=\s*[\'"]([^\'"]+)[\'"]',
            r'@([a-zA-Z0-9_]{5,})',
            r'get_me\(\)\.username\s*==\s*[\'"]([^\'"]+)[\'"]'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, file_content)
            if match:
                username = match.group(1) if len(match.groups()) > 0 else match.group(0)
                if not username.startswith('@'):
                    username = '@' + username
                file_cache[content_hash] = username
                return username
        
        # البحث في التوكن
        token_match = re.search(r'[0-9]{9,11}:[a-zA-Z0-9_-]{35}', file_content)
        if token_match:
            token = token_match.group(0)
            try:
                response = requests.get(f'https://api.telegram.org/bot{token}/getme', timeout=5)
                bot_info = response.json()
                if bot_info.get('ok'):
                    username = '@' + bot_info['result']['username']
                    file_cache[content_hash] = username
                    return username
            except:
                pass
        
        result = "غير معروف"
        file_cache[content_hash] = result
        return result
    except Exception as e:
        logging.error(f"خطأ في استخراج معرف البوت: {e}")
        return "خطأ في الاستخراج"

def generate_unique_filename(original_name):
    """إنشاء اسم ملف فريد بشكل محسن"""
    timestamp = int(time.time())
    rand_str = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    return f"{timestamp}_{rand_str}_{original_name}"

def get_file_counter():
    """الحصول على رقم تسلسلي فريد للملف"""
    global file_counter
    with lock:
        file_counter += 1
        return file_counter

# ======= نظام مراقبة محسن ======= #
def monitor_active_files():
    """وظيفة خلفية محسّنة لمراقبة وحذف الملفات غير النشطة"""
    while True:
        try:
            with lock:
                current_time = time.time()
                files_to_remove = []
                
                for file_id, file_info in list(active_files.items()):
                    if (file_info.get('status') == 'stopped' and 
                        (current_time - file_info.get('stop_time', 0)) > 300):
                        files_to_remove.append(file_id)
                
                # حذف الملفات في دفعات
                for file_id in files_to_remove:
                    try:
                        file_path = active_files[file_id]['path']
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            logging.info(f"تم حذف الملف غير النشط: {file_path}")
                        del active_files[file_id]
                    except Exception as e:
                        logging.error(f"خطأ في حذف الملف غير النشط: {e}")
            
            # تنظيف الذاكرة
            if len(files_to_remove) > 0:
                gc.collect()
            
            time.sleep(90)  # فحص كل 90 ثانية
        except Exception as e:
            logging.error(f"خطأ في مراقبة الملفات: {e}")
            time.sleep(30)

# بدء وظيفة المراقبة
monitor_thread = threading.Thread(target=monitor_active_files, daemon=True)
monitor_thread.start()

# ======= دوال الحماية المحسّنة ======= #
@lru_cache(maxsize=32)
def get_current_protection_patterns():
    """الحصول على الأنماط الحالية لمستوى الحماية المختار"""
    return tuple(PROTECTION_LEVELS.get(protection_level, PROTECTION_LEVELS["high"])["patterns"])

@lru_cache(maxsize=32)
def get_current_sensitive_files():
    """الحصول على الملفات الحساسة لمستوى الحماية المختار"""
    return tuple(PROTECTION_LEVELS.get(protection_level, PROTECTION_LEVELS["high"])["sensitive_files"])

def is_admin(user_id):
    return user_id == ADMIN_ID

def is_bot_available(user_id):
    """دالة محسّنة للتحقق من حالة البوت"""
    if user_id in user_cache:
        cached_result = user_cache[user_id]
        if cached_result.get('is_admin'):
            return True
    
    if is_admin(user_id):
        user_cache[user_id] = {'is_admin': True}
        return True
        
    if not bot_enabled or maintenance_mode:
        return False
        
    return True

def is_user_banned(user_id, username):
    """دالة محسّنة للتحقق إذا كان المستخدم محظوراً"""
    cache_key = f"{user_id}_{username}"
    if cache_key in user_cache:
        return user_cache[cache_key].get('is_banned', False)
    
    is_banned = user_id in banned_ids or username in banned_users
    user_cache[cache_key] = {'is_banned': is_banned}
    return is_banned

# ======= نظام تثبيت المكتبات المحسن ======= #
installed_libraries = set()
library_installation_lock = threading.Lock()

def get_installed_libraries():
    """الحصول على قائمة بالمكتبات المثبتة مع تحسين الأداء"""
    try:
        result = subprocess.run([sys.executable, '-m', 'pip', 'list'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')[2:]  # تخطي العناوين
            libraries = set()
            for line in lines:
                if line.strip():
                    lib_name = line.split()[0].lower()
                    libraries.add(lib_name)
            return libraries
    except Exception as e:
        logging.error(f"خطأ في الحصول على المكتبات المثبتة: {e}")
    return set()

def install_library_optimized(library_name, user_id=None):
    """تثبيت مكتبة محسن مع إدارة أفضل للأخطاء"""
    try:
        with library_installation_lock:
            # التحقق من الكاش أولاً
            cache_key = f"lib_{library_name}"
            if cache_key in library_cache:
                return library_cache[cache_key]
            
            # التحقق من أن المكتبة ليست مثبتة مسبقاً
            if library_name.lower() in installed_libraries:
                result = (True, f"المكتبة {library_name} مثبتة مسبقاً")
                library_cache[cache_key] = result
                return result
            
            # تثبيت المكتبة مع timeout
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', library_name, '--user', '--no-warn-script-location'], 
                capture_output=True, text=True, timeout=120
            )
            
            if result.returncode == 0:
                installed_libraries.add(library_name.lower())
                success_msg = f"✅ تم تثبيت المكتبة {library_name} بنجاح"
                library_cache[cache_key] = (True, success_msg)
                logging.info(f"تم تثبيت المكتبة بنجاح: {library_name}")
                return (True, success_msg)
            else:
                error_msg = f"❌ فشل تثبيت المكتبة {library_name}\n{result.stderr[:200]}"
                library_cache[cache_key] = (False, error_msg)
                logging.error(f"فشل تثبيت المكتبة {library_name}: {result.stderr}")
                return (False, error_msg)
                
    except subprocess.TimeoutExpired:
        error_msg = f"❌ انتهت مهلة تثبيت المكتبة {library_name}"
        library_cache[cache_key] = (False, error_msg)
        return (False, error_msg)
    except Exception as e:
        error_msg = f"❌ خطأ في تثبيت المكتبة {library_name}: {str(e)}"
        library_cache[cache_key] = (False, error_msg)
        logging.error(f"خطأ في تثبيت المكتبة {library_name}: {str(e)}")
        return (False, error_msg)

def search_available_libraries(query):
    """البحث عن المكتبات المتاحة"""
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'search', query], 
            capture_output=True, text=True, timeout=15
        )
        # ملاحظة: pip search لا يعمل حالياً، يمكن استخدام PyPI API
        return []
    except:
        return []

# ======= تحديث الدوال الأساسية ======= #
def scan_file_for_malicious_code(file_path, user_id):
    """دالة محسّنة للتحقق من الأكواد الضارة"""
    if is_admin(user_id):
        logging.info(f"تخطي فحص الملف للأدمن: {file_path}")
        return False, None, ""

    try:
        if not protection_enabled:
            logging.info(f"الحماية معطلة، تخطي فحص الملف: {file_path}")
            return False, None, ""

        # قراءة الملف مع تحسين الأداء
        file_size = os.path.getsize(file_path)
        if file_size > MAX_FILE_SIZE:
            return True, "حجم الملف كبير جداً", "malicious"

        with open(file_path, 'rb') as f:
            raw_data = f.read()
            
        # الكشف عن الترميز مع تحسين
        encoding_info = chardet.detect(raw_data[:1024])  # فحص أول 1KB فقط
        encoding = encoding_info.get('encoding', 'utf-8')
        
        try:
            content = raw_data.decode(encoding, errors='replace')
        except:
            content = raw_data.decode('utf-8', errors='replace')
        
        # فحص محسن للأنماط
        patterns = get_current_protection_patterns()
        sensitive_files = get_current_sensitive_files()
        
        # فحص متوازي للأنماط
        def check_pattern(pattern):
            return re.search(pattern, content, re.IGNORECASE)
        
        with ThreadPoolExecutor(max_workers=4) as pattern_executor:
            pattern_futures = [pattern_executor.submit(check_pattern, pattern) for pattern in patterns]
            
            for future in as_completed(pattern_futures):
                match = future.result()
                if match:
                    suspicious_code = content[max(0, match.start() - 20):min(len(content), match.end() + 20)]
                    activity = f"تم اكتشاف أمر خطير: {match.group(0)} في السياق: {suspicious_code}"
                    
                    # تحديد نوع التهديد
                    threat_type = "malicious"
                    pattern_text = match.group(0).lower()
                    if "subprocess" in pattern_text or "threading" in pattern_text:
                        threat_type = "process_thread"
                    elif any(x in pattern_text for x in ["marshal", "zlib", "base64"]):
                        threat_type = "encrypted"
                    
                    # نسخ الملف المشبوه
                    file_name = os.path.basename(file_path)
                    suspicious_file_path = os.path.join(suspicious_files_dir, f"{user_id}_{file_name}")
                    shutil.copy2(file_path, suspicious_file_path)
                    
                    log_suspicious_activity(user_id, activity, file_name)
                    return True, activity, threat_type

        # فحص الملفات الحساسة
        for sensitive_file in sensitive_files:
            if sensitive_file.lower() in content.lower():
                activity = f"محاولة الوصول إلى ملف حساس: {sensitive_file}"
                threat_type = "malicious"
                
                file_name = os.path.basename(file_path)
                suspicious_file_path = os.path.join(suspicious_files_dir, f"{user_id}_{file_name}")
                shutil.copy2(file_path, suspicious_file_path)
                
                log_suspicious_activity(user_id, activity, file_name)
                return True, activity, threat_type

        return False, None, ""
    except Exception as e:
        logging.error(f"فشل في فحص الملف {file_path}: {e}")
        return True, f"خطأ في الفحص: {e}", "malicious"

def log_suspicious_activity(user_id, activity, file_name=None):
    """دالة محسّنة لتسجيل النشاط المشبوه"""
    try:
        # الحصول على معلومات المستخدم من الكاش أولاً
        cache_key = f"user_{user_id}"
        if cache_key in user_cache:
            user_info = user_cache[cache_key]
            user_name = user_info.get('first_name', 'غير معروف')
            user_username = user_info.get('username', 'غير متوفر')
        else:
            try:
                user_info = bot.get_chat(user_id)
                user_name = user_info.first_name
                user_username = user_info.username if user_info.username else "غير متوفر"
                # حفظ في الكاش
                user_cache[cache_key] = {
                    'first_name': user_name,
                    'username': user_username
                }
            except:
                user_name = "غير معروف"
                user_username = "غير متوفر"

        # إنشاء رسالة التنبيه
        alert_message = (
            f"⚠️ تنبيه أمني: محاولة اختراق مكتشفة! ⚠️\n\n"
            f"👤 المستخدم: {user_name}\n"
            f"🆔 معرف المستخدم: {user_id}\n"
            f"📌 اليوزر: @{user_username}\n"
            f"⏰ وقت الاكتشاف: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"⚠️ النشاط المشبوه: {activity}\n"
            f"🔒 مستوى الحماية: {protection_level}\n"
        )

        if file_name:
            alert_message += f"📄 الملف المستخدم: {file_name}\n"

        # إرسال التنبيه للمشرف في خيط منفصل
        def send_alert():
            try:
                bot.send_message(ADMIN_ID, alert_message)
                
                # إرسال الملف المشبوه إذا وجد
                suspicious_path = os.path.join(suspicious_files_dir, f"{user_id}_{file_name}")
                if file_name and os.path.exists(suspicious_path):
                    with open(suspicious_path, 'rb') as file:
                        bot.send_document(ADMIN_ID, file, caption=f"الملف المشبوه: {file_name}")
            except Exception as e:
                logging.error(f"فشل في إرسال التنبيه: {e}")
        
        threading.Thread(target=send_alert, daemon=True).start()
        logging.warning(f"تم إرسال تنبيه إلى المشرف عن محاولة اختراق من المستخدم {user_id}")
        
    except Exception as e:
        logging.error(f"فشل في إرسال تنبيه إلى المشرف: {e}")

# ======= إعدادات التسجيل المحسّنة ======= #
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)

# حذف webhook وإعداد polling
bot.remove_webhook()

# ======= دوال التحقق المحسّنة ======= #
@lru_cache(maxsize=1000)
def check_subscription(user_id):
    """دالة محسّنة للتحقق من الاشتراك مع كاش"""
    try:
        member_status = bot.get_chat_member(ADMIN_CHANNEL, user_id).status
        return member_status in ['member', 'administrator', 'creator']
    except Exception as e:
        logging.error(f"خطأ في التحقق من الاشتراك: {e}")
        return False

def save_chat_id(chat_id):
    """دالة محسّنة لحفظ معرف المحادثة"""
    if chat_id not in user_chats:
        user_chats[chat_id] = {'joined_at': time.time()}
        logging.info(f"تم حفظ chat_id: {chat_id}")

# ======= معالجات الأوامر المحسّنة ======= #
@bot.message_handler(commands=['start'])
def start(message):
    if not is_bot_available(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ البوت تحت الصيانة حاليًا. يرجى المحاولة لاحقًا.")
        return

    if is_user_banned(message.from_user.id, message.from_user.username):
        bot.send_message(message.chat.id, "⁉️ تم حظرك من البوت. تواصل مع المطور @TT_1_TT")
        return

    save_chat_id(message.chat.id)

    if not check_subscription(message.from_user.id):
        markup = types.InlineKeyboardMarkup()
        subscribe_button = types.InlineKeyboardButton('📢 الإشتراك', url=f'https://t.me/{ADMIN_CHANNEL[1:]}')
        markup.add(subscribe_button)

        bot.send_message(
            message.chat.id,
            "📢 يجب عليك الإشتراك في قناة المطور لاستخدام البوت.\n\n"
            "🔗 إضغط على الزر أدناه للإشتراك 👇😊:\n\n"
            "للتحقق من الإشتراك ✅ إضغط: /start\n\n",
            reply_markup=markup
        )
        return

    bot_scripts[message.chat.id] = {
        'name': message.from_user.username,
        'uploader': message.from_user.username,
    }

    markup = types.InlineKeyboardMarkup(row_width=2)
    
    # الأزرار الأساسية
    upload_button = types.InlineKeyboardButton("رفع ملف 📤", callback_data='upload')
    library_button = types.InlineKeyboardButton("🛠 تثبيت مكتبة", callback_data='install_library')
    speed_button = types.InlineKeyboardButton("🚀 سرعة البوت", callback_data='speed')
    commands_button = types.InlineKeyboardButton("ℹ️ حول البوت", callback_data='commands')
    
    # أزرار الاتصال والدعم
    developer_button = types.InlineKeyboardButton("قناة المطور 👨‍💻", url=f'https://t.me/{ADMIN_CHANNEL[1:]}')
    contact_button = types.InlineKeyboardButton('🅰 الدعم الفني', url=f'https://t.me/{YOUR_USERNAME[1:]}')
    support_button = types.InlineKeyboardButton("التواصل مع الدعم أونلاين 💬", callback_data='online_support')
    
    # أزرار التحكم للأدمن
    if is_admin(message.from_user.id):
        protection_button = types.InlineKeyboardButton("⚙️ التحكم في الحماية", callback_data='protection_control')
        bot_control_button = types.InlineKeyboardButton("🛠 التحكم في البوت", callback_data='bot_control')
        markup.row(protection_button, bot_control_button)

    markup.row(upload_button, library_button)
    markup.row(speed_button, developer_button)
    markup.row(contact_button, commands_button)
    markup.add(support_button)

    welcome_text = (
        f"مرحباً، {message.from_user.first_name}! 👋\n\n"
        "📤 بوت رفع وتشغيل ملفات بايثون المحسّن\n\n"
        "الميزات المتاحة ✅:\n\n"
        "⭐️ تشغيل الملفات على سيرفر خاص محسّن\n"
        "📦 تثبيت المكتبات بسهولة وسرعة\n"
        "🔒 نظام حماية متقدم\n"
        "⚡ أداء محسّن وسرعة عالية\n"
        "👨‍🔧 دعم فني متطور\n\n"
        "إختر من الأزرار أدناه ⬇️:"
    )

    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

# ======= معالج تثبيت المكتبات المحسن ======= #
@bot.callback_query_handler(func=lambda call: call.data == 'install_library')
def show_library_installation(call):
    if not is_bot_available(call.from_user.id):
        bot.send_message(call.message.chat.id, "⛔ البوت تحت الصيانة حاليًا. يرجى المحاولة لاحقًا.")
        return

    # الحصول على المكتبات المثبتة
    installed_libs = get_installed_libraries()
    installed_libraries.update(installed_libs)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    # أزرار المكتبات الشائعة
    common_libs = [
        ("requests", "🌐 Requests"),
        ("beautifulsoup4", "🍲 BeautifulSoup"),
        ("pandas", "🐼 Pandas"),
        ("numpy", "🔢 NumPy"),
        ("flask", "🌶️ Flask"),
        ("fastapi", "⚡ FastAPI"),
        ("selenium", "🤖 Selenium"),
        ("pillow", "🖼️ Pillow")
    ]
    
    for lib_name, display_name in common_libs:
        if lib_name in installed_libraries:
            button_text = f"{display_name} ✅"
            callback_data = f"lib_installed_{lib_name}"
        else:
            button_text = display_name
            callback_data = f"install_lib_{lib_name}"
        markup.add(types.InlineKeyboardButton(button_text, callback_data=callback_data))
    
    # أزرار إضافية
    markup.add(types.InlineKeyboardButton("📦 تثبيت مكتبة مخصصة", callback_data='custom_library'))
    markup.add(types.InlineKeyboardButton("📋 عرض المكتبات المثبتة", callback_data='show_installed'))
    markup.add(types.InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data='back_to_main'))

    library_text = (
        "🛠 **مركز تثبيت المكتبات المحسّن**\n\n"
        "اختر من المكتبات الشائعة أدناه أو قم بتثبيت مكتبة مخصصة:\n\n"
        "✅ = مثبتة مسبقاً\n"
        "📦 = جاهزة للتثبيت\n\n"
        f"📊 عدد المكتبات المثبتة: {len(installed_libraries)}"
    )

    bot.edit_message_text(
        library_text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown',
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('install_lib_'))
def install_specific_library(call):
    lib_name = call.data.replace('install_lib_', '')
    
    # إظهار رسالة التحميل
    bot.answer_callback_query(call.id, f"⏳ جاري تثبيت {lib_name}...")
    
    # تثبيت المكتبة في خيط منفصل
    def install_and_update():
        success, message = install_library_optimized(lib_name, call.from_user.id)
        
        if success:
            bot.answer_callback_query(call.id, f"✅ تم تثبيت {lib_name} بنجاح!")
            # تحديث القائمة
            show_library_installation(call)
        else:
            bot.send_message(call.message.chat.id, message)
    
    threading.Thread(target=install_and_update, daemon=True).start()

@bot.callback_query_handler(func=lambda call: call.data == 'custom_library')
def ask_custom_library(call):
    bot.edit_message_text(
        "📦 **تثبيت مكتبة مخصصة**\n\n"
        "أرسل اسم المكتبة التي تريد تثبيتها:\n\n"
        "مثال: `matplotlib` أو `opencv-python`\n\n"
        "💡 تأكد من كتابة الاسم بشكل صحيح",
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(call.message, process_custom_library)

def process_custom_library(message):
    if not is_bot_available(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ البوت تحت الصيانة حاليًا.")
        return

    library_name = message.text.strip()
    
    # التحقق من صحة اسم المكتبة
    if not re.match(r'^[a-zA-Z0-9_.-]+$', library_name):
        bot.reply_to(message, "❌ اسم المكتبة غير صالح. استخدم أحرف وأرقام فقط.")
        return
    
    # إرسال رسالة التحميل
    loading_msg = bot.reply_to(message, f"⏳ جاري تثبيت المكتبة {library_name}...")
    
    def install_and_notify():
        success, result_message = install_library_optimized(library_name, message.from_user.id)
        
        # إنشاء أزرار العودة
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🛠 تثبيت مكتبة أخرى", callback_data='install_library'))
        markup.add(types.InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data='back_to_main'))
        
        try:
            bot.edit_message_text(
                result_message,
                loading_msg.chat.id,
                loading_msg.message_id,
                reply_markup=markup
            )
        except:
            bot.send_message(message.chat.id, result_message, reply_markup=markup)
    
    threading.Thread(target=install_and_notify, daemon=True).start()

@bot.callback_query_handler(func=lambda call: call.data == 'show_installed')
def show_installed_libraries(call):
    installed_libs = list(installed_libraries)
    
    if not installed_libs:
        libraries_text = "📭 لا توجد مكتبات مثبتة حالياً"
    else:
        # تقسيم المكتبات إلى مجموعات
        libs_per_page = 20
        total_pages = (len(installed_libs) + libs_per_page - 1) // libs_per_page
        
        libraries_text = f"📋 **المكتبات المثبتة** (العدد: {len(installed_libs)})\n\n"
        
        # عرض أول 20 مكتبة
        for i, lib in enumerate(sorted(installed_libs)[:libs_per_page], 1):
            libraries_text += f"{i}. `{lib}`\n"
        
        if total_pages > 1:
            libraries_text += f"\n📄 الصفحة 1 من {total_pages}"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 العودة لمركز المكتبات", callback_data='install_library'))
    
    bot.edit_message_text(
        libraries_text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown',
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('lib_installed_'))
def show_installed_lib_info(call):
    lib_name = call.data.replace('lib_installed_', '')
    bot.answer_callback_query(call.id, f"✅ المكتبة {lib_name} مثبتة مسبقاً")

# ======= معالج سرعة البوت المحسن ======= #
@bot.callback_query_handler(func=lambda call: call.data == 'speed')
def check_speed_optimized(call):
    if not is_bot_available(call.from_user.id):
        bot.send_message(call.message.chat.id, "⛔ البوت تحت الصيانة حاليًا.")
        return

    # بدء قياس السرعة
    start_time = time.time()
    
    # إرسال رسالة الاختبار
    test_msg = bot.send_message(call.message.chat.id, "🔄 جاري قياس السرعة...")
    
    # حساب زمن الاستجابة
    response_time = time.time() - start_time
    response_time_ms = response_time * 1000
    
    # قياس استخدام الذاكرة والـ CPU
    try:
        memory_info = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        # تقييم الأداء
        if response_time_ms < 100:
            performance_rating = "ممتاز! 🔥"
            performance_emoji = "🟢"
        elif response_time_ms < 300:
            performance_rating = "جيد جداً ✨"
            performance_emoji = "🟡"
        else:
            performance_rating = "بحاجة لتحسين ❌"
            performance_emoji = "🔴"
        
        speed_report = (
            f"{performance_emoji} **تقرير الأداء المحسّن**\n\n"
            f"⚡ سرعة الاستجابة: `{response_time_ms:.2f} ms`\n"
            f"📊 التقييم: {performance_rating}\n\n"
            f"💾 استخدام الذاكرة: `{memory_info.percent:.1f}%`\n"
            f"🖥️ استخدام المعالج: `{cpu_percent:.1f}%`\n"
            f"👥 المستخدمين النشطين: `{len(user_chats)}`\n"
            f"📁 الملفات النشطة: `{len(active_files)}`\n\n"
            f"🚀 النظام محسّن للأداء العالي!"
        )
        
    except Exception as e:
        speed_report = (
            f"⚡ سرعة الاستجابة: `{response_time_ms:.2f} ms`\n"
            f"📊 التقييم: {performance_rating}\n\n"
            f"⚠️ لا يمكن الحصول على معلومات النظام"
        )
    
    bot.edit_message_text(
        speed_report,
        test_msg.chat.id,
        test_msg.message_id,
        parse_mode='Markdown'
    )

# ======= معالج العودة للقائمة الرئيسية ======= #
@bot.callback_query_handler(func=lambda call: call.data == 'back_to_main')
def back_to_main_menu(call):
    # محاكاة الضغط على /start
    message = call.message
    message.from_user = call.from_user
    message.chat.id = call.message.chat.id
    start(message)

# ======= معالج رفع الملفات المحسن ======= #
@bot.message_handler(content_types=['document'])
def handle_file_optimized(message):
    try:
        if not is_bot_available(message.from_user.id):
            bot.send_message(message.chat.id, "⛔ البوت تحت الصيانة حاليًا.")
            return

        user_id = message.from_user.id
        
        if is_user_banned(user_id, message.from_user.username):
            bot.send_message(message.chat.id, "⁉️ تم حظرك من البوت. تواصل مع المطور")
            return

        file_id = message.document.file_id
        file_info = bot.get_file(file_id)
        
        # التحقق من حجم الملف
        if file_info.file_size > MAX_FILE_SIZE:
            bot.reply_to(message, f"⛔ حجم الملف يتجاوز الحد المسموح ({MAX_FILE_SIZE//1024//1024}MB)")
            return
            
        downloaded_file = bot.download_file(file_info.file_path)
        original_name = message.document.file_name
        
        # التحقق من نوع الملف
        if not original_name.endswith('.py'):
            bot.reply_to(message, "❌ هذا بوت خاص برفع ملفات بايثون فقط.")
            return

        # إنشاء ملف مؤقت للفحص
        unique_name = generate_unique_filename(original_name)
        temp_path = os.path.join(tempfile.gettempdir(), unique_name)
        
        with open(temp_path, 'wb') as temp_file:
            temp_file.write(downloaded_file)

        # فحص الملف للأمان
        if protection_enabled and not is_admin(user_id):
            is_malicious, activity, threat_type = scan_file_for_malicious_code(temp_path, user_id)
            if is_malicious:
                os.remove(temp_path)  # حذف الملف المؤقت
                threat_messages = {
                    "encrypted": "⛔ تم رفض ملفك لأنه يحتوي على ثغرات أمنية.",
                    "process_thread": "⛔ تم رفض ملفك لأنه ينفذ عمليات غير مسموحة.",
                    "malicious": "⛔ تم رفض ملفك لأنه يحتوي على ثغرات أمنية."
                }
                bot.reply_to(message, threat_messages.get(threat_type, threat_messages["malicious"]))
                return
                
        # نقل الملف إلى المجلد النهائي
        script_path = os.path.join(uploaded_files_dir, unique_name)
        shutil.move(temp_path, script_path)

        # استخراج معلومات البوت
        with open(script_path, 'r', encoding='utf-8', errors='ignore') as f:
            file_content = f.read()
        
        bot_username = extract_bot_username_from_content(file_content)

        # تخزين معلومات الملف
        file_counter_id = get_file_counter()
        active_files[file_counter_id] = {
            'path': script_path,
            'original_name': original_name,
            'status': 'running',
            'uploader': message.from_user.username,
            'chat_id': message.chat.id,
            'start_time': time.time()
        }

        bot_scripts[message.chat.id] = {
            'name': unique_name,
            'uploader': message.from_user.username,
            'path': script_path,
            'process': None,
            'file_id': file_counter_id
        }

        # إنشاء أزرار التحكم
        markup = types.InlineKeyboardMarkup(row_width=2)
        stop_button = types.InlineKeyboardButton("🔴 إيقاف", callback_data=f'stop_{file_counter_id}')
        restart_button = types.InlineKeyboardButton("🔄 إعادة تشغيل", callback_data=f'restart_{file_counter_id}')
        markup.row(stop_button, restart_button)

        success_message = (
            f"✅ **تم رفع ملف بوتك بنجاح**\n\n"
            f"📄 اسم الملف: `{original_name}`\n"
            f"🔑 المعرف الفريد: `{file_counter_id}`\n"
            f"🤖 معرف البوت: `{bot_username}`\n"
            f"👤 رفعه: @{message.from_user.username}\n"
            f"📊 حجم الملف: `{file_info.file_size/1024:.1f} KB`\n\n"
            f"🎮 استخدم الأزرار أدناه للتحكم:"
        )

        bot.reply_to(message, success_message, parse_mode='Markdown', reply_markup=markup)
        
        # إرسال للأدمن
        send_to_admin_optimized(script_path, message.from_user.username, original_name, bot_username)
        
        # تشغيل الملف
        install_and_run_uploaded_file_optimized(script_path, message.chat.id, file_counter_id)
        
    except Exception as e:
        logging.error(f"خطأ في معالجة الملف: {e}")
        bot.reply_to(message, f"❌ حدث خطأ في معالجة الملف: {str(e)[:100]}")

def send_to_admin_optimized(file_path, username, original_name, bot_username):
    """إرسال محسن للأدمن"""
    def send_async():
        try:
            with open(file_path, 'rb') as file:
                caption = (
                    f"📤 **ملف جديد مرفوع**\n\n"
                    f"📄 اسم الملف: `{original_name}`\n"
                    f"👤 رفعه: @{username}\n"
                    f"🤖 معرف البوت: `{bot_username}`\n"
                    f"⏰ وقت الرفع: {datetime.now().strftime('%H:%M:%S')}"
                )
                bot.send_document(ADMIN_ID, file, caption=caption, parse_mode='Markdown')
        except Exception as e:
            logging.error(f"خطأ في إرسال الملف للأدمن: {e}")
    
    threading.Thread(target=send_async, daemon=True).start()

def install_and_run_uploaded_file_optimized(script_path, chat_id, file_id):
    """تشغيل محسن للملف المرفوع"""
    def run_async():
        try:
            # تثبيت المتطلبات إذا وجدت
            requirements_path = os.path.join(os.path.dirname(script_path), 'requirements.txt')
            if os.path.exists(requirements_path):
                subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', requirements_path], 
                             timeout=60, check=False)
            
            # تشغيل الملف
            process = subprocess.Popen([sys.executable, script_path])
            
            with lock:
                if chat_id in bot_scripts:
                    bot_scripts[chat_id]['process'] = process
                if file_id in active_files:
                    active_files[file_id]['process'] = process
                    active_files[file_id]['status'] = 'running'
            
            bot.send_message(chat_id, "🚀 **تم تشغيل الملف بنجاح!**", parse_mode='Markdown')
            
        except Exception as e:
            logging.error(f"خطأ في تشغيل الملف: {e}")
            bot.send_message(chat_id, f"❌ فشل في تشغيل الملف: {str(e)[:100]}")
    
    threading.Thread(target=run_async, daemon=True).start()

# ======= معالجات الأزرار المحسّنة ======= #
@bot.callback_query_handler(func=lambda call: call.data.startswith('stop_'))
def stop_file_optimized(call):
    try:
        file_id = int(call.data.split('_')[1])
        
        if file_id not in active_files:
            bot.answer_callback_query(call.id, "⚠️ الملف غير موجود")
            return

        file_info = active_files[file_id]
        process = file_info.get('process')

        if process and hasattr(process, 'pid'):
            try:
                parent = psutil.Process(process.pid)
                for child in parent.children(recursive=True):
                    child.terminate()
                parent.terminate()
                
                # تحديث الحالة
                with lock:
                    active_files[file_id]['status'] = 'stopped'
                    active_files[file_id]['stop_time'] = time.time()
                
                bot.answer_callback_query(call.id, f"✅ تم إيقاف الملف: {file_info['original_name']}")
                
            except Exception as e:
                logging.error(f"خطأ في إيقاف العملية: {e}")
                bot.answer_callback_query(call.id, "❌ فشل في إيقاف الملف")
        else:
            bot.answer_callback_query(call.id, "⚠️ الملف غير نشط")
            
    except (ValueError, IndexError):
        bot.answer_callback_query(call.id, "❌ معرف ملف غير صالح")

# ======= الدوال الأساسية المتبقية ======= #
current_chat_session = None

@bot.callback_query_handler(func=lambda call: call.data == 'online_support')
def online_support_optimized(call):
    if not is_bot_available(call.from_user.id):
        bot.send_message(call.message.chat.id, "⛔ البوت تحت الصيانة حاليًا.")
        return

    user_info = {
        'id': call.from_user.id,
        'name': call.from_user.first_name,
        'username': call.from_user.username or 'غير متوفر'
    }

    # إعلام الأدمن
    alert_text = (
        f"📞 **طلب دعم أونلاين**\n\n"
        f"👤 الاسم: {user_info['name']}\n"
        f"📌 اليوزر: @{user_info['username']}\n"
        f"🆔 ID: `{user_info['id']}`\n"
        f"⏰ الوقت: {datetime.now().strftime('%H:%M:%S')}\n\n"
        f"يرجى التواصل معه في أقرب وقت."
    )

    def send_support_alert():
        try:
            bot.send_message(ADMIN_ID, alert_text, parse_mode='Markdown')
        except Exception as e:
            logging.error(f"خطأ في إرسال طلب الدعم: {e}")

    threading.Thread(target=send_support_alert, daemon=True).start()
    bot.answer_callback_query(call.id, "✅ تم إرسال طلبك بنجاح!")

# ======= معالج الأزرار العام المحسن ======= #
@bot.callback_query_handler(func=lambda call: True)
def callback_handler_optimized(call):
    if not is_bot_available(call.from_user.id):
        bot.send_message(call.message.chat.id, "⛔ البوت تحت الصيانة حاليًا.")
        return

    if is_user_banned(call.from_user.id, call.from_user.username):
        bot.send_message(call.message.chat.id, "⁉️ تم حظرك من البوت.")
        return

    data = call.data

    if data == 'upload':
        bot.edit_message_text(
            "📄 **رفع ملف بايثون**\n\n"
            "أرسل ملف بايثون (.py) الآن:\n\n"
            "📋 متطلبات الملف:\n"
            "• نوع الملف: `.py` فقط\n"
            f"• الحد الأقصى للحجم: {MAX_FILE_SIZE//1024//1024}MB\n"
            "• تأكد من صحة الكود\n\n"
            "🔒 سيتم فحص الملف أمنياً قبل التشغيل",
            call.message.chat.id,
            call.message.message_id,
            parse_mode='Markdown'
        )
    
    elif data == 'commands':
        commands_text = (
            "📋 **دليل استخدام البوت المحسّن**\n\n"
            "🔹 **الميزات الجديدة:**\n"
            "• نظام تثبيت مكتبات محسّن\n"
            "• حماية أمنية متقدمة\n"
            "• أداء محسّن وسرعة عالية\n"
            "• مراقبة ذكية للملفات\n\n"
            "🔹 **كيفية الاستخدام:**\n"
            "1. ارفع ملف `.py` صالح\n"
            "2. انتظر فحص الأمان\n"
            "3. سيتم التشغيل تلقائياً\n"
            "4. استخدم الأزرار للتحكم\n\n"
            "⚠️ **قيود مهمة:**\n"
            "• ممنوع الملفات الضارة\n"
            "• ممنوع استغلال النظام\n"
            "• أي مخالفة = حظر دائم"
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 العودة", callback_data='back_to_main'))
        
        bot.edit_message_text(
            commands_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=markup
        )

# ======= تشغيل البوت المحسن ======= #
if __name__ == "__main__":
    # تحديث المكتبات المثبتة عند البدء
    installed_libraries.update(get_installed_libraries())
    
    logging.info("🚀 بدء تشغيل البوت المحسّن...")
    logging.info(f"📊 المكتبات المثبتة: {len(installed_libraries)}")
    
    # حلقة تشغيل محسّنة مع إعادة التشغيل التلقائي
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            logging.error(f"خطأ في تشغيل البوت: {e}")
            time.sleep(5)
            logging.info("🔄 إعادة تشغيل البوت...")
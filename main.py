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
import threading
import requests
from collections import defaultdict
import io
from flask import Flask, request
import math
import base64
from github import Github

# إعداد التوكن وإنشاء البوت وFlask app
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# إعدادات GitHub
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_REPO_NAME = os.getenv('GITHUB_REPO_NAME', 'user_bots_repo')
GITHUB_USERNAME = os.getenv('GITHUB_USERNAME')

# آيدي المطور من متغير البيئة
admin_id = int(os.getenv('ADMIN_ID', '7384683084'))

# تخزين العمليات والملفات
user_files = {}  # {chat_id: {file_key: {'process': Popen, 'github_path': str, 'file_name': str, 'temp_path': str}}}
pending_files = {}  # {pending_key: {'user_id': int, 'file_name': str, 'file_data': bytes, 'message_id': int}}
banned_users = set()
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
MAX_MEMORY_USAGE = 500 * 1024 * 1024  # 500MB كحد أقصى لاستخدام الذاكرة (تم زيادتها)

# تخزين بيانات الأدمن
admin_users = {admin_id}  # مجموعة من آيدي الأدمن
premium_users = set()  # المستخدمون المميزون
upload_settings = {
    'global': 'approval',  # 'allow_all', 'deny_all', 'approval'
    'non_premium_approval': True
}
user_activity = []  # سجل النشاطات
all_users = set()  # جميع المستخدمين الذين بدأوا البوت
user_stats = {  # إحصائيات البوت
    'total_users': 0,
    'total_files': 0,
    'running_bots': 0,
    'command_usage': defaultdict(int),
    'memory_usage': 0
}
bot_locked = False  # حالة قفل البوت
live_monitoring = False  # حالة المراقبة المباشرة

# تخزين بيانات المستخدمين في ملف
DATA_FILE = "bot_data.json"

# متغير لحفظ كائن المستودع
github_repo = None

# ===== وظائف جديدة مضافة =====
def bot_monitor():
    """مراقبة البوتات وإعادة تشغيلها إذا توقفت"""
    while True:
        try:
            for user_id, files in list(user_files.items()):
                for file_key, file_info in list(files.items()):
                    # تخطي الملفات التي تم إيقافها يدوياً
                    if file_info.get('manually_stopped', False):
                        continue
                        
                    if file_info['file_name'].endswith('.py'):
                        proc = file_info.get('process')
                        # إذا كانت العملية موجودة وقد انتهت ولم يتم إيقافها يدوياً
                        if proc and proc.poll() is not None:
                            print(f"إعادة تشغيل بوت توقف: {file_info['file_name']}")
                            
                            # إعادة تحميل المحتوى من GitHub
                            file_content = download_from_github(file_info['github_path'])
                            if file_content is None:
                                continue
                            
                            # إنشاء ملف مؤقت جديد
                            temp_path = create_temp_file(file_content, '.py')
                            file_info['temp_path'] = temp_path
                            
                            # إعادة التشغيل
                            new_proc = run_bot_process(temp_path)
                            file_info['process'] = new_proc
                            
            # انتظر دقيقة قبل الفحص التالي
            time.sleep(60)
        except Exception as e:
            print(f"خطأ في المراقب: {str(e)}")
            # إرسال إخطار للأدمن
            for admin in admin_users:
                try:
                    bot.send_message(admin, f"⚠️ خطأ في مراقب البوتات:\n{str(e)}")
                except:
                    pass
            time.sleep(30)

def memory_cleaner():
    """تنظيف الذاكرة التلقائي"""
    while True:
        try:
            current_usage = get_memory_usage()
            if current_usage > MAX_MEMORY_USAGE * 0.8:  # إذا تجاوز 80%
                # حذف أقدم ملف غير نشط
                for user_id, files in list(user_files.items()):
                    for file_key, file_info in list(files.items()):
                        if file_info.get('process') and file_info['process'].poll() is not None:
                            delete_bot_file(user_id, file_key)
                            print(f"تنظيف الذاكرة: حذف {file_info['file_name']}")
                            break
        except Exception as e:
            print(f"خطأ في منظف الذاكرة: {str(e)}")
        time.sleep(60 * 30)  # كل 30 دقيقة

def run_bot_process(temp_path):
    """تشغيل البوت مع تسجيل الأخطاء"""
    log_file_path = f"{temp_path}.log"
    try:
        with open(log_file_path, 'w') as log_file:
            return subprocess.Popen(
                ["python3", temp_path],
                stdout=log_file,
                stderr=log_file
            )
    except Exception as e:
        print(f"فشل تشغيل البوت: {str(e)}")
        return None

# ===== وظائف GitHub =====
def init_github_repo():
    """تهيئة المستودع على GitHub"""
    global github_repo
    try:
        g = Github(GITHUB_TOKEN)
        user = g.get_user()
        try:
            github_repo = user.get_repo(GITHUB_REPO_NAME)
            print(f"تم تحميل المستودع: {github_repo.name}")
        except:
            github_repo = user.create_repo(GITHUB_REPO_NAME, private=True)
            print(f"تم إنشاء مستودع جديد: {github_repo.name}")
        return github_repo
    except Exception as e:
        print(f"خطأ في تهيئة GitHub: {str(e)}")
        return None

def upload_to_github(file_name, content, user_id):
    """رفع ملف إلى مستودع GitHub"""
    try:
        if not github_repo:
            init_github_repo()
            if not github_repo:
                return None
        
        # إنشاء مسار فريد للملف
        file_path = f"user_{user_id}/{uuid.uuid4().hex}_{file_name}"
        
        # رفع الملف
        github_repo.create_file(
            path=file_path,
            message=f"رفع بواسطة المستخدم: {user_id}",
            content=content,
            branch="main"
        )
        
        return file_path
    except Exception as e:
        print(f"فشل الرفع إلى GitHub: {str(e)}")
        return None

def download_from_github(file_path):
    """تنزيل ملف من مستودع GitHub"""
    try:
        if not github_repo:
            init_github_repo()
            if not github_repo:
                return None
        
        file = github_repo.get_contents(file_path)
        return base64.b64decode(file.content)
    except Exception as e:
        print(f"فشل التنزيل من GitHub: {str(e)}")
        return None

def delete_from_github(file_path):
    """حذف ملف من مستودع GitHub"""
    try:
        if not github_repo:
            init_github_repo()
            if not github_repo:
                return False
        
        file = github_repo.get_contents(file_path)
        github_repo.delete_file(
            path=file_path,
            message=f"حذف الملف",
            sha=file.sha
        )
        return True
    except Exception as e:
        print(f"فشل الحذف من GitHub: {str(e)}")
        return False

# ===== وظائف النظام الأساسية =====
def save_data():
    """حفظ بيانات البوت في ملف"""
    data = {
        'banned_users': list(banned_users),
        'admin_users': list(admin_users),
        'premium_users': list(premium_users),
        'upload_settings': upload_settings,
        'all_users': list(all_users),
        'user_stats': user_stats,
        'bot_locked': bot_locked,
        'live_monitoring': live_monitoring
    }
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f)

def load_data():
    """تحميل بيانات البوت من ملف"""
    global banned_users, admin_users, premium_users, upload_settings, all_users, user_stats, bot_locked, live_monitoring
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                banned_users = set(data.get('banned_users', []))
                admin_users = set(data.get('admin_users', [admin_id]))
                premium_users = set(data.get('premium_users', []))
                upload_settings = data.get('upload_settings', upload_settings)
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
مرحباً، {user_name} |! 👋
أهلاً بك في بوت رفع واستضافة بوتات بايثون!

🎯 مهمة البوت:
- رفع وتشغيل بوتاتك البرمجية.

🚀 كيفية الاستخدام:
1. استخدم الأزرار للتنقل.
2. للأطلاع على المزيد من معلومات البوت اضغط على المساعدة
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

def get_memory_usage():
    """الحصول على إجمالي استخدام الذاكرة للملفات المؤقتة فقط"""
    total = 0
    for user_id, files in user_files.items():
        for file_key, file_info in files.items():
            if 'temp_path' in file_info and os.path.exists(file_info['temp_path']):
                total += os.path.getsize(file_info['temp_path'])
    return total

def check_memory_available(additional_size):
    """التحقق من توفر مساحة ذاكرة كافية"""
    current_usage = get_memory_usage()
    return (current_usage + additional_size) <= MAX_MEMORY_USAGE

def create_temp_file(content, suffix=''):
    """إنشاء ملف مؤقت وإرجاع مساره"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(content)
        return temp_file.name

def get_progress_bar(percent):
    """إنشاء شريط تقدم نصي"""
    bar_length = 20
    filled_length = int(bar_length * percent // 100)
    bar = '▰' * filled_length + '▱' * (bar_length - filled_length)
    return f"⇜ جـارِ  تشغيـل  البوت أنتظر قليلا  . . .🌐\n\n{bar}\n{percent}%"

def update_progress_bar(chat_id, message_id, process_func, *args, **kwargs):
    """تحديث شريط التقدم بشكل متحرك"""
    # إرسال الرسالة الأولية
    progress_msg = bot.send_message(chat_id, get_progress_bar(10))
    
    # قائمة بنسب التحديث
    progress_steps = [20, 30, 40, 50, 60, 70, 80, 90]
    current_step = 0
    
    # متغير لحفظ نتيجة العملية
    result = {"status": "processing", "message": "", "file_info": None, "file_key": None}
    
    # دالة لتشغيل العملية الرئيسية
    def run_process():
        try:
            success, message, file_info, file_key = process_func(*args, **kwargs)
            result.update({
                "status": "success" if success else "error",
                "message": message,
                "file_info": file_info,
                "file_key": file_key
            })
        except Exception as e:
            result.update({
                "status": "error",
                "message": f"❌ فشل في معالجة الملف: {str(e)}"
            })
    
    # بدء العملية في خيط منفصل
    process_thread = threading.Thread(target=run_process)
    process_thread.start()
    
    # تحديث شريط التقدم أثناء معالجة الملفات
    while process_thread.is_alive() and current_step < len(progress_steps):
        time.sleep(0.5)
        try:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_msg.message_id,
                text=get_progress_bar(progress_steps[current_step])
            )
            current_step += 1
        except:
            pass
    
    # انتظار انتهاء العملية مع تحديث أخير
    process_thread.join()
    
    # التحديث النهائي إلى 100%
    try:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=progress_msg.message_id,
            text=get_progress_bar(100)
        )
    except:
        pass
    
    # إضافة تأخير بسيط قبل إظهار النتيجة
    time.sleep(0.5)
    
    # إظهار نتيجة العملية النهائية
    final_text = "✅ تم تشغيل بوتك بنجاح" if result["status"] == "success" else "❌ فشل تشغيل البوت"
    final_text += "\n\n" + result["message"]
    
    # إنشاء أزرار التحكم إن وجدت
    markup = None
    if result["file_info"] and result["file_key"]:
        file_name = result["file_info"]["file_name"]
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton(f"⏹️ ايقاف تشغيل {file_name}", callback_data=f'stop_{result["file_key"]}'),
            types.InlineKeyboardButton(f"🗑️ حذف {file_name}", callback_data=f'delete_{result["file_key"]}')
        )
        markup.add(types.InlineKeyboardButton("📂 عرض جميع ملفاتي", callback_data='my_files'))
    
    # إرسال الرسالة النهائية
    try:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=progress_msg.message_id,
            text=final_text,
            reply_markup=markup,
            parse_mode="Markdown"
        )
    except:
        bot.send_message(chat_id, final_text, reply_markup=markup, parse_mode="Markdown")
    
    return result

def process_and_run_file(user_id, file_name, file_data):
    """معالجة وتشغيل الملف مع إرجاع النتائج"""
    # إنشاء مفتاح فريد للملف
    file_key = str(uuid.uuid4())[:8]
    success = False
    message = ""
    file_info = None
    
    try:
        if file_name.endswith(".py"):
            # تحويل المحتوى إلى نص لرفعه على GitHub
            try:
                content_str = file_data.decode('utf-8')
            except UnicodeDecodeError:
                # إذا كان الملف ثنائي، نستخدم base64
                content_str = base64.b64encode(file_data).decode('utf-8')
            
            # رفع الملف إلى GitHub
            github_path = upload_to_github(file_name, content_str, user_id)
            
            if not github_path:
                return False, "❌ فشل في حفظ الملف على GitHub", None, None
            
            if user_id not in user_files:
                user_files[user_id] = {}
            
            # إنشاء ملف مؤقت للتشغيل
            temp_path = create_temp_file(file_data, '.py')
            
            # تثبيت المتطلبات
            install_requirements(temp_path)
            
            # تشغيل الملف بشكل دائم
            proc = run_bot_process(temp_path)
            
            if proc is None:
                return False, "❌ فشل في تشغيل الملف", None, None
            
            # حفظ المعلومات
            user_files[user_id][file_key] = {
                'file_name': file_name,
                'github_path': github_path,
                'process': proc,
                'temp_path': temp_path,
                'manually_stopped': False  # تم إضافته
            }
            
            message = f"✅ تم رفع وتشغيل ملفك `{file_name}` بنجاح."
            file_info = user_files[user_id][file_key]
            success = True
            
        elif file_name.endswith(".zip"):
            # إنشاء مجلد مؤقت لفك الضغط
            temp_dir = tempfile.mkdtemp()
            zip_path = os.path.join(temp_dir, file_name)
            with open(zip_path, 'wb') as f:
                f.write(file_data)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # البحث عن ملفات البايثون في جميع المجلدات
            py_files = []
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith('.py'):
                        py_files.append(os.path.join(root, file))
            
            main_file = None
            
            # محاولة العثور على ملف رئيسي
            for candidate in ['main.py', 'bot.py', 'start.py', 'app.py']:
                for py_file in py_files:
                    if os.path.basename(py_file).lower() == candidate:
                        main_file = py_file
                        break
                if main_file:
                    break
            
            # إذا لم يتم العثور، استخدام أول ملف بايثون
            if not main_file and py_files:
                main_file = py_files[0]
            
            if main_file:
                # قراءة محتوى الملف الرئيسي
                with open(main_file, 'rb') as f:
                    main_content = f.read()
                
                # تحويل المحتوى إلى نص لرفعه على GitHub
                try:
                    content_str = main_content.decode('utf-8')
                except UnicodeDecodeError:
                    content_str = base64.b64encode(main_content).decode('utf-8')
                
                # رفع الملف إلى GitHub
                github_path = upload_to_github(os.path.basename(main_file), content_str, user_id)
                
                if not github_path:
                    return False, "❌ فشل في حفظ الملف على GitHub", None, None
                
                if user_id not in user_files:
                    user_files[user_id] = {}
                
                # إنشاء ملف مؤقت للتشغيل
                temp_path = create_temp_file(main_content, '.py')
                
                # تثبيت المتطلبات من الملفات المضغوطة
                for root, _, files in os.walk(temp_dir):
                    if 'requirements.txt' in files:
                        requirements_path = os.path.join(root, 'requirements.txt')
                        print(f"تم العثور على ملف المتطلبات: {requirements_path}")
                        subprocess.call(['pip', 'install', '-r', requirements_path])
                
                # تشغيل الملف بشكل دائم
                proc = run_bot_process(temp_path)
                
                if proc is None:
                    return False, "❌ فشل في تشغيل الملف", None, None
                
                # حفظ المعلومات
                user_files[user_id][file_key] = {
                    'file_name': os.path.basename(main_file),
                    'github_path': github_path,
                    'process': proc,
                    'temp_path': temp_path,
                    'temp_dir': temp_dir,  # تخزين المسار لحذفه لاحقاً
                    'manually_stopped': False  # تم إضافته
                }
                
                message = f"✅ تم رفع وتشغيل الملف الرئيسي `{os.path.basename(main_file)}` من الأرشيف بنجاح."
                file_info = user_files[user_id][file_key]
                success = True
            else:
                message = f"✅ تم رفع الملف المضغوط `{file_name}`.\n\n⚠️ لم يتم العثور على ملف بايثون رئيسي للتشغيل"
                success = True
        else:
            message = f"❌ صيغة غير مدعومة: {file_name}"
        
        # تسجيل النشاط
        if success:
            user_stats['total_files'] += 1
            log_activity(user_id, "رفع ملف", f"ملف: {file_name}")
        
    except Exception as e:
        message = f"❌ فشل في معالجة الملف `{file_name}`: {str(e)}"
    
    return success, message, file_info, file_key

def restart_all_bots_from_github():
    """إعادة تشغيل جميع البوتات من مستودع GitHub"""
    if not github_repo:
        init_github_repo()
        if not github_repo:
            print("❌ فشل في تهيئة GitHub")
            return
    
    print("جاري إعادة تشغيل البوتات من GitHub...")
    
    try:
        # الحصول على جميع المجلدات في المستودع
        contents = github_repo.get_contents("")
        user_folders = [c for c in contents if c.type == "dir" and c.path.startswith("user_")]
        
        for folder in user_folders:
            user_id = int(folder.path.replace("user_", ""))
            bot_files = github_repo.get_contents(folder.path)
            
            for bot_file in bot_files:
                if bot_file.name.endswith('.py'):
                    # تنزيل المحتوى
                    file_content = base64.b64decode(bot_file.content)
                    
                    # إنشاء ملف مؤقت
                    temp_path = create_temp_file(file_content, '.py')
                    
                    # تثبيت المتطلبات
                    install_requirements(temp_path)
                    
                    # تشغيل البوت
                    proc = run_bot_process(temp_path)
                    
                    if proc is None:
                        continue
                    
                    # تخزين المعلومات
                    file_key = str(uuid.uuid4())[:8]
                    
                    if user_id not in user_files:
                        user_files[user_id] = {}
                    
                    user_files[user_id][file_key] = {
                        'file_name': bot_file.name,
                        'github_path': bot_file.path,
                        'process': proc,
                        'temp_path': temp_path,
                        'manually_stopped': False  # تم إضافته
                    }
                    
                    print(f"تم إعادة تشغيل بوت: {bot_file.name} للمستخدم {user_id}")
    except Exception as e:
        print(f"خطأ في إعادة التشغيل من GitHub: {str(e)}")
        # إعادة المحاولة بعد 10 ثواني
        time.sleep(10)
        restart_all_bots_from_github()

def delete_bot_file(user_id, file_key):
    """حذف ملف البوت مع حذفه من GitHub"""
    if user_id in user_files and file_key in user_files[user_id]:
        file_info = user_files[user_id].pop(file_key)
        
        # إيقاف العملية إن كانت نشطة
        if file_info.get('process') and file_info['process'].poll() is None:
            file_info['process'].terminate()
        
        # حذف الملف المؤقت
        if 'temp_path' in file_info and os.path.exists(file_info['temp_path']):
            os.unlink(file_info['temp_path'])
        
        # حذف المجلد المؤقت إن وجد
        if 'temp_dir' in file_info and os.path.exists(file_info['temp_dir']):
            shutil.rmtree(file_info['temp_dir'], ignore_errors=True)
        
        # حذف الملف من GitHub
        if 'github_path' in file_info:
            delete_from_github(file_info['github_path'])
        
        return True
    return False

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
        types.InlineKeyboardButton("المطور 👨‍💻", url="https://t.me/TT_1_TT")
    ]
    markup.add(*help_dev_buttons)
    
    welcome = get_welcome_message(user_name)
    bot.send_message(message.chat.id, welcome, reply_markup=markup)
    save_data()

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
  • سيتم البحث عن ملف رئيسي (main.py, bot.py, start.py, app.py)
  • سيتم تثبيت المكتبات من ملف requirements.txt تلقائيًا
- الحد الأقصى لحجم الملف: 100MB
- الملفات تحفظ مؤقتًا في الذاكرة وتُحذف عند التوقف

📦 مثال لملف requirements.txt:
telebot
requests
python-dotenv
    """
    
    # إضافة زر العودة أسفل قائمة المساعدة
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("العودة إلى الواجهة الرئيسية", callback_data='back_to_main'))
    
    bot.send_message(call.message.chat.id, help_text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    load_data()  # تأكد من تحميل أحدث البيانات
    user_id = message.from_user.id
    if user_id not in admin_users:
        bot.reply_to(message, "أنت لست أدمن 🙃")
        return
    
    log_activity(user_id, "فتح لوحة الأدمن")
    send_admin_panel(message.chat.id)

def send_admin_panel(chat_id, message_id=None):
    """إرسال أو تحديث لوحة الأدمن"""
    markup = generate_admin_markup()
    text = "👮‍♂️ *لوحة تحكم الأدمن*"
    
    if message_id:
        try:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=markup
            )
        except:
            bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

def generate_admin_markup():
    """إنشاء أزرار لوحة الأدمن"""
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
        types.InlineKeyboardButton("👁️‍🗨️ مراقبة مباشرة", callback_data='admin_monitor'),
        types.InlineKeyboardButton("📭 ملفات في انتظار الموافقة", callback_data='admin_pending_files'),
        types.InlineKeyboardButton("⭐ إضافة Premium", callback_data='admin_add_premium'),
        types.InlineKeyboardButton("❌ إزالة Premium", callback_data='admin_remove_premium'),
        types.InlineKeyboardButton("✅ سماح للكل", callback_data='admin_allow_all'),
        types.InlineKeyboardButton("❌ رفض الكل", callback_data='admin_deny_all'),
        types.InlineKeyboardButton("🔐 إعدادات الرفع", callback_data='admin_upload_settings'),
        types.InlineKeyboardButton("🗑️ حذف جميع الملفات المعلقة", callback_data='admin_delete_all_pending')
    ]
    
    # إضافة الأزرار في مجموعات
    for i in range(0, len(buttons), 2):
        row = buttons[i:i+2]
        markup.add(*row)
    
    return markup

# ===== معالجات لوحة الأدمن =====
@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def handle_admin_callback(call):
    load_data()  # تأكد من تحميل أحدث البيانات
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
    
    elif data == 'admin_pending_files':
        show_pending_files(call)
    
    elif data == 'admin_add_premium':
        msg = bot.send_message(chat_id, "أرسل آيدي المستخدم الذي تريد منحه صلاحية Premium:")
        bot.register_next_step_handler(msg, process_add_premium)
    
    elif data == 'admin_remove_premium':
        msg = bot.send_message(chat_id, "أرسل آيدي المستخدم الذي تريد إزالة صلاحية Premium منه:")
        bot.register_next_step_handler(msg, process_remove_premium)
    
    elif data == 'admin_allow_all':
        upload_settings['global'] = 'allow_all'
        save_data()
        bot.answer_callback_query(call.id, "✅ تم السماح للكل برفع الملفات دون موافقة")
        log_activity(user_id, "تغيير إعدادات الرفع", "السماح للكل")
    
    elif data == 'admin_deny_all':
        upload_settings['global'] = 'deny_all'
        save_data()
        bot.answer_callback_query(call.id, "✅ تم رفض رفع الملفات للكل حتى Premium")
        log_activity(user_id, "تغيير إعدادات الرفع", "رفض الكل")
    
    elif data == 'admin_upload_settings':
        show_upload_settings(call)
    
    # معالجة زر حذف جميع الملفات المعلقة
    elif data == 'admin_delete_all_pending':
        count = len(pending_files)
        pending_files.clear()
        bot.answer_callback_query(call.id, f"✅ تم حذف {count} ملف معلق")
        log_activity(user_id, "حذف جميع الملفات المعلقة", f"عدد: {count}")
    
    # إضافة معالجة للزر العودة في لوحة الأدمن
    elif data == 'admin_back':
        send_admin_panel(chat_id, call.message.message_id)

def process_add_premium(message):
    try:
        user_id = int(message.text)
        premium_users.add(user_id)
        save_data()
        bot.reply_to(message, f"✅ تم منح صلاحية Premium للمستخدم {user_id}")
        log_activity(message.from_user.id, "إضافة Premium", f"ID: {user_id}")
        
        # إرسال إشعار للمستخدم
        try:
            bot.send_message(user_id, "🎉 تم ترقيتك إلى مستخدم Premium! يمكنك الآن رفع الملفات دون الحاجة إلى موافقة الأدمن.")
        except:
            pass
    except:
        bot.reply_to(message, "❌ آيدي غير صالح. يجب أن يكون رقمًا")

def process_remove_premium(message):
    try:
        user_id = int(message.text)
        if user_id in premium_users:
            premium_users.remove(user_id)
            save_data()
            bot.reply_to(message, f"✅ تم إزالة صلاحية Premium من المستخدم {user_id}")
            log_activity(message.from_user.id, "إزالة Premium", f"ID: {user_id}")
            
            # إرسال إشعار للمستخدم
            try:
                bot.send_message(user_id, "⚠️ تم إزالة صلاحية Premium من حسابك. ستحتاج الآن إلى موافقة الأدمن لرفع الملفات.")
            except:
                pass
        else:
            bot.reply_to(message, "❌ هذا المستخدم ليس لديه صلاحية Premium")
    except:
        bot.reply_to(message, "❌ آيدي غير صالح. يجب أن يكون رقمًا")

def show_upload_settings(call):
    settings = f"""
⚙️ *إعدادات رفع الملفات الحالية*:

- 🟢 الوضع العام: {upload_settings['global']}
- 🟢 وضع Non-Premium: {'يتطلب موافقة' if upload_settings['non_premium_approval'] else 'مرفوض'}
- 🟢 عدد مستخدمي Premium: {len(premium_users)}
"""
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ تفعيل وضع الموافقة", callback_data='set_approval_mode'))
    markup.add(types.InlineKeyboardButton("❌ رفض Non-Premium", callback_data='toggle_non_premium'))
    markup.add(types.InlineKeyboardButton("العودة ←", callback_data='admin_back'))
    bot.send_message(call.message.chat.id, settings, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'set_approval_mode')
def set_approval_mode(call):
    upload_settings['global'] = 'approval'
    save_data()
    bot.answer_callback_query(call.id, "✅ تم تفعيل وضع الموافقة (الافتراضي)")
    log_activity(call.from_user.id, "تغيير إعدادات الرفع", "وضع الموافقة")
    show_upload_settings(call)  # تحديث العرض

@bot.callback_query_handler(func=lambda call: call.data == 'toggle_non_premium')
def toggle_non_premium(call):
    upload_settings['non_premium_approval'] = not upload_settings['non_premium_approval']
    save_data()
    status = "يتطلب موافقة" if upload_settings['non_premium_approval'] else "مرفوض"
    bot.answer_callback_query(call.id, f"✅ تم تغيير وضع Non-Premium إلى: {status}")
    log_activity(call.from_user.id, "تغيير إعدادات Non-Premium", f"الحالة: {status}")
    show_upload_settings(call)  # تحديث العرض

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
                
                # إنشاء ملف مؤقت
                temp_path = create_temp_file(download_from_github(file_info['github_path']), '.py')
                file_info['temp_path'] = temp_path
                
                # تشغيل الملف
                proc = run_bot_process(temp_path)
                file_info['process'] = proc
                file_info['manually_stopped'] = False  # تم إضافته
        
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
                
                # إنشاء ملف مؤقت
                temp_path = create_temp_file(download_from_github(file_info['github_path']), '.py')
                file_info['temp_path'] = temp_path
                
                # تشغيل الملف
                proc = run_bot_process(temp_path)
                file_info['process'] = proc
                file_info['manually_stopped'] = False  # تم إضافته
        
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
                # حذف الملف المؤقت
                if 'temp_path' in file_info and os.path.exists(file_info['temp_path']):
                    os.unlink(file_info['temp_path'])
                    del file_info['temp_path']
                file_info['manually_stopped'] = True  # تم إضافته
        
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
                
                # إنشاء ملف مؤقت
                temp_path = create_temp_file(download_from_github(file_info['github_path']), '.py')
                file_info['temp_path'] = temp_path
                
                # تشغيل الملف
                proc = run_bot_process(temp_path)
                file_info['process'] = proc
                file_info['manually_stopped'] = False  # تم إضافته
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
                delete_bot_file(user_id, file_key)
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
    memory_usage_mb = get_memory_usage() / (1024 * 1024)
    max_memory_mb = MAX_MEMORY_USAGE / (1024 * 1024)
    
    settings = f"""
⚙️ *إعدادات البوت الحالية*:

- 🔒 حالة القفل: {'مقفل' if bot_locked else 'مفتوح'}
- 👁️‍🗨️ المراقبة المباشرة: {'مفعلة' if live_monitoring else 'معطلة'}
- 📏 الحد الأقصى لحجم الملف: {MAX_FILE_SIZE // (1024*1024)} MB
- 🧠 استخدام الذاكرة: {memory_usage_mb:.2f} MB / {max_memory_mb:.2f} MB
- 👮 عدد الأدمن: {len(admin_users)}
- 🚫 عدد المحظورين: {len(banned_users)}
- 📭 الملفات في انتظار الموافقة: {len(pending_files)}
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
        is_premium = "نعم" if user_id in premium_users else "لا"
        num_files = len(user_files.get(user_id, {}))
        
        response = f"""
🔍 *معلومات المستخدم*:

- 🆔 الآيدي: `{user_id}`
- 🚫 محظور: {is_banned}
- ⭐ Premium: {is_premium}
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
    
    memory_usage_mb = get_memory_usage() / (1024 * 1024)
    max_memory_mb = MAX_MEMORY_USAGE / (1024 * 1024)
    
    stats = f"""
📊 *إحصائيات البوت*:

- 👥 إجمالي المستخدمين: {user_stats['total_users']}
- ⭐ مستخدمي Premium: {len(premium_users)}
- 📂 إجمالي الملفات: {user_stats['total_files']}
- 🤖 البوتات النشطة: {running_bots}
- 🧠 استخدام الذاكرة: {memory_usage_mb:.2f} MB / {max_memory_mb:.2f} MB
- 📭 الملفات في انتظار الموافقة: {len(pending_files)}
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

# ===== وظائف نظام الموافقة =====
def show_pending_files(call):
    """عرض الملفات في انتظار الموافقة"""
    if not pending_files:
        bot.answer_callback_query(call.id, "📭 لا يوجد ملفات في انتظار الموافقة")
        return
    
    markup = types.InlineKeyboardMarkup()
    for pending_key, file_info in pending_files.items():
        user_id = file_info['user_id']
        file_name = file_info['file_name']
        markup.add(
            types.InlineKeyboardButton(
                f"👤 {user_id} - 📄 {file_name}",
                callback_data=f"review_{pending_key}"
            )
        )
    
    markup.add(types.InlineKeyboardButton("العودة ←", callback_data='admin_back'))
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="📭 *الملفات في انتظار الموافقة*:",
        parse_mode="Markdown",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('review_'))
def review_pending_file(call):
    """مراجعة ملف معلق"""
    pending_key = call.data.split('_')[1]
    if pending_key not in pending_files:
        bot.answer_callback_query(call.id, "❌ الملف غير موجود أو تمت معالجته مسبقاً")
        return
    
    file_info = pending_files[pending_key]
    
    # إرسال الملف للأدمن للمراجعة
    try:
        bot.send_document(
            call.message.chat.id,
            io.BytesIO(file_info['file_data']),
            visible_file_name=file_info['file_name'],
            caption=f"📄 ملف مرفوع من المستخدم: {file_info['user_id']}\nاسم الملف: {file_info['file_name']}"
        )
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ فشل إرسال الملف: {str(e)}")
        return
    
    # إنشاء أزرار الموافقة والرفض
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("✅ قبول الملف", callback_data=f"approve_{pending_key}"),
        types.InlineKeyboardButton("❌ رفض الملف", callback_data=f"reject_{pending_key}")
    )
    markup.add(types.InlineKeyboardButton("العودة ←", callback_data='admin_back'))
    
    bot.send_message(
        call.message.chat.id,
        f"⚖️ اختر الإجراء المناسب لهذا الملف:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_'))
def approve_file(call):
    """موافقة الأدمن على رفع الملف"""
    pending_key = call.data.split('_')[1]
    if pending_key not in pending_files:
        bot.answer_callback_query(call.id, "❌ الملف غير موجود أو تمت معالجته مسبقاً")
        return
    
    file_info = pending_files.pop(pending_key)
    user_id = file_info['user_id']
    file_name = file_info['file_name']
    file_data = file_info['file_data']
    original_msg_id = file_info['message_id']
    
    # استخدام شريط التقدم المتحرك
    update_progress_bar(
        user_id,
        original_msg_id,
        process_and_run_file,
        user_id,
        file_name,
        file_data
    )
    
    # إرسال إشعار للأدمن
    bot.answer_callback_query(call.id, f"✅ تم قبول الملف للمستخدم {user_id}")
    bot.send_message(call.message.chat.id, f"✅ تم قبول ملف `{file_name}` للمستخدم {user_id}", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('reject_'))
def reject_file(call):
    """رفض الأدمن لرفع الملف"""
    pending_key = call.data.split('_')[1]
    if pending_key not in pending_files:
        bot.answer_callback_query(call.id, "❌ الملف غير موجود أو تمت معالجته مسبقاً")
        return
    
    file_info = pending_files.pop(pending_key)
    user_id = file_info['user_id']
    file_name = file_info['file_name']
    original_msg_id = file_info['message_id']
    
    # إرسال إشعار للمستخدم
    try:
        bot.edit_message_text(
            chat_id=user_id,
            message_id=original_msg_id,
            text=f"❌ تم رفض ملفك `{file_name}` من قبل الأدمن.",
            parse_mode="Markdown"
        )
    except:
        # في حالة حذف المستخدم للرسالة الأصلية
        bot.send_message(
            user_id,
            f"❌ تم رفض ملفك `{file_name}` من قبل الأدمن.",
            parse_mode="Markdown"
        )
    
    # إرسال إشعار للأدمن
    bot.answer_callback_query(call.id, f"❌ تم رفض الملف للمستخدم {user_id}")
    bot.send_message(call.message.chat.id, f"❌ تم رفض ملف `{file_name}` للمستخدم {user_id}", parse_mode="Markdown")
    log_activity(call.from_user.id, "رفض ملف", f"المستخدم: {user_id}, ملف: {file_name}")

# ===== معالجة الملفات مع الزرين الجديدين =====
@bot.callback_query_handler(func=lambda call: call.data == 'delete_all_files')
def delete_all_user_files(call):
    chat_id = call.message.chat.id
    if chat_id not in user_files or not user_files[chat_id]:
        bot.answer_callback_query(call.id, "⚠️ ليس لديك أي ملفات لحذفها.")
        return
    
    count = 0
    for file_key in list(user_files[chat_id].keys()):
        if delete_bot_file(chat_id, file_key):
            count += 1
    
    if count > 0:
        bot.answer_callback_query(call.id, f"✅ تم حذف {count} ملف")
        # تحديث الواجهة
        show_user_files(call)
        log_activity(chat_id, "حذف جميع الملفات", f"عدد: {count}")
    else:
        bot.answer_callback_query(call.id, "⚠️ لم يتم حذف أي ملف")

@bot.callback_query_handler(func=lambda call: call.data == 'stop_all_files')
def stop_all_user_files(call):
    chat_id = call.message.chat.id
    if chat_id not in user_files or not user_files[chat_id]:
        bot.answer_callback_query(call.id, "⚠️ ليس لديك أي ملفات نشطة.")
        return
    
    count = 0
    for file_key, file_info in user_files[chat_id].items():
        if file_info.get('process') and file_info['process'].poll() is None:
            file_info['process'].terminate()
            file_info['manually_stopped'] = True
            
            # حذف الملف المؤقت
            if 'temp_path' in file_info and os.path.exists(file_info['temp_path']):
                os.unlink(file_info['temp_path'])
                del file_info['temp_path']
            
            count += 1
    
    if count > 0:
        bot.answer_callback_query(call.id, f"⏹️ تم إيقاف {count} ملف نشط")
        # تحديث الواجهة
        show_user_files(call)
        log_activity(chat_id, "إيقاف جميع الملفات", f"عدد: {count}")
    else:
        bot.answer_callback_query(call.id, "⚠️ لا توجد ملفات نشطة لإيقافها")

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
    waiting_msg = bot.send_message(message.chat.id, f"⏳ جاري معالجة الملف `{file_name}`...", parse_mode="Markdown")
    
    if file_size > MAX_FILE_SIZE:
        bot.edit_message_text(
            chat_id=waiting_msg.chat.id,
            message_id=waiting_msg.message_id,
            text=f"⚠️ الملف `{file_name}` يتجاوز الحجم المسموح ({MAX_FILE_SIZE//(1024*1024)}MB)."
        )
        return
    
    # التحقق من توفر مساحة ذاكرة كافية
    if not check_memory_available(file_size):
        bot.edit_message_text(
            chat_id=waiting_msg.chat.id,
            message_id=waiting_msg.message_id,
            text=f"⚠️ تجاوزت سعة الذاكرة المؤقتة، يرجى حذف بعض الملفات أو رفع ملف أصغر."
        )
        return

    # تحميل الملف
    try:
        file_data = bot.download_file(file_info.file_path)
    except Exception as e:
        bot.edit_message_text(
            chat_id=waiting_msg.chat.id,
            message_id=waiting_msg.message_id,
            text=f"❌ فشل في رفع الملف `{file_name}`: {str(e)}"
        )
        return

    # التحقق من صلاحيات الرفع
    user_id = message.chat.id
    
    # معالجة خاصة للأدمن: رفع مباشر بدون موافقة
    if user_id in admin_users:
        update_progress_bar(
            user_id,
            waiting_msg.message_id,
            process_and_run_file,
            user_id,
            file_name,
            file_data
        )
        return

    # التحقق من صلاحيات الرفع للمستخدمين العاديين
    if upload_settings['global'] == 'allow_all':
        # السماح للكل بدون موافقة
        update_progress_bar(
            user_id,
            waiting_msg.message_id,
            process_and_run_file,
            user_id,
            file_name,
            file_data
        )
        return
        
    elif upload_settings['global'] == 'deny_all':
        # رفض الكل حتى Premium
        bot.edit_message_text(
            chat_id=waiting_msg.chat.id,
            message_id=waiting_msg.message_id,
            text="⛔ تم رفع الملف بنجاح ولكن يحتاج لموافقة الأدمن"
        )
        add_to_pending(user_id, file_name, file_data, waiting_msg.message_id)
        return
        
    elif upload_settings['global'] == 'approval':
        # وضع الموافقة الافتراضي
        if user_id in premium_users:
            # مستخدم Premium لا يحتاج موافقة
            update_progress_bar(
                user_id,
                waiting_msg.message_id,
                process_and_run_file,
                user_id,
                file_name,
                file_data
            )
        else:
            # مستخدم عادي يحتاج موافقة
            if upload_settings['non_premium_approval']:
                # يحتاج موافقة
                bot.edit_message_text(
                    chat_id=waiting_msg.chat.id,
                    message_id=waiting_msg.message_id,
                    text="⏳ جاري انتظار موافقة الأدمن..."
                )
                add_to_pending(user_id, file_name, file_data, waiting_msg.message_id)
            else:
                # رفض مباشر لغير Premium
                bot.edit_message_text(
                    chat_id=waiting_msg.chat.id,
                    message_id=waiting_msg.message_id,
                    text="⛔ تم رفض رفع الملف لأنك لست مستخدم Premium"
                )
                log_activity(user_id, "رفض رفع ملف", f"ملف: {file_name} (غير Premium)")
        return

def add_to_pending(user_id, file_name, file_data, message_id):
    """إضافة ملف إلى قائمة الانتظار"""
    pending_key = str(uuid.uuid4())[:8]
    pending_files[pending_key] = {
        'user_id': user_id,
        'file_name': file_name,
        'file_data': file_data,
        'message_id': message_id
    }
    
    # إرسال إشعار للأدمن
    for admin in admin_users:
        try:
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("📭 عرض الملفات المعلقة", callback_data='admin_pending_files')
            )
            bot.send_message(
                admin,
                f"📬 هناك ملف جديد في انتظار الموافقة:\n"
                f"👤 المستخدم: {user_id}\n"
                f"📄 اسم الملف: {file_name}\n"
                f"📏 حجم الملف: {len(file_data)//1024} KB",
                reply_markup=markup
            )
        except:
            pass
    
    log_activity(user_id, "رفع ملف", f"ملف: {file_name} (في انتظار الموافقة)")

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
                file_info['manually_stopped'] = True  # تم إضافته
                
                # حذف الملف المؤقت
                if 'temp_path' in file_info and os.path.exists(file_info['temp_path']):
                    os.unlink(file_info['temp_path'])
                    del file_info['temp_path']
                
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
                    # تنزيل المحتوى من GitHub
                    file_content = download_from_github(file_info['github_path'])
                    if file_content is None:
                        bot.answer_callback_query(call.id, "❌ فشل في تحميل الملف من GitHub")
                        return
                    
                    # إنشاء ملف مؤقت جديد
                    temp_path = create_temp_file(file_content, '.py')
                    file_info['temp_path'] = temp_path
                    
                    # تشغيل الملف بشكل دائم
                    proc = run_bot_process(temp_path)
                    file_info['process'] = proc
                    file_info['manually_stopped'] = False  # تم إضافته
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
        if delete_bot_file(chat_id, file_key):
            bot.answer_callback_query(call.id, f"🗑️ تم حذف الملف")
            # العودة لقائمة الملفات
            show_user_files(call)
            log_activity(chat_id, "حذف ملف")
        else:
            bot.answer_callback_query(call.id, "❌ الملف غير موجود أو تم حذفه مسبقاً.")

    # معالجة طلبات التنزيل
    elif data.startswith('download_'):
        file_key = data.split('_')[1]
        if chat_id in user_files and file_key in user_files[chat_id]:
            file_info = user_files[chat_id][file_key]
            try:
                # تنزيل المحتوى من GitHub
                file_content = download_from_github(file_info['github_path'])
                if file_content is None:
                    bot.answer_callback_query(call.id, "❌ فشل في تحميل الملف من GitHub")
                    return
                
                # إرسال الملف
                bot.send_document(
                    chat_id, 
                    io.BytesIO(file_content), 
                    visible_file_name=file_info['file_name'],
                    caption=f"📥 {file_info['file_name']}"
                )
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
    
    # أزرار التحكم الجماعية
    control_buttons = []
    if user_files[chat_id]:
        # زر إيقاف جميع الملفات النشطة
        control_buttons.append(types.InlineKeyboardButton("⏹️ ايقاف جميع الملفات", callback_data="stop_all_files"))
        # زر حذف جميع الملفات
        control_buttons.append(types.InlineKeyboardButton("🗑️ حذف جميع الملفات", callback_data="delete_all_files"))
    
    # إضافة الأزرار في صف واحد إذا كان هناك ملفات
    if control_buttons:
        markup.row(*control_buttons)
    
    # إدراج ملفات المستخدم
    for file_key, file_info in user_files[chat_id].items():
        file_name = file_info['file_name']
        status = "🟢 قيد التشغيل" if file_info.get('process') and file_info['process'].poll() is None else "🔴 متوقف"
        
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
    
    # تحسين التنسيق لعرض معلومات الملف
    file_details = (
        f"⚙️ *تحكم في الملف*\n\n"
        f"📄 اسم الملف: `{file_name}`\n"
        f"🔧 الحالة: {status}\n"
    )
    
    # إضافة معلومات إضافية إن وجدت
    if 'github_path' in file_info:
        file_details += f"🌐 مسار GitHub: `{file_info['github_path']}`\n"
    
    if 'temp_path' in file_info and os.path.exists(file_info['temp_path']):
        file_size = os.path.getsize(file_info['temp_path']) / 1024  # حجم الملف بالكيلوبايت
        file_details += f"📏 حجم الملف: {file_size:.2f} KB\n"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    # خيارات خاصة لملفات البايثون
    if file_info['file_name'].endswith('.py'):
        if file_info['process'] and file_info['process'].poll() is None:
            markup.add(types.InlineKeyboardButton("⏹️ إيقاف التشغيل", callback_data=f"stop_{file_key}"))
        else:
            markup.add(types.InlineKeyboardButton("▶️ تشغيل الملف", callback_data=f"run_{file_key}"))
    
    # أزرار التحكم العامة
    markup.row(
        types.InlineKeyboardButton("🗑️ حذف الملف", callback_data=f"delete_{file_key}"),
        types.InlineKeyboardButton("📥 تنزيل الملف", callback_data=f"download_{file_key}")
    )
    
    # زر العودة
    markup.add(types.InlineKeyboardButton("↩️ العودة إلى ملفاتي", callback_data='my_files'))
    
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=call.message.message_id,
        text=file_details,
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
        types.InlineKeyboardButton("المطور 👨‍💻", url="https://t.me/TT_1_TT")
    ]
    markup.add(*help_dev_buttons)
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=start_message,
        reply_markup=markup
    )

# نقطة النهاية التي تستقبل التحديثات من Telegram
@app.route(f"/{TOKEN}", methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "OK", 200

# نقطة للتأكد أن الخدمة تعمل (لأغراض keep_alive)
@app.route("/keepalive", methods=["GET"])
def keepalive():
    return "I am alive!", 200

# بدء التطبيق
if __name__ == "__main__":
    # إعداد Webhook
    bot.remove_webhook()
    bot.set_webhook(url=f"https://zil-xz70.onrender.com/{TOKEN}")  # ✅ عدّل الرابط حسب رابط تطبيقك

    load_data()  # تحميل البيانات المحفوظة
    
    # تهيئة GitHub
    init_github_repo()
    
    # إعادة تشغيل البوتات المحفوظة
    restart_all_bots_from_github()
    
    # بدء خدمات المراقبة والإدارة
    threading.Thread(target=bot_monitor, daemon=True).start()
    threading.Thread(target=memory_cleaner, daemon=True).start()
    
    # إضافة وظيفة Keep-Alive
    def keep_alive():
        while True:
            try:
                requests.get("https://zil-xz70.onrender.com/keepalive")
                print("تم إرسال طلب Keep-Alive")
            except Exception as e:
                print(f"خطأ في Keep-Alive: {str(e)}")
            time.sleep(180)  # كل 3 دقائق
    
    threading.Thread(target=keep_alive, daemon=True).start()

    print("🚀 Bot is running with Webhook...")

    # تشغيل تطبيق Flask على المنفذ المطلوب
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

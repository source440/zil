#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🚀 بوت استضافة تليجرام المتقدم
نظام استضافة شامل مع إدارة المستخدمين والخوادم والمدفوعات
"""

import os
import sys
import time
import json
import sqlite3
import logging
import asyncio
import threading
import subprocess
import hashlib
import uuid
import shutil
import zipfile
import tarfile
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import requests
from dataclasses import dataclass, asdict
from enum import Enum
import psutil
import telebot
from telebot import types
from concurrent.futures import ThreadPoolExecutor
import schedule

# تكوين التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('hosting_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ======= إعدادات البوت ======= #
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
ADMIN_IDS = list(map(int, os.getenv('ADMIN_IDS', '123456789').split(',')))
PAYMENT_TOKEN = os.getenv('PAYMENT_TOKEN', 'YOUR_PAYMENT_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')
DATABASE_PATH = os.getenv('DATABASE_PATH', 'hosting_bot.db')

# إعدادات الاستضافة
HOSTING_ROOT = os.getenv('HOSTING_ROOT', '/var/hosting')
MAX_STORAGE_FREE = int(os.getenv('MAX_STORAGE_FREE', '500'))  # MB
MAX_STORAGE_PREMIUM = int(os.getenv('MAX_STORAGE_PREMIUM', '5000'))  # MB
MAX_BANDWIDTH_FREE = int(os.getenv('MAX_BANDWIDTH_FREE', '1000'))  # MB/شهر
MAX_BANDWIDTH_PREMIUM = int(os.getenv('MAX_BANDWIDTH_PREMIUM', '50000'))  # MB/شهر

# إعدادات الخادم
SERVER_IP = os.getenv('SERVER_IP', '127.0.0.1')
DEFAULT_PORT_RANGE = (8000, 9000)
NGINX_CONFIG_PATH = '/etc/nginx/sites-available'
NGINX_ENABLED_PATH = '/etc/nginx/sites-enabled'

# إنشاء البوت
bot = telebot.TeleBot(BOT_TOKEN)
executor = ThreadPoolExecutor(max_workers=10)

# ======= نماذج البيانات ======= #
class SubscriptionType(Enum):
    FREE = "free"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"

class ProjectStatus(Enum):
    ACTIVE = "active"
    STOPPED = "stopped"
    BUILDING = "building"
    ERROR = "error"
    SUSPENDED = "suspended"

@dataclass
class User:
    user_id: int
    username: str
    first_name: str
    subscription_type: SubscriptionType
    storage_used: int = 0  # MB
    bandwidth_used: int = 0  # MB
    projects_count: int = 0
    subscription_expires: Optional[datetime] = None
    created_at: datetime = None
    last_active: datetime = None
    is_banned: bool = False

@dataclass
class Project:
    project_id: str
    user_id: int
    name: str
    domain: str
    port: int
    status: ProjectStatus
    storage_used: int = 0
    bandwidth_used: int = 0
    created_at: datetime = None
    last_deployed: datetime = None
    environment: str = "python"
    git_repo: Optional[str] = None
    build_command: str = ""
    start_command: str = ""

@dataclass
class Payment:
    payment_id: str
    user_id: int
    amount: float
    subscription_type: SubscriptionType
    months: int
    status: str = "pending"
    created_at: datetime = None

# ======= إدارة قاعدة البيانات ======= #
class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """إنشاء جداول قاعدة البيانات"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # جدول المستخدمين
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                subscription_type TEXT DEFAULT 'free',
                storage_used INTEGER DEFAULT 0,
                bandwidth_used INTEGER DEFAULT 0,
                projects_count INTEGER DEFAULT 0,
                subscription_expires TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_banned BOOLEAN DEFAULT 0
            )
        ''')
        
        # جدول المشاريع
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                user_id INTEGER,
                name TEXT,
                domain TEXT UNIQUE,
                port INTEGER UNIQUE,
                status TEXT DEFAULT 'stopped',
                storage_used INTEGER DEFAULT 0,
                bandwidth_used INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_deployed TIMESTAMP,
                environment TEXT DEFAULT 'python',
                git_repo TEXT,
                build_command TEXT,
                start_command TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # جدول المدفوعات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                payment_id TEXT PRIMARY KEY,
                user_id INTEGER,
                amount REAL,
                subscription_type TEXT,
                months INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # جدول إحصائيات الاستخدام
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usage_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                project_id TEXT,
                bandwidth_mb INTEGER,
                requests_count INTEGER,
                date DATE DEFAULT CURRENT_DATE,
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                FOREIGN KEY (project_id) REFERENCES projects (project_id)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")

    def get_user(self, user_id: int) -> Optional[User]:
        """الحصول على بيانات المستخدم"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return User(
                user_id=row['user_id'],
                username=row['username'],
                first_name=row['first_name'],
                subscription_type=SubscriptionType(row['subscription_type']),
                storage_used=row['storage_used'],
                bandwidth_used=row['bandwidth_used'],
                projects_count=row['projects_count'],
                subscription_expires=datetime.fromisoformat(row['subscription_expires']) if row['subscription_expires'] else None,
                created_at=datetime.fromisoformat(row['created_at']),
                last_active=datetime.fromisoformat(row['last_active']),
                is_banned=bool(row['is_banned'])
            )
        return None

    def create_user(self, user_id: int, username: str, first_name: str) -> User:
        """إنشاء مستخدم جديد"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, username, first_name, subscription_type, created_at, last_active)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, SubscriptionType.FREE.value, 
              datetime.now().isoformat(), datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        return self.get_user(user_id)

    def update_user_subscription(self, user_id: int, subscription_type: SubscriptionType, months: int):
        """تحديث اشتراك المستخدم"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        expires_at = datetime.now() + timedelta(days=30 * months)
        
        cursor.execute('''
            UPDATE users 
            SET subscription_type = ?, subscription_expires = ?
            WHERE user_id = ?
        ''', (subscription_type.value, expires_at.isoformat(), user_id))
        
        conn.commit()
        conn.close()

    def get_user_projects(self, user_id: int) -> List[Project]:
        """الحصول على مشاريع المستخدم"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM projects WHERE user_id = ?', (user_id,))
        rows = cursor.fetchall()
        conn.close()
        
        projects = []
        for row in rows:
            projects.append(Project(
                project_id=row['project_id'],
                user_id=row['user_id'],
                name=row['name'],
                domain=row['domain'],
                port=row['port'],
                status=ProjectStatus(row['status']),
                storage_used=row['storage_used'],
                bandwidth_used=row['bandwidth_used'],
                created_at=datetime.fromisoformat(row['created_at']),
                last_deployed=datetime.fromisoformat(row['last_deployed']) if row['last_deployed'] else None,
                environment=row['environment'],
                git_repo=row['git_repo'],
                build_command=row['build_command'],
                start_command=row['start_command']
            ))
        
        return projects

    def create_project(self, user_id: int, name: str, environment: str = "python") -> Project:
        """إنشاء مشروع جديد"""
        project_id = str(uuid.uuid4())[:8]
        domain = f"{name.lower().replace(' ', '-')}-{project_id}.{SERVER_IP}.nip.io"
        port = self._get_available_port()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO projects 
            (project_id, user_id, name, domain, port, status, environment, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (project_id, user_id, name, domain, port, ProjectStatus.STOPPED.value, 
              environment, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        # إنشاء مجلد المشروع
        project_path = os.path.join(HOSTING_ROOT, project_id)
        os.makedirs(project_path, exist_ok=True)
        
        return self.get_project(project_id)

    def get_project(self, project_id: str) -> Optional[Project]:
        """الحصول على بيانات المشروع"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM projects WHERE project_id = ?', (project_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return Project(
                project_id=row['project_id'],
                user_id=row['user_id'],
                name=row['name'],
                domain=row['domain'],
                port=row['port'],
                status=ProjectStatus(row['status']),
                storage_used=row['storage_used'],
                bandwidth_used=row['bandwidth_used'],
                created_at=datetime.fromisoformat(row['created_at']),
                last_deployed=datetime.fromisoformat(row['last_deployed']) if row['last_deployed'] else None,
                environment=row['environment'],
                git_repo=row['git_repo'],
                build_command=row['build_command'],
                start_command=row['start_command']
            )
        return None

    def _get_available_port(self) -> int:
        """الحصول على منفذ متاح"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT port FROM projects ORDER BY port')
        used_ports = {row[0] for row in cursor.fetchall()}
        conn.close()
        
        for port in range(DEFAULT_PORT_RANGE[0], DEFAULT_PORT_RANGE[1]):
            if port not in used_ports:
                return port
        
        raise Exception("No available ports")

# إنشاء مدير قاعدة البيانات
db = DatabaseManager(DATABASE_PATH)

# ======= إدارة الاستضافة ======= #
class HostingManager:
    def __init__(self):
        os.makedirs(HOSTING_ROOT, exist_ok=True)
        self.running_processes = {}

    def deploy_project(self, project: Project, file_path: str = None) -> bool:
        """نشر المشروع"""
        try:
            project_path = os.path.join(HOSTING_ROOT, project.project_id)
            
            # إذا تم رفع ملف
            if file_path:
                self._extract_project_files(file_path, project_path)
            
            # تثبيت المتطلبات
            self._install_requirements(project_path)
            
            # تحديث nginx config
            self._update_nginx_config(project)
            
            # بدء المشروع
            if self._start_project(project):
                self._update_project_status(project.project_id, ProjectStatus.ACTIVE)
                return True
            
        except Exception as e:
            logger.error(f"Failed to deploy project {project.project_id}: {e}")
            self._update_project_status(project.project_id, ProjectStatus.ERROR)
        
        return False

    def _extract_project_files(self, file_path: str, project_path: str):
        """استخراج ملفات المشروع"""
        if file_path.endswith('.zip'):
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(project_path)
        elif file_path.endswith(('.tar.gz', '.tgz')):
            with tarfile.open(file_path, 'r:gz') as tar_ref:
                tar_ref.extractall(project_path)
        else:
            # نسخ ملف واحد
            shutil.copy2(file_path, project_path)

    def _install_requirements(self, project_path: str):
        """تثبيت متطلبات المشروع"""
        requirements_file = os.path.join(project_path, 'requirements.txt')
        if os.path.exists(requirements_file):
            subprocess.run([
                sys.executable, '-m', 'pip', 'install', '-r', requirements_file
            ], cwd=project_path, check=True)

    def _update_nginx_config(self, project: Project):
        """تحديث إعدادات nginx"""
        config_content = f"""
server {{
    listen 80;
    server_name {project.domain};
    
    location / {{
        proxy_pass http://127.0.0.1:{project.port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""
        
        config_path = os.path.join(NGINX_CONFIG_PATH, f"{project.project_id}")
        with open(config_path, 'w') as f:
            f.write(config_content)
        
        # تفعيل الموقع
        enabled_path = os.path.join(NGINX_ENABLED_PATH, f"{project.project_id}")
        if not os.path.exists(enabled_path):
            os.symlink(config_path, enabled_path)
        
        # إعادة تحميل nginx
        subprocess.run(['nginx', '-s', 'reload'], check=False)

    def _start_project(self, project: Project) -> bool:
        """بدء تشغيل المشروع"""
        try:
            project_path = os.path.join(HOSTING_ROOT, project.project_id)
            
            # تحديد أمر التشغيل
            if project.start_command:
                cmd = project.start_command.split()
            else:
                # البحث عن ملف main.py أو app.py
                if os.path.exists(os.path.join(project_path, 'main.py')):
                    cmd = [sys.executable, 'main.py']
                elif os.path.exists(os.path.join(project_path, 'app.py')):
                    cmd = [sys.executable, 'app.py']
                else:
                    return False
            
            # بدء العملية
            env = os.environ.copy()
            env['PORT'] = str(project.port)
            
            process = subprocess.Popen(
                cmd,
                cwd=project_path,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            self.running_processes[project.project_id] = process
            return True
            
        except Exception as e:
            logger.error(f"Failed to start project {project.project_id}: {e}")
            return False

    def stop_project(self, project_id: str) -> bool:
        """إيقاف المشروع"""
        try:
            if project_id in self.running_processes:
                process = self.running_processes[project_id]
                process.terminate()
                process.wait(timeout=10)
                del self.running_processes[project_id]
            
            self._update_project_status(project_id, ProjectStatus.STOPPED)
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop project {project_id}: {e}")
            return False

    def _update_project_status(self, project_id: str, status: ProjectStatus):
        """تحديث حالة المشروع"""
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        cursor.execute(
            'UPDATE projects SET status = ? WHERE project_id = ?',
            (status.value, project_id)
        )
        
        conn.commit()
        conn.close()

    def get_project_stats(self, project_id: str) -> Dict[str, Any]:
        """الحصول على إحصائيات المشروع"""
        project_path = os.path.join(HOSTING_ROOT, project_id)
        stats = {
            'storage_used': 0,
            'files_count': 0,
            'is_running': project_id in self.running_processes
        }
        
        if os.path.exists(project_path):
            # حساب المساحة المستخدمة
            total_size = 0
            files_count = 0
            
            for dirpath, dirnames, filenames in os.walk(project_path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    total_size += os.path.getsize(filepath)
                    files_count += 1
            
            stats['storage_used'] = total_size // (1024 * 1024)  # MB
            stats['files_count'] = files_count
        
        return stats

# إنشاء مدير الاستضافة
hosting = HostingManager()

# ======= إدارة المدفوعات ======= #
class PaymentManager:
    def __init__(self):
        self.prices = {
            SubscriptionType.PREMIUM: 5.0,  # دولار شهرياً
            SubscriptionType.ENTERPRISE: 20.0  # دولار شهرياً
        }

    def create_payment(self, user_id: int, subscription_type: SubscriptionType, months: int) -> str:
        """إنشاء دفعة جديدة"""
        payment_id = str(uuid.uuid4())
        amount = self.prices[subscription_type] * months
        
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO payments 
            (payment_id, user_id, amount, subscription_type, months, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (payment_id, user_id, amount, subscription_type.value, months, 
              datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        return payment_id

    def process_payment(self, payment_id: str) -> bool:
        """معالجة الدفعة"""
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM payments WHERE payment_id = ?', (payment_id,))
        payment_data = cursor.fetchone()
        
        if payment_data:
            # تحديث حالة الدفعة
            cursor.execute(
                'UPDATE payments SET status = ? WHERE payment_id = ?',
                ('completed', payment_id)
            )
            
            # تحديث اشتراك المستخدم
            db.update_user_subscription(
                payment_data[1],  # user_id
                SubscriptionType(payment_data[3]),  # subscription_type
                payment_data[4]  # months
            )
            
            conn.commit()
            conn.close()
            return True
        
        conn.close()
        return False

# إنشاء مدير المدفوعات
payment_manager = PaymentManager()

# ======= معالجات البوت ======= #

@bot.message_handler(commands=['start'])
def handle_start(message):
    """معالج أمر البدء"""
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    
    # إنشاء أو تحديث المستخدم
    user = db.get_user(user_id)
    if not user:
        user = db.create_user(user_id, username, first_name)
        logger.info(f"New user registered: {user_id}")
    
    # رسالة الترحيب
    welcome_text = f"""
🚀 **مرحباً بك في خدمة الاستضافة المتقدمة** 

👋 أهلاً {first_name}!

🎯 **ما يمكنك فعله:**
• رفع وتشغيل مشاريع Python/Node.js
• الحصول على نطاق فرعي مجاني
• مراقبة استخدام الموارد
• إدارة مشاريعك بسهولة

📊 **حسابك الحالي:**
• الاشتراك: {user.subscription_type.value.title()}
• المشاريع: {user.projects_count}
• المساحة المستخدمة: {user.storage_used} MB

استخدم الأزرار أدناه للبدء! 👇
"""
    
    markup = create_main_menu(user)
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup, parse_mode='Markdown')

def create_main_menu(user: User) -> types.InlineKeyboardMarkup:
    """إنشاء القائمة الرئيسية"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    # أزرار أساسية
    markup.add(
        types.InlineKeyboardButton("🚀 مشاريعي", callback_data="my_projects"),
        types.InlineKeyboardButton("➕ مشروع جديد", callback_data="new_project")
    )
    
    markup.add(
        types.InlineKeyboardButton("📊 الإحصائيات", callback_data="stats"),
        types.InlineKeyboardButton("💎 الترقية", callback_data="upgrade")
    )
    
    markup.add(
        types.InlineKeyboardButton("📖 الدليل", callback_data="help"),
        types.InlineKeyboardButton("🎧 الدعم", callback_data="support")
    )
    
    # أزرار الإدارة للمشرفين
    if user.user_id in ADMIN_IDS:
        markup.add(
            types.InlineKeyboardButton("⚙️ لوحة الإدارة", callback_data="admin_panel")
        )
    
    return markup

@bot.callback_query_handler(func=lambda call: call.data == "my_projects")
def handle_my_projects(call):
    """عرض مشاريع المستخدم"""
    user_id = call.from_user.id
    projects = db.get_user_projects(user_id)
    
    if not projects:
        bot.edit_message_text(
            "📂 **لا توجد مشاريع حالياً**\n\n"
            "ابدأ بإنشاء مشروعك الأول! 🚀",
            call.message.chat.id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("➕ إنشاء مشروع", callback_data="new_project"),
                types.InlineKeyboardButton("🔙 العودة", callback_data="back_to_main")
            )
        )
        return
    
    # عرض قائمة المشاريع
    text = "📂 **مشاريعك:**\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for project in projects:
        status_emoji = {
            ProjectStatus.ACTIVE: "🟢",
            ProjectStatus.STOPPED: "🔴", 
            ProjectStatus.BUILDING: "🟡",
            ProjectStatus.ERROR: "💥",
            ProjectStatus.SUSPENDED: "⏸️"
        }
        
        emoji = status_emoji.get(project.status, "❓")
        text += f"{emoji} **{project.name}**\n"
        text += f"   🌐 {project.domain}\n"
        text += f"   📊 {project.storage_used} MB\n\n"
        
        markup.add(
            types.InlineKeyboardButton(
                f"{emoji} {project.name}", 
                callback_data=f"project_{project.project_id}"
            )
        )
    
    markup.add(
        types.InlineKeyboardButton("➕ مشروع جديد", callback_data="new_project"),
        types.InlineKeyboardButton("🔙 العودة", callback_data="back_to_main")
    )
    
    bot.edit_message_text(
        text, call.message.chat.id, call.message.message_id,
        parse_mode='Markdown', reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("project_"))
def handle_project_details(call):
    """عرض تفاصيل المشروع"""
    project_id = call.data.split("_")[1]
    project = db.get_project(project_id)
    
    if not project:
        bot.answer_callback_query(call.id, "❌ المشروع غير موجود")
        return
    
    # الحصول على إحصائيات المشروع
    stats = hosting.get_project_stats(project_id)
    
    # حالة المشروع
    status_text = {
        ProjectStatus.ACTIVE: "🟢 نشط",
        ProjectStatus.STOPPED: "🔴 متوقف",
        ProjectStatus.BUILDING: "🟡 جاري البناء",
        ProjectStatus.ERROR: "💥 خطأ",
        ProjectStatus.SUSPENDED: "⏸️ معلق"
    }
    
    text = f"""
🚀 **{project.name}**

📊 **معلومات المشروع:**
• الحالة: {status_text.get(project.status, "❓ غير معروف")}
• النطاق: `{project.domain}`
• المنفذ: `{project.port}`
• البيئة: {project.environment}

💾 **الموارد:**
• المساحة: {stats['storage_used']} MB
• عدد الملفات: {stats['files_count']}
• عرض النطاق: {project.bandwidth_used} MB

📅 **التواريخ:**
• تم الإنشاء: {project.created_at.strftime('%Y-%m-%d %H:%M')}
• آخر نشر: {project.last_deployed.strftime('%Y-%m-%d %H:%M') if project.last_deployed else 'لم يتم النشر بعد'}
"""
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    # أزرار التحكم
    if project.status == ProjectStatus.STOPPED:
        markup.add(types.InlineKeyboardButton("▶️ تشغيل", callback_data=f"start_{project_id}"))
    elif project.status == ProjectStatus.ACTIVE:
        markup.add(types.InlineKeyboardButton("⏹️ إيقاف", callback_data=f"stop_{project_id}"))
    
    markup.add(
        types.InlineKeyboardButton("🔄 إعادة نشر", callback_data=f"redeploy_{project_id}"),
        types.InlineKeyboardButton("🌐 فتح الموقع", url=f"http://{project.domain}")
    )
    
    markup.add(
        types.InlineKeyboardButton("📁 رفع ملفات", callback_data=f"upload_{project_id}"),
        types.InlineKeyboardButton("⚙️ الإعدادات", callback_data=f"settings_{project_id}")
    )
    
    markup.add(
        types.InlineKeyboardButton("🗑️ حذف المشروع", callback_data=f"delete_{project_id}"),
        types.InlineKeyboardButton("🔙 العودة", callback_data="my_projects")
    )
    
    bot.edit_message_text(
        text, call.message.chat.id, call.message.message_id,
        parse_mode='Markdown', reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "new_project")
def handle_new_project(call):
    """إنشاء مشروع جديد"""
    user_id = call.from_user.id
    user = db.get_user(user_id)
    
    # التحقق من الحدود
    max_projects = 1 if user.subscription_type == SubscriptionType.FREE else 10
    if user.projects_count >= max_projects:
        bot.answer_callback_query(
            call.id, 
            f"❌ وصلت للحد الأقصى ({max_projects} مشاريع). قم بالترقية للمزيد!"
        )
        return
    
    bot.edit_message_text(
        "📝 **إنشاء مشروع جديد**\n\n"
        "أرسل اسم المشروع (بالإنجليزية، بدون مسافات):",
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown'
    )
    
    bot.register_next_step_handler(call.message, process_project_name, user_id)

def process_project_name(message, user_id):
    """معالجة اسم المشروع"""
    project_name = message.text.strip()
    
    # التحقق من صحة الاسم
    if not project_name.isalnum() or len(project_name) < 3:
        bot.reply_to(
            message,
            "❌ اسم المشروع يجب أن يكون بالإنجليزية، بدون مسافات، وأكثر من 3 أحرف."
        )
        return
    
    try:
        # إنشاء المشروع
        project = db.create_project(user_id, project_name)
        
        text = f"""
✅ **تم إنشاء المشروع بنجاح!**

🚀 **{project.name}**
• النطاق: `{project.domain}`
• المنفذ: `{project.port}`

🔗 **ما التالي؟**
1. ارفع ملفات مشروعك
2. قم بنشر المشروع  
3. افتح موقعك الجديد!
"""
        
        markup = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("📁 رفع ملفات", callback_data=f"upload_{project.project_id}"),
            types.InlineKeyboardButton("👀 عرض المشروع", callback_data=f"project_{project.project_id}")
        )
        
        bot.reply_to(message, text, parse_mode='Markdown', reply_markup=markup)
        
    except Exception as e:
        logger.error(f"Failed to create project: {e}")
        bot.reply_to(message, "❌ فشل في إنشاء المشروع. حاول مرة أخرى.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("upload_"))
def handle_upload_request(call):
    """طلب رفع ملفات"""
    project_id = call.data.split("_")[1]
    project = db.get_project(project_id)
    
    if not project:
        bot.answer_callback_query(call.id, "❌ المشروع غير موجود")
        return
    
    bot.edit_message_text(
        f"📁 **رفع ملفات للمشروع: {project.name}**\n\n"
        "أرسل ملف ZIP يحتوي على مشروعك\n"
        "أو أرسل ملف Python واحد (.py)\n\n"
        "💡 **نصائح:**\n"
        "• تأكد من وجود ملف main.py أو app.py\n"
        "• أضف ملف requirements.txt للمكتبات\n"
        "• الحد الأقصى: 50 MB",
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown'
    )
    
    bot.register_next_step_handler(call.message, process_file_upload, project_id)

def process_file_upload(message, project_id):
    """معالجة رفع الملف"""
    if not message.document:
        bot.reply_to(message, "❌ يرجى إرسال ملف صالح")
        return
    
    file_info = bot.get_file(message.document.file_id)
    file_size = message.document.file_size
    
    # التحقق من حجم الملف
    max_size = 50 * 1024 * 1024  # 50 MB
    if file_size > max_size:
        bot.reply_to(message, "❌ حجم الملف كبير جداً (الحد الأقصى 50 MB)")
        return
    
    # تنزيل الملف
    try:
        downloaded_file = bot.download_file(file_info.file_path)
        temp_path = f"/tmp/{project_id}_{message.document.file_name}"
        
        with open(temp_path, 'wb') as f:
            f.write(downloaded_file)
        
        # نشر المشروع
        project = db.get_project(project_id)
        loading_msg = bot.reply_to(message, "🔄 جاري نشر المشروع...")
        
        success = hosting.deploy_project(project, temp_path)
        
        if success:
            bot.edit_message_text(
                f"✅ **تم نشر المشروع بنجاح!**\n\n"
                f"🌐 موقعك: http://{project.domain}\n"
                f"🚀 المشروع نشط الآن!",
                loading_msg.chat.id,
                loading_msg.message_id,
                parse_mode='Markdown',
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("🌐 فتح الموقع", url=f"http://{project.domain}"),
                    types.InlineKeyboardButton("👀 عرض المشروع", callback_data=f"project_{project_id}")
                )
            )
        else:
            bot.edit_message_text(
                "❌ فشل في نشر المشروع\n"
                "تحقق من الملفات وحاول مرة أخرى",
                loading_msg.chat.id,
                loading_msg.message_id
            )
        
        # حذف الملف المؤقت
        os.remove(temp_path)
        
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        bot.reply_to(message, "❌ فشل في رفع الملف")

@bot.callback_query_handler(func=lambda call: call.data.startswith("start_"))
def handle_start_project(call):
    """تشغيل المشروع"""
    project_id = call.data.split("_")[1]
    project = db.get_project(project_id)
    
    if not project:
        bot.answer_callback_query(call.id, "❌ المشروع غير موجود")
        return
    
    # التحقق من ملكية المشروع
    if project.user_id != call.from_user.id:
        bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
        return
    
    success = hosting.deploy_project(project)
    
    if success:
        bot.answer_callback_query(call.id, "✅ تم بدء تشغيل المشروع")
        # تحديث عرض المشروع
        handle_project_details(call)
    else:
        bot.answer_callback_query(call.id, "❌ فشل في تشغيل المشروع")

@bot.callback_query_handler(func=lambda call: call.data.startswith("stop_"))
def handle_stop_project(call):
    """إيقاف المشروع"""
    project_id = call.data.split("_")[1]
    project = db.get_project(project_id)
    
    if not project:
        bot.answer_callback_query(call.id, "❌ المشروع غير موجود")
        return
    
    if project.user_id != call.from_user.id:
        bot.answer_callback_query(call.id, "❌ ليس لديك صلاحية")
        return
    
    success = hosting.stop_project(project_id)
    
    if success:
        bot.answer_callback_query(call.id, "✅ تم إيقاف المشروع")
        handle_project_details(call)
    else:
        bot.answer_callback_query(call.id, "❌ فشل في إيقاف المشروع")

@bot.callback_query_handler(func=lambda call: call.data == "stats")
def handle_stats(call):
    """عرض الإحصائيات"""
    user_id = call.from_user.id
    user = db.get_user(user_id)
    projects = db.get_user_projects(user_id)
    
    # حساب الإحصائيات
    total_storage = sum(p.storage_used for p in projects)
    total_bandwidth = sum(p.bandwidth_used for p in projects)
    active_projects = len([p for p in projects if p.status == ProjectStatus.ACTIVE])
    
    # حدود الاشتراك
    if user.subscription_type == SubscriptionType.FREE:
        storage_limit = MAX_STORAGE_FREE
        bandwidth_limit = MAX_BANDWIDTH_FREE
        projects_limit = 1
    else:
        storage_limit = MAX_STORAGE_PREMIUM
        bandwidth_limit = MAX_BANDWIDTH_PREMIUM
        projects_limit = 10
    
    text = f"""
📊 **إحصائياتك**

👤 **المستخدم:**
• الاشتراك: {user.subscription_type.value.title()}
• تاريخ التسجيل: {user.created_at.strftime('%Y-%m-%d')}

📈 **الاستخدام:**
• المشاريع: {len(projects)}/{projects_limit}
• المشاريع النشطة: {active_projects}
• المساحة: {total_storage}/{storage_limit} MB
• عرض النطاق: {total_bandwidth}/{bandwidth_limit} MB

⏰ **هذا الشهر:**
• الزيارات: --
• وقت التشغيل: --
"""
    
    if user.subscription_expires:
        days_left = (user.subscription_expires - datetime.now()).days
        text += f"\n⏳ **الاشتراك:** ينتهي خلال {days_left} يوم"
    
    markup = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("🔄 تحديث", callback_data="stats"),
        types.InlineKeyboardButton("🔙 العودة", callback_data="back_to_main")
    )
    
    bot.edit_message_text(
        text, call.message.chat.id, call.message.message_id,
        parse_mode='Markdown', reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "upgrade")
def handle_upgrade(call):
    """عرض خيارات الترقية"""
    text = """
💎 **ترقية حسابك**

🆓 **المجاني (حالي):**
• مشروع واحد
• 500 MB مساحة
• 1 GB عرض نطاق شهرياً
• نطاق فرعي

💎 **المميز ($5/شهر):**
• 10 مشاريع
• 5 GB مساحة
• 50 GB عرض نطاق شهرياً
• SSL مجاني
• دعم أولوية

🏢 **المؤسسي ($20/شهر):**
• مشاريع غير محدودة
• 50 GB مساحة
• 500 GB عرض نطاق شهرياً
• نطاق مخصص
• دعم 24/7
• نسخ احتياطي يومي
"""
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💎 مميز", callback_data="buy_premium"),
        types.InlineKeyboardButton("🏢 مؤسسي", callback_data="buy_enterprise")
    )
    markup.add(
        types.InlineKeyboardButton("🔙 العودة", callback_data="back_to_main")
    )
    
    bot.edit_message_text(
        text, call.message.chat.id, call.message.message_id,
        parse_mode='Markdown', reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def handle_purchase(call):
    """معالجة الشراء"""
    subscription_type = call.data.split("_")[1]
    
    if subscription_type == "premium":
        sub_type = SubscriptionType.PREMIUM
        price = 5.0
        name = "المميز"
    else:
        sub_type = SubscriptionType.ENTERPRISE
        price = 20.0
        name = "المؤسسي"
    
    text = f"""
💳 **اشتراك {name}**

💰 السعر: ${price}/شهر

📅 اختر مدة الاشتراك:
"""
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    for months in [1, 3, 6, 12]:
        total = price * months
        discount = ""
        if months >= 6:
            discount = " (خصم 10%)"
            total *= 0.9
        elif months >= 12:
            discount = " (خصم 20%)"
            total *= 0.8
        
        markup.add(types.InlineKeyboardButton(
            f"{months} شهر - ${total:.2f}{discount}",
            callback_data=f"pay_{subscription_type}_{months}"
        ))
    
    markup.add(types.InlineKeyboardButton("🔙 العودة", callback_data="upgrade"))
    
    bot.edit_message_text(
        text, call.message.chat.id, call.message.message_id,
        parse_mode='Markdown', reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def handle_back_to_main(call):
    """العودة للقائمة الرئيسية"""
    user = db.get_user(call.from_user.id)
    
    welcome_text = f"""
🚀 **خدمة الاستضافة المتقدمة**

📊 **حسابك:**
• الاشتراك: {user.subscription_type.value.title()}
• المشاريع: {user.projects_count}
• المساحة: {user.storage_used} MB

ماذا تريد أن تفعل؟
"""
    
    markup = create_main_menu(user)
    bot.edit_message_text(
        welcome_text, call.message.chat.id, call.message.message_id,
        parse_mode='Markdown', reply_markup=markup
    )

# ======= النظام الإداري ======= #

@bot.callback_query_handler(func=lambda call: call.data == "admin_panel")
def handle_admin_panel(call):
    """لوحة الإدارة"""
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ غير مصرح")
        return
    
    # إحصائيات النظام
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM projects')
    total_projects = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM projects WHERE status = ?', (ProjectStatus.ACTIVE.value,))
    active_projects = cursor.fetchone()[0]
    
    conn.close()
    
    # معلومات الخادم
    cpu_percent = psutil.cpu_percent()
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    text = f"""
⚙️ **لوحة الإدارة**

👥 **المستخدمين:**
• إجمالي المستخدمين: {total_users}
• مشاريع إجمالية: {total_projects}
• مشاريع نشطة: {active_projects}

🖥️ **الخادم:**
• المعالج: {cpu_percent}%
• الذاكرة: {memory.percent}%
• القرص: {disk.percent}%

💾 **الموارد:**
• الذاكرة المستخدمة: {memory.used // (1024**3)} GB
• المساحة المتاحة: {disk.free // (1024**3)} GB
"""
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("👥 إدارة المستخدمين", callback_data="admin_users"),
        types.InlineKeyboardButton("🚀 إدارة المشاريع", callback_data="admin_projects")
    )
    markup.add(
        types.InlineKeyboardButton("📊 التقارير", callback_data="admin_reports"),
        types.InlineKeyboardButton("⚙️ إعدادات النظام", callback_data="admin_settings")
    )
    markup.add(
        types.InlineKeyboardButton("🔙 العودة", callback_data="back_to_main")
    )
    
    bot.edit_message_text(
        text, call.message.chat.id, call.message.message_id,
        parse_mode='Markdown', reply_markup=markup
    )

# ======= مراقبة النظام ======= #

def system_monitor():
    """مراقب النظام"""
    while True:
        try:
            # فحص المشاريع النشطة
            for project_id, process in list(hosting.running_processes.items()):
                if process.poll() is not None:
                    # المشروع متوقف
                    hosting._update_project_status(project_id, ProjectStatus.ERROR)
                    del hosting.running_processes[project_id]
                    logger.warning(f"Project {project_id} stopped unexpectedly")
            
            # تنظيف الملفات المؤقتة
            temp_files = [f for f in os.listdir('/tmp') if f.startswith('hosting_')]
            for temp_file in temp_files:
                temp_path = os.path.join('/tmp', temp_file)
                if os.path.getctime(temp_path) < time.time() - 3600:  # أقدم من ساعة
                    os.remove(temp_path)
            
            time.sleep(60)  # فحص كل دقيقة
            
        except Exception as e:
            logger.error(f"System monitor error: {e}")
            time.sleep(60)

# ======= مهام مجدولة ======= #

def reset_monthly_usage():
    """إعادة تعيين الاستخدام الشهري"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute('UPDATE users SET bandwidth_used = 0')
    cursor.execute('UPDATE projects SET bandwidth_used = 0')
    
    conn.commit()
    conn.close()
    
    logger.info("Monthly usage reset completed")

def backup_database():
    """نسخ احتياطي لقاعدة البيانات"""
    backup_path = f"backup_hosting_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(DATABASE_PATH, backup_path)
    logger.info(f"Database backup created: {backup_path}")

# جدولة المهام
schedule.every().month.do(reset_monthly_usage)
schedule.every().day.at("02:00").do(backup_database)

def run_scheduler():
    """تشغيل جدولة المهام"""
    while True:
        schedule.run_pending()
        time.sleep(60)

# ======= معالج الأخطاء ======= #

@bot.message_handler(func=lambda message: True)
def handle_unknown_message(message):
    """معالج الرسائل غير المعروفة"""
    user = db.get_user(message.from_user.id)
    if not user:
        bot.reply_to(message, "👋 أهلاً! استخدم /start للبدء")
        return
    
    bot.reply_to(
        message,
        "🤔 لم أفهم هذه الرسالة\n"
        "استخدم الأزرار في القائمة الرئيسية",
        reply_markup=create_main_menu(user)
    )

# ======= تشغيل البوت ======= #

def main():
    """الدالة الرئيسية"""
    logger.info("🚀 Starting Hosting Bot...")
    
    # إنشاء مجلدات النظام
    os.makedirs(HOSTING_ROOT, exist_ok=True)
    os.makedirs('/tmp', exist_ok=True)
    
    # بدء مراقب النظام
    monitor_thread = threading.Thread(target=system_monitor, daemon=True)
    monitor_thread.start()
    
    # بدء جدولة المهام
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # إرسال إشعار للمشرفين
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(
                admin_id,
                "🚀 **تم بدء تشغيل نظام الاستضافة**\n\n"
                f"⏰ الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"🖥️ الخادم: جاهز\n"
                f"📊 قاعدة البيانات: متصلة",
                parse_mode='Markdown'
            )
        except:
            pass
    
    logger.info("✅ Hosting Bot started successfully")
    
    # تشغيل البوت
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        logger.error(f"Bot polling error: {e}")
        time.sleep(5)
        main()  # إعادة التشغيل

if __name__ == "__main__":
    main()
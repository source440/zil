# 🚀 بوت استضافة تليجرام المتقدم

## 📋 نظرة عامة

بوت تليجرام شامل لخدمات الاستضافة يوفر منصة متكاملة لاستضافة مشاريع Python و Node.js مع نظام إدارة متقدم وخطط اشتراك متنوعة.

## ✨ الميزات الرئيسية

### 🏗️ **إدارة المشاريع**
- رفع ونشر مشاريع Python/Node.js تلقائياً
- نطاقات فرعية مجانية لكل مشروع
- تثبيت المتطلبات تلقائياً من requirements.txt
- إدارة متقدمة لحالة المشاريع (تشغيل/إيقاف)
- مراقبة استخدام الموارد

### 👥 **إدارة المستخدمين**
- نظام اشتراكات متدرج (مجاني/مميز/مؤسسي)
- تتبع استخدام المساحة وعرض النطاق
- إحصائيات مفصلة لكل مستخدم
- نظام نقاط وحدود الاستخدام

### 💳 **نظام المدفوعات**
- دعم مدفوعات Telegram
- خطط اشتراك مرنة
- خصومات للاشتراكات طويلة المدى
- فواتير ومتابعة المدفوعات

### 🛡️ **الأمان والمراقبة**
- مراقبة مستمرة للخادم والمشاريع
- نسخ احتياطية تلقائية
- تنبيهات عند تجاوز حدود الموارد
- سجلات مفصلة لجميع العمليات

### ⚙️ **لوحة إدارة متقدمة**
- إحصائيات شاملة للنظام
- إدارة المستخدمين والمشاريع
- مراقبة استخدام الخادم
- تقارير مفصلة

## 📦 التثبيت والإعداد

### 1. متطلبات النظام

```bash
# نظام التشغيل
Ubuntu 20.04+ أو CentOS 8+

# Python
Python 3.8 أو أحدث

# خدمات النظام
nginx
systemd
git
```

### 2. تثبيت التبعيات

```bash
# تحديث النظام
sudo apt update && sudo apt upgrade -y

# تثبيت Python و pip
sudo apt install python3 python3-pip python3-venv -y

# تثبيت nginx
sudo apt install nginx -y

# تثبيت git
sudo apt install git -y
```

### 3. إعداد المشروع

```bash
# استنساخ المشروع
git clone https://github.com/your-repo/hosting-bot
cd hosting-bot

# إنشاء بيئة افتراضية
python3 -m venv venv
source venv/bin/activate

# تثبيت المكتبات المطلوبة
pip install -r hosting_requirements.txt

# نسخ ملف الإعدادات
cp hosting_env_example.txt .env

# تحرير الإعدادات
nano .env
```

### 4. إعداد قاعدة البيانات

```bash
# إنشاء مجلد قاعدة البيانات
mkdir -p data

# تشغيل البوت لإنشاء الجداول (سيتوقف بعد إنشائها)
python hosting_bot.py
```

## ⚙️ الإعداد المتقدم

### إعداد Nginx

```bash
# إنشاء ملف إعداد Nginx الأساسي
sudo nano /etc/nginx/sites-available/hosting-bot

# محتوى الملف:
server {
    listen 80 default_server;
    server_name _;
    
    # Proxy headers
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    # Default location
    location / {
        return 404;
    }
}

# تفعيل الإعدادات
sudo ln -s /etc/nginx/sites-available/hosting-bot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### إعداد خدمة النظام

```bash
# إنشاء ملف الخدمة
sudo nano /etc/systemd/system/hosting-bot.service

# محتوى الملف:
[Unit]
Description=Hosting Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/path/to/hosting-bot
Environment=PATH=/path/to/hosting-bot/venv/bin
ExecStart=/path/to/hosting-bot/venv/bin/python hosting_bot.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target

# تفعيل الخدمة
sudo systemctl daemon-reload
sudo systemctl enable hosting-bot
sudo systemctl start hosting-bot
```

### إعداد Firewall

```bash
# تفعيل UFW
sudo ufw enable

# السماح بـ SSH
sudo ufw allow ssh

# السماح بـ HTTP/HTTPS
sudo ufw allow 80
sudo ufw allow 443

# السماح بنطاق منافذ المشاريع
sudo ufw allow 8000:9000/tcp

# فحص الحالة
sudo ufw status
```

## 🔧 الاستخدام

### للمستخدمين

#### البدء
1. ابدأ محادثة مع البوت
2. اضغط `/start`
3. اختر "➕ مشروع جديد"
4. أدخل اسم المشروع

#### رفع المشروع
1. اختر المشروع من "🚀 مشاريعي"
2. اضغط "📁 رفع ملفات"
3. أرسل ملف ZIP أو ملف Python
4. انتظر النشر التلقائي

#### إدارة المشروع
- **▶️ تشغيل**: بدء تشغيل المشروع
- **⏹️ إيقاف**: إيقاف المشروع
- **🔄 إعادة نشر**: إعادة نشر بالملفات الحالية
- **🌐 فتح الموقع**: زيارة المشروع

### للمشرفين

#### لوحة الإدارة
```
/start → ⚙️ لوحة الإدارة
```

#### الأوامر المباشرة
- `/admin` - لوحة الإدارة
- `/users` - إدارة المستخدمين
- `/projects` - إدارة المشاريع
- `/stats` - إحصائيات النظام
- `/backup` - إنشاء نسخة احتياطية

## 📊 خطط الاشتراك

### 🆓 المجاني
```
• مشروع واحد
• 500 MB مساحة تخزين
• 1 GB عرض نطاق شهرياً
• نطاق فرعي مجاني
• دعم مجتمعي
```

### 💎 المميز ($5/شهر)
```
• 10 مشاريع
• 5 GB مساحة تخزين
• 50 GB عرض نطاق شهرياً
• شهادة SSL مجانية
• دعم أولوية
• إحصائيات متقدمة
```

### 🏢 المؤسسي ($20/شهر)
```
• مشاريع غير محدودة
• 50 GB مساحة تخزين
• 500 GB عرض نطاق شهرياً
• نطاق مخصص
• دعم 24/7
• نسخ احتياطية يومية
• API مخصص
```

## 🛠️ التخصيص والتطوير

### إضافة ميزات جديدة

```python
# مثال: إضافة دعم لـ Node.js
def deploy_nodejs_project(self, project: Project, file_path: str):
    project_path = os.path.join(HOSTING_ROOT, project.project_id)
    
    # البحث عن package.json
    package_json = os.path.join(project_path, 'package.json')
    if os.path.exists(package_json):
        # تثبيت npm packages
        subprocess.run(['npm', 'install'], cwd=project_path)
        
        # تحديد أمر التشغيل
        with open(package_json, 'r') as f:
            package_data = json.load(f)
            start_command = package_data.get('scripts', {}).get('start', 'node index.js')
```

### إضافة موفر دفع جديد

```python
class PayPalPaymentProvider:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
    
    def create_payment(self, amount, currency='USD'):
        # تنفيذ منطق PayPal
        pass
    
    def verify_payment(self, payment_id):
        # التحقق من الدفعة
        pass
```

## 📊 المراقبة والصيانة

### فحص حالة النظام

```bash
# حالة البوت
sudo systemctl status hosting-bot

# حالة nginx
sudo systemctl status nginx

# استخدام الموارد
htop

# مساحة القرص
df -h

# سجلات البوت
tail -f hosting_bot.log

# سجلات nginx
tail -f /var/log/nginx/error.log
```

### النسخ الاحتياطية

```bash
# نسخة احتياطية يدوية لقاعدة البيانات
sqlite3 hosting_bot.db ".backup backup_$(date +%Y%m%d_%H%M%S).db"

# نسخة احتياطية للمشاريع
tar -czf projects_backup_$(date +%Y%m%d_%H%M%S).tar.gz /var/hosting/

# جدولة النسخ الاحتياطية
# إضافة إلى crontab
0 2 * * * /path/to/backup_script.sh
```

### تحديث النظام

```bash
# إيقاف البوت
sudo systemctl stop hosting-bot

# سحب أحدث التحديثات
git pull origin main

# تحديث المكتبات
pip install -r hosting_requirements.txt --upgrade

# تشغيل البوت
sudo systemctl start hosting-bot
```

## 🐞 استكشاف الأخطاء

### مشاكل شائعة

#### البوت لا يستجيب
```bash
# فحص حالة الخدمة
sudo systemctl status hosting-bot

# فحص السجلات
journalctl -u hosting-bot -f

# إعادة تشغيل
sudo systemctl restart hosting-bot
```

#### المشاريع لا تعمل
```bash
# فحص nginx
sudo nginx -t
sudo systemctl status nginx

# فحص المنافذ
netstat -tulpn | grep :80

# فحص ملفات المشاريع
ls -la /var/hosting/
```

#### قاعدة البيانات معطلة
```bash
# فحص سلامة قاعدة البيانات
sqlite3 hosting_bot.db "PRAGMA integrity_check;"

# إصلاح قاعدة البيانات
sqlite3 hosting_bot.db "VACUUM;"
```

## 🔐 الأمان

### أفضل الممارسات

1. **تحديثات منتظمة**
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

2. **تشفير قاعدة البيانات**
   ```python
   # استخدام SQLCipher
   pip install pysqlcipher3
   ```

3. **حماية الملفات**
   ```bash
   # تعيين صلاحيات محدودة
   chmod 750 /var/hosting/
   chown -R hosting-user:hosting-group /var/hosting/
   ```

4. **تفعيل SSL**
   ```bash
   # تثبيت Let's Encrypt
   sudo apt install certbot python3-certbot-nginx
   sudo certbot --nginx
   ```

## 📞 الدعم الفني

### التواصل
- 🐛 **الأخطاء**: افتح Issue على GitHub
- 💬 **الدعم**: تواصل عبر Telegram
- 📧 **التعاون**: للشراكات التجارية

### المساهمة
1. Fork المستودع
2. إنشاء branch للميزة الجديدة
3. إرسال Pull Request
4. مراجعة الكود

### الترخيص
هذا المشروع مرخص تحت [MIT License](LICENSE)

---

## 🚀 ابدأ الآن!

```bash
# نسخ المشروع
git clone https://github.com/your-repo/hosting-bot
cd hosting-bot

# الإعداد السريع
chmod +x quick_setup.sh
./quick_setup.sh

# تشغيل البوت
python hosting_bot.py
```

**مرحباً بك في مستقبل الاستضافة! 🎉**
#!/bin/bash

# 🚀 سكريپت الإعداد السريع لبوت الاستضافة
# Quick Setup Script for Hosting Bot

set -e

# الألوان للإخراج
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # بدون لون

# دالة طباعة ملونة
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# فحص إذا كان النظام Ubuntu/Debian
check_system() {
    if [[ ! -f /etc/debian_version ]]; then
        print_error "هذا السكريپت يدعم Ubuntu/Debian فقط"
        exit 1
    fi
    
    print_success "النظام متوافق"
}

# فحص صلاحيات المستخدم
check_permissions() {
    if [[ $EUID -eq 0 ]]; then
        print_error "لا تشغل هذا السكريپت كـ root"
        print_warning "استخدم مستخدم عادي مع sudo"
        exit 1
    fi
    
    # فحص إذا كان sudo متاحاً
    if ! sudo -n true 2>/dev/null; then
        print_error "تحتاج صلاحيات sudo"
        exit 1
    fi
    
    print_success "الصلاحيات صحيحة"
}

# تثبيت التبعيات الأساسية
install_dependencies() {
    print_status "تحديث النظام وتثبيت التبعيات..."
    
    sudo apt update && sudo apt upgrade -y
    
    # تثبيت الحزم المطلوبة
    sudo apt install -y \
        python3 \
        python3-pip \
        python3-venv \
        nginx \
        git \
        curl \
        wget \
        htop \
        ufw \
        sqlite3 \
        build-essential \
        python3-dev
    
    print_success "تم تثبيت التبعيات بنجاح"
}

# إعداد Python Environment
setup_python_env() {
    print_status "إعداد البيئة الافتراضية لـ Python..."
    
    # إنشاء البيئة الافتراضية
    python3 -m venv venv
    
    # تفعيل البيئة الافتراضية
    source venv/bin/activate
    
    # تحديث pip
    pip install --upgrade pip
    
    # تثبيت المكتبات المطلوبة
    if [[ -f hosting_requirements.txt ]]; then
        pip install -r hosting_requirements.txt
        print_success "تم تثبيت مكتبات Python"
    else
        print_warning "لم يتم العثور على hosting_requirements.txt"
    fi
}

# إعداد ملف البيئة
setup_env_file() {
    print_status "إعداد ملف المتغيرات البيئية..."
    
    if [[ -f hosting_env_example.txt ]]; then
        cp hosting_env_example.txt .env
        print_success "تم إنشاء ملف .env"
        print_warning "يرجى تحرير ملف .env وإضافة البيانات المطلوبة"
    else
        print_error "لم يتم العثور على hosting_env_example.txt"
    fi
}

# إعداد المجلدات
setup_directories() {
    print_status "إنشاء المجلدات المطلوبة..."
    
    # مجلد الاستضافة
    sudo mkdir -p /var/hosting
    sudo chown $USER:$USER /var/hosting
    sudo chmod 755 /var/hosting
    
    # مجلد النسخ الاحتياطية
    sudo mkdir -p /var/backups/hosting
    sudo chown $USER:$USER /var/backups/hosting
    
    # مجلد السجلات
    mkdir -p logs
    
    # مجلد قاعدة البيانات
    mkdir -p data
    
    print_success "تم إنشاء المجلدات"
}

# إعداد Nginx الأساسي
setup_nginx() {
    print_status "إعداد Nginx..."
    
    # إنشاء ملف إعداد Nginx
    sudo tee /etc/nginx/sites-available/hosting-bot > /dev/null <<EOF
server {
    listen 80 default_server;
    server_name _;
    
    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    
    # Proxy headers
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
    
    # Default location
    location / {
        return 404;
    }
    
    # Health check
    location /health {
        access_log off;
        return 200 "OK";
        add_header Content-Type text/plain;
    }
}
EOF
    
    # تفعيل الموقع
    sudo ln -sf /etc/nginx/sites-available/hosting-bot /etc/nginx/sites-enabled/
    
    # إزالة الموقع الافتراضي
    sudo rm -f /etc/nginx/sites-enabled/default
    
    # فحص إعدادات nginx
    if sudo nginx -t; then
        sudo systemctl restart nginx
        sudo systemctl enable nginx
        print_success "تم إعداد Nginx بنجاح"
    else
        print_error "خطأ في إعدادات Nginx"
        exit 1
    fi
}

# إعداد Firewall
setup_firewall() {
    print_status "إعداد Firewall..."
    
    # تفعيل UFW
    sudo ufw --force enable
    
    # السماح بـ SSH
    sudo ufw allow ssh
    
    # السماح بـ HTTP/HTTPS
    sudo ufw allow 80
    sudo ufw allow 443
    
    # السماح بنطاق منافذ المشاريع
    sudo ufw allow 8000:9000/tcp
    
    print_success "تم إعداد Firewall"
}

# إعداد خدمة النظام
setup_systemd_service() {
    print_status "إعداد خدمة النظام..."
    
    CURRENT_DIR=$(pwd)
    USER_NAME=$(whoami)
    
    # إنشاء ملف الخدمة
    sudo tee /etc/systemd/system/hosting-bot.service > /dev/null <<EOF
[Unit]
Description=Hosting Bot Service
After=network.target nginx.service
Wants=nginx.service

[Service]
Type=simple
User=$USER_NAME
Group=$USER_NAME
WorkingDirectory=$CURRENT_DIR
Environment=PATH=$CURRENT_DIR/venv/bin
ExecStart=$CURRENT_DIR/venv/bin/python hosting_bot.py
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$CURRENT_DIR /var/hosting /var/backups/hosting

[Install]
WantedBy=multi-user.target
EOF
    
    # إعادة تحميل systemd
    sudo systemctl daemon-reload
    
    # تفعيل الخدمة
    sudo systemctl enable hosting-bot
    
    print_success "تم إعداد خدمة النظام"
}

# إعداد قاعدة البيانات
setup_database() {
    print_status "إعداد قاعدة البيانات..."
    
    # تشغيل سكريپت Python لإنشاء قاعدة البيانات
    source venv/bin/activate
    python3 -c "
from hosting_bot import DatabaseManager
import os

# تحديد مسار قاعدة البيانات
db_path = os.getenv('DATABASE_PATH', 'hosting_bot.db')

# إنشاء قاعدة البيانات
db = DatabaseManager(db_path)
print('تم إنشاء قاعدة البيانات بنجاح')
"
    
    print_success "تم إعداد قاعدة البيانات"
}

# إنشاء سكريپت النسخ الاحتياطي
create_backup_script() {
    print_status "إنشاء سكريپت النسخ الاحتياطي..."
    
    cat > backup_script.sh << 'EOF'
#!/bin/bash

# سكريپت النسخ الاحتياطي لبوت الاستضافة

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/var/backups/hosting"
PROJECT_DIR=$(dirname "$(readlink -f "$0")")

# إنشاء مجلد النسخة الاحتياطية
mkdir -p "$BACKUP_DIR"

# نسخ احتياطية لقاعدة البيانات
echo "إنشاء نسخة احتياطية لقاعدة البيانات..."
sqlite3 "$PROJECT_DIR/hosting_bot.db" ".backup $BACKUP_DIR/db_backup_$DATE.db"

# نسخ احتياطية للمشاريع
echo "إنشاء نسخة احتياطية للمشاريع..."
tar -czf "$BACKUP_DIR/projects_backup_$DATE.tar.gz" -C /var/hosting .

# نسخ احتياطية لإعدادات البوت
echo "إنشاء نسخة احتياطية للإعدادات..."
tar -czf "$BACKUP_DIR/config_backup_$DATE.tar.gz" -C "$PROJECT_DIR" .env hosting_bot.py

# حذف النسخ الاحتياطية القديمة (أكثر من 30 يوم)
find "$BACKUP_DIR" -name "*backup*" -mtime +30 -delete

echo "تم إنشاء النسخ الاحتياطية بنجاح في $BACKUP_DIR"
EOF
    
    chmod +x backup_script.sh
    
    # إضافة مهمة cron للنسخ الاحتياطي اليومي
    (crontab -l 2>/dev/null; echo "0 2 * * * $(pwd)/backup_script.sh") | crontab -
    
    print_success "تم إنشاء سكريپت النسخ الاحتياطي"
}

# فحص التثبيت
verify_installation() {
    print_status "فحص التثبيت..."
    
    # فحص Python
    if source venv/bin/activate && python3 -c "import telebot, sqlite3, psutil"; then
        print_success "مكتبات Python متاحة"
    else
        print_error "مشكلة في مكتبات Python"
        return 1
    fi
    
    # فحص Nginx
    if sudo systemctl is-active --quiet nginx; then
        print_success "Nginx يعمل بشكل صحيح"
    else
        print_error "مشكلة في Nginx"
        return 1
    fi
    
    # فحص ملف .env
    if [[ -f .env ]]; then
        print_success "ملف .env موجود"
    else
        print_warning "ملف .env غير موجود - تحتاج لإنشائه"
    fi
    
    # فحص المجلدات
    if [[ -d /var/hosting ]]; then
        print_success "مجلد الاستضافة جاهز"
    else
        print_error "مجلد الاستضافة غير موجود"
        return 1
    fi
    
    print_success "التحقق من التثبيت اكتمل بنجاح"
}

# عرض الخطوات التالية
show_next_steps() {
    cat << EOF

${GREEN}🎉 تم الإعداد بنجاح! 🎉${NC}

${YELLOW}الخطوات التالية:${NC}

1. ${BLUE}تحرير ملف الإعدادات:${NC}
   nano .env
   
   ${YELLOW}يجب تعديل هذه المتغيرات:${NC}
   - BOT_TOKEN (من @BotFather)
   - ADMIN_IDS (معرف المشرف)
   - SERVER_IP (عنوان IP للخادم)

2. ${BLUE}تشغيل البوت:${NC}
   sudo systemctl start hosting-bot
   
3. ${BLUE}مراقبة السجلات:${NC}
   sudo journalctl -u hosting-bot -f
   
4. ${BLUE}فحص حالة الخدمة:${NC}
   sudo systemctl status hosting-bot

${YELLOW}أوامر مفيدة:${NC}

- ${BLUE}إيقاف البوت:${NC} sudo systemctl stop hosting-bot
- ${BLUE}إعادة تشغيل:${NC} sudo systemctl restart hosting-bot
- ${BLUE}فحص Nginx:${NC} sudo nginx -t
- ${BLUE}نسخة احتياطية:${NC} ./backup_script.sh

${GREEN}مرحباً بك في نظام الاستضافة المتقدم! 🚀${NC}

EOF
}

# الدالة الرئيسية
main() {
    echo -e "${BLUE}"
    cat << "EOF"
    ╔═══════════════════════════════════════╗
    ║     🚀 بوت الاستضافة المتقدم 🚀      ║
    ║           Hosting Bot Setup           ║
    ╚═══════════════════════════════════════╝
EOF
    echo -e "${NC}"
    
    print_status "بدء عملية الإعداد..."
    
    # فحص النظام والصلاحيات
    check_system
    check_permissions
    
    # تثبيت وإعداد المكونات
    install_dependencies
    setup_directories
    setup_python_env
    setup_env_file
    setup_nginx
    setup_firewall
    setup_systemd_service
    setup_database
    create_backup_script
    
    # فحص التثبيت
    if verify_installation; then
        show_next_steps
    else
        print_error "فشل في التحقق من التثبيت"
        exit 1
    fi
}

# تشغيل الدالة الرئيسية
main "$@"
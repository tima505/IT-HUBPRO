#!/bin/bash
# =============================================================================
#  Deploy — IT HubPro (Django + DRF + Vue 3)
#  Сервер:  root@84.247.131.147   (тот же, где OtyrarMebel и др.)
#  Домен:   ithubpro.inbrain.kz
#
#  БЕЗОПАСНОСТЬ СОСЕДНИХ САЙТОВ (важно!):
#   • Всё кладётся в ОТДЕЛЬНУЮ папку ($REMOTE_DIR), под ОТДЕЛЬНЫМ systemd-сервисом
#     ($SERVICE), на ОТДЕЛЬНОМ порту ($APP_PORT), с ОТДЕЛЬНЫМ nginx-конфигом.
#   • nginx: добавляется новый файл в sites-available + симлинк. Общие конфиги и
#     чужие виртуалхосты НЕ трогаются. Маршрутизация идёт по server_name.
#   • Только `apt-get install` (+ при необходимости PPA deadsnakes для python3.12).
#     Никаких remove/purge/autoremove/upgrade — установленное соседями не меняется.
#   • Перед применением nginx — `nginx -t`, затем мягкий reload (чужие сайты живут).
#   • База — SQLite (файл внутри $REMOTE_DIR), общий Postgres не затрагивается.
#   • db.sqlite3 исключён из rsync — прод-данные никогда не перезаписываются.
#
#  ТРЕБОВАНИЯ ЛОКАЛЬНО: bash + ssh + rsync + node/npm (Mac/Linux/WSL или Git Bash с rsync).
#  Запуск:  bash deploy.sh
# =============================================================================
set -e

# ----------------------------- Настройки -------------------------------------
SERVER="root@84.247.131.147"
DOMAIN="ithubpro.inbrain.kz"
REMOTE_DIR="/home/it_hubpro"
APP_PORT="8020"                 # порт gunicorn (127.0.0.1). Должен быть свободен.
SERVICE="it_hubpro-backend"     # имя systemd-сервиса (уникальное)
NGINX_SITE="it_hubpro"          # имя файла в /etc/nginx/sites-available
CERT_EMAIL="admin@inbrain.kz"   # e-mail для Let's Encrypt (уведомления о продлении)
INSTALL_PYTHON312="true"        # если на сервере нет Python 3.12 — доустановить через deadsnakes (только ДОБАВляет)

LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GITHUB_REPO="https://github.com/tima505/IT-HUBPRO.git"

# =============================================================================
echo "=== 1/6: Сборка фронтенда локально ==="
cd "$LOCAL_DIR/frontend"
if [ ! -d node_modules ]; then npm install; fi
npm run build   # axios в api.js использует относительный /api → сборка не зависит от домена
echo "Готово → frontend/dist/"

# -----------------------------------------------------------------------------
echo ""
echo "=== 2/6: Загрузка файлов на сервер (rsync, db.sqlite3 исключён) ==="
rsync -avz \
    --exclude '.git' \
    --exclude '.claude' \
    --exclude 'venv' \
    --exclude 'node_modules' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude 'db.sqlite3' \
    --exclude 'staticfiles' \
    --exclude '.DS_Store' \
    -e ssh \
    "$LOCAL_DIR/" "$SERVER:$REMOTE_DIR/"

# -----------------------------------------------------------------------------
echo ""
echo "=== 3/6: Системные пакеты (только install, без upgrade/remove) ==="
ssh "$SERVER" INSTALL_PYTHON312="$INSTALL_PYTHON312" bash -s <<'REMOTE'
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq

# nginx + certbot (если уже стоят у соседей — apt просто скажет "newest")
apt-get install -y -qq --no-install-recommends nginx certbot python3-certbot-nginx

# Django 6 требует Python >= 3.12. Ищем подходящий, ничего существующего не трогаем.
PYBIN=""
for c in python3.13 python3.12; do command -v "$c" >/dev/null 2>&1 && { PYBIN="$c"; break; }; done

if [ -z "$PYBIN" ]; then
  if [ "$INSTALL_PYTHON312" = "true" ]; then
    echo "Python 3.12+ не найден — доустанавливаю python3.12 (deadsnakes, только ДОБАВляет)."
    apt-get install -y -qq --no-install-recommends software-properties-common
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update -qq
    apt-get install -y -qq --no-install-recommends python3.12 python3.12-venv python3.12-dev
  else
    echo "ОШИБКА: нужен Python 3.12+ (Django 6), а его нет. Поставьте вручную или INSTALL_PYTHON312=true." >&2
    exit 1
  fi
fi
echo "Системные пакеты OK"
REMOTE

# -----------------------------------------------------------------------------
echo ""
echo "=== 4/6: Backend — venv, .env, миграции, статика, супер-админ ==="
ssh "$SERVER" REMOTE_DIR="$REMOTE_DIR" DOMAIN="$DOMAIN" bash -s <<'REMOTE'
set -e
cd "$REMOTE_DIR/backend"

# выбираем интерпретатор (>=3.12)
PYBIN=""
for c in python3.13 python3.12; do command -v "$c" >/dev/null 2>&1 && { PYBIN="$c"; break; }; done

# venv пересоздаём начисто (в отдельной папке проекта — соседей не касается)
rm -rf .venv
"$PYBIN" -m venv .venv
. .venv/bin/activate
pip install --upgrade pip wheel -q
pip install -r requirements.txt -q

# .env создаём только если его ещё нет (идемпотентно, прод-секреты не перезаписываем)
if [ ! -f "$REMOTE_DIR/.env" ]; then
  SECRET=$(openssl rand -hex 32)
  ADMIN_PASS=$(openssl rand -base64 15 | tr -dc 'A-Za-z0-9' | cut -c1-16)
  cat > "$REMOTE_DIR/.env" <<ENVEOF
DJANGO_SECRET_KEY=$SECRET
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=$DOMAIN
DJANGO_CSRF_TRUSTED_ORIGINS=https://$DOMAIN
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_PASSWORD=$ADMIN_PASS
ENVEOF
  chmod 600 "$REMOTE_DIR/.env"
  echo ">>> СОЗДАН .env. Логин: admin | Пароль: $ADMIN_PASS  (сохраните!)"
else
  echo ".env уже существует — оставляю как есть."
fi

# подгружаем переменные для manage.py
set -a; . "$REMOTE_DIR/.env"; set +a

python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py createadmin   # логин/пароль из DJANGO_SUPERUSER_* (без демо-данных)
echo "Backend готов"
REMOTE

# -----------------------------------------------------------------------------
echo ""
echo "=== 5/6: systemd-сервис gunicorn (отдельный юнит) ==="
ssh "$SERVER" REMOTE_DIR="$REMOTE_DIR" APP_PORT="$APP_PORT" SERVICE="$SERVICE" bash -s <<'REMOTE'
set -e
cat > "/etc/systemd/system/$SERVICE.service" <<UNIT
[Unit]
Description=IT HubPro — Django backend (gunicorn)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$REMOTE_DIR/backend
EnvironmentFile=$REMOTE_DIR/.env
ExecStart=$REMOTE_DIR/backend/.venv/bin/gunicorn config.wsgi:application \
    --bind 127.0.0.1:$APP_PORT --workers 3 --timeout 120
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable "$SERVICE"
systemctl restart "$SERVICE"
sleep 2
systemctl --no-pager status "$SERVICE" | head -8 || true
REMOTE

# -----------------------------------------------------------------------------
echo ""
echo "=== 6/6: nginx (новый сайт) + SSL ==="
ssh "$SERVER" REMOTE_DIR="$REMOTE_DIR" DOMAIN="$DOMAIN" APP_PORT="$APP_PORT" \
    NGINX_SITE="$NGINX_SITE" CERT_EMAIL="$CERT_EMAIL" bash -s <<'REMOTE'
set -e
cat > "/etc/nginx/sites-available/$NGINX_SITE" <<NGINX
server {
    listen 80;
    server_name $DOMAIN;
    client_max_body_size 10M;

    # Фронтенд (Vue SPA)
    root $REMOTE_DIR/frontend/dist;
    index index.html;

    # API → gunicorn
    location /api/ {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120;
    }

    # Django-админка → gunicorn
    location /admin/ {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Статика Django-админки (collectstatic)
    location /static/ {
        alias $REMOTE_DIR/backend/staticfiles/;
        access_log off;
        expires 30d;
    }

    # SPA fallback
    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
NGINX

# только добавляем симлинк своего сайта; чужие не трогаем
ln -sf "/etc/nginx/sites-available/$NGINX_SITE" "/etc/nginx/sites-enabled/$NGINX_SITE"

nginx -t                      # проверка конфига (упадёт до перезагрузки, если что-то не так)
systemctl reload nginx        # мягко: открытые соединения соседей не рвутся

# SSL (нужна DNS-запись $DOMAIN → этот сервер). certbot правит только наш site-файл.
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$CERT_EMAIL" --redirect \
  || echo "SSL пропущен: проверьте, что DNS $DOMAIN уже указывает на сервер, затем повторите certbot."
systemctl reload nginx
echo "nginx настроен"
REMOTE

echo ""
echo "============================================================"
echo "  Деплой завершён!"
echo "  Сайт:     https://$DOMAIN"
echo "  Админка:  https://$DOMAIN/admin/"
echo "  Логин супер-админа — 'admin', пароль был показан в шаге 4"
echo "  (или лежит в $REMOTE_DIR/.env на сервере: DJANGO_SUPERUSER_PASSWORD)."
echo ""
echo "  Повторный деплой (обновление кода): просто снова 'bash deploy.sh'."
echo "  .env и база данных при этом сохраняются."
echo "============================================================"

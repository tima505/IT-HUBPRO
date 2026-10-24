#!/bin/bash
# =============================================================================
#  server-deploy.sh — выполняется НА СЕРВЕРЕ (его вызывают deploy.sh / deploy.ps1).
#  Ставит/обновляет IT HubPro строго «додающим» способом. Соседние сайты не трогает:
#   отдельная папка/сервис/порт/nginx-конфиг, только apt-get install, мягкий reload.
#  Файлы проекта уже распакованы в $APP_DIR лаунчером.
# =============================================================================
set -e

DOMAIN="${DOMAIN:-ithubpro.inbrain.kz}"
APP_DIR="${APP_DIR:-/home/it_hubpro}"
APP_PORT="${APP_PORT:-8020}"            # порт gunicorn (127.0.0.1), должен быть свободен
SERVICE="${SERVICE:-it_hubpro-backend}"
# Префикс zz- → nginx читает sites-enabled по алфавиту, наш конфиг грузится ПОСЛЕДНИМ
# и никогда не станет «сайтом по умолчанию» (не перехватит чужие https/IP-запросы).
NGINX_SITE="${NGINX_SITE:-zz-it_hubpro}"
CERT_EMAIL="${CERT_EMAIL:-admin@inbrain.kz}"
INSTALL_PYTHON312="${INSTALL_PYTHON312:-true}"

export DEBIAN_FRONTEND=noninteractive

echo "=== [server] 1/4 Системные пакеты (только недостающие) ==="
# Ставим ТОЛЬКО то, чего нет. Уже установленное не трогаем: «apt-get install nginx»
# при стоящем nginx обновил бы его и перезапустил — это задело бы соседние сайты.
MISSING=""
for pkg in nginx certbot python3-certbot-nginx; do
  dpkg -s "$pkg" >/dev/null 2>&1 || MISSING="$MISSING $pkg"
done
if [ -n "$MISSING" ]; then
  echo "Доустанавливаю:$MISSING"
  apt-get update -qq
  apt-get install -y -qq --no-install-recommends $MISSING
else
  echo "Всё нужное уже установлено — системные пакеты не трогаю."
fi

# Django 6 требует Python >= 3.12. Ищем; ничего существующего не трогаем.
PYBIN=""
for c in python3.13 python3.12; do command -v "$c" >/dev/null 2>&1 && { PYBIN="$c"; break; }; done
if [ -z "$PYBIN" ]; then
  if [ "$INSTALL_PYTHON312" = "true" ]; then
    echo "Python 3.12+ не найден — доустанавливаю python3.12 (deadsnakes, только ДОБАВляет)."
    apt-get install -y -qq --no-install-recommends software-properties-common
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update -qq
    apt-get install -y -qq --no-install-recommends python3.12 python3.12-venv python3.12-dev
    PYBIN=python3.12
  else
    echo "ОШИБКА: нужен Python 3.12+ (Django 6). Поставьте вручную или INSTALL_PYTHON312=true." >&2
    exit 1
  fi
fi

echo "=== [server] 2/4 Backend: venv, .env, миграции, статика, админ ==="
cd "$APP_DIR/backend"
rm -rf .venv
"$PYBIN" -m venv .venv
. .venv/bin/activate
pip install --upgrade pip wheel -q
pip install -r requirements.txt -q

# .env создаём только при первом деплое (секреты/пароль не перезаписываем)
if [ ! -f "$APP_DIR/.env" ]; then
  SECRET=$(openssl rand -hex 32)
  ADMIN_PASS=$(openssl rand -base64 15 | tr -dc 'A-Za-z0-9' | cut -c1-16)
  cat > "$APP_DIR/.env" <<ENVEOF
DJANGO_SECRET_KEY=$SECRET
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=$DOMAIN
DJANGO_CSRF_TRUSTED_ORIGINS=https://$DOMAIN
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_PASSWORD=$ADMIN_PASS
ENVEOF
  chmod 600 "$APP_DIR/.env"
  echo ">>> Создан .env. Логин: admin | Пароль: $ADMIN_PASS  (СОХРАНИТЕ!)"
else
  echo ".env уже существует — оставляю как есть."
fi

set -a; . "$APP_DIR/.env"; set +a

# Копия базы ПЕРЕД миграциями. Хранятся 10 последних: $APP_DIR/backups/
DB_FILE="$APP_DIR/backend/db.sqlite3"
if [ -f "$DB_FILE" ]; then
  mkdir -p "$APP_DIR/backups"
  BACKUP="$APP_DIR/backups/db-$(date +%Y%m%d-%H%M%S).sqlite3"
  cp "$DB_FILE" "$BACKUP"
  echo "Резервная копия базы: $BACKUP"
  ls -1t "$APP_DIR"/backups/db-*.sqlite3 | tail -n +11 | xargs -r rm -f
fi

# Тесты под Django этого сервера — ДО миграций: если что-то несовместимо,
# деплой остановится, а база останется нетронутой (тесты идут на отдельной временной базе).
python manage.py test core --noinput -v 1

python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py createadmin

echo "=== [server] 3/4 systemd-сервис gunicorn ==="
cat > "/etc/systemd/system/$SERVICE.service" <<UNIT
[Unit]
Description=IT HubPro — Django backend (gunicorn)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR/backend
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/backend/.venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:$APP_PORT --workers 3 --timeout 120
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable "$SERVICE" >/dev/null 2>&1 || true
systemctl restart "$SERVICE"

echo "=== [server] 4/4 nginx (отдельный сайт) + SSL ==="
# Миграция со старого имени it_hubpro → zz-it_hubpro (удаляется только НАШ файл).
if [ "$NGINX_SITE" != "it_hubpro" ]; then
  rm -f /etc/nginx/sites-enabled/it_hubpro /etc/nginx/sites-available/it_hubpro
fi

SITE_FILE="/etc/nginx/sites-available/$NGINX_SITE"
CERT_DIR="/etc/letsencrypt/live/$DOMAIN"

# Тело сайта — одинаковое для http- и https-варианта.
read -r -d '' APP_BODY <<BODY || true
    client_max_body_size 10M;

    root $APP_DIR/frontend/dist;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120;
    }
    location /admin/ {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    location /static/ {
        alias $APP_DIR/backend/staticfiles/;
        access_log off;
        expires 30d;
    }
    # PWA: service worker, манифест и index.html всегда перепроверяются —
    # иначе установленное приложение не получит обновление
    location = /sw.js {
        add_header Cache-Control "no-cache";
        try_files \$uri =404;
    }
    location = /manifest.webmanifest {
        default_type application/manifest+json;
        add_header Cache-Control "no-cache";
    }
    location = /index.html {
        add_header Cache-Control "no-cache";
    }
    # сборка Vite: имена файлов с хэшем — можно кэшировать надолго
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }
    location / {
        try_files \$uri \$uri/ /index.html;
    }
BODY

# Пишем конфиг: "ssl" — с 443 и редиректом, "plain" — только http.
write_site_config() {
  if [ "$1" = "ssl" ]; then
    SSL_OPTS=""
    [ -f /etc/letsencrypt/options-ssl-nginx.conf ] && SSL_OPTS="    include /etc/letsencrypt/options-ssl-nginx.conf;"
    SSL_DH=""
    [ -f /etc/letsencrypt/ssl-dhparams.pem ] && SSL_DH="    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;"
    cat > "$SITE_FILE" <<CFG
server {
    listen 80;
    server_name $DOMAIN;
    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / { return 301 https://\$host\$request_uri; }
}

server {
    listen 443 ssl;
    server_name $DOMAIN;

    ssl_certificate $CERT_DIR/fullchain.pem;
    ssl_certificate_key $CERT_DIR/privkey.pem;
$SSL_OPTS
$SSL_DH

$APP_BODY
}
CFG
  else
    cat > "$SITE_FILE" <<CFG
server {
    listen 80;
    server_name $DOMAIN;
    location /.well-known/acme-challenge/ { root /var/www/html; }

$APP_BODY
}
CFG
  fi
}

# Включаем конфиг. Если nginx -t падает — убираем ТОЛЬКО наш сайт, соседей не трогаем.
enable_and_reload() {
  ln -sf "$SITE_FILE" "/etc/nginx/sites-enabled/$NGINX_SITE"
  if ! nginx -t; then
    echo "!!! nginx -t не прошёл — отключаю наш сайт, соседей не трогаю." >&2
    rm -f "/etc/nginx/sites-enabled/$NGINX_SITE"
    nginx -t && systemctl reload nginx || true
    return 1
  fi
  systemctl reload nginx
}

# 1) Сначала http — он нужен и сам по себе, и для проверки домена при выпуске SSL.
write_site_config plain
enable_and_reload || exit 1

# 2) Сертификат выпускаем только если его ещё нет. certonly НЕ трогает конфиги nginx.
if [ ! -f "$CERT_DIR/fullchain.pem" ]; then
  certbot certonly --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$CERT_EMAIL" \
    || echo "!!! Не удалось выпустить сертификат — проверьте, что DNS $DOMAIN → этот сервер."
fi

# 3) Есть сертификат — включаем https. Раньше это делал certbot, и SSL слетал
#    при каждом деплое (конфиг перезаписывался). Теперь блок пишем сами.
SITE_URL="http://$DOMAIN"
if [ -f "$CERT_DIR/fullchain.pem" ]; then
  write_site_config ssl
  if enable_and_reload; then
    SITE_URL="https://$DOMAIN"
  else
    echo "!!! SSL-конфиг не прошёл проверку — возвращаю http-вариант." >&2
    write_site_config plain
    enable_and_reload || true
  fi
else
  echo "!!! SSL нет: сайт работает по http. По https откроется чужой сайт по умолчанию."
fi

echo ""
echo "============================================================"
echo "  Готово!  $SITE_URL"
echo "============================================================"
systemctl --no-pager status "$SERVICE" | head -6 || true

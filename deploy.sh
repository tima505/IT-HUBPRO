#!/bin/bash
# =============================================================================
#  deploy.sh — запуск деплоя из Git Bash / Linux / macOS.
#  Нужно только: node/npm, tar, scp, ssh (всё есть в Git Bash).
#  Собирает фронтенд, пакует проект, заливает на сервер и запускает server-deploy.sh.
#  Соседние сайты не трогает (см. server-deploy.sh). Запуск:  bash deploy.sh
# =============================================================================
set -e

SERVER="root@84.247.131.147"
APP_DIR="/home/it_hubpro"
LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$LOCAL_DIR"

echo "=== 1/4: Сборка фронтенда ==="
[ -d frontend/node_modules ] || ( cd frontend && npm install )
( cd frontend && npm run build )

echo "=== 2/4: Упаковка проекта (db.sqlite3 и мусор исключены) ==="
TAR="$(mktemp -u)_ithub.tgz"
tar -czf "$TAR" \
    --exclude='.git' --exclude='.claude' --exclude='venv' --exclude='node_modules' \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='db.sqlite3' \
    --exclude='staticfiles' --exclude='.DS_Store' .

echo "=== 3/4: Загрузка на сервер ==="
scp "$TAR" "$SERVER:/tmp/ithub_deploy.tgz"
rm -f "$TAR"

echo "=== 4/4: Установка на сервере ==="
# .env и db.sqlite3 на сервере не в архиве → tar их не тронет (данные сохраняются).
ssh "$SERVER" "mkdir -p $APP_DIR && tar xzf /tmp/ithub_deploy.tgz -C $APP_DIR && rm -f /tmp/ithub_deploy.tgz && bash $APP_DIR/server-deploy.sh"

echo ""
echo "Готово — адрес сайта см. выше (http или https, в зависимости от SSL)."

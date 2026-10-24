# =============================================================================
#  deploy.ps1 — запуск деплоя из PowerShell (Windows).
#  Нужно только: node/npm, tar, scp, ssh (tar и ssh встроены в Windows 10/11).
#  Делает то же, что deploy.sh: сборка фронта, упаковка, заливка, server-deploy.sh.
#  Запуск:  powershell -ExecutionPolicy Bypass -File .\deploy.ps1
# =============================================================================
$ErrorActionPreference = "Stop"

$SERVER  = "root@84.247.131.147"
$APP_DIR = "/home/it_hubpro"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "=== 1/4: Сборка фронтенда ===" -ForegroundColor Cyan
if (-not (Test-Path "frontend/node_modules")) { npm --prefix frontend install }
npm --prefix frontend run build
if ($LASTEXITCODE -ne 0) { throw "npm run build упал" }

Write-Host "=== 2/4: Упаковка проекта (db.sqlite3 и мусор исключены) ===" -ForegroundColor Cyan
$TAR = Join-Path $env:TEMP "ithub_deploy.tgz"
if (Test-Path $TAR) { Remove-Item $TAR -Force }
tar -czf $TAR `
    "--exclude=.git" "--exclude=.claude" "--exclude=venv" "--exclude=node_modules" `
    "--exclude=__pycache__" "--exclude=*.pyc" "--exclude=db.sqlite3" `
    "--exclude=staticfiles" "--exclude=.DS_Store" "."
if ($LASTEXITCODE -ne 0) { throw "tar упал" }

Write-Host "=== 3/4: Загрузка на сервер ===" -ForegroundColor Cyan
scp $TAR "${SERVER}:/tmp/ithub_deploy.tgz"
if ($LASTEXITCODE -ne 0) { throw "scp упал" }
Remove-Item $TAR -Force

Write-Host "=== 4/4: Установка на сервере ===" -ForegroundColor Cyan
# .env и db.sqlite3 на сервере не в архиве → tar их не тронет (данные сохраняются).
ssh $SERVER "mkdir -p $APP_DIR && tar xzf /tmp/ithub_deploy.tgz -C $APP_DIR && rm -f /tmp/ithub_deploy.tgz && bash $APP_DIR/server-deploy.sh"
if ($LASTEXITCODE -ne 0) { throw "удалённая установка упала" }

Write-Host ""
Write-Host "Готово — адрес сайта см. выше (http или https, в зависимости от SSL)." -ForegroundColor Green

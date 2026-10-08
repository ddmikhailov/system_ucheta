# Ежедневная резервная копия БД платформы (Windows). Запуск из Планировщика заданий (см. инструкцию):
#   schtasks /Create /TN kait20-backup /SC DAILY /ST 02:30 /RU kait20svc /TR "powershell -ExecutionPolicy Bypass -File C:\kait20\kait20-backup.ps1"
# Учётные данные БД — в файле C:\kait20\backup.cnf (права только для kait20svc и администраторов):
#   [client]
#   user=kait20
#   password=...
param(
    [string]$Dest = "D:\Backups\kait20",
    [string]$MysqlBin = "C:\Program Files\MySQL\MySQL Server 8.1\bin",
    [string]$Defaults = "C:\kait20\backup.cnf",
    [int]$KeepDays = 30
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmm"
$sql = Join-Path $Dest "kait20-$stamp.sql"
& "$MysqlBin\mysqldump.exe" "--defaults-extra-file=$Defaults" --single-transaction --no-tablespaces --routines --triggers `
    --default-character-set=utf8mb4 "--result-file=$sql" kait20
if ($LASTEXITCODE -ne 0) { throw "mysqldump завершился с кодом $LASTEXITCODE" }
# Проверка: в дампе есть таблицы (пустой дамп — тоже сбой).
if ((Select-String -Path $sql -Pattern "CREATE TABLE" | Measure-Object).Count -lt 20) { throw "В дампе слишком мало таблиц" }
Compress-Archive -Path $sql -DestinationPath "$sql.zip" -Force
Remove-Item $sql
Get-ChildItem $Dest -Filter "kait20-*.sql.zip" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepDays) } | Remove-Item
Write-Host "OK: $sql.zip"

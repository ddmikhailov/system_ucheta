# Регистрация приложения как задачи Планировщика заданий Windows (встроенное средство, ничего ставить не нужно).
# Запуск: PowerShell «от имени администратора»:   powershell -ExecutionPolicy Bypass -File .\kait20-service.ps1
# Задача стартует при загрузке сервера (без входа пользователя), перезапускается при падении, работает ровно в одном экземпляре.
# Не проверялось на реальном сервере Windows — выполните п. «Проверка» из инструкции.
param(
    [string]$Root = "C:\kait20\backend",       # папка backend из архива
    [string]$RunAs = "kait20svc"               # локальная учётная запись службы (см. инструкцию, п. 4.2 для Windows)
)
$ErrorActionPreference = "Stop"
$python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Не найден $python — сначала создайте виртуальное окружение (python -m venv .venv)" }

$log = Join-Path $Root "..\logs"
New-Item -ItemType Directory -Force -Path $log | Out-Null

# HOST/PORT — в окружение процесса; остальные настройки приложение читает из .env рядом с кодом.
$cmd = "/c set HOST=127.0.0.1&& set PORT=8000&& set PYTHONUTF8=1&& `"$python`" -m scripts.entrypoint >> `"$log\kait20.log`" 2>&1"
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $cmd -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable
$password = Read-Host "Пароль учётной записи $RunAs" -AsSecureString
$plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($password))
Register-ScheduledTask -TaskName "kait20" -Action $action -Trigger $trigger -Settings $settings `
    -User $RunAs -Password $plain -RunLevel Limited -Force | Out-Null
Start-ScheduledTask -TaskName "kait20"
Write-Host "Готово: задача kait20 зарегистрирована и запущена. Журнал: $log\kait20.log"
Write-Host "Проверка: Invoke-WebRequest http://127.0.0.1:8000/health -UseBasicParsing"

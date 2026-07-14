param(
    [string]$MqttHost = "127.0.0.1",
    [int]$MqttPort = 1883,
    [string]$MysqlHost = "127.0.0.1",
    [int]$MysqlPort = 3306,
    [string]$MysqlPassword = "jyt20050315",
    [string]$RosBridgeHttpUrl = "http://192.168.137.89:8001",
    [int]$Port = 8000,
    [string]$MqttClientId = "parking_backend",
    [switch]$SkipDocker,
    [switch]$ForceRestart
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$backendDir = Join-Path $repoRoot "backend"
$python = Join-Path $backendDir ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

if (-not $SkipDocker) {
    docker compose -f (Join-Path $repoRoot "docker-compose.yml") up -d mysql mosquitto
}

$env:MYSQL_HOST = $MysqlHost
$env:MYSQL_PORT = "$MysqlPort"
$env:MYSQL_USER = "root"
$env:MYSQL_PASSWORD = $MysqlPassword
$env:MYSQL_DATABASE = "parking_inspection_robot"
$env:MQTT_BROKER_HOST = $MqttHost
$env:MQTT_BROKER_PORT = "$MqttPort"
$env:MQTT_USERNAME = "parking_backend"
$env:MQTT_PASSWORD = "parking_backend_dev"
$env:MQTT_CLIENT_ID = $MqttClientId
$env:ROS_BRIDGE_HTTP_URL = $RosBridgeHttpUrl

$existing = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
    Where-Object { $_.State -eq "Listen" } |
    Select-Object -First 1

if ($existing -and $ForceRestart) {
    Stop-Process -Id $existing.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    $existing = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
        Where-Object { $_.State -eq "Listen" } |
        Select-Object -First 1
}

if (-not $existing) {
    $runDir = Join-Path $backendDir ".run"
    New-Item -ItemType Directory -Force -Path $runDir | Out-Null
    $out = Join-Path $runDir "web_api_windows.out.log"
    $err = Join-Path $runDir "web_api_windows.err.log"

    Start-Process `
        -FilePath $python `
        -ArgumentList @("-m", "uvicorn", "apps.web_api.main:app", "--host", "0.0.0.0", "--port", "$Port") `
        -WorkingDirectory $backendDir `
        -RedirectStandardOutput $out `
        -RedirectStandardError $err `
        -WindowStyle Hidden | Out-Null

    Start-Sleep -Seconds 6
}

Invoke-RestMethod "http://127.0.0.1:$Port/health"
Invoke-RestMethod "http://127.0.0.1:$Port/api/fleet/robots"

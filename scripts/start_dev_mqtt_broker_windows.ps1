param(
    [int]$Port = 1883
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$runtimeDir = Join-Path $repoRoot "runtime"
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

$existing = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
    Where-Object { $_.State -eq "Listen" } |
    Select-Object -First 1

if ($existing) {
    Write-Host "MQTT broker already listening on port $Port, pid=$($existing.OwningProcess)"
    exit 0
}

$importCheck = & python -c "import amqtt" 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Python package 'amqtt' is not installed. Run: python -m pip install --user amqtt"
}

$out = Join-Path $runtimeDir "dev_mqtt_broker.out.log"
$err = Join-Path $runtimeDir "dev_mqtt_broker.err.log"

$process = Start-Process `
    -FilePath "python" `
    -ArgumentList @(".\scripts\dev_mqtt_broker.py") `
    -WorkingDirectory $repoRoot `
    -RedirectStandardOutput $out `
    -RedirectStandardError $err `
    -WindowStyle Hidden `
    -PassThru

Start-Sleep -Seconds 4

$listener = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
    Where-Object { $_.State -eq "Listen" } |
    Select-Object -First 1

if (-not $listener) {
    Write-Host "--- broker stderr ---"
    Get-Content $err -Tail 80 -ErrorAction SilentlyContinue
    throw "dev MQTT broker did not start on port $Port"
}

Write-Host "dev MQTT broker listening on 0.0.0.0:$Port, pid=$($process.Id)"

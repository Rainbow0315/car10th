param(
    [Parameter(Mandatory = $true)]
    [string]$RobotHost,

    [Parameter(Mandatory = $true)]
    [string]$RobotUser,

    [string]$RemoteDir = "",
    [int]$SshPort = 22,
    [string]$IdentityFile = "",

    [Parameter(Mandatory = $true)]
    [string]$MqttHost,

    [int]$MqttPort = 1883,
    [string]$RobotCode = "robot_001",
    [string]$MqttRobotUsername = "parking_robot",
    [string]$MqttRobotPassword = "parking_robot_dev",
    [switch]$InstallService,
    [switch]$AllowDirty
)

$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $FilePath $($Arguments -join ' ')"
    }
}

function New-SshArgs {
    $args = @("-p", "$SshPort")
    if ($IdentityFile) {
        $args += @("-i", $IdentityFile)
    }
    return $args
}

function New-ScpArgs {
    $args = @("-P", "$SshPort")
    if ($IdentityFile) {
        $args += @("-i", $IdentityFile)
    }
    return $args
}

function Invoke-Remote {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [switch]$Tty
    )
    $sshArgs = New-SshArgs
    if ($Tty) {
        $sshArgs += @("-tt")
    }
    $sshArgs += @("$RobotUser@$RobotHost", $Command)
    Invoke-Checked -FilePath "ssh" -Arguments $sshArgs
}

if (-not $RemoteDir) {
    $RemoteDir = "/home/$RobotUser/car10th"
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$dirty = git status --porcelain
if ($dirty -and -not $AllowDirty) {
    throw "Working tree is dirty. Commit or stash changes before deploy, or pass -AllowDirty for manual testing."
}

$commit = (git rev-parse --short HEAD).Trim()
$timestamp = Get-Date -Format "yyyyMMddHHmmss"
$releaseName = "release-$timestamp-$commit"
$archivePath = Join-Path $env:TEMP "car10th-$releaseName.tar"

Write-Host "Packaging commit $commit ..."
Invoke-Checked -FilePath "git" -Arguments @("archive", "--format=tar", "--output=$archivePath", "HEAD")

$remoteTmp = "/tmp/car10th-$releaseName.tar"
$remoteReleaseDir = "$RemoteDir/releases/$releaseName"
$remoteCurrentDir = "$RemoteDir/current"
$remoteServiceName = "car10th-robot-agent"

Write-Host "Uploading archive to $RobotUser@$RobotHost ..."
$scpArgs = New-ScpArgs
$scpArgs += @($archivePath, "$RobotUser@$RobotHost`:$remoteTmp")
Invoke-Checked -FilePath "scp" -Arguments $scpArgs

Write-Host "Preparing remote release $remoteReleaseDir ..."
$setupCommand = @"
set -e
mkdir -p '$RemoteDir/releases' '$remoteReleaseDir'
tar -xf '$remoteTmp' -C '$remoteReleaseDir'
rm -f '$remoteTmp'
if [ -f '$remoteCurrentDir/backend/.env' ]; then
  cp '$remoteCurrentDir/backend/.env' '$remoteReleaseDir/backend/.env'
elif [ -f '$remoteReleaseDir/backend/.env.example' ]; then
  cp '$remoteReleaseDir/backend/.env.example' '$remoteReleaseDir/backend/.env'
fi
python3 - '$remoteReleaseDir/backend/.env' '$MqttHost' '$MqttPort' '$RobotCode' '$MqttRobotUsername' '$MqttRobotPassword' <<'PY'
from pathlib import Path
import sys

env_path = Path(sys.argv[1])
updates = {
    "MQTT_BROKER_HOST": sys.argv[2],
    "MQTT_BROKER_PORT": sys.argv[3],
    "ROBOT_CODE": sys.argv[4],
    "MQTT_ROBOT_USERNAME": sys.argv[5],
    "MQTT_ROBOT_PASSWORD": sys.argv[6],
}

lines = []
seen = set()
if env_path.exists():
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        key = raw.split("=", 1)[0] if "=" in raw else ""
        if key in updates:
            lines.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            lines.append(raw)
for key, value in updates.items():
    if key not in seen:
        lines.append(f"{key}={value}")
env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
python3 -m venv '$remoteReleaseDir/backend/.venv'
'$remoteReleaseDir/backend/.venv/bin/python' -m pip install --upgrade pip
'$remoteReleaseDir/backend/.venv/bin/python' -m pip install -r '$remoteReleaseDir/backend/requirements.txt'
ln -sfn '$remoteReleaseDir' '$remoteCurrentDir'
echo '$commit' > '$RemoteDir/current/DEPLOYED_COMMIT'
"@
Invoke-Remote $setupCommand

if ($InstallService) {
    Write-Host "Installing systemd service $remoteServiceName ..."
    $serviceCommand = @"
set -e
sudo tee /etc/systemd/system/$remoteServiceName.service >/dev/null <<'EOF'
[Unit]
Description=car10th robot MQTT agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$remoteCurrentDir/backend
EnvironmentFile=$remoteCurrentDir/backend/.env
ExecStart=$remoteCurrentDir/backend/.venv/bin/python -m apps.robot_agent.main --robot-code $RobotCode
Restart=always
RestartSec=3
User=$RobotUser

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable $remoteServiceName
"@
    Invoke-Remote -Command $serviceCommand -Tty
}

Write-Host "Restarting robot agent ..."
if ($InstallService) {
    Invoke-Remote -Command "sudo systemctl restart $remoteServiceName && systemctl is-active $remoteServiceName" -Tty
}
else {
    Invoke-Remote -Command "if systemctl list-unit-files '$remoteServiceName.service' 2>/dev/null | grep -q '^$remoteServiceName.service'; then sudo systemctl restart $remoteServiceName && systemctl is-active $remoteServiceName; else pkill -f 'apps.robot_agent.main' || true; cd '$remoteCurrentDir/backend'; nohup '$remoteCurrentDir/backend/.venv/bin/python' -m apps.robot_agent.main --robot-code '$RobotCode' > '$RemoteDir/robot-agent.log' 2>&1 & fi" -Tty
}

Write-Host "Deployment finished."
Write-Host "Remote current: $remoteCurrentDir"
Write-Host "Deployed commit: $commit"
Write-Host "Robot code: $RobotCode"
Write-Host "MQTT broker: $MqttHost`:$MqttPort"
Write-Host ""
Write-Host "Useful checks:"
Write-Host "  ssh $RobotUser@$RobotHost 'cat $RemoteDir/current/DEPLOYED_COMMIT'"
Write-Host "  ssh $RobotUser@$RobotHost 'systemctl status $remoteServiceName --no-pager'"

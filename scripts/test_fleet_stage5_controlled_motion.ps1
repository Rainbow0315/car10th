param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$TargetRobot = "robot_001",
    [string]$TargetRosBridgeUrl = "http://192.168.137.239:8001",
    [double]$LinearX = 0.12,
    [double]$DurationSec = 1.5,
    [int]$AckTimeoutSec = 10,
    [switch]$ArmMotion,
    [switch]$AllowDryRun
)

$ErrorActionPreference = "Stop"

function Invoke-ApiJson {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [string]$Method = "GET",
        [object]$Body = $null
    )

    if ($null -eq $Body) {
        return Invoke-RestMethod -Method $Method -Uri "$BaseUrl$Path" -TimeoutSec 8
    }

    $json = $Body | ConvertTo-Json -Compress -Depth 8
    return Invoke-RestMethod -Method $Method -Uri "$BaseUrl$Path" -ContentType "application/json" -Body $json -TimeoutSec 8
}

function Assert-Condition {
    param(
        [Parameter(Mandatory = $true)]
        [bool]$Condition,
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Wait-CommandAck {
    param(
        [Parameter(Mandatory = $true)][string]$CommandId,
        [Parameter(Mandatory = $true)][string]$ExpectedRobot
    )

    $deadline = (Get-Date).AddSeconds($AckTimeoutSec)
    $last = $null
    while ((Get-Date) -lt $deadline) {
        $last = Invoke-ApiJson "/api/fleet/commands/$CommandId"
        if ($last.status -in @("acked", "failed", "timeout")) {
            break
        }
        Start-Sleep -Milliseconds 300
    }

    Assert-Condition ($null -ne $last) "command $CommandId was not found"
    Assert-Condition ($last.robot_code -eq $ExpectedRobot) "command robot mismatch: expected $ExpectedRobot, got $($last.robot_code)"
    Assert-Condition ($last.status -eq "acked") "command $CommandId did not ACK, status=$($last.status), error=$($last.error)"
    Assert-Condition ($last.ack.robot_code -eq $ExpectedRobot) "ACK robot mismatch: expected $ExpectedRobot, got $($last.ack.robot_code)"
    Assert-Condition ($last.ack.status -eq "accepted") "ACK status is not accepted for ${ExpectedRobot}: $($last.ack.status), detail=$($last.ack.detail)"
    return $last
}

function Send-SafetyStop {
    param([Parameter(Mandatory = $true)][string]$RobotCode)

    $response = Invoke-ApiJson `
        -Method "POST" `
        -Path "/api/fleet/safety/stop" `
        -Body @{
            robot_codes = @($RobotCode)
            incident_id = "stage5_controlled_motion"
            reason = "stage5 controlled motion safety stop"
        }

    Assert-Condition ($response.commands.Count -eq 1) "safety stop command count mismatch"
    return Wait-CommandAck -CommandId $response.commands[0].command_id -ExpectedRobot $RobotCode
}

Write-Host "== Fleet stage 5 controlled real-motion smoke test =="
Write-Host "BaseUrl: $BaseUrl"
Write-Host "TargetRobot: $TargetRobot"
Write-Host "TargetRosBridgeUrl: $TargetRosBridgeUrl"
Write-Host "Motion: linear_x=$LinearX m/s, duration=$DurationSec s, armed=$([bool]$ArmMotion)"

Assert-Condition ($LinearX -ge 0.0 -and $LinearX -le 0.12) "LinearX must be between 0.0 and 0.12 for stage 5"
Assert-Condition ($DurationSec -ge 0.2 -and $DurationSec -le 3.0) "DurationSec must be between 0.2 and 3.0 for stage 5"

$health = Invoke-ApiJson "/health"
Assert-Condition ($health.status -eq "ok") "web_api health is not ok"
Assert-Condition ([bool]$health.mqtt_connected) "web_api MQTT is not connected"

$robot = Invoke-ApiJson "/api/fleet/robots/$TargetRobot"
Assert-Condition ($robot.status -eq "online") "$TargetRobot is not online: $($robot.status)"

$rosHealth = Invoke-RestMethod -Method GET -Uri "$TargetRosBridgeUrl/health" -TimeoutSec 8
Assert-Condition ($rosHealth.status -eq "ok") "target ros_bridge is not ok: $($rosHealth.status)"
Assert-Condition ($rosHealth.cmd_vel_topic -eq "/cmd_vel") "unexpected cmd_vel topic: $($rosHealth.cmd_vel_topic)"
Assert-Condition ([int]$rosHealth.subscriber_count -ge 1) "target /cmd_vel has no active subscriber"
Write-Host "Preflight OK: ros_bridge subscriber_count=$($rosHealth.subscriber_count)"

$stopAck = Send-SafetyStop -RobotCode $TargetRobot
Write-Host "Safety stop ACKed: command_id=$($stopAck.command_id), dry_run=$($stopAck.ack.dry_run), detail=$($stopAck.ack.detail)"

if (-not $ArmMotion) {
    Write-Host "PASS: preflight and safety stop succeeded. Add -ArmMotion to execute the short low-speed movement."
    exit 0
}

$crawl = Invoke-ApiJson `
    -Method "POST" `
    -Path "/api/fleet/corridor/crawl" `
    -Body @{
        robot_codes = @($TargetRobot)
        corridor_id = "stage5-controlled-motion"
        linear_x = $LinearX
        duration = $DurationSec
        spacing_m = 1.0
        start_interval_sec = 0.0
        require_all_ready = $true
    }

Assert-Condition ($crawl.commands.Count -eq 1) "corridor crawl command count mismatch"
$command = $crawl.commands[0]
Assert-Condition ($command.command -eq "corridor_crawl") "unexpected command: $($command.command)"
Assert-Condition ($command.payload.motion.linear_x -eq $LinearX) "linear_x payload mismatch"
Assert-Condition ($command.payload.motion.duration -eq $DurationSec) "duration payload mismatch"

$motionAck = Wait-CommandAck -CommandId $command.command_id -ExpectedRobot $TargetRobot
if ([bool]$motionAck.ack.dry_run -and -not $AllowDryRun) {
    throw "motion ACK was dry_run=true; this did not prove real wheel movement. Use a non-dry-run agent or pass -AllowDryRun for simulation only."
}
Write-Host "Motion ACKed: command_id=$($motionAck.command_id), dry_run=$($motionAck.ack.dry_run), detail=$($motionAck.ack.detail)"

$holdMs = [Math]::Ceiling(($DurationSec + 0.5) * 1000)
Write-Host "Holding motion window for $($DurationSec + 0.5)s before final safety stop..."
Start-Sleep -Milliseconds $holdMs
$finalStopAck = Send-SafetyStop -RobotCode $TargetRobot
Write-Host "Final safety stop ACKed: command_id=$($finalStopAck.command_id), dry_run=$($finalStopAck.ack.dry_run), detail=$($finalStopAck.ack.detail)"

Write-Host "PASS: controlled motion command completed and final stop was ACKed."

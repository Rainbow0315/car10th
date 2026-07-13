param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$TargetRobot = "robot_002",
    [string]$OtherRobot = "robot_001",
    [string]$TestMode = "patrol",
    [string]$RestoreMode = "idle",
    [int]$AckTimeoutSec = 8
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

function Get-Robot {
    param([Parameter(Mandatory = $true)][string]$RobotCode)
    return Invoke-ApiJson "/api/fleet/robots/$RobotCode"
}

function Send-SetMode {
    param(
        [Parameter(Mandatory = $true)][string]$RobotCode,
        [Parameter(Mandatory = $true)][string]$Mode
    )

    return Invoke-ApiJson `
        -Method "POST" `
        -Path "/api/fleet/robots/$RobotCode/commands" `
        -Body @{
            command = "set_mode"
            payload = @{ mode = $Mode }
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
        Start-Sleep -Milliseconds 500
    }

    Assert-Condition ($null -ne $last) "command $CommandId was not found"
    Assert-Condition ($last.status -eq "acked") "command $CommandId did not ACK, status=$($last.status), error=$($last.error)"
    Assert-Condition ($last.robot_code -eq $ExpectedRobot) "command robot mismatch: expected $ExpectedRobot, got $($last.robot_code)"
    Assert-Condition ($last.ack.robot_code -eq $ExpectedRobot) "ACK robot mismatch: expected $ExpectedRobot, got $($last.ack.robot_code)"
    Assert-Condition ($last.ack.status -eq "accepted") "ACK status is not accepted: $($last.ack.status)"
    return $last
}

Write-Host "== Fleet stage 2 single-robot command smoke test =="
Write-Host "BaseUrl: $BaseUrl"
Write-Host "TargetRobot: $TargetRobot"
Write-Host "OtherRobot: $OtherRobot"

$health = Invoke-ApiJson "/health"
Assert-Condition ($health.status -eq "ok") "web_api health is not ok"
Assert-Condition ([bool]$health.mqtt_connected) "web_api MQTT is not connected"

$targetBefore = Get-Robot $TargetRobot
$otherBefore = Get-Robot $OtherRobot
Assert-Condition ($targetBefore.status -eq "online") "$TargetRobot is not online: $($targetBefore.status)"
Assert-Condition ($otherBefore.status -eq "online") "$OtherRobot is not online: $($otherBefore.status)"

Write-Host "Before: $TargetRobot mode=$($targetBefore.mode), $OtherRobot mode=$($otherBefore.mode)"

$command = Send-SetMode -RobotCode $TargetRobot -Mode $TestMode
Assert-Condition ($command.topic -eq "fleet/command/$TargetRobot") "published topic mismatch: $($command.topic)"
Assert-Condition ($command.status -eq "published") "initial command status is not published: $($command.status)"

$acked = Wait-CommandAck -CommandId $command.command_id -ExpectedRobot $TargetRobot
Start-Sleep -Seconds 2

$targetAfter = Get-Robot $TargetRobot
$otherAfter = Get-Robot $OtherRobot

Assert-Condition ($targetAfter.mode -eq $TestMode) "$TargetRobot mode did not change to $TestMode, got $($targetAfter.mode)"
Assert-Condition ($otherAfter.mode -eq $otherBefore.mode) "$OtherRobot mode changed unexpectedly: before=$($otherBefore.mode), after=$($otherAfter.mode)"

Write-Host "Command ACKed: command_id=$($acked.command_id), detail=$($acked.ack.detail)"
Write-Host "After:  $TargetRobot mode=$($targetAfter.mode), $OtherRobot mode=$($otherAfter.mode)"

if ($RestoreMode) {
    $restore = Send-SetMode -RobotCode $TargetRobot -Mode $RestoreMode
    $restoreAck = Wait-CommandAck -CommandId $restore.command_id -ExpectedRobot $TargetRobot
    Start-Sleep -Seconds 2
    $targetRestored = Get-Robot $TargetRobot
    Assert-Condition ($targetRestored.mode -eq $RestoreMode) "$TargetRobot restore mode failed: expected $RestoreMode, got $($targetRestored.mode)"
    Write-Host "Restored: $TargetRobot mode=$($targetRestored.mode), command_id=$($restoreAck.command_id)"
}

Write-Host "PASS: command was delivered only to $TargetRobot and ACKed by the same robot."

param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string[]]$RobotCodes = @("robot_001", "robot_002"),
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

function Send-BatchSetMode {
    param(
        [Parameter(Mandatory = $true)][string[]]$Codes,
        [Parameter(Mandatory = $true)][string]$Mode
    )

    return Invoke-ApiJson `
        -Method "POST" `
        -Path "/api/fleet/commands/batch" `
        -Body @{
            robot_codes = $Codes
            command = "set_mode"
            payload = @{ mode = $Mode }
            require_all_ready = $true
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
    Assert-Condition ($last.ack.status -eq "accepted") "ACK status is not accepted for ${ExpectedRobot}: $($last.ack.status)"
    return $last
}

function Wait-AllModes {
    param(
        [Parameter(Mandatory = $true)][string[]]$Codes,
        [Parameter(Mandatory = $true)][string]$ExpectedMode
    )

    $deadline = (Get-Date).AddSeconds($AckTimeoutSec)
    $snapshot = @{}
    while ((Get-Date) -lt $deadline) {
        $allMatched = $true
        foreach ($code in $Codes) {
            $robot = Get-Robot $code
            $snapshot[$code] = $robot
            if ($robot.mode -ne $ExpectedMode) {
                $allMatched = $false
            }
        }
        if ($allMatched) {
            return $snapshot
        }
        Start-Sleep -Milliseconds 500
    }

    foreach ($code in $Codes) {
        $mode = if ($snapshot.ContainsKey($code)) { $snapshot[$code].mode } else { "<missing>" }
        Assert-Condition $false "$code mode did not become $ExpectedMode, got $mode"
    }
}

function Assert-BatchResponse {
    param(
        [Parameter(Mandatory = $true)]$BatchResponse,
        [Parameter(Mandatory = $true)][string[]]$ExpectedCodes
    )

    Assert-Condition ($BatchResponse.commands.Count -eq $ExpectedCodes.Count) "batch command count mismatch"

    $ids = @()
    foreach ($code in $ExpectedCodes) {
        $command = $BatchResponse.commands | Where-Object { $_.robot_code -eq $code } | Select-Object -First 1
        Assert-Condition ($null -ne $command) "missing batch command for $code"
        Assert-Condition ($command.command -eq "set_mode") "$code command mismatch: $($command.command)"
        Assert-Condition ($command.topic -eq "fleet/command/$code") "$code topic mismatch: $($command.topic)"
        Assert-Condition ($command.status -eq "published") "$code initial status mismatch: $($command.status)"
        $ids += $command.command_id
    }

    $uniqueIds = @($ids | Select-Object -Unique)
    Assert-Condition ($uniqueIds.Count -eq $ids.Count) "batch command_id values are not unique"
}

Write-Host "== Fleet stage 3 batch command smoke test =="
Write-Host "BaseUrl: $BaseUrl"
Write-Host "Robots: $($RobotCodes -join ', ')"

Assert-Condition ($RobotCodes.Count -ge 2) "stage 3 requires at least two robot codes"

$health = Invoke-ApiJson "/health"
Assert-Condition ($health.status -eq "ok") "web_api health is not ok"
Assert-Condition ([bool]$health.mqtt_connected) "web_api MQTT is not connected"

$beforeRows = @()
foreach ($code in $RobotCodes) {
    $robot = Get-Robot $code
    Assert-Condition ($robot.status -eq "online") "$code is not online: $($robot.status)"
    $beforeRows += [PSCustomObject]@{
        robot_code = $code
        status = $robot.status
        mode = $robot.mode
        agent_ip = $robot.agent_ip
    }
}

Write-Host "Before:"
$beforeRows | Format-Table -AutoSize

$batch = Send-BatchSetMode -Codes $RobotCodes -Mode $TestMode
Assert-BatchResponse -BatchResponse $batch -ExpectedCodes $RobotCodes

$ackRows = @()
foreach ($command in $batch.commands) {
    $acked = Wait-CommandAck -CommandId $command.command_id -ExpectedRobot $command.robot_code
    $ackRows += [PSCustomObject]@{
        robot_code = $acked.robot_code
        command_id = $acked.command_id
        status = $acked.status
        ack_detail = $acked.ack.detail
        dry_run = $acked.ack.dry_run
    }
}

$after = Wait-AllModes -Codes $RobotCodes -ExpectedMode $TestMode

Write-Host "Batch ACKs:"
$ackRows | Format-Table -AutoSize

Write-Host "After ${TestMode}:"
$RobotCodes | ForEach-Object {
    $robot = $after[$_]
    [PSCustomObject]@{
        robot_code = $_
        status = $robot.status
        mode = $robot.mode
        agent_ip = $robot.agent_ip
    }
} | Format-Table -AutoSize

if ($RestoreMode) {
    $restoreBatch = Send-BatchSetMode -Codes $RobotCodes -Mode $RestoreMode
    Assert-BatchResponse -BatchResponse $restoreBatch -ExpectedCodes $RobotCodes
    foreach ($command in $restoreBatch.commands) {
        [void](Wait-CommandAck -CommandId $command.command_id -ExpectedRobot $command.robot_code)
    }
    $restored = Wait-AllModes -Codes $RobotCodes -ExpectedMode $RestoreMode

    Write-Host "Restored ${RestoreMode}:"
    $RobotCodes | ForEach-Object {
        $robot = $restored[$_]
        [PSCustomObject]@{
            robot_code = $_
            status = $robot.status
            mode = $robot.mode
            agent_ip = $robot.agent_ip
        }
    } | Format-Table -AutoSize
}

Write-Host "PASS: one batch request produced independent commands and ACKs for all robots."

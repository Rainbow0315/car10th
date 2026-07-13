param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string[]]$RobotCodes = @("robot_001", "robot_002"),
    [string]$FormationType = "line",
    [string]$Mode = "patrol",
    [double]$SpacingM = 1.2,
    [int]$ReadyTimeoutSec = 10,
    [switch]$RestoreIdle
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

function Wait-CommandAck {
    param(
        [Parameter(Mandatory = $true)][string]$CommandId,
        [Parameter(Mandatory = $true)][string]$ExpectedRobot
    )

    $deadline = (Get-Date).AddSeconds($ReadyTimeoutSec)
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

function Wait-FormationReady {
    param([Parameter(Mandatory = $true)][string]$FormationId)

    $deadline = (Get-Date).AddSeconds($ReadyTimeoutSec)
    $snapshot = $null
    while ((Get-Date) -lt $deadline) {
        $snapshot = Invoke-ApiJson "/api/fleet/formations/$FormationId"
        if ($snapshot.ready -and $snapshot.acked_commands -eq $snapshot.total_robots) {
            return $snapshot
        }
        Start-Sleep -Milliseconds 500
    }

    if ($null -ne $snapshot) {
        $memberState = ($snapshot.members | ForEach-Object {
            "$($_.robot_code):ready=$($_.ready),cmd=$($_.command.status),role=$($_.robot.formation_role),slot=$($_.robot.formation_slot)"
        }) -join "; "
        throw "formation $FormationId did not become ready. ready=$($snapshot.ready), acked=$($snapshot.acked_commands)/$($snapshot.total_robots), members=$memberState"
    }
    throw "formation $FormationId was not found while waiting for readiness"
}

function Send-BatchSetMode {
    param(
        [Parameter(Mandatory = $true)][string[]]$Codes,
        [Parameter(Mandatory = $true)][string]$TargetMode
    )

    return Invoke-ApiJson `
        -Method "POST" `
        -Path "/api/fleet/commands/batch" `
        -Body @{
            robot_codes = $Codes
            command = "set_mode"
            payload = @{ mode = $TargetMode }
            require_all_ready = $true
        }
}

Write-Host "== Fleet stage 4 formation smoke test =="
Write-Host "BaseUrl: $BaseUrl"
Write-Host "Robots: $($RobotCodes -join ', ')"
Write-Host "Formation: type=$FormationType, mode=$Mode, spacing_m=$SpacingM"

Assert-Condition ($RobotCodes.Count -ge 2) "stage 4 requires at least two robot codes"

$health = Invoke-ApiJson "/health"
Assert-Condition ($health.status -eq "ok") "web_api health is not ok"
Assert-Condition ([bool]$health.mqtt_connected) "web_api MQTT is not connected"

foreach ($code in $RobotCodes) {
    $robot = Get-Robot $code
    Assert-Condition ($robot.status -eq "online") "$code is not online: $($robot.status)"
}

$request = @{
    robot_codes = $RobotCodes
    formation_type = $FormationType
    mode = $Mode
    spacing_m = $SpacingM
    require_all_ready = $true
}

$response = Invoke-ApiJson -Method "POST" -Path "/api/fleet/formations" -Body $request
Assert-Condition (-not [string]::IsNullOrWhiteSpace([string]$response.formation_id)) "formation_id is empty"
Assert-Condition ($response.commands.Count -eq $RobotCodes.Count) "formation command count mismatch"

Write-Host "Formation created: $($response.formation_id)"

$commandIds = @()
foreach ($index in 0..($RobotCodes.Count - 1)) {
    $code = $RobotCodes[$index]
    $expectedRole = if ($index -eq 0) { "leader" } else { "follower" }
    $command = $response.commands | Where-Object { $_.robot_code -eq $code } | Select-Object -First 1

    Assert-Condition ($null -ne $command) "missing formation command for $code"
    Assert-Condition ($command.command -eq "set_formation") "$code command mismatch: $($command.command)"
    Assert-Condition ($command.topic -eq "fleet/command/$code") "$code topic mismatch: $($command.topic)"
    Assert-Condition ($command.payload.formation_id -eq $response.formation_id) "$code formation_id payload mismatch"
    Assert-Condition ($command.payload.role -eq $expectedRole) "$code role payload mismatch: expected $expectedRole, got $($command.payload.role)"
    Assert-Condition ($command.payload.slot_index -eq $index) "$code slot_index payload mismatch"
    $commandIds += $command.command_id

    [void](Wait-CommandAck -CommandId $command.command_id -ExpectedRobot $code)
}

$uniqueCommandIds = @($commandIds | Select-Object -Unique)
Assert-Condition ($uniqueCommandIds.Count -eq $commandIds.Count) "formation command_id values are not unique"

$formation = Wait-FormationReady -FormationId $response.formation_id
Assert-Condition ($formation.total_robots -eq $RobotCodes.Count) "formation total_robots mismatch"
Assert-Condition ($formation.online_robots -eq $RobotCodes.Count) "formation online_robots mismatch"
Assert-Condition ($formation.acked_commands -eq $RobotCodes.Count) "formation acked_commands mismatch"
Assert-Condition ([bool]$formation.ready) "formation is not ready"

$rows = @()
foreach ($index in 0..($RobotCodes.Count - 1)) {
    $code = $RobotCodes[$index]
    $expectedRole = if ($index -eq 0) { "leader" } else { "follower" }
    $member = $formation.members | Where-Object { $_.robot_code -eq $code } | Select-Object -First 1
    Assert-Condition ($null -ne $member) "missing formation member for $code"
    Assert-Condition ([bool]$member.ready) "$code formation member is not ready"
    Assert-Condition ($member.role -eq $expectedRole) "$code member role mismatch: expected $expectedRole, got $($member.role)"
    Assert-Condition ($member.slot_index -eq $index) "$code member slot mismatch"
    Assert-Condition ($member.command.status -eq "acked") "$code formation command is not acked"
    Assert-Condition ($member.robot.formation_id -eq $response.formation_id) "$code robot formation_id mismatch"
    Assert-Condition ($member.robot.formation_role -eq $expectedRole) "$code robot formation_role mismatch"
    Assert-Condition ($member.robot.formation_slot -eq $index) "$code robot formation_slot mismatch"
    Assert-Condition ($member.robot.mode -eq $Mode) "$code robot mode mismatch: expected $Mode, got $($member.robot.mode)"

    $rows += [PSCustomObject]@{
        robot_code = $code
        role = $member.role
        slot = $member.slot_index
        mode = $member.robot.mode
        command_id = $member.command.command_id
        command_status = $member.command.status
        ready = $member.ready
    }
}

Write-Host "Formation ready:"
$rows | Format-Table -AutoSize

if ($RestoreIdle) {
    $restore = Send-BatchSetMode -Codes $RobotCodes -TargetMode "idle"
    foreach ($command in $restore.commands) {
        [void](Wait-CommandAck -CommandId $command.command_id -ExpectedRobot $command.robot_code)
    }
    Start-Sleep -Seconds 2
    Write-Host "Restored modes to idle. Formation metadata is retained until overwritten by a later formation command."
}

Write-Host "PASS: formation is ready and all robots reported expected roles."

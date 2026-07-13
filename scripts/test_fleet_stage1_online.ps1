param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string[]]$RobotCodes = @("robot_001", "robot_002"),
    [int]$SampleIntervalSec = 4,
    [int]$MaxLastSeenAgeSec = 12
)

$ErrorActionPreference = "Stop"

function Invoke-ApiJson {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    Invoke-RestMethod -Uri "$BaseUrl$Path" -TimeoutSec 8
}

function Convert-ToUtc {
    param([Parameter(Mandatory = $true)] $Value)
    $text = [string]$Value
    if ($text -match "(Z|[+-]\d{2}:\d{2})$") {
        return ([DateTimeOffset]::Parse($text)).UtcDateTime
    }

    $dateTime = [DateTime]::Parse($text)
    return [DateTime]::SpecifyKind($dateTime, [DateTimeKind]::Utc)
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

Write-Host "== Fleet stage 1 online/heartbeat smoke test =="
Write-Host "BaseUrl: $BaseUrl"
Write-Host "Robots: $($RobotCodes -join ', ')"

$health = Invoke-ApiJson "/health"
Assert-Condition ($health.status -eq "ok") "web_api health is not ok"
Assert-Condition ([bool]$health.mqtt_connected) "web_api MQTT is not connected"
Write-Host "Health: ok, mqtt_connected=true"

$summary = Invoke-ApiJson "/api/fleet/summary"
Assert-Condition ($summary.online_robots -ge $RobotCodes.Count) "online robot count is too low: $($summary.online_robots)"
Write-Host "Summary: total=$($summary.total_robots), online=$($summary.online_robots), acked_commands=$($summary.acked_commands)"

$first = Invoke-ApiJson "/api/fleet/robots"
Start-Sleep -Seconds $SampleIntervalSec
$second = Invoke-ApiJson "/api/fleet/robots"

$now = (Get-Date).ToUniversalTime()
$rows = @()

foreach ($code in $RobotCodes) {
    $robot1 = $first.robots | Where-Object { $_.robot_code -eq $code } | Select-Object -First 1
    $robot2 = $second.robots | Where-Object { $_.robot_code -eq $code } | Select-Object -First 1

    Assert-Condition ($null -ne $robot1) "missing robot in first sample: $code"
    Assert-Condition ($null -ne $robot2) "missing robot in second sample: $code"
    Assert-Condition ($robot2.status -eq "online") "$code is not online: $($robot2.status)"

    $firstSeen = Convert-ToUtc $robot1.last_seen_at
    $secondSeen = Convert-ToUtc $robot2.last_seen_at
    $ageSec = [Math]::Round(($now - $secondSeen).TotalSeconds, 1)

    Assert-Condition ($secondSeen -gt $firstSeen) "$code heartbeat did not refresh between samples"
    Assert-Condition ($ageSec -le $MaxLastSeenAgeSec) "$code last_seen_at is stale: ${ageSec}s"

    $rows += [PSCustomObject]@{
        robot_code = $code
        status = $robot2.status
        mode = $robot2.mode
        agent_ip = $robot2.agent_ip
        last_seen_age_sec = $ageSec
        last_message_type = $robot2.last_message_type
    }
}

$rows | Format-Table -AutoSize

Write-Host "PASS: all expected robots are online and heartbeats are refreshing."

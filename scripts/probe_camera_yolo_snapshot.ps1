param(
    [string]$RobotHost = "192.168.137.239",
    [string]$TopicName = "/image_raw",
    [string]$SnapshotOut = "$env:TEMP\car10th_snapshot_probe.jpg",
    [switch]$StartYolo
)

$ErrorActionPreference = "Stop"

$baseUrl = "http://${RobotHost}:8000"

function Invoke-JsonProbe {
    param(
        [string]$Method,
        [string]$Path,
        [object]$Body = $null,
        [int]$TimeoutSec = 20,
        [switch]$AllowFailure
    )

    $uri = "$baseUrl$Path"
    Write-Host ""
    Write-Host "$Method $uri"

    $parameters = @{
        Method = $Method
        Uri = $uri
        TimeoutSec = $TimeoutSec
    }
    if ($null -ne $Body) {
        $parameters.ContentType = "application/json"
        $parameters.Body = ($Body | ConvertTo-Json -Depth 8)
    }

    try {
        $result = Invoke-RestMethod @parameters
        $result | ConvertTo-Json -Depth 8
    }
    catch {
        if (-not $AllowFailure) {
            throw
        }
        Write-Warning "Optional probe failed: $($_.Exception.Message)"
    }
}

Write-Host "Probing web_api on $baseUrl"
Invoke-JsonProbe -Method Get -Path "/health" -TimeoutSec 8
Invoke-JsonProbe -Method Get -Path "/api/inspection/health" -TimeoutSec 8
Invoke-JsonProbe -Method Get -Path "/api/inspection/camera/status" -TimeoutSec 8 -AllowFailure

$snapshotUrl = "$baseUrl/api/inspection/camera/snapshot?topic_name=$([uri]::EscapeDataString($TopicName))&timeout_sec=3"
Write-Host ""
Write-Host "GET $snapshotUrl"
Invoke-WebRequest -Uri $snapshotUrl -OutFile $SnapshotOut -TimeoutSec 12
$snapshot = Get-Item -LiteralPath $SnapshotOut
Write-Host "Snapshot saved: $($snapshot.FullName) ($($snapshot.Length) bytes)"

Invoke-JsonProbe -Method Get -Path "/api/inspection/camera/status" -TimeoutSec 8 -AllowFailure
Invoke-JsonProbe -Method Get -Path "/api/inspection/monitor/status" -TimeoutSec 8

if ($StartYolo) {
    Write-Warning "StartYolo is still a stress probe. It now shares the ai_service latest-frame cache with snapshot, but Jetson memory and model latency still need robot-side verification."

    $body = @{
        topic_name = $TopicName
        interval_sec = 1.0
        timeout_sec = 10
        robot_code = "robot_001"
        camera_code = "usb_cam"
        enabled_models = @("unified")
    }

    Invoke-JsonProbe -Method Post -Path "/api/inspection/monitor/start" -Body $body -TimeoutSec 30
    Start-Sleep -Seconds 5
    Invoke-JsonProbe -Method Get -Path "/api/inspection/camera/status" -TimeoutSec 8 -AllowFailure
    Invoke-JsonProbe -Method Get -Path "/api/inspection/monitor/status" -TimeoutSec 8
    Write-Host ""
    Write-Host "YOLO monitor left running. Stop it with:"
    Write-Host "Invoke-RestMethod -Method Post $baseUrl/api/inspection/monitor/stop"
}

param([string]$BoardSerial)

$ErrorActionPreference = 'Stop'
$mirrorSerial = $BoardSerial
$mirrorAdb = Join-Path $env:LOCALAPPDATA 'Arduino15\packages\arduino\tools\adb\32.0.0\adb.exe'
$mirrorUrl = 'http://localhost:7000'

function Get-MirrorStatus {
    try { return Invoke-RestMethod "$mirrorUrl/api/status" -TimeoutSec 3 }
    catch { return $null }
}

try {
    if (-not (Test-Path -LiteralPath $mirrorAdb)) {
        throw 'Arduino ADB was not found. Install Arduino App Lab on this laptop first.'
    }
    if (-not $mirrorSerial) {
        $mirrorDevices = @(& $mirrorAdb devices | Where-Object { $_ -match '^([^\s]+)\s+device$' } | ForEach-Object { ($_ -split '\s+')[0] })
        if ($mirrorDevices.Count -ne 1) { throw 'Connect one VENTUNO Q, or run this script with -BoardSerial YOUR_BOARD_SERIAL.' }
        $mirrorSerial = $mirrorDevices[0]
    }
    $mirrorState = & $mirrorAdb -s $mirrorSerial get-state 2>$null
    if ($LASTEXITCODE -ne 0 -or $mirrorState -ne 'device') {
        throw 'VENTUNO Q is not connected. Power the board and connect its USB-C data port to this laptop.'
    }
    $mirrorForwards = & $mirrorAdb forward --list
    $mirrorExisting = @($mirrorForwards | Where-Object { $_ -match '\stcp:7000\s' })
    if ($mirrorExisting.Count -gt 0) {
        if ($mirrorExisting.Count -ne 1 -or $mirrorExisting[0] -ne "$mirrorSerial tcp:7000 tcp:7000") {
            throw 'Local port 7000 is forwarded to a different service. Close that service before opening this mirror.'
        }
    } else {
        & $mirrorAdb -s $mirrorSerial forward --no-rebind tcp:7000 tcp:7000
        if ($LASTEXITCODE -ne 0) { throw 'Local port 7000 is unavailable. Close the app using that port and try again.' }
    }
    $mirrorStatus = Get-MirrorStatus
    if ($mirrorStatus -and $mirrorStatus.app_id -ne 'smart-mirror-laptop') {
        throw 'Another application is using port 7000 on the board. Stop it in App Lab first.'
    }
    if (-not $mirrorStatus) {
        Write-Host 'Starting Smart Mirror on your VENTUNO Q. This can take a minute…'
        & $mirrorAdb -s $mirrorSerial shell arduino-app-cli app start user:smart-mirror-laptop
        # An already-running app can return a nonzero CLI status. Verify the actual server below.
    }
    $mirrorDeadline = (Get-Date).AddMinutes(3)
    do {
        $mirrorStatus = Get-MirrorStatus
        if ($mirrorStatus -and $mirrorStatus.app_id -eq 'smart-mirror-laptop' -and $mirrorStatus.ready) { break }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $mirrorDeadline)
    if (-not $mirrorStatus -or -not $mirrorStatus.ready -or $mirrorStatus.app_id -ne 'smart-mirror-laptop') {
        throw 'The mirror server did not start. Check the Smart Mirror • Laptop logs in App Lab and confirm both AI models are installed.'
    }
    Start-Process $mirrorUrl
    Write-Host 'Mirror opened. Select Enter the mirror once; automatic scans use the board webcam.'
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}

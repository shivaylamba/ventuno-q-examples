param([string]$BoardSerial)

$ErrorActionPreference = 'Stop'
$balanceSerial = $BoardSerial
$balanceAdb = Join-Path $env:LOCALAPPDATA 'Arduino15\packages\arduino\tools\adb\32.0.0\adb.exe'
$balanceUrl = 'http://localhost:7000'

try {
    if (-not (Test-Path -LiteralPath $balanceAdb)) { throw 'Arduino ADB was not found. Install Arduino App Lab first.' }
    if (-not $balanceSerial) {
        $balanceDevices = @(& $balanceAdb devices | Where-Object { $_ -match '^([^\s]+)\s+device$' } | ForEach-Object { ($_ -split '\s+')[0] })
        if ($balanceDevices.Count -ne 1) { throw 'Connect one VENTUNO Q, or run this script with -BoardSerial YOUR_BOARD_SERIAL.' }
        $balanceSerial = $balanceDevices[0]
    }
    $balanceDevice = & $balanceAdb -s $balanceSerial get-state 2>$null
    if ($LASTEXITCODE -ne 0 -or $balanceDevice -ne 'device') { throw 'Power VENTUNO Q and connect its USB-C data port to this laptop.' }
    $balanceForwards = @(& $balanceAdb forward --list | Where-Object { $_ -match '\stcp:7000\s' })
    if ($balanceForwards.Count -gt 0) {
        if ($balanceForwards.Count -ne 1 -or $balanceForwards[0] -ne "$balanceSerial tcp:7000 tcp:7000") {
            throw 'Port 7000 is forwarded elsewhere. Close the other service first.'
        }
    } else {
        & $balanceAdb -s $balanceSerial forward --no-rebind tcp:7000 tcp:7000
        if ($LASTEXITCODE -ne 0) { throw 'Port 7000 is unavailable. Close the application using that port first.' }
    }
    try { $balanceStatus = Invoke-RestMethod "$balanceUrl/api/status" -TimeoutSec 4 }
    catch { throw 'In App Lab, open AI Balance Challenge and press Run. Wait for startup, then open this launcher again.' }
    if ($balanceStatus.app_id -ne 'ai-balance-challenge') { throw 'Another app is running. Stop it in App Lab, then run AI Balance Challenge.' }
    Start-Process $balanceUrl
    Write-Host 'Balance opened. Click Enter the hatchery once, then choose a difficulty, then press the Knob.'
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}

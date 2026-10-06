param([string]$BoardSerial)

$ErrorActionPreference = 'Stop'
$boothSerial = $BoardSerial
$boothAdb = Join-Path $env:LOCALAPPDATA 'Arduino15\packages\arduino\tools\adb\32.0.0\adb.exe'
$boothUrl = 'http://localhost:7000'

try {
    if (-not (Test-Path -LiteralPath $boothAdb)) { throw 'Arduino ADB was not found. Install Arduino App Lab first.' }
    if (-not $boothSerial) {
        $boothDevices = @(& $boothAdb devices | Where-Object { $_ -match '^([^\s]+)\s+device$' } | ForEach-Object { ($_ -split '\s+')[0] })
        if ($boothDevices.Count -ne 1) { throw 'Connect one VENTUNO Q, or run this script with -BoardSerial YOUR_BOARD_SERIAL.' }
        $boothSerial = $boothDevices[0]
    }
    $boothDevice = & $boothAdb -s $boothSerial get-state 2>$null
    if ($LASTEXITCODE -ne 0 -or $boothDevice -ne 'device') { throw 'Power VENTUNO Q and connect its USB-C data port to this laptop.' }
    $boothForwards = @(& $boothAdb forward --list | Where-Object { $_ -match '\stcp:7000\s' })
    if ($boothForwards.Count -gt 0) {
        if ($boothForwards.Count -ne 1 -or $boothForwards[0] -ne "$boothSerial tcp:7000 tcp:7000") {
            throw 'Port 7000 is forwarded elsewhere. Close the other service first.'
        }
    } else {
        & $boothAdb -s $boothSerial forward --no-rebind tcp:7000 tcp:7000
        if ($LASTEXITCODE -ne 0) { throw 'Port 7000 is unavailable. Close the application using that port first.' }
    }
    try { $boothStatus = Invoke-RestMethod "$boothUrl/api/status" -TimeoutSec 4 }
    catch { throw 'In App Lab, open AI Object Story Booth and press Run. Wait for startup, then open this launcher again.' }
    if ($boothStatus.app_id -ne 'ai-object-story-booth') { throw 'Another app is running. Stop it in App Lab, then run AI Object Story Booth.' }
    Start-Process $boothUrl
    Write-Host 'Booth opened. Click Open the story booth once, then turn and press the Knob.'
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}

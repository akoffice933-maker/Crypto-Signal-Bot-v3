# Crypto Signal Bot v3 - Upload to VPS (PSCP Version)
# Requires PSCP from PuTTY: https://www.chiark.greenend.org.uk/~sgtatham/putty/latest.html

$VPS_IP = "148.222.186.16"
$VPS_USER = "root"
$VPS_PASSWORD = "6A0nZceRZE"
$LOCAL_PATH = "d:\bot_final"
$REMOTE_PATH = "/tmp/crypto-bot-source"
$ARCHIVE_NAME = "bot_final.zip"
$PSCP_PATH = "C:\Program Files\PuTTY\pscp.exe"  # Измените если PSCP в другом месте

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Crypto Signal Bot v3 - VPS Upload (PSCP)" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# Create archive
Write-Host "[1/4] Creating archive..." -ForegroundColor Green
$archivePath = Join-Path $LOCAL_PATH $ARCHIVE_NAME
if (Test-Path $archivePath) {
    Write-Host "Archive already exists, skipping..." -ForegroundColor Yellow
} else {
    Compress-Archive -Path "$LOCAL_PATH\*" -DestinationPath $archivePath -Force
}

# Check if PSCP exists
if (-not (Test-Path $PSCP_PATH)) {
    Write-Host "PSCP not found at $PSCP_PATH" -ForegroundColor Red
    Write-Host "Please install PuTTY or download pscp.exe" -ForegroundColor Red
    Write-Host "Download from: https://www.chiark.greenend.org.uk/~sgtatham/putty/latest.html" -ForegroundColor Yellow
    exit 1
}

# Upload to VPS using PSCP
Write-Host "[2/4] Uploading to VPS using PSCP..." -ForegroundColor Green
Write-Host "This will take a few minutes..." -ForegroundColor Yellow

# PSCP with password (note: not secure but works for automation)
$pscpArgs = "-pw", $VPS_PASSWORD, $archivePath, "${VPS_USER}@${VPS_IP}:${REMOTE_PATH}/"
& $PSCP_PATH @pscpArgs

if ($LASTEXITCODE -eq 0) {
    Write-Host "[3/4] Upload successful!" -ForegroundColor Green
    
    Write-Host ""
    Write-Host "=========================================" -ForegroundColor Cyan
    Write-Host "  Upload completed!" -ForegroundColor Green
    Write-Host "=========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Next steps on VPS:" -ForegroundColor Yellow
    Write-Host "  1. Open PuTTY or CMD" -ForegroundColor White
    Write-Host "  2. Connect: ssh root@148.222.186.16" -ForegroundColor White
    Write-Host "  3. Password: $VPS_PASSWORD" -ForegroundColor White
    Write-Host "  4. Run: sudo bash ${REMOTE_PATH}/deploy/deploy.sh" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "=========================================" -ForegroundColor Red
    Write-Host "  Upload failed!" -ForegroundColor Red
    Write-Host "=========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Try WinSCP instead:" -ForegroundColor Yellow
    Write-Host "  1. Download: https://winscp.net" -ForegroundColor White
    Write-Host "  2. Connect to: ${VPS_IP}" -ForegroundColor White
    Write-Host "  3. Username: ${VPS_USER}" -ForegroundColor White
    Write-Host "  4. Password: ${VPS_PASSWORD}" -ForegroundColor White
    Write-Host "  5. Copy folder to: ${REMOTE_PATH}" -ForegroundColor White
    Write-Host ""
}

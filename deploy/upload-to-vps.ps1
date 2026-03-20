# Crypto Signal Bot v3 - Upload to VPS
# Run this on your LOCAL computer (Windows)

$VPS_IP = "148.222.186.16"
$VPS_USER = "root"
$VPS_PASSWORD = "6A0nZceRZE"
$LOCAL_PATH = "d:\bot_final"
$REMOTE_PATH = "/tmp/crypto-bot-source"
$ARCHIVE_NAME = "bot_final.zip"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Crypto Signal Bot v3 - VPS Upload" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "VPS: ${VPS_USER}@${VPS_IP}" -ForegroundColor Yellow
Write-Host ""

# Create archive
Write-Host "[1/4] Creating archive..." -ForegroundColor Green
$archivePath = Join-Path $LOCAL_PATH $ARCHIVE_NAME
Compress-Archive -Path "$LOCAL_PATH\*" -DestinationPath $archivePath -Force

# Upload to VPS
Write-Host "[2/4] Uploading to VPS..." -ForegroundColor Green
Write-Host "This will take a few minutes..." -ForegroundColor Yellow

# Use SCP (requires OpenSSH client)
$scpSource = $archivePath
$scpDest = "${VPS_USER}@${VPS_IP}:${REMOTE_PATH}/"
scp $scpSource $scpDest

if ($LASTEXITCODE -eq 0) {
    Write-Host "[3/4] Upload successful!" -ForegroundColor Green
    
    # Extract on VPS
    Write-Host "[4/4] Extracting on VPS..." -ForegroundColor Green
    ssh "${VPS_USER}@${VPS_IP}" "mkdir -p ${REMOTE_PATH} && unzip -o ${REMOTE_PATH}/${ARCHIVE_NAME} -d ${REMOTE_PATH}"
    
    Write-Host ""
    Write-Host "=========================================" -ForegroundColor Cyan
    Write-Host "  Upload completed!" -ForegroundColor Green
    Write-Host "=========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Next steps on VPS:" -ForegroundColor Yellow
    Write-Host "  1. SSH to VPS: ssh ${VPS_USER}@${VPS_IP}" -ForegroundColor White
    Write-Host "  2. Run deploy: sudo bash ${REMOTE_PATH}/deploy/deploy.sh" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "=========================================" -ForegroundColor Red
    Write-Host "  Upload failed!" -ForegroundColor Red
    Write-Host "=========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Alternative: Use WinSCP or FileZilla" -ForegroundColor Yellow
    Write-Host "  - WinSCP: https://winscp.net" -ForegroundColor White
    Write-Host "  - FileZilla: https://filezilla-project.org" -ForegroundColor White
    Write-Host ""
}

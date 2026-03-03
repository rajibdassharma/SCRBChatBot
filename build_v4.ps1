Set-Location 'C:\Users\Rajib Das Sharma\OneDrive\Desktop\SCRBChatBot\YAIA-main\ISDDocumentIntelligence_V4\frontend'
Write-Host "=== Installing dependencies (--legacy-peer-deps) ==="
npm install --legacy-peer-deps 2>&1 | Select-Object -Last 8
Write-Host ""
Write-Host "=== node_modules exists: $(Test-Path 'node_modules') ==="
Write-Host ""
Write-Host "=== Building ==="
npm run build 2>&1
Write-Host "=== Done ==="

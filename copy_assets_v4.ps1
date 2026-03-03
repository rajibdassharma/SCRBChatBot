$v3 = 'C:\Users\Rajib Das Sharma\OneDrive\Desktop\SCRBChatBot\YAIA-main\ISDDocumentIntelligence_V3\frontend\src\assets'
$v4 = 'C:\Users\Rajib Das Sharma\OneDrive\Desktop\SCRBChatBot\YAIA-main\ISDDocumentIntelligence_V4\frontend\src\assets'

Copy-Item "$v3\ksp_logo.png"    "$v4\ksp_logo.png"    -Force
Copy-Item "$v3\banner_logo.png" "$v4\banner_logo.png" -Force

Write-Host "=== V4 assets folder now contains ==="
Get-ChildItem $v4 | Select-Object Name

# Start V4 backend on port 8001 (V3 uses 8000)
Set-Location 'C:\Users\Rajib Das Sharma\OneDrive\Desktop\SCRBChatBot\YAIA-main\ISDDocumentIntelligence_V4\backend'
Write-Host "=== Starting V4 backend on http://localhost:8001 ==="
C:\Anaconda3\anaconda3\python.exe -m uvicorn app:app --reload --port 8001

# Start V5 backend on port 8002 (V4 uses 8001, V3 uses 8000)
Set-Location 'C:\Users\Rajib Das Sharma\OneDrive\Desktop\SCRBChatBot\YAIA-main\ISDDocumentIntelligence_V5\backend'
Write-Host "=== Starting V5 backend on http://localhost:8002 ==="
C:\Anaconda3\anaconda3\python.exe -m uvicorn app:app --reload --port 8002

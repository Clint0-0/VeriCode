# VeriCode Windows Launcher
$HostName = if ($env:VERICODE_HOST) { $env:VERICODE_HOST } else { "127.0.0.1" }
$Port = if ($env:PORT) { $env:PORT } else { "8000" }
& .\.venv\Scripts\python.exe -m uvicorn vericode.api:app --app-dir backend --host $HostName --port $Port


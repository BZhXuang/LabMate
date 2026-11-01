param(
  [int]$ApiPort = 8002,
  [int]$FrontendPort = 5173,
  [switch]$Lightweight
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
  throw "未找到 .venv，请先创建虚拟环境并安装项目依赖。"
}

if ($Lightweight) {
  $env:LOCAL_EMBEDDING_ENABLED = "false"
  $env:CROSS_ENCODER_ENABLED = "false"
  $env:UNSTRUCTURED_ENABLED = "false"
} else {
  $env:LOCAL_EMBEDDING_ENABLED = "true"
  $env:CROSS_ENCODER_ENABLED = "true"
}
$env:HF_HOME = Join-Path $root "data/local/huggingface"
$env:VITE_API_BASE = "http://127.0.0.1:$ApiPort"

Start-Process -FilePath ".venv\Scripts\python.exe" `
  -ArgumentList "-m", "uvicorn", "app.asgi:app", "--host", "127.0.0.1", "--port", "$ApiPort" `
  -WorkingDirectory $root -WindowStyle Hidden

Start-Process -FilePath "frontend\.\node_modules\.bin\vite.cmd" `
  -ArgumentList "--host", "127.0.0.1", "--port", "$FrontendPort" `
  -WorkingDirectory (Join-Path $root "frontend") -WindowStyle Hidden

Write-Host "API:      http://127.0.0.1:$ApiPort"
Write-Host "Frontend: http://127.0.0.1:$FrontendPort"

param(
  [ValidateSet("all", "intent", "retrieval", "generation", "e2e")]
  [string]$Task = "all",
  [switch]$WithLLM
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONIOENCODING = "utf-8"
$env:HF_HOME = Join-Path $root "data/local/huggingface"
$env:HF_HUB_OFFLINE = "1"
$env:TOKENIZERS_PARALLELISM = "false"
$env:OMP_NUM_THREADS = "4"
$env:MKL_NUM_THREADS = "4"
$env:LOCAL_EMBEDDING_ENABLED = "true"
$env:CROSS_ENCODER_ENABLED = "true"
$env:DATABASE_URL = "sqlite+aiosqlite:///:memory:"
$env:LOG_LEVEL = "WARNING"
$arguments = @("-u", "-m", "eval.runner", "--task", $Task, "--require-real-models")
if ($WithLLM) {
  $arguments += "--llm"
} elseif ($Task -in @("generation", "e2e")) {
  throw "generation/e2e 会调用付费模型，请显式添加 -WithLLM。"
}
& ".venv/Scripts/python.exe" @arguments
if ($LASTEXITCODE -ne 0) {
  throw "评测失败，退出码 $LASTEXITCODE。"
}

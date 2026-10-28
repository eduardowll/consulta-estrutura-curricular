param([switch]$LoadData, [int]$Port = 8000)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $projectPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $projectPython)) {
        throw 'Crie o ambiente virtual e instale requirements.txt conforme o README.md.'
    }
    docker compose up -d --wait
    if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel iniciar os bancos. Verifique o Docker Desktop.' }
    if ($LoadData) {
        foreach ($loader in @('load_postgres', 'load_mongo', 'load_neo4j')) {
            & $projectPython "etl/$loader.py" data/processed/tads_2015.json data/processed/tads_2019.json
            if ($LASTEXITCODE -ne 0) { throw "Falha na carga: $loader" }
        }
    }
    Write-Host "Trama: http://127.0.0.1:$Port (Ctrl+C para encerrar a API)"
    & $projectPython -m uvicorn backend.main:app --host 127.0.0.1 --port $Port
}
finally { Pop-Location }

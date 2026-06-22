param(
    [string]$BaseUrl = "http://127.0.0.1:8003",
    [int]$TimeoutSec = 20
)

$ErrorActionPreference = "Stop"

function Test-Endpoint {
    param(
        [string]$Name,
        [scriptblock]$Action
    )

    try {
        & $Action
        Write-Host "[PASS] $Name" -ForegroundColor Green
    } catch {
        Write-Host "[FAIL] $Name -> $($_.Exception.Message)" -ForegroundColor Red
        throw
    }
}

Write-Host "[Retrieval Test] Base URL: $BaseUrl" -ForegroundColor Cyan

$headers = @{ "Content-Type" = "application/json" }

Test-Endpoint -Name "Health check (/v1/health)" -Action {
    $health = Invoke-RestMethod -Uri "$BaseUrl/v1/health" -Method GET -TimeoutSec $TimeoutSec
    if (-not $health.status) { throw "Missing status in health response" }
    Write-Host "  status: $($health.status)" -ForegroundColor DarkGray
}

Test-Endpoint -Name "Definition query (what is SAD?)" -Action {
    $payload = @{
        query = "What is SAD?"
        top_k = 5
        generate_answer = $true
    } | ConvertTo-Json -Depth 5

    $res = Invoke-RestMethod -Uri "$BaseUrl/v1/definition" -Method POST -Headers $headers -Body $payload -TimeoutSec $TimeoutSec

    if ($res.status -ne "success") { throw "Unexpected status: $($res.status)" }
    if (-not $res.final_answer) { throw "Missing final_answer in response" }

    Write-Host "  final_answer: $($res.final_answer)" -ForegroundColor DarkGray
    Write-Host "  answer_source: $($res.answer_source)" -ForegroundColor DarkGray
}

Test-Endpoint -Name "HS code lookup query" -Action {
    $payload = @{
        query = "What is the HS code for chickens?"
        top_k = 3
        generate_answer = $true
    } | ConvertTo-Json -Depth 5

    $res = Invoke-RestMethod -Uri "$BaseUrl/v1/hs-code-lookup" -Method POST -Headers $headers -Body $payload -TimeoutSec $TimeoutSec

    if ($res.status -ne "success") { throw "Unexpected status: $($res.status)" }
    if ($null -eq $res.documents) { throw "Missing documents in response" }

    Write-Host "  documents: $($res.documents.Count)" -ForegroundColor DarkGray
}

Write-Host "[Retrieval Test] All checks passed." -ForegroundColor Green

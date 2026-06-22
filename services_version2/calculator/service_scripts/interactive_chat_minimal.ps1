param(
    [string]$OrchestratorUrl = "http://127.0.0.1:8001",
    [string]$RetrievalUrl = "http://127.0.0.1:8003"
)
$ErrorActionPreference = "Continue"

function Write-C {
    param(
        [string]$msg,
        [string]$color = "White",
        [bool]$noNewline = $false
    )
    if ($noNewline) {
        Write-Host $msg -ForegroundColor $color -NoNewline
    } else {
        Write-Host $msg -ForegroundColor $color
    }
}

function Test-Service {
    param(
        [string]$name,
        [string]$url
    )
    try {
        Invoke-WebRequest "$url/health" -TimeoutSec 3 | Out-Null
        Write-C "OK: $name ($url)" "Green"
        return $true
    } catch {
        try {
            Invoke-WebRequest "$url/health" -TimeoutSec 3 | Out-Null
            Write-C "OK: $name ($url)" "Green"
            return $true
        } catch {
            Write-C "FAIL: $name ($url)" "Red"
            return $false
        }
    }
}

function Send-Query {
    param([string]$query)
    $body = @{ question = $query } | ConvertTo-Json
    try {
        $res = Invoke-WebRequest -Uri "$OrchestratorUrl/query" -Method POST -ContentType "application/json" -Body $body -TimeoutSec 30
        $parsed = $res.Content | ConvertFrom-Json
        return @{ ok = $true; data = $parsed }
    } catch {
        return @{ ok = $false; error = $_.Exception.Message }
    }
}

Clear-Host
Write-C "=====================================" "Cyan"
Write-C "   GDCE CHAT (MINIMAL MODE)" "Cyan"
Write-C "=====================================" "Cyan"
Write-Host ""

Write-C "Checking services..." "Cyan"
$orch = Test-Service "Orchestrator" $OrchestratorUrl
$ret  = Test-Service "Retrieval" $RetrievalUrl
Write-Host ""

if (-not $orch -or -not $ret) {
    Write-C "WARNING: One or more services are down!" "Yellow"
    Write-Host ""
}

Write-C "Type your query or 'exit' to quit." "Cyan"
Write-Host ""

while ($true) {
    Write-C "You: " "Green" $true
    $userInput = Read-Host

    if ([string]::IsNullOrWhiteSpace($userInput)) {
        continue
    }

    if ($userInput -in @("exit", "quit", "q")) {
        Write-C "Goodbye!" "Green"
        break
    }

    Write-C "Sending to Orchestrator..." "Cyan"
    $result = Send-Query $userInput

    if ($result.ok) {
        Write-Host ""
        Write-C "Response:" "Cyan"
        Write-Host "--------------------------------"
        $answer = $result.data.answer
        if ($answer) {
            Write-Host $answer
        } else {
            Write-C "(No answer returned)" "Yellow"
        }
        Write-Host "--------------------------------"
    } else {
        Write-C "ERROR: $($result.error)" "Red"
    }

    Write-Host ""
}
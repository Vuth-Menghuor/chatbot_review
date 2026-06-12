#!/usr/bin/env pwsh
<#
.SYNOPSIS
Test GDCE Trade Query Service v2

.DESCRIPTION
Runs lightweight endpoint checks for Trade Query v2.

.EXAMPLE
.\test_trade_query.ps1

.EXAMPLE
.\test_trade_query.ps1 -ServiceURL "http://localhost:8004" -MaxWaitTime 30
#>

param(
    [string]$ServiceURL = "http://127.0.0.1:8004",
    [int]$MaxWaitTime = 30,
    [int]$TestDelay = 500
)

$green = [System.ConsoleColor]::Green
$red = [System.ConsoleColor]::Red
$yellow = [System.ConsoleColor]::Yellow
$cyan = [System.ConsoleColor]::Cyan

$testResults = @()
$passCount = 0
$failCount = 0

function Write-Header {
    param([string]$Message)
    Write-Host "============================================================" -ForegroundColor $cyan
    Write-Host $Message -ForegroundColor $cyan
    Write-Host "============================================================" -ForegroundColor $cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[+] $Message" -ForegroundColor $green
}

function Write-CustomError {
    param([string]$Message)
    Write-Host "[-] $Message" -ForegroundColor $red
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[!] $Message" -ForegroundColor $yellow
}

function Write-Info {
    param([string]$Message)
    Write-Host "[*] $Message" -ForegroundColor $cyan
}

function Write-TestResult {
    param(
        [string]$TestName,
        [bool]$Passed,
        [string]$Details = ""
    )

    if ($Passed) {
        Write-Success $TestName
        $script:passCount += 1
    }
    else {
        Write-CustomError $TestName
        if ($Details) {
            Write-Host "   Details: $Details" -ForegroundColor $yellow
        }
        $script:failCount += 1
    }

    $script:testResults += @{
        Name = $TestName
        Passed = $Passed
        Details = $Details
    }
}

function Wait-ForService {
    param([string]$URL, [int]$MaxWaitSeconds)

    Write-Info "Waiting for service readiness (timeout: ${MaxWaitSeconds}s)..."
    $sw = [System.Diagnostics.Stopwatch]::StartNew()

    while ($sw.Elapsed.TotalSeconds -lt $MaxWaitSeconds) {
        try {
            $response = Invoke-WebRequest -Uri "$URL/health" -TimeoutSec 2 -ErrorAction Stop -UseBasicParsing
            if ($response.StatusCode -eq 200) {
                Write-Success "Service is ready"
                return $true
            }
        }
        catch {
            # wait
        }

        Start-Sleep -Milliseconds 500
        Write-Host "." -NoNewline -ForegroundColor $cyan
    }

    Write-Host ""
    return $false
}

function Invoke-TestGet {
    param([string]$Path, [string]$TestName)

    try {
        $response = Invoke-WebRequest -Uri "$ServiceURL$Path" -Method GET -TimeoutSec 10 -UseBasicParsing
        if ($response.StatusCode -eq 200) {
            $json = $response.Content | ConvertFrom-Json
            Write-TestResult $TestName $true "HTTP 200"
            return $json
        }
        Write-TestResult $TestName $false "HTTP $($response.StatusCode)"
    }
    catch {
        Write-TestResult $TestName $false $_.Exception.Message
    }
    return $null
}

function Invoke-TestPost {
    param([string]$Path, [hashtable]$Body, [string]$TestName)

    try {
        $payload = $Body | ConvertTo-Json
        $response = Invoke-WebRequest -Uri "$ServiceURL$Path" -Method POST -ContentType "application/json" -Body $payload -TimeoutSec 15 -UseBasicParsing

        if ($response.StatusCode -eq 200) {
            $json = $response.Content | ConvertFrom-Json
            Write-TestResult $TestName $true "HTTP 200"
            return $json
        }
        Write-TestResult $TestName $false "HTTP $($response.StatusCode)"
    }
    catch {
        Write-TestResult $TestName $false $_.Exception.Message
    }
    return $null
}

Write-Header "GDCE Trade Query Service v2 - Test Script"
Write-Info "Service URL: $ServiceURL"
Write-Host ""

if (-not (Wait-ForService -URL $ServiceURL -MaxWaitSeconds $MaxWaitTime)) {
    Write-CustomError "Service not ready within $MaxWaitTime seconds"
    Write-Info "Start it first with: .\start_trade_query.ps1"
    exit 1
}

Write-Host ""
Start-Sleep -Milliseconds $TestDelay

Write-Header "Endpoint Checks"

# 1) Health
$health = Invoke-TestGet -Path "/health" -TestName "GET /health"
if ($health) {
    Write-Info "Health status: $($health.status), DB: $($health.database)"
}

Start-Sleep -Milliseconds $TestDelay

# 2) Extract params with month
$extractBody = @{
    question = "Export from Cambodia to US by air in March 2022"
}
$extract = Invoke-TestPost -Path "/extract-params" -Body $extractBody -TestName "POST /extract-params"
if ($extract) {
    $ok = ($extract.origin_country -eq "KH" -and $extract.destination_country -eq "US" -and $extract.year -eq 2022 -and $extract.month -eq 3)
    Write-TestResult "Extracted expected key params" $ok "origin=$($extract.origin_country), dest=$($extract.destination_country), year=$($extract.year), month=$($extract.month)"
}

Start-Sleep -Milliseconds $TestDelay

# 3) Query
$queryBody = @{
    question = "Trade between Cambodia and US via air in 2022 month 3"
}
$query = Invoke-TestPost -Path "/query" -Body $queryBody -TestName "POST /query"
if ($query) {
    $hasFields = ($null -ne $query.status -and $null -ne $query.count -and $null -ne $query.query_params)
    Write-TestResult "Query response has expected envelope" $hasFields "status=$($query.status), count=$($query.count)"
}

Start-Sleep -Milliseconds $TestDelay

# 4) Records browse
$records = Invoke-TestGet -Path "/records?limit=5" -TestName "GET /records?limit=5"
if ($records) {
    $hasFields = ($null -ne $records.status -and $null -ne $records.data -and $null -ne $records.count)
    Write-TestResult "Records response has expected envelope" $hasFields "count=$($records.count)"
}

Write-Host ""
Write-Header "Test Summary"
Write-Info "Passed: $passCount"
Write-Info "Failed: $failCount"
Write-Info "Total : $($passCount + $failCount)"

if ($failCount -eq 0) {
    Write-Success "All checks passed"
    exit 0
}
else {
    Write-Warning "Some checks failed"
    exit 1
}

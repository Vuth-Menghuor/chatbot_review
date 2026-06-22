# Test GDCE Orchestrator Service v2
# This script runs comprehensive tests to verify the orchestrator service is working correctly

param(
    [string]$ServiceURL = "http://localhost:8001",
    [int]$MaxWaitTime = 30,
    [int]$TestDelay = 1000
)

# Colors for output
$green = [System.ConsoleColor]::Green
$red = [System.ConsoleColor]::Red
$yellow = [System.ConsoleColor]::Yellow
$cyan = [System.ConsoleColor]::Cyan

# Global test results
$testResults = @()
$passCount = 0
$failCount = 0

# =============================================================================
# FUNCTIONS
# =============================================================================

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
        Write-Success "$TestName"
        $script:passCount += 1
    }
    else {
        Write-CustomError "$TestName"
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
    param(
        [string]$URL,
        [int]$MaxWaitSeconds
    )
    
    Write-Info "Waiting for service to be ready (timeout: ${MaxWaitSeconds}s)..."
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    
    while ($sw.Elapsed.TotalSeconds -lt $MaxWaitSeconds) {
        try {
            $response = Invoke-WebRequest -Uri "$URL/health" -TimeoutSec 2 -ErrorAction Stop
            if ($response.StatusCode -eq 200) {
                Write-Success "Service is ready!"
                return $true
            }
        }
        catch {
            # Service not ready yet
        }
        
        Start-Sleep -Milliseconds 500
        Write-Host "." -NoNewline -ForegroundColor $cyan
    }
    
    Write-Host ""
    return $false
}

function Invoke-TestQuery {
    param(
        [string]$TestName,
        [string]$Question,
        [string]$ExpectedIntent = ""
    )
    
    try {
        $body = @{
            question = $Question
            session_id = "test_session_$(Get-Random)"
        } | ConvertTo-Json
        
        $response = Invoke-WebRequest `
            -Uri "$ServiceURL/query" `
            -Method POST `
            -ContentType "application/json" `
            -Body $body `
            -TimeoutSec 10
        
        $data = $response.Content | ConvertFrom-Json
        
        if ($response.StatusCode -eq 200 -and $data.answer) {
            $intentMatch = $true
            if ($ExpectedIntent -and $data.intent -ne $ExpectedIntent) {
                $intentMatch = $false
            }
            
            if ($intentMatch) {
                $details = "Intent: $($data.intent) | Latency: $($data.latency_ms)ms"
                Write-TestResult $TestName $true $details
            }
            else {
                Write-TestResult $TestName $false "Expected intent '$ExpectedIntent' but got '$($data.intent)'"
            }
        }
        else {
            Write-TestResult $TestName $false "Empty response"
        }
    }
    catch {
        Write-TestResult $TestName $false $_.Exception.Message
    }
}

function Test-Endpoint {
    param(
        [string]$Endpoint,
        [string]$Method = "GET",
        [hashtable]$Body = $null,
        [string]$TestName = ""
    )
    
    if (-not $TestName) {
        $TestName = "$Method $Endpoint"
    }
    
    try {
        if ($Method -eq "GET") {
            $response = Invoke-WebRequest `
                -Uri "$ServiceURL$Endpoint" `
                -Method GET `
                -TimeoutSec 5
        }
        else {
            $jsonBody = $Body | ConvertTo-Json
            $response = Invoke-WebRequest `
                -Uri "$ServiceURL$Endpoint" `
                -Method POST `
                -ContentType "application/json" `
                -Body $jsonBody `
                -TimeoutSec 5
        }
        
        if ($response.StatusCode -eq 200) {
            Write-TestResult $TestName $true "HTTP 200"
            return $response.Content | ConvertFrom-Json
        }
        else {
            Write-TestResult $TestName $false "HTTP $($response.StatusCode)"
        }
    }
    catch {
        Write-TestResult $TestName $false $_.Exception.Message
    }
    
    return $null
}

# =============================================================================
# MAIN TEST SUITE
# =============================================================================

Write-Header "GDCE Orchestrator Service v2 - Test Suite"
Write-Info "Service URL: $ServiceURL"
Write-Host ""

# =============================================================================
# STEP 1: WAIT FOR SERVICE
# =============================================================================

Write-Info "Waiting for service to start..."
if (-not (Wait-ForService $ServiceURL $MaxWaitTime)) {
    Write-CustomError "Service did not start within $MaxWaitTime seconds"
    Write-Header "Test Results"
    Write-CustomError "Cannot proceed with tests - service is not running"
    Write-Info "Start the service with: .\start_orchestrator_v2.ps1"
    exit 1
}

Write-Host ""
Start-Sleep -Milliseconds $TestDelay

# =============================================================================
# STEP 2: ENDPOINT TESTS
# =============================================================================

Write-Header "Endpoint Tests"

# Test 2.1: Health Check
Write-Info "Testing /health endpoint..."
$healthData = Test-Endpoint "/health" "GET" @{} "GET /health"
if ($healthData) {
    if ($healthData.status) {
        Write-Info "   Orchestrator Status: $($healthData.status)"
        if ($healthData.services) {
            foreach ($service in $healthData.services.PSObject.Properties) {
                Write-Info "   - $($service.Name): $($service.Value.status)"
            }
        }
    }
}
Write-Host ""

# Test 2.2: Service Info
Write-Info "Testing /info endpoint..."
$infoData = Test-Endpoint "/info" "GET" @{} "GET /info"
if ($infoData) {
    Write-Info "   Service: $($infoData.service)"
    Write-Info "   Version: $($infoData.version)"
    Write-Info "   Capabilities: $($infoData.capabilities.Count) items"
}
Write-Host ""

# Test 2.3: Status
Write-Info "Testing /status endpoint..."
$statusData = Test-Endpoint "/status" "GET" @{} "GET /status"
if ($statusData) {
    Write-Info "   Service: $($statusData.service)"
    Write-Info "   Status: $($statusData.status)"
}
Write-Host ""

# =============================================================================
# STEP 3: INTENT DETECTION TESTS
# =============================================================================

Write-Header "Intent Detection Tests (Using /query/explain)"

# Test 3.1: Calculation intent
Write-Info "Testing CALCULATION intent..."
try {
    $body = @{ question = "Calculate tax for HS 0102.29.11 CIF $800 from China" } | ConvertTo-Json
    $response = Invoke-WebRequest `
        -Uri "$ServiceURL/query/explain" `
        -Method POST `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 5
    
    $data = $response.Content | ConvertFrom-Json
    if ($data.intent -eq "calculation") {
        Write-TestResult "Intent: CALCULATION" $true "Detected correctly"
    }
    else {
        Write-TestResult "Intent: CALCULATION" $false "Expected 'calculation' but got '$($data.intent)'"
    }
}
catch {
    Write-TestResult "Intent: CALCULATION" $false $_.Exception.Message
}
Write-Host ""

# Test 3.2: HS Code Lookup intent
Write-Info "Testing HS_CODE_LOOKUP intent..."
try {
    $body = @{ question = "What is the HS code for chickens?" } | ConvertTo-Json
    $response = Invoke-WebRequest `
        -Uri "$ServiceURL/query/explain" `
        -Method POST `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 5
    
    $data = $response.Content | ConvertFrom-Json
    if ($data.intent -eq "hs_code_lookup") {
        Write-TestResult "Intent: HS_CODE_LOOKUP" $true "Detected correctly"
    }
    else {
        Write-TestResult "Intent: HS_CODE_LOOKUP" $false "Expected 'hs_code_lookup' but got '$($data.intent)'"
    }
}
catch {
    Write-TestResult "Intent: HS_CODE_LOOKUP" $false $_.Exception.Message
}
Write-Host ""

# Test 3.3: Definition intent
Write-Info "Testing DEFINITION intent..."
try {
    $body = @{ question = "Define CIF in customs terminology" } | ConvertTo-Json
    $response = Invoke-WebRequest `
        -Uri "$ServiceURL/query/explain" `
        -Method POST `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 5
    
    $data = $response.Content | ConvertFrom-Json
    if ($data.intent -eq "definition") {
        Write-TestResult "Intent: DEFINITION" $true "Detected correctly"
    }
    else {
        Write-TestResult "Intent: DEFINITION" $false "Expected 'definition' but got '$($data.intent)'"
    }
}
catch {
    Write-TestResult "Intent: DEFINITION" $false $_.Exception.Message
}
Write-Host ""

# =============================================================================
# STEP 4: QUERY PROCESSING TESTS
# =============================================================================

Write-Header "Query Processing Tests (Using /query)"

# Test 4.1: Calculation Query
Write-Info "Processing CALCULATION query..."
Invoke-TestQuery "Query: Calculate tax" `
    "Calculate import tax for HS 0102.29.11 CIF $800 from China" `
    "calculation"
Write-Host ""

# Test 4.2: HS Code Lookup Query
Write-Info "Processing HS_CODE_LOOKUP query..."
Invoke-TestQuery "Query: HS code lookup" `
    "What is the HS code for chickens?" `
    "hs_code_lookup"
Write-Host ""

# Test 4.3: Definition Query
Write-Info "Processing DEFINITION query..."
Invoke-TestQuery "Query: Definition" `
    "Define CIF in customs" `
    "definition"
Write-Host ""

# Test 4.4: General Query
Write-Info "Processing GENERAL query..."
Invoke-TestQuery "Query: General information" `
    "Tell me about customs procedures" `
    "general"
Write-Host ""

# =============================================================================
# STEP 5: SECURITY TESTS
# =============================================================================

Write-Header "Security & Validation Tests"

# Test 5.1: Injection Detection
Write-Info "Testing injection detection..."
try {
    $body = @{ 
        question = "DROP TABLE users; --"
        session_id = "test_injection"
    } | ConvertTo-Json
    
    $response = Invoke-WebRequest `
        -Uri "$ServiceURL/query" `
        -Method POST `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 5
    
    $data = $response.Content | ConvertFrom-Json
    if ($data.status -eq "refused" -or $data.intent -eq "refusal") {
        Write-TestResult "SQL Injection Detection" $true "Injection attempt was blocked"
    }
    else {
        Write-TestResult "SQL Injection Detection" $false "Injection attempt was not blocked"
    }
}
catch {
    Write-TestResult "SQL Injection Detection" $false $_.Exception.Message
}
Write-Host ""

# Test 5.2: Out-of-Scope Detection
Write-Info "Testing out-of-scope detection..."
try {
    $body = @{ 
        question = "Tell me about basketball"
        session_id = "test_outofscope"
    } | ConvertTo-Json
    
    $response = Invoke-WebRequest `
        -Uri "$ServiceURL/query" `
        -Method POST `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 5
    
    $data = $response.Content | ConvertFrom-Json
    # Should either refuse or return general info
    if ($response.StatusCode -eq 200) {
        Write-TestResult "Out-of-Scope Detection" $true "Request was processed (may have been routed to general intent)"
    }
    else {
        Write-TestResult "Out-of-Scope Detection" $false "Unexpected status code: $($response.StatusCode)"
    }
}
catch {
    Write-TestResult "Out-of-Scope Detection" $false $_.Exception.Message
}
Write-Host ""

# =============================================================================
# STEP 6: BACKEND SERVICE HEALTH
# =============================================================================

Write-Header "Backend Service Health Check"

# Test 6.1: Calculator Service
Write-Info "Checking Calculator Service (8002)..."
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8002/health" -TimeoutSec 3 -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        Write-TestResult "Calculator Service Health" $true "HTTP 200 - Service is healthy"
    }
    else {
        Write-TestResult "Calculator Service Health" $false "HTTP $($response.StatusCode)"
    }
}
catch {
    Write-TestResult "Calculator Service Health" $false "Not responding - Is it running on port 8002?"
}
Write-Host ""

# Test 6.2: Retrieval Service
Write-Info "Checking Retrieval Service (8003)..."
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8003/health" -TimeoutSec 3 -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        Write-TestResult "Retrieval Service Health" $true "HTTP 200 - Service is healthy"
    }
    else {
        Write-TestResult "Retrieval Service Health" $false "HTTP $($response.StatusCode)"
    }
}
catch {
    Write-TestResult "Retrieval Service Health" $false "Not responding - Is it running on port 8003?"
}
Write-Host ""

# Test 6.3: Trade Data Service
Write-Info "Checking Trade Data Service (8004)..."
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8004/health" -TimeoutSec 3 -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        Write-TestResult "Trade Data Service Health" $true "HTTP 200 - Service is healthy"
    }
    else {
        Write-TestResult "Trade Data Service Health" $false "HTTP $($response.StatusCode)"
    }
}
catch {
    Write-TestResult "Trade Data Service Health" $false "Not responding - Is it running on port 8004?"
}
Write-Host ""

# =============================================================================
# RESULTS SUMMARY
# =============================================================================

Write-Header "Test Results Summary"

Write-Host ""
Write-Info "Total Tests: $($passCount + $failCount)"
Write-Success "Passed: $passCount"
Write-CustomError "Failed: $failCount"
Write-Host ""

if ($failCount -eq 0) {
    Write-Header "SUCCESS - ALL TESTS PASSED"
    Write-Success "The Orchestrator Service v2 is working correctly!"
    Write-Info "API Documentation: http://localhost:8001/docs"
    exit 0
}
else {
    Write-Header "WARNING - SOME TESTS FAILED"
    Write-Warning "Please check the errors above"
    Write-Info "Common issues:"
    Write-Info "  - Backend services not running (Calculator, Retrieval, Trade Data)"
    Write-Info "  - Network connectivity issues"
    Write-Info "  - Configuration problems"
    Write-Info "  - Check service logs for more details"
    exit 1
}

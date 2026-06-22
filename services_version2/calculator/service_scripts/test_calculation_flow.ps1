#Requires -Version 5.1
<#
.SYNOPSIS
    Test orchestrator integration with calculator and trade_query

.DESCRIPTION
    Sends test calculation queries and a trade query to the orchestrator and verifies responses

.EXAMPLE
    .\test_calculation_flow.ps1
#>

param(
    [int]$OrchestratorPort = 8001,
    [int]$CalculatorPort = 8002,
    [int]$TradeQueryPort = 8004,
    [int]$Timeout = 5
)

# Color codes
$Colors = @{
    Reset = "`e[0m"
    Green = "`e[32m"
    Red = "`e[31m"
    Yellow = "`e[33m"
    Blue = "`e[34m"
    Cyan = "`e[36m"
}

function Write-Status { param([string]$Text, [string]$Status = "info") 
    $color = @{info="Cyan"; success="Green"; error="Red"; warning="Yellow"}[$Status]
    Write-Host "$($Colors[$color])>>> $Text$($Colors.Reset)"
}

function Test-Service {
    param(
        [string]$Url,
        [string]$ServiceName,
        [int]$Timeout
    )
    
    try {
        $response = Invoke-WebRequest -Uri $Url -Method GET -TimeoutSec $Timeout -SkipHttpErrorCheck
        if ($response.StatusCode -eq 200) {
            Write-Status "$ServiceName is RUNNING on $Url" "success"
            return $true
        } else {
            Write-Status "$ServiceName returned status $($response.StatusCode)" "warning"
            return $false
        }
    } catch {
        Write-Status "$ServiceName is NOT RUNNING ($($_.Exception.Message))" "error"
        return $false
    }
}

function Send-Query {
    param(
        [string]$Query,
        [string]$Url,
        [int]$Timeout
    )
    
    Write-Host ""
    Write-Status "Query: $Query" "info"
    
    $body = @{
        question = $Query
    } | ConvertTo-Json
    
    try {
        $response = Invoke-WebRequest `
            -Uri $Url `
            -Method POST `
            -ContentType 'application/json' `
            -Body $body `
            -TimeoutSec $Timeout `
            -SkipHttpErrorCheck
        
        if ($response.StatusCode -eq 200) {
            Write-Status "✓ Response received (Status: $($response.StatusCode))" "success"
            $result = $response.Content | ConvertFrom-Json
            
            # Display key information
            if ($result.intent) {
                Write-Host "$($Colors.Cyan)Intent detected: $($result.intent)$($Colors.Reset)"
            }
            
            if ($result.calculation_result) {
                $calc = $result.calculation_result
                Write-Host "$($Colors.Green)Calculation Result:$($Colors.Reset)"
                if ($calc.total_tax) {
                    Write-Host "  Total Tax: $($calc.total_tax) $($calc.currency)"
                }
                if ($calc.duty_amount) {
                    Write-Host "  Duty Amount: $($calc.duty_amount)"
                }
                if ($calc.hs_code) {
                    Write-Host "  HS Code: $($calc.hs_code)"
                }
            }
            
            if ($result.error) {
                Write-Status "Error in response: $($result.error)" "error"
            }
            
            if ($result.message) {
                Write-Host "$($Colors.Blue)Message: $($result.message)$($Colors.Reset)"
            }
            
            return $true
        } else {
            Write-Status "✗ Request failed with status $($response.StatusCode)" "error"
            Write-Host "Response: $($response.Content)"
            return $false
        }
    } catch {
        Write-Status "✗ Request exception: $($_.Exception.Message)" "error"
        return $false
    }
}

# Main execution
Write-Host ""
Write-Host "$($Colors.Cyan)===============================================================$($Colors.Reset)"
Write-Host "$($Colors.Cyan)= GDCE Orchestrator + Calculator + Trade Query Test =$($Colors.Reset)"
Write-Host "$($Colors.Cyan)===============================================================$($Colors.Reset)"

# Check service availability
Write-Host ""
Write-Status "Step 1: Verifying service availability..." "info"

$orchestrator_running = Test-Service "http://localhost:$OrchestratorPort/health" "Orchestrator" $Timeout
$calculator_running = Test-Service "http://localhost:$CalculatorPort/health" "Calculator" $Timeout
$trade_query_running = Test-Service "http://localhost:$TradeQueryPort/health" "Trade Query" $Timeout

if (-not $orchestrator_running -or -not $calculator_running -or -not $trade_query_running) {
    Write-Status "Services not available. Please start them first:" "error"
    Write-Host "  $($Colors.Yellow).\service_scripts\orchestrator_scripts\start_orchestrator_v2.ps1$($Colors.Reset)"
    Write-Host "  $($Colors.Yellow).\service_scripts\calculator_scripts\start_calculator_v2.ps1$($Colors.Reset)"
    Write-Host "  $($Colors.Yellow).\service_scripts\trade_scripts\start_trade_query.ps1$($Colors.Reset)"
    exit 1
}

# Test queries
Write-Host ""
Write-Status "Step 2: Sending test calculation queries..." "info"

$testQueries = @(
    "Calculate import duty for HS 0102.29.11 CIF $800 from China",
    "What is the tax for live cattle from Thailand worth 5000 USD?",
    "Duty rate for HS code 0702.00.00 value 1500 USD from Vietnam",
    "Import tax calculation: HS 0406.90.99, CIF $2000, origin: Germany"
)

$successCount = 0
$failureCount = 0

foreach ($query in $testQueries) {
    if (Send-Query $query "http://localhost:$OrchestratorPort/query" $Timeout) {
        $successCount++
    } else {
        $failureCount++
    }
    Start-Sleep -Milliseconds 500
}

# Trade query path test via orchestrator
Write-Host ""
Write-Status "Step 3: Sending trade query through orchestrator..." "info"

$tradeQuery = "Show trade between Cambodia and US via air in March 2022"
if (Send-Query $tradeQuery "http://localhost:$OrchestratorPort/query" $Timeout) {
    $successCount++
}
else {
    $failureCount++
}

# Summary
Write-Host ""
Write-Host "$($Colors.Cyan)===============================================================$($Colors.Reset)"
Write-Status "Test Summary: $successCount successful, $failureCount failed" $(if ($failureCount -eq 0) { "success" } else { "warning" })
Write-Host "$($Colors.Cyan)===============================================================$($Colors.Reset)"

if ($failureCount -eq 0) {
    Write-Status "✓ All tests passed! Orchestrator ↔ Calculator ↔ Trade Query integration is working." "success"
    exit 0
} else {
    Write-Status "✗ Some tests failed. Check the details above." "error"
    exit 1
}

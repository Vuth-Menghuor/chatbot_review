#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Interactive Chat Script - GDCE ChatBot Orchestrator + Calculator + Trade Query Service v2
    
.DESCRIPTION
    Provides an interactive console for testing the GDCE Orchestrator, Calculator,
    and Trade Query services.
    Queries are sent to the Orchestrator (port 8001), which routes to Calculator (port 8002)
    or Trade Query (port 8004) based on detected intent.
    
.PARAMETER OrchestratorUrl
    URL of the Orchestrator service (default: http://127.0.0.1:8001)
    
.PARAMETER CalculatorUrl
    URL of the Calculator service (default: http://127.0.0.1:8002)

.PARAMETER TradeQueryUrl
    URL of the Trade Query service (default: http://127.0.0.1:8004)
    
.EXAMPLE
    .\interactive_chat.ps1
    
.NOTES
    Version: 1.1
    Date: 2026-04-03
    Author: GDCE Development Team
#>

param(
    [string]$OrchestratorUrl = "http://127.0.0.1:8001",
    [string]$CalculatorUrl = "http://127.0.0.1:8002",
    [string]$RetrievalUrl = "http://127.0.0.1:8003",
    [string]$TradeQueryUrl = "http://127.0.0.1:8004",
    [string]$SessionId = ""
)

# =====================================================================
# CONFIGURATION
# =====================================================================
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

# Color definitions
$colors = @{
    Header    = "Cyan"
    Prompt    = "Green"
    Intent    = "Yellow"
    Success   = "Green"
    Warning   = "Yellow"
    Error     = "Red"
    Info      = "Cyan"
    Latency   = "Magenta"
    Query     = "White"
    Response  = "Gray"
}

# =====================================================================
# HELPER FUNCTIONS
# =====================================================================

function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White",
        [switch]$NoNewline
    )

    if ($NoNewline) {
        Write-Host $Message -ForegroundColor $Color -NoNewline
    }
    else {
        Write-Host $Message -ForegroundColor $Color
    }
}

function Write-Header {
    param([string]$Title)
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor $colors.Header
    Write-Host $Title -ForegroundColor $colors.Header -NoNewline
    Write-Host (" " * (70 - $Title.Length - 1)) -ForegroundColor $colors.Header
    Write-Host ("=" * 70) -ForegroundColor $colors.Header
}

function Test-ServiceHealth {
    param([string]$ServiceName, [string]$Url)
    
    try {
        # Try /health first
        try {
            $response = Invoke-WebRequest -Uri "$Url/health" -Method GET -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
            if ($response.StatusCode -eq 200) {
                Write-ColorOutput ('✓ {0} is running on {1}' -f $ServiceName, $Url) $colors.Success
                return $true
            }
        }
        catch {
            # If 404, that's expected - try /v1/health
            if ($_.Exception.Response.StatusCode -ne 404) {
                throw
            }
        }
        
        # Try /v1/health as fallback (for Retrieval service)
        try {
            $response = Invoke-WebRequest -Uri "$Url/v1/health" -Method GET -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
            if ($response.StatusCode -eq 200) {
                Write-ColorOutput ('✓ {0} is running on {1}' -f $ServiceName, $Url) $colors.Success
                return $true
            }
        }
        catch {
            # Service is not responding properly
            throw
        }
    }
    catch {
        Write-ColorOutput ('✗ {0} is not accessible at {1}' -f $ServiceName, $Url) $colors.Error
        Write-ColorOutput ('  Error: {0}' -f $_.Exception.Message) $colors.Error
        return $false
    }
}

function Send-Query {
    param(
        [string]$Query,
        [string]$Url,
        [string]$SessionId
    )
    
    $body = @{
        question = $Query
        session_id = $SessionId
    } | ConvertTo-Json
    
    try {
        $startTime = Get-Date
        $response = Invoke-WebRequest `
            -Uri "$Url/query" `
            -Method POST `
            -ContentType "application/json" `
            -Body $body `
            -ErrorAction Stop `
            -TimeoutSec 60 `
            -UseBasicParsing
        
        $endTime = Get-Date
        $latency = ($endTime - $startTime).TotalMilliseconds
        
        $result = $response.Content | ConvertFrom-Json
        return @{
            Success = $true
            Data = $result
            Latency = $latency
            StatusCode = $response.StatusCode
        }
    }
    catch [System.Net.WebException] {
        $errorMsg = $_.Exception.Message
        if ($_.Exception.Response) {
            $errorMsg += " (HTTP " + $_.Exception.Response.StatusCode + ")"
        }
        return @{
            Success = $false
            Error = $errorMsg
            Latency = 0
        }
    }
    catch {
        return @{
            Success = $false
            Error = $_.Exception.Message
            Latency = 0
        }
    }
}

function Format-Response {
    param($ResponseData, [double]$Latency)
    
    Write-Host ''
    Write-ColorOutput 'RESPONSE' $colors.Header
    Write-ColorOutput ('-' * 70) $colors.Header
    
    # Display intent
    if ($ResponseData.PSObject.Properties.Name -contains 'intent') {
        $intent = $ResponseData.intent
        Write-ColorOutput ('Intent: {0}' -f $intent) $colors.Intent
    }
    
    # Display status
    if ($ResponseData.PSObject.Properties.Name -contains 'status') {
        $status = $ResponseData.status
        $statusColor = if ($status -eq 'completed') { $colors.Success } elseif ($status -eq 'success') { $colors.Success } else { $colors.Warning }
        Write-ColorOutput ('Status: {0}' -f $status) $statusColor
    }
    
    # Display answer (preserve full formatting for multi-line content)
    if ($ResponseData.PSObject.Properties.Name -contains 'answer') {
        $answer = $ResponseData.answer
        if ([string]::IsNullOrEmpty($answer) -or $answer -eq '') {
            Write-ColorOutput 'Answer: (No output)' $colors.Warning
        } else {
            Write-Host ''
            # Print answer without additional formatting to preserve original formatting
            Write-Host $answer
            Write-Host ''
        }
    }
    
    # Display request ID if available
    if ($ResponseData.PSObject.Properties.Name -contains 'request_id') {
        Write-ColorOutput ('Request ID: {0}' -f $ResponseData.request_id) $colors.Info
    }
    
    # Display latency
    Write-ColorOutput ('Latency: {0:F2} ms' -f $Latency) $colors.Latency
    Write-ColorOutput ('-' * 70) $colors.Header
}

function Show-Usage {
    Write-Host ''
    Write-ColorOutput 'EXAMPLE QUERIES:' $colors.Header
    Write-Host ''
    Write-ColorOutput 'Calculation Intent (Most Common):' $colors.Intent
    Write-ColorOutput '  "Calculate import duty for HS 0102.29.11 CIF $800 from China"' $colors.Query
    Write-ColorOutput '  "What is the tax for HS 8471.30.00 worth $5000 USD from Thailand?"' $colors.Query
    Write-ColorOutput '  "Import tax calculation: HS code 0702.00.00, CIF value $1200, origin Vietnam"' $colors.Query
    Write-Host ''

    Write-ColorOutput 'Trade Query Intent (routes to Trade Query service):' $colors.Intent
    Write-ColorOutput '  "Show trade between Cambodia and US via air in March 2022"' $colors.Query
    Write-ColorOutput '  "Export from Cambodia to Thailand by sea in 2023 month 8"' $colors.Query
    Write-ColorOutput '  "Trade volume for HS 8517 between Vietnam and Singapore"' $colors.Query
    Write-Host ''
    
    Write-ColorOutput 'HS Code Lookup:' $colors.Intent
    Write-ColorOutput '  "What is the HS code for live cattle?"' $colors.Query
    Write-ColorOutput '  "Find HS code for ceramic tiles"' $colors.Query
    Write-Host ''
    
    Write-ColorOutput 'Definition/General Queries:' $colors.Intent
    Write-ColorOutput '  "What does CIF mean in trade?"' $colors.Query
    Write-ColorOutput '  "Define FOB value"' $colors.Query
    Write-ColorOutput '  "Tell me about Cambodia customs regulations"' $colors.Query
    Write-Host ''
}

function Show-Help {
    Write-Host ''
    Write-ColorOutput 'COMMANDS:' $colors.Header
    Write-ColorOutput '  help      - Show this help message' $colors.Info
    Write-ColorOutput '  examples  - Show example queries' $colors.Info
    Write-ColorOutput '  status    - Check service status' $colors.Info
    Write-ColorOutput '  session   - Show current session ID' $colors.Info
    Write-ColorOutput '  newsession - Generate a new session ID' $colors.Info
    Write-ColorOutput '  session <id> - Set a custom session ID' $colors.Info
    Write-ColorOutput '  clear     - Clear screen' $colors.Info
    Write-ColorOutput '  exit/quit - Exit the chat' $colors.Info
    Write-Host ''
    Write-ColorOutput 'TIPS:' $colors.Header
    Write-ColorOutput '  • Just type your query naturally and press Enter' $colors.Info
    Write-ColorOutput '  • For calculations, include: HS code, CIF value, currency, origin country' $colors.Info
    Write-ColorOutput '  • Example: "Calculate import duty for HS 0102.29.11 CIF $800 from China"' $colors.Query
    Write-ColorOutput '  • You can continue to ask more questions after each response' $colors.Info
    Write-Host ''
}

# =====================================================================
# MAIN PROGRAM
# =====================================================================

if ([string]::IsNullOrWhiteSpace($SessionId)) {
    $SessionId = "chat-" + [guid]::NewGuid().ToString("N").Substring(0, 12)
}

$script:CurrentSessionId = $SessionId

Clear-Host
Write-Header 'GDCE ChatBot Interactive Chat v2.0'

# Display welcome
Write-ColorOutput 'Welcome to the GDCE ChatBot Interactive Interface!' $colors.Header
Write-ColorOutput 'Querying Orchestrator (8001) -> Calculator (8002) / Retrieval (8003) / Trade Query (8004)' $colors.Info
Write-ColorOutput ('Session ID: {0}' -f $script:CurrentSessionId) $colors.Info
Write-Host ''

# Test service health
Write-ColorOutput 'Checking service connectivity...' $colors.Info
$orchestratorOK = Test-ServiceHealth 'Orchestrator Service' $OrchestratorUrl
$calculatorOK = Test-ServiceHealth 'Calculator Service' $CalculatorUrl
$retrievalOK = Test-ServiceHealth 'Retrieval Service' $RetrievalUrl
$tradeQueryOK = Test-ServiceHealth 'Trade Query Service' $TradeQueryUrl
Write-Host ''

if (-not $orchestratorOK -or -not $calculatorOK -or -not $retrievalOK -or -not $tradeQueryOK) {
    Write-ColorOutput 'WARNING: One or more services are not available!' $colors.Warning
    Write-ColorOutput 'Please ensure all services are running:' $colors.Warning
    Write-ColorOutput ('  • Orchestrator: {0}' -f $OrchestratorUrl) $colors.Warning
    Write-ColorOutput ('  • Calculator:   {0}' -f $CalculatorUrl) $colors.Warning
    Write-ColorOutput ('  • Retrieval:    {0}' -f $RetrievalUrl) $colors.Warning
    Write-ColorOutput ('  • Trade Query:  {0}' -f $TradeQueryUrl) $colors.Warning
    Write-Host ''
}

Show-Usage
Show-Help

# =====================================================================
# INTERACTIVE LOOP
# =====================================================================
$queryCount = 0

while ($true) {
    Write-ColorOutput 'Enter your query (or type help for commands): ' $colors.Prompt -NoNewline
    $userInput = Read-Host
    
    # Handle empty input
    if ([string]::IsNullOrWhiteSpace($userInput)) {
        continue
    }
    
    # Handle commands
    if ($userInput -match '^session\s+(.+)$') {
        $newSessionId = $Matches[1].Trim()
        if ([string]::IsNullOrWhiteSpace($newSessionId)) {
            Write-ColorOutput 'Session ID cannot be empty.' $colors.Warning
        }
        else {
            $script:CurrentSessionId = $newSessionId
            Write-ColorOutput ('Session ID set to: {0}' -f $script:CurrentSessionId) $colors.Success
        }
        continue
    }

    switch ($userInput.ToLower().Trim()) {
        { $_ -eq 'exit' -or $_ -eq 'quit' -or $_ -eq 'q' } {
            Write-ColorOutput 'Thank you for using GDCE ChatBot! Goodbye.' $colors.Success
            exit 0
        }
        
        { $_ -eq 'help' -or $_ -eq '?' } {
            Show-Help
            Show-Usage
            continue
        }
        
        { $_ -eq 'examples' } {
            Show-Usage
            continue
        }
        
        { $_ -eq 'status' } {
            Write-Header 'Service Status'
            $orchestratorOK = Test-ServiceHealth 'Orchestrator Service' $OrchestratorUrl
            $calculatorOK = Test-ServiceHealth 'Calculator Service' $CalculatorUrl
            $retrievalOK = Test-ServiceHealth 'Retrieval Service' $RetrievalUrl
            $tradeQueryOK = Test-ServiceHealth 'Trade Query Service' $TradeQueryUrl
            Write-Host ''
            continue
        }

        { $_ -eq 'session' } {
            Write-ColorOutput ('Current Session ID: {0}' -f $script:CurrentSessionId) $colors.Info
            continue
        }

        { $_ -eq 'newsession' } {
            $script:CurrentSessionId = "chat-" + [guid]::NewGuid().ToString("N").Substring(0, 12)
            Write-ColorOutput ('New Session ID: {0}' -f $script:CurrentSessionId) $colors.Success
            continue
        }
        
        { $_ -eq 'clear' } {
            Clear-Host
            continue
        }
    }
    
    # Send query to orchestrator
    $queryCount++
    Write-Host ''
    Write-ColorOutput ('QUERY #{0}' -f $queryCount) $colors.Header
    Write-ColorOutput ('-' * 70) $colors.Header
    Write-ColorOutput ('You: {0}' -f $userInput) $colors.Query
    Write-ColorOutput 'Sending to Orchestrator...' $colors.Info
    Write-ColorOutput ('Using Session ID: {0}' -f $script:CurrentSessionId) $colors.Info
    
    $response = Send-Query -Query $userInput -Url $OrchestratorUrl -SessionId $script:CurrentSessionId
    
    if ($response.Success) {
        Format-Response -ResponseData $response.Data -Latency $response.Latency
    }
    else {
        Write-ColorOutput ('ERROR: {0}' -f $response.Error) $colors.Error
        Write-ColorOutput 'Please make sure the Orchestrator service is running on the correct URL:' $colors.Error
        Write-ColorOutput ('  {0}' -f $OrchestratorUrl) $colors.Error
    }
    
    Write-Host ''
    Write-ColorOutput 'Ready for next query. Type "help" for commands.' $colors.Info
}

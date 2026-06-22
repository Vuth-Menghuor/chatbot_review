"""
GDCE Calculator v2 - Usage Guide for New Features
==================================================
Quick reference for using the new modularized handlers and improved API.

Version: 2.0.0
Date: 2026-04-22
"""

# ================================================================
# 1. CURRENCY HANDLER USAGE
# ================================================================

from core.currency_handler import CurrencyHandler
from infrastructure.csv_database import CSVDatabase

db = CSVDatabase()
currency_handler = CurrencyHandler(db)

# Validate currency
try:
    normalized = currency_handler.validate_currency("usd")  # Returns "USD"
    print(f"Valid currency: {normalized}")
except ValueError as e:
    print(f"Invalid currency: {e}")

# Get exchange rate
rate = currency_handler.get_exchange_rate("USD", "KHR", "2026-04-22")
print(f"1 USD = {rate} KHR")

# Convert amount
from decimal import Decimal
amount_khr = currency_handler.convert(
    Decimal("1000"),
    from_currency="USD",
    to_currency="KHR",
    calculation_date="2026-04-22"
)
print(f"1000 USD = {amount_khr} KHR")

# Format for display
formatted = currency_handler.format_currency(75250.0, "KHR")
print(f"Formatted: {formatted}")  # "75,250 KHR"

# Get currency note for response
note = currency_handler.get_currency_note("USD", "KHR", exchange_rate=Decimal("4022"))
print(f"Currency note: {note}")
# Output: "Input valuation was in US Dollar (USD). All values converted to 
#          Cambodian Riel (KHR) at rate 1 USD = 4022 KHR."


# ================================================================
# 2. HS CODE HANDLER USAGE
# ================================================================

from core.hs_code_handler import HSCodeHandler

hs_handler = HSCodeHandler(db)

# Validate HS code
is_valid = hs_handler.is_valid_code("0102.10.00")  # True
is_valid = hs_handler.is_valid_code("invalid")      # False

# Normalize HS code
normalized = hs_handler.normalize_code("0102 10 00")   # "0102.10.00"
normalized = hs_handler.normalize_code("01021000")     # "0102.10.00"

# Get HS code info
info = hs_handler.get_code_info("0102.10.00")
if info:
    print(f"HS Code: {info['hs_code']}")
    print(f"Description: {info['description']}")
    print(f"Unit: {info['unit']}")

# Get candidate suggestions (for fallback scenarios)
candidates = hs_handler.get_candidates(
    query="live cattle",
    limit=5,
    fuzzy=True
)
for candidate in candidates:
    print(f"HS Code: {candidate['hs_code']}, Score: {candidate['score']:.2f}")
    print(f"  Description: {candidate['description']}")

# Extract HS code from text
text = "Import of live cattle, HS 0102.10.00"
extracted = hs_handler.extract_hs_code_from_text(text)
print(f"Extracted: {extracted}")  # "0102.10.00"

# Get hierarchical level
level = hs_handler.get_child_level("0102.10.00")
print(f"Level: {level}")  # "subchapter"

# Get parent codes
parents = hs_handler.get_parent_codes("0102.10.00")
print(f"Parents: {parents}")  # ["0102.10", "0102"]


# ================================================================
# 3. UPDATED CALCULATOR WITH HANDLERS
# ================================================================

from core.calculator import ImportTaxCalculator

calculator = ImportTaxCalculator(db)

# Access handlers
currency_rate = calculator.currency_handler.get_exchange_rate("USD", "KHR")
hs_info = calculator.hs_code_handler.get_code_info("0102.10.00")

# Get HS code candidates
candidates = calculator.get_hs_code_candidates("live cattle", limit=5)

# Access settings
print(f"Service version: {calculator.settings.calculator_version}")
print(f"Currency cache enabled: {calculator.settings.enable_currency_cache}")
print(f"HS fuzzy search enabled: {calculator.settings.enable_hs_fuzzy_search}")


# ================================================================
# 4. NEW API ENDPOINTS
# ================================================================

"""
GET /v1/health
  Returns service health with database status
  
GET /v1/lookup/duty-rate?hs_code=0102.10.00&origin_country=TH&effective_date=2026-04-22
  Returns duty rates for HS code
  
GET /v1/lookup/hs-info?hs_code=0102.10.00
  Returns HS code description and unit
  
GET /v1/lookup/exchange-rate?currency=USD&effective_date=2026-04-22
  Returns exchange rate to KHR
  
POST /v1/lookup/hs-code-candidates
  Body: {"query": "live cattle", "limit": 5}
  Returns candidate HS codes with scores
  
POST /v1/calculate_import_taxes
  Returns calculation result with new fields:
  - currency_note: Human-readable currency conversion info
  - hs_code_info: HS code metadata (description, unit, level)
"""


# ================================================================
# 5. RESPONSE EXAMPLE
# ================================================================

"""
Example POST /v1/calculate_import_taxes response:

{
  "calculation_id": "calc_2026-04-22_123456789",
  "currency": "KHR",
  "total": 75250.0,
  "breakdown": {
    "cif_value": 50000.0,
    "cop_amount": 7500.0,
    "sop_amount": 0.0,
    "vop_amount": 5750.0,
    "fees": 0.0
  },
  "line_items": [
    {
      "name": "COP (Customs of Payment)",
      "tax_type": "CD",
      "amount": 7500.0,
      "currency": "KHR",
      "base": 50000.0,
      "rate": 15.0
    },
    {
      "name": "VOP (VAT of Payment)",
      "tax_type": "VAT",
      "amount": 5750.0,
      "currency": "KHR",
      "base": 57500.0,
      "rate": 10.0
    }
  ],
  "assumptions": [...],
  "references": [...],
  "exchange_rate_usd_to_khr": 4022.0,
  "cif_value_usd": 50000.0,
  
  "currency_note": "Input valuation was in US Dollar (USD). All values converted 
                    to Cambodian Riel (KHR) at rate 1 USD = 4022 KHR.",
  
  "hs_code_info": {
    "hs_code": "0102.10.00",
    "description": "Pure-bred breeding bovine animals",
    "unit": "head",
    "level": "subchapter"
  }
}
"""


# ================================================================
# 6. CONFIGURATION EXAMPLES
# ================================================================

"""
Environment variables for new features:

# Orchestrator integration
ORCHESTRATOR_SERVICE_URL=http://orchestrator:8001

# Currency settings
ENABLE_CURRENCY_CACHE=true              # Cache exchange rates
USD_TO_KHR_RATE=4022.0                  # Fallback rate

# HS code settings
ENABLE_HS_FUZZY_SEARCH=true             # Enable fuzzy matching
HS_CODE_CANDIDATE_LIMIT=5               # Max candidates returned

# Logging
LOG_LEVEL=INFO                          # INFO, DEBUG, WARNING, ERROR

# Example: Access in code
from config import get_settings
settings = get_settings()
settings.calculator_port                # 8002
settings.orchestrator_service_url       # "http://orchestrator:8001"
settings.enable_currency_cache          # True
settings.hs_code_candidate_limit        # 5
"""


# ================================================================
# 7. ERROR HANDLING
# ================================================================

"""
Common scenarios and error handling:

# Currency validation
try:
    rate = currency_handler.get_exchange_rate("INVALID", "KHR")
except ValueError as e:
    print(f"Currency error: {e}")

# HS code validation
try:
    hs_handler.validate_code("invalid-code")
except ValueError as e:
    print(f"HS code error: {e}")

# Calculation with missing HS code
candidates = calculator.get_hs_code_candidates("live animals")
if candidates:
    best_hs_code = candidates[0]["hs_code"]
    print(f"Using: {best_hs_code}")
else:
    print("No HS code candidates found")

# Exchange rate fallback
rate = currency_handler.get_exchange_rate(
    "USD",
    "KHR",
    use_fallback=True  # Uses default if DB unavailable
)
"""

# ================================================================
# END OF USAGE GUIDE
# ================================================================

"""
GDCE Calculator Service - Currency Handler
===========================================
Handles currency parsing, normalization, and conversion operations.
Provides utilities for working with multiple currencies and exchange rates.

Supported currencies:
- USD (US Dollar) - primary input currency
- KHR (Cambodian Riel) - primary output currency
- EUR, THB, VND, CNY, JPY, KRW - regional currencies
- GBP, AUD, SGD, MYR, IDR, HKD, TWD, INR, LAK, MMK, PHP, NZD, CAD, CHF, RUB, AED, BRL - additional

Usage:
    handler = CurrencyHandler(db)
    rate = handler.get_exchange_rate('USD', '2026-03-04')
    normalized = handler.normalize_code('usd')
    parsed = handler.parse_currency_input('€5000')     # → 'EUR'
    parsed = handler.parse_currency_input('50000usd')  # → 'USD'
    inferred = handler.infer_currency_from_country('Thailand')  # → 'THB'
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)


# ================================================================
# SUPPORTED CURRENCIES
# ================================================================

SUPPORTED_CURRENCIES = {
    # Primary
    "USD": {"name": "US Dollar", "symbol": "$", "decimals": 2},
    "KHR": {"name": "Cambodian Riel", "symbol": "៛", "decimals": 0},
    # Regional (ASEAN + East Asia)
    "EUR": {"name": "Euro", "symbol": "€", "decimals": 2},
    "THB": {"name": "Thai Baht", "symbol": "฿", "decimals": 2},
    "VND": {"name": "Vietnamese Dong", "symbol": "₫", "decimals": 0},
    "CNY": {"name": "Chinese Yuan", "symbol": "¥", "decimals": 2},
    "JPY": {"name": "Japanese Yen", "symbol": "¥", "decimals": 0},
    "KRW": {"name": "South Korean Won", "symbol": "₩", "decimals": 0},
    "SGD": {"name": "Singapore Dollar", "symbol": "S$", "decimals": 2},
    "MYR": {"name": "Malaysian Ringgit", "symbol": "RM", "decimals": 2},
    "IDR": {"name": "Indonesian Rupiah", "symbol": "Rp", "decimals": 0},
    "LAK": {"name": "Lao Kip", "symbol": "₭", "decimals": 0},
    "MMK": {"name": "Myanmar Kyat", "symbol": "K", "decimals": 0},
    "PHP": {"name": "Philippine Peso", "symbol": "₱", "decimals": 2},
    # Other major
    "GBP": {"name": "British Pound", "symbol": "£", "decimals": 2},
    "AUD": {"name": "Australian Dollar", "symbol": "A$", "decimals": 2},
    "NZD": {"name": "New Zealand Dollar", "symbol": "NZ$", "decimals": 2},
    "CAD": {"name": "Canadian Dollar", "symbol": "C$", "decimals": 2},
    "CHF": {"name": "Swiss Franc", "symbol": "CHF", "decimals": 2},
    "INR": {"name": "Indian Rupee", "symbol": "₹", "decimals": 2},
    "HKD": {"name": "Hong Kong Dollar", "symbol": "HK$", "decimals": 2},
    "TWD": {"name": "Taiwan Dollar", "symbol": "NT$", "decimals": 2},
    "RUB": {"name": "Russian Ruble", "symbol": "₽", "decimals": 2},
    "AED": {"name": "UAE Dirham", "symbol": "د.إ", "decimals": 2},
    "BRL": {"name": "Brazilian Real", "symbol": "R$", "decimals": 2},
}

# Currency symbol to code mapping
# Multi-character symbols MUST come before single-character ones
# in the lookup logic to avoid partial matches.
SYMBOL_TO_CODE = {
    # Multi-char symbols (checked first via longest-match)
    "HK$": "HKD",
    "NT$": "TWD",
    "NZ$": "NZD",
    "A$": "AUD",
    "S$": "SGD",
    "C$": "CAD",
    "R$": "BRL",
    "RM": "MYR",
    "Rp": "IDR",
    # Single-char symbols
    "$": "USD",
    "£": "GBP",
    "€": "EUR",
    "¥": "JPY",   # Default for ¥; overridden to CNY when origin_country is China
    "₹": "INR",
    "₽": "RUB",
    "₩": "KRW",
    "฿": "THB",
    "₫": "VND",
    "₭": "LAK",
    "₱": "PHP",
    "¢": "USD",
    "៛": "KHR",
}

# Natural-language currency name → ISO code
CURRENCY_NAME_TO_CODE = {
    "dollar": "USD", "dollars": "USD",
    "riel": "KHR", "riels": "KHR",
    "euro": "EUR", "euros": "EUR",
    "baht": "THB",
    "yen": "JPY",
    "yuan": "CNY", "renminbi": "CNY", "rmb": "CNY",
    "dong": "VND",
    "won": "KRW",
    "pound": "GBP", "pounds": "GBP", "sterling": "GBP",
    "rupee": "INR", "rupees": "INR",
    "ringgit": "MYR",
    "rupiah": "IDR",
    "peso": "PHP", "pesos": "PHP",
    "kip": "LAK",
    "kyat": "MMK",
    "franc": "CHF", "francs": "CHF",
    "dirham": "AED", "dirhams": "AED",
    "real": "BRL", "reais": "BRL",
    "ruble": "RUB", "rubles": "RUB", "rouble": "RUB",
}

# Country keyword → default currency code
COUNTRY_TO_CURRENCY = {
    # Cambodia
    "cambodia": "KHR", "khmer": "KHR", "cambodian": "KHR",
    # ASEAN
    "thailand": "THB", "thai": "THB",
    "vietnam": "VND", "vietnamese": "VND",
    "singapore": "SGD", "singaporean": "SGD",
    "malaysia": "MYR", "malaysian": "MYR",
    "indonesia": "IDR", "indonesian": "IDR",
    "laos": "LAK", "lao": "LAK",
    "myanmar": "MMK", "burmese": "MMK", "burma": "MMK",
    "philippines": "PHP", "filipino": "PHP",
    # East Asia
    "china": "CNY", "chinese": "CNY",
    "japan": "JPY", "japanese": "JPY",
    "south korea": "KRW", "korean": "KRW", "korea": "KRW",
    "hong kong": "HKD",
    "taiwan": "TWD", "taiwanese": "TWD",
    # Major trading partners
    "united states": "USD", "usa": "USD", "america": "USD", "american": "USD",
    "united kingdom": "GBP", "uk": "GBP", "british": "GBP", "great britain": "GBP",
    "france": "EUR", "germany": "EUR", "italy": "EUR", "spain": "EUR",
    "netherlands": "EUR", "belgium": "EUR", "austria": "EUR",
    "europe": "EUR", "european union": "EUR", "eu": "EUR",
    "australia": "AUD", "australian": "AUD",
    "new zealand": "NZD",
    "canada": "CAD", "canadian": "CAD",
    "india": "INR", "indian": "INR",
    "switzerland": "CHF", "swiss": "CHF",
    "brazil": "BRL", "brazilian": "BRL",
    "russia": "RUB", "russian": "RUB",
    "uae": "AED", "united arab emirates": "AED", "dubai": "AED",
}

# Pre-sorted multi-char symbols (longest first) for matching
_MULTI_CHAR_SYMBOLS = sorted(
    [s for s in SYMBOL_TO_CODE if len(s) > 1],
    key=len, reverse=True,
)


# ================================================================
# CURRENCY HANDLER
# ================================================================

class CurrencyHandler:
    """
    Handles all currency-related operations.
    
    Responsibilities:
    - Validate and normalize currency codes
    - Fetch and cache exchange rates
    - Convert between currencies
    - Format currency for display
    - Generate currency notes for API responses
    - Parse any currency format (codes, symbols, names)
    - Infer currency from origin country
    """
    
    def __init__(self, db=None, redis_client=None):
        """
        Initialize currency handler.

        Args:
            db: Database interface for fetching exchange rates (fallback)
            redis_client: Optional Redis client for exchange rates (preferred)
        """
        self.db = db
        self.redis_client = redis_client
        self._exchange_rate_cache: dict[str, Decimal] = {}

    # ================================================================
    # VALIDATION
    # ================================================================
    
    def is_valid_currency(self, currency_code: str) -> bool:
        """Check if currency code is supported."""
        normalized = self.normalize_code(currency_code)
        return normalized in SUPPORTED_CURRENCIES
    
    def validate_currency(self, currency_code: str) -> str:
        """
        Validate and normalize currency code.
        
        Args:
            currency_code: Currency code (case-insensitive)
            
        Returns:
            Normalized currency code (uppercase)
            
        Raises:
            ValueError: If currency is not supported
        """
        normalized = self.normalize_code(currency_code)
        if normalized not in SUPPORTED_CURRENCIES:
            allowed = list(SUPPORTED_CURRENCIES.keys())
            raise ValueError(
                f"Currency '{currency_code}' not supported. Allowed: {allowed}"
            )
        return normalized
    
    def normalize_code(self, currency_code: str) -> str:
        """Normalize currency code to uppercase."""
        return currency_code.strip().upper()
    
    # ================================================================
    # SYMBOL & NAME LOOKUP
    # ================================================================
    
    def symbol_to_code(self, symbol: str, origin_country: str = None) -> Optional[str]:
        """
        Convert currency symbol to ISO code.
        
        Checks multi-character symbols first (longest-match), then
        single-character symbols. Handles ¥ ambiguity: returns CNY
        if origin_country is China, otherwise JPY.
        
        Args:
            symbol: Currency symbol (e.g., "$", "€", "₫", "HK$")
            origin_country: Optional origin country for disambiguation
            
        Returns:
            ISO currency code (e.g., "USD", "EUR", "VND"), or None if not found
        """
        if not symbol or len(symbol) == 0:
            return None
        
        # Try multi-char symbols first (longest match)
        for multi_sym in _MULTI_CHAR_SYMBOLS:
            if symbol.startswith(multi_sym):
                return SYMBOL_TO_CODE[multi_sym]
        
        # Try single-char symbol
        first_char = symbol[0]
        code = SYMBOL_TO_CODE.get(first_char)
        if code:
            # Handle ¥ ambiguity: default JPY, but CNY if origin is China
            if first_char == "¥" and origin_country:
                origin_lower = origin_country.strip().lower()
                if origin_lower in ("china", "chinese", "cn", "chn"):
                    return "CNY"
            return code
        
        return None
    
    def name_to_code(self, name: str) -> Optional[str]:
        """
        Convert natural-language currency name to ISO code.
        
        Args:
            name: Currency name (e.g., "dollar", "baht", "euro")
            
        Returns:
            ISO currency code, or None if not found
        """
        if not name:
            return None
        return CURRENCY_NAME_TO_CODE.get(name.strip().lower())
    
    # ================================================================
    # UNIVERSAL PARSER
    # ================================================================
    
    def parse_currency_input(
        self,
        currency_input: str,
        origin_country: str = None,
    ) -> str:
        """
        Parse currency from ANY user input format.

        Priority order:
        1. ISO codes: "USD", "usd", "Usd" → "USD"
        2. Multi-char symbols: "HK$", "A$", "RM" → mapped code
        3. Single-char symbols: "$", "€", "៛" → mapped code
        4. Currency names: "dollar", "baht", "yen" → mapped code
        5. Symbol+number: "$800", "€5000" → extract symbol
        6. Number+symbol: "800$", "5000€" → extract symbol
        7. Code+number (no space): "usd800", "800usd" → extract code
        8. Country-based inference from origin_country
        9. Default fallback → "KHR"
        
        Args:
            currency_input: Currency code, symbol, name, or mixed value string
            origin_country: Optional origin country for inference fallback
            
        Returns:
            Normalized ISO currency code
            
        Raises:
            ValueError: If input is explicitly wrong (e.g., "XYZ123")
                        but NOT if it's empty/None — those fall through
                        to country inference or KHR default.
        """
        if not currency_input or not isinstance(currency_input, str):
            # No explicit currency → try country inference → KHR
            inferred = self.infer_currency_from_country(origin_country)
            if inferred:
                logger.info(
                    f"No currency provided; inferred '{inferred}' "
                    f"from origin country '{origin_country}'"
                )
                return inferred
            logger.info("No currency provided and no origin country; defaulting to KHR")
            return "KHR"
        
        stripped = currency_input.strip()
        if not stripped:
            inferred = self.infer_currency_from_country(origin_country)
            return inferred or "KHR"
        
        # ----------------------------------------------------------
        # 1) Pure 3-letter ISO code: "USD", "usd", "Eur"
        # ----------------------------------------------------------
        if len(stripped) == 3 and stripped.isalpha():
            upper = stripped.upper()
            if upper in SUPPORTED_CURRENCIES:
                return upper
            # Not a known code — fall through (don't error yet,
            # could still be a currency name like "yen")
        
        # ----------------------------------------------------------
        # 2) Multi-char symbol (exact match or prefix + non-alpha)
        #    Only match when the remainder is NOT alphabetic, to avoid
        #    matching "rmb" as symbol "RM" + leftover "b".
        # ----------------------------------------------------------
        for multi_sym in _MULTI_CHAR_SYMBOLS:
            sym_len = len(multi_sym)
            if stripped.startswith(multi_sym) or stripped.upper().startswith(multi_sym.upper()):
                remainder = stripped[sym_len:]
                # Accept if: exact match, or remainder starts with digit/space/comma
                if not remainder or not remainder[0].isalpha():
                    code = SYMBOL_TO_CODE[multi_sym]
                    return self._validate_or_pass(code)
        
        # ----------------------------------------------------------
        # 3) Single-char symbol (exact single char)
        # ----------------------------------------------------------
        if len(stripped) == 1:
            code = self.symbol_to_code(stripped, origin_country)
            if code:
                return self._validate_or_pass(code)
        
        # ----------------------------------------------------------
        # 4) Natural-language currency name: "dollar", "baht", etc.
        # ----------------------------------------------------------
        code = self.name_to_code(stripped)
        if code:
            return self._validate_or_pass(code)
        
        # ----------------------------------------------------------
        # 5) Symbol-prefixed value: "$800", "€5000", "HK$3000"
        # ----------------------------------------------------------
        # Try multi-char symbol prefix first
        for multi_sym in _MULTI_CHAR_SYMBOLS:
            if stripped.startswith(multi_sym):
                rest = stripped[len(multi_sym):]
                if rest and (rest[0].isdigit() or rest[0] in ' ,'):
                    code = SYMBOL_TO_CODE[multi_sym]
                    return self._validate_or_pass(code)
        # Try single-char symbol prefix
        if len(stripped) > 1:
            first_char = stripped[0]
            code = self.symbol_to_code(first_char, origin_country)
            if code:
                # Check that after the symbol there's a number or space
                rest = stripped[1:].lstrip()
                if rest and (rest[0].isdigit() or rest[0] in ','):
                    return self._validate_or_pass(code)
        
        # ----------------------------------------------------------
        # 6) Number-suffixed symbol: "800$", "5000€"
        # ----------------------------------------------------------
        if len(stripped) > 1:
            last_char = stripped[-1]
            code = self.symbol_to_code(last_char, origin_country)
            if code:
                prefix = stripped[:-1].rstrip()
                if prefix and prefix.replace(',', '').replace('.', '').isdigit():
                    return self._validate_or_pass(code)
            # Multi-char suffix: "5000HK$", "3000RM"
            for multi_sym in _MULTI_CHAR_SYMBOLS:
                if stripped.upper().endswith(multi_sym.upper()):
                    prefix = stripped[:-len(multi_sym)].rstrip()
                    if prefix and prefix.replace(',', '').replace('.', '').isdigit():
                        code = SYMBOL_TO_CODE[multi_sym]
                        return self._validate_or_pass(code)
        
        # ----------------------------------------------------------
        # 7) Code glued to number: "usd800", "800usd", "50000EUR"
        # ----------------------------------------------------------
        # Pattern: 3-letter code at start or end, rest is numeric
        match_code_first = re.match(
            r'^([a-zA-Z]{3})\s*([0-9,]+(?:\.[0-9]+)?)$', stripped
        )
        if match_code_first:
            candidate_code = match_code_first.group(1).upper()
            if candidate_code in SUPPORTED_CURRENCIES:
                return candidate_code
        
        match_code_last = re.match(
            r'^([0-9,]+(?:\.[0-9]+)?)\s*([a-zA-Z]{3})$', stripped
        )
        if match_code_last:
            candidate_code = match_code_last.group(2).upper()
            if candidate_code in SUPPORTED_CURRENCIES:
                return candidate_code
        
        # ----------------------------------------------------------
        # 8) Last resort: try as partial name or known alias
        # ----------------------------------------------------------
        stripped_lower = stripped.lower()
        for name_key, name_code in CURRENCY_NAME_TO_CODE.items():
            if name_key in stripped_lower:
                return self._validate_or_pass(name_code)
        
        # ----------------------------------------------------------
        # Explicit but unrecognized → error
        # ----------------------------------------------------------
        raise ValueError(
            f"Cannot parse currency from '{currency_input}'. "
            f"Expected ISO code (e.g., 'USD'), symbol (e.g., '$', '៛'), "
            f"or currency name (e.g., 'dollar', 'baht')."
        )
    
    def _validate_or_pass(self, code: str) -> str:
        """Validate a resolved code, raising if unsupported."""
        if code in SUPPORTED_CURRENCIES:
            return code
        raise ValueError(
            f"Currency '{code}' is not supported. "
            f"Allowed: {list(SUPPORTED_CURRENCIES.keys())}"
        )
    
    # ================================================================
    # COUNTRY → CURRENCY INFERENCE
    # ================================================================
    
    def infer_currency_from_country(self, country: str) -> Optional[str]:
        """
        Infer currency from origin country name.
        
        Uses keyword matching (case-insensitive) against
        the COUNTRY_TO_CURRENCY mapping.
        
        Args:
            country: Country name or code (e.g., "Thailand", "CN", "USA")
            
        Returns:
            ISO currency code, or None if no match
        """
        if not country:
            return None
        country_lower = country.strip().lower()
        
        # Direct match
        code = COUNTRY_TO_CURRENCY.get(country_lower)
        if code:
            return code
        
        # Substring match for compound names
        for keyword, currency_code in COUNTRY_TO_CURRENCY.items():
            if keyword in country_lower or country_lower in keyword:
                return currency_code
        
        return None
    
    # ================================================================
    # EXCHANGE RATES
    # ================================================================
    
    def get_exchange_rate(
        self,
        source_currency: str,
        target_currency: str = "KHR",
        calculation_date: Optional[str] = None,
    ) -> Decimal:
        """
        Get exchange rate from source to target currency.

        Args:
            source_currency: Source currency code
            target_currency: Target currency code (default: KHR)
            calculation_date: Date for historical rates (YYYY-MM-DD)

        Returns:
            Exchange rate as Decimal

        Raises:
            ValueError: If rate not found in database
        """
        source = self.validate_currency(source_currency)
        target = self.validate_currency(target_currency)

        # Same currency = 1.0
        if source == target:
            return Decimal("1.0")

        # If target is KHR, use single direction rate
        if target == "KHR":
            return self._get_rate_to_khr(source, calculation_date)

        # Cross-currency: convert through KHR
        rate_source_to_khr = self._get_rate_to_khr(source, calculation_date)
        rate_khr_to_target = self._get_rate_to_khr(target, calculation_date)
        return rate_source_to_khr / rate_khr_to_target

    def _get_rate_to_khr(
        self,
        currency: str,
        calculation_date: Optional[str] = None,
    ) -> Decimal:
        """Get exchange rate to KHR from Redis (preferred) or database (fallback)."""
        if currency == "KHR":
            return Decimal("1.0")

        # Check in-memory cache
        cache_key = f"{currency}_{calculation_date}"
        if cache_key in self._exchange_rate_cache:
            return self._exchange_rate_cache[cache_key]

        # 1. Try Redis first (fast, no PostgreSQL connection needed)
        if self.redis_client:
            try:
                rate = self.redis_client.get_exchange_rate(currency, calculation_date)
                if rate is not None:
                    self._exchange_rate_cache[cache_key] = rate
                    logger.debug(f"Redis rate {currency}->{rate} KHR")
                    return rate
            except Exception as e:
                logger.warning(f"Redis exchange rate lookup failed for {currency}: {e}")

        # 2. Fallback to database (PostgreSQL)
        if self.db:
            try:
                rate = self.db.get_exchange_rate(currency, calculation_date)
                if rate is not None:
                    rate_decimal = Decimal(str(rate))
                    self._exchange_rate_cache[cache_key] = rate_decimal
                    return rate_decimal
            except Exception as e:
                logger.error(f"Database exchange rate lookup failed for {currency}: {e}")

        raise ValueError(
            f"No exchange rate available for {currency}"
            f"{' on ' + calculation_date if calculation_date else ''}. "
            f"Please provide an exchange_rate_to_khr value."
        )
    
    def clear_rate_cache(self) -> None:
        """Clear cached exchange rates."""
        self._exchange_rate_cache.clear()
    
    # ================================================================
    # CONVERSION
    # ================================================================
    
    def convert(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str = "KHR",
        calculation_date: Optional[str] = None
    ) -> Decimal:
        """
        Convert amount from one currency to another.
        
        Args:
            amount: Amount to convert
            from_currency: Source currency code
            to_currency: Target currency code (default: KHR)
            calculation_date: Date for historical rates
            
        Returns:
            Converted amount as Decimal
        """
        rate = self.get_exchange_rate(from_currency, to_currency, calculation_date)
        return amount * rate
    
    # ================================================================
    # FORMATTING
    # ================================================================
    
    def get_currency_info(self, currency_code: str) -> dict:
        """Get metadata for a currency."""
        normalized = self.validate_currency(currency_code)
        return SUPPORTED_CURRENCIES[normalized].copy()
    
    def format_currency(
        self,
        amount: float,
        currency_code: str,
        include_symbol: bool = True
    ) -> str:
        """
        Format amount for display.
        
        Args:
            amount: Numeric amount
            currency_code: Currency code
            include_symbol: Include currency symbol in output
            
        Returns:
            Formatted string (e.g., "$50,000.00" or "50000 USD")
        """
        normalized = self.validate_currency(currency_code)
        info = SUPPORTED_CURRENCIES[normalized]
        
        # Format with thousands separator
        if info["decimals"] == 0:
            formatted = f"{int(amount):,}"
        else:
            formatted = f"{amount:,.{info['decimals']}f}"
        
        if include_symbol and normalized != "KHR":
            return f"{info['symbol']}{formatted}"
        else:
            return f"{formatted} {normalized}"
    
    def get_currency_note(
        self,
        input_currency: str,
        output_currency: str = "KHR",
        exchange_rate: Optional[Decimal] = None,
        calculation_date: Optional[str] = None
    ) -> str:
        """
        Generate a currency note for API response.
        
        Args:
            input_currency: Input currency code
            output_currency: Output currency code (default: KHR)
            exchange_rate: Exchange rate used (if known)
            calculation_date: Calculation date
            
        Returns:
            Human-readable currency note
        """
        input_normalized = self.validate_currency(input_currency)
        output_normalized = self.validate_currency(output_currency)
        
        if input_normalized == output_normalized:
            return f"All values in {output_normalized}."
        
        if exchange_rate is None:
            exchange_rate = self.get_exchange_rate(
                input_normalized,
                output_normalized,
                calculation_date
            )
        
        input_name = SUPPORTED_CURRENCIES[input_normalized]["name"]
        output_name = SUPPORTED_CURRENCIES[output_normalized]["name"]
        
        return (
            f"Input valuation was in {input_name} ({input_normalized}). "
            f"All values converted to {output_name} ({output_normalized}) "
            f"at rate 1 {input_normalized} = {exchange_rate} {output_normalized}."
        )

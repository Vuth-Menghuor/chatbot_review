# Input validation utilities for API layer
# Validators are part of API layer but use domain exceptions from core
import re
from typing import Any, List, Dict, Optional

try:
    from ..core.exceptions import ValidationError
except ImportError:
    from core.exceptions import ValidationError

class InputValidator:
    @staticmethod
    def validate_string(value: str, min_length: int = 1, max_length: int = 5000, field_name: str = "string") -> str:
        if not isinstance(value, str):
            raise ValidationError(f"{field_name} must be a string", field_name)
        value = value.strip()
        if len(value) < min_length:
            raise ValidationError(f"{field_name} must be at least {min_length} characters", field_name)
        if len(value) > max_length:
            raise ValidationError(f"{field_name} must not exceed {max_length} characters", field_name)
        return value
    @staticmethod
    def validate_hs_code(hs_code: str) -> str:
        if not isinstance(hs_code, str):
            raise ValidationError("HS code must be a string", "hs_code")
        hs_code = hs_code.strip()
        pattern = r'^\d{4}(\.\d{2})?(\.\d{2})?$|^\d{6}(\.\d{2})?$'
        if not re.match(pattern, hs_code):
            raise ValidationError("HS code must be in format XXXX.XX.XX or XXXXXX", "hs_code")
        return hs_code
    @staticmethod
    def validate_currency(currency: str) -> str:
        allowed_currencies = ["USD", "KHR", "EUR", "THB", "VND", "CNY", "JPY", "KRW", "SGD", "MYR"]
        currency = currency.upper().strip()
        if currency not in allowed_currencies:
            raise ValidationError(f"Currency must be one of {allowed_currencies}", "currency")
        return currency
    @staticmethod
    def validate_number(value: Any, min_val: float = None, max_val: float = None, field_name: str = "number") -> float:
        try:
            num = float(value)
        except (ValueError, TypeError):
            raise ValidationError(f"{field_name} must be a valid number", field_name)
        if min_val is not None and num < min_val:
            raise ValidationError(f"{field_name} must be >= {min_val}", field_name)
        if max_val is not None and num > max_val:
            raise ValidationError(f"{field_name} must be <= {max_val}", field_name)
        return num
    @staticmethod
    def validate_country_code(country_code: str) -> str:
        country_code = country_code.upper().strip()
        if len(country_code) != 2 or not country_code.isalpha():
            raise ValidationError("Country code must be a 2-letter ISO code", "country_code")
        return country_code

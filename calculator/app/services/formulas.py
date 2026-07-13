"""
GDCE Calculator Service - Formula Implementation
=================================================
100% local Python logic for customs duty and tax calculations.
No infrastructure dependency except DB.

Implements all formulas from:
- configs/formula_registry.json        (local to calculator)
- configs/rounding_rules.json          (local to calculator)
- configs/exchange_rate_policy.json    (local to calculator)

Version: 1.0
Last Updated: 2026-03-04
"""

from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING
from typing import Dict, Any, Optional, Union
import math


# ================================================================
# ROUNDING FUNCTIONS
# ================================================================

def round_to_whole_number(amount: Union[float, Decimal]) -> Decimal:
    """
    Standard rounding to whole number (0.5 and above rounds up).
    Used for tax base amounts (CIF, duty, excise, VAT, total_duties_and_taxes).
    
    Examples:
        12345.04 → 12345
        12345.50 → 12346
        12345.99 → 12346
    
    Args:
        amount: Amount to round
        
    Returns:
        Rounded Decimal value
    """
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    return amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP)


def round_up_to_hundred(amount: Union[float, Decimal]) -> Decimal:
    """
    ALWAYS round UP to nearest 100 (never down).
    Used ONLY for final payment amounts when ready to pay.
    
    Formula: CEILING(amount / 100) * 100
    
    Examples:
        12345678 → 12345700
        12345601 → 12345700
        12345649 → 12345700
        12345600 → 12345600
    
    Args:
        amount: Amount to round up
        
    Returns:
        Rounded up Decimal value (to nearest 100)
    """
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    
    # CEILING(amount / 100) * 100
    return (amount / Decimal('100')).quantize(Decimal('1'), rounding=ROUND_CEILING) * Decimal('100')


# ================================================================
# BASIC VALUATION FORMULAS
# ================================================================

def calculate_cif_value(
    fob_value: Union[float, Decimal],
    freight: Union[float, Decimal],
    insurance: Union[float, Decimal]
) -> Decimal:
    """
    Calculate CIF (Cost, Insurance, Freight) value.
    
    Formula: fob_value + freight + insurance
    
    Args:
        fob_value: Free On Board value
        freight: Freight cost
        insurance: Insurance cost
        
    Returns:
        CIF value (rounded to whole number)
    """
    cif = Decimal(str(fob_value)) + Decimal(str(freight)) + Decimal(str(insurance))
    return round_to_whole_number(cif)


def calculate_dv_declared_value(
    fair_market_value: Union[float, Decimal]
) -> Decimal:
    """
    Calculate DV (Declared Value).
    DV is the fair amount of price that keeps the market in the middle,
    not too high or too low.
    Used as the customs valuation basis for imports only (not exports).
    
    Formula: fair_market_value
    
    Args:
        fair_market_value: Fair market value
        
    Returns:
        DV amount
    """
    return Decimal(str(fair_market_value))


# ================================================================
# DUTY CALCULATION FORMULAS
# ================================================================

def calculate_import_duty(
    cif_value: Union[float, Decimal],
    duty_rate: Union[float, Decimal]
) -> Decimal:
    """
    Calculate standard import duty.
    
    Formula: cif_value * duty_rate
    
    Args:
        cif_value: CIF value in USD
        duty_rate: Duty rate as decimal (e.g., 0.15 for 15%)
        
    Returns:
        Import duty amount (rounded to whole number)
    """
    duty = Decimal(str(cif_value)) * Decimal(str(duty_rate))
    return round_to_whole_number(duty)


def calculate_preferential_duty(
    cif_value: Union[float, Decimal],
    preferential_rate: Union[float, Decimal]
) -> Decimal:
    """
    Calculate duty using preferential tariff rate (e.g., ASEAN, USA agreements).
    Requires valid certificate of origin.
    
    Formula: cif_value * preferential_rate
    
    Args:
        cif_value: CIF value in USD
        preferential_rate: Preferential rate as decimal (often 0.0)
        
    Returns:
        Preferential duty amount (rounded to whole number)
    """
    duty = Decimal(str(cif_value)) * Decimal(str(preferential_rate))
    return round_to_whole_number(duty)


def calculate_duty_exemption() -> Decimal:
    """
    Calculate duty as zero when valid exemption applies.
    Requires valid exemption certificate and authorized category.
    
    Formula: 0
    
    Returns:
        Zero
    """
    return Decimal('0')


# ================================================================
# FTA (FREE TRADE AGREEMENT) DUTY FORMULAS
# ================================================================

def calculate_acfta_duty(cif_value: Union[float, Decimal]) -> Decimal:
    """
    ACFTA (ASEAN-China FTA) duty calculation.
    Requires Form E Certificate of Origin.
    
    Formula: cif_value * 0.00
    
    Args:
        cif_value: CIF value in USD
        
    Returns:
        Zero (ACFTA makes duty rate 0%)
    """
    return Decimal('0')


def calculate_atiga_duty(cif_value: Union[float, Decimal]) -> Decimal:
    """
    ATIGA (ASEAN Trade in Goods Agreement) duty calculation.
    Most commonly used FTA in Cambodia for intra-ASEAN trade.
    Requires Form D Certificate of Origin.
    
    Formula: cif_value * 0.00
    
    Args:
        cif_value: CIF value in USD
        
    Returns:
        Zero (ATIGA makes duty rate 0% for intra-ASEAN trade)
    """
    return Decimal('0')


def calculate_akfta_duty(
    cif_value: Union[float, Decimal],
    akfta_rate: Union[float, Decimal]
) -> Decimal:
    """
    AKFTA (ASEAN-Korea FTA) duty calculation.
    Requires Form AK Certificate of Origin.
    
    Formula: cif_value * akfta_rate
    
    Args:
        cif_value: CIF value in USD
        akfta_rate: Rate as decimal (typically 0.0)
        
    Returns:
        AKFTA duty amount
    """
    duty = Decimal(str(cif_value)) * Decimal(str(akfta_rate))
    return round_to_whole_number(duty)


def calculate_ajcep_duty(
    cif_value: Union[float, Decimal],
    ajcep_rate: Union[float, Decimal]
) -> Decimal:
    """
    AJCEP (ASEAN-Japan Comprehensive Economic Partnership) duty calculation.
    Requires Form AJ Certificate of Origin.
    
    Formula: cif_value * ajcep_rate
    
    Args:
        cif_value: CIF value in USD
        ajcep_rate: Rate as decimal (typically 0.0 or reduced)
        
    Returns:
        AJCEP duty amount
    """
    duty = Decimal(str(cif_value)) * Decimal(str(ajcep_rate))
    return round_to_whole_number(duty)


def calculate_rcep_duty(
    cif_value: Union[float, Decimal],
    rcep_rate: Union[float, Decimal]
) -> Decimal:
    """
    RCEP (Regional Comprehensive Economic Partnership) duty calculation.
    Newest and largest FTA covering 15 countries.
    Requires Form RCEP Certificate of Origin.
    
    Formula: cif_value * rcep_rate
    
    Args:
        cif_value: CIF value in USD
        rcep_rate: Rate varies by origin and commodity
        
    Returns:
        RCEP duty amount
    """
    duty = Decimal(str(cif_value)) * Decimal(str(rcep_rate))
    return round_to_whole_number(duty)


def calculate_aanzfta_duty(
    cif_value: Union[float, Decimal],
    aanzfta_rate: Union[float, Decimal]
) -> Decimal:
    """
    AANZFTA (ASEAN-Australia-New Zealand FTA) duty calculation.
    Requires Form AANZ Certificate of Origin.
    
    Formula: cif_value * aanzfta_rate
    
    Args:
        cif_value: CIF value in USD
        aanzfta_rate: Rate as decimal (most tariffs reduced to 0%)
        
    Returns:
        AANZFTA duty amount
    """
    duty = Decimal(str(cif_value)) * Decimal(str(aanzfta_rate))
    return round_to_whole_number(duty)


# ================================================================
# TAX CALCULATION FORMULAS
# ================================================================

def calculate_excise_tax(
    cif_value: Union[float, Decimal],
    excise_rate: Union[float, Decimal]
) -> Decimal:
    """
    Calculate excise tax for specific goods.
    Applies to: alcohol, tobacco, petroleum, vehicles, luxury goods.
    
    Formula: cif_value * excise_rate
    
    Args:
        cif_value: CIF value in USD
        excise_rate: Excise rate as decimal
        
    Returns:
        Excise tax amount (rounded to whole number)
    """
    excise = Decimal(str(cif_value)) * Decimal(str(excise_rate))
    return round_to_whole_number(excise)


def calculate_vat(
    cif_value: Union[float, Decimal],
    import_duty: Union[float, Decimal],
    excise_tax: Union[float, Decimal],
    vat_rate: Union[float, Decimal] = Decimal('0.10')
) -> Decimal:
    """
    Calculate VAT on the sum of CIF value plus all duties and excise taxes.
    Standard VAT rate is 10% per Law on Taxation 2023.
    
    Formula: (cif_value + import_duty + excise_tax) * vat_rate
    
    Args:
        cif_value: CIF value in USD
        import_duty: Import duty amount
        excise_tax: Excise tax amount
        vat_rate: VAT rate as decimal (default 0.10 = 10%)
        
    Returns:
        VAT amount (rounded to whole number)
    """
    base = Decimal(str(cif_value)) + Decimal(str(import_duty)) + Decimal(str(excise_tax))
    vat = base * Decimal(str(vat_rate))
    return round_to_whole_number(vat)


def calculate_specific_tax(
    quantity: Union[float, Decimal],
    specific_rate: Union[float, Decimal]
) -> Decimal:
    """
    Calculate specific tax based on quantity rather than value.
    Used for commodities like petroleum (per liter) or alcohol (per volume).
    
    Formula: quantity * specific_rate
    
    Args:
        quantity: Quantity in units (liters, kg, units)
        specific_rate: Rate per unit
        
    Returns:
        Specific tax amount (rounded to whole number)
    """
    tax = Decimal(str(quantity)) * Decimal(str(specific_rate))
    return round_to_whole_number(tax)


# ================================================================
# COMMODITY-SPECIFIC TAX FORMULAS
# ================================================================

def calculate_commodity_tax_by_mass(
    net_mass_kg: Union[float, Decimal],
    rate_per_kg: Union[float, Decimal]
) -> Decimal:
    """
    Calculate tax based on net mass in kilograms.
    Used for commodities like rubber.
    
    Formula: net_mass_kg * rate_per_kg
    
    Args:
        net_mass_kg: Net mass in kilograms
        rate_per_kg: Rate per kilogram
        
    Returns:
        Tax amount (rounded to whole number)
    """
    tax = Decimal(str(net_mass_kg)) * Decimal(str(rate_per_kg))
    return round_to_whole_number(tax)


def calculate_commodity_tax_by_volume(
    volume_ltr: Union[float, Decimal],
    rate_per_ltr: Union[float, Decimal]
) -> Decimal:
    """
    Calculate tax based on volume in liters.
    Used for commodities like petroleum.
    
    Formula: volume_ltr * rate_per_ltr
    
    Args:
        volume_ltr: Volume in liters
        rate_per_ltr: Rate per liter
        
    Returns:
        Tax amount (rounded to whole number)
    """
    tax = Decimal(str(volume_ltr)) * Decimal(str(rate_per_ltr))
    return round_to_whole_number(tax)


def calculate_commodity_tax_hybrid(
    net_mass_kg: Union[float, Decimal],
    mass_rate: Union[float, Decimal],
    volume_ltr: Union[float, Decimal],
    volume_rate: Union[float, Decimal]
) -> Decimal:
    """
    Calculate tax using both net mass and volume.
    Most frequently used for rubber and petroleum.
    
    Formula: (net_mass_kg * mass_rate) + (volume_ltr * volume_rate)
    
    Args:
        net_mass_kg: Net mass in kilograms
        mass_rate: Rate per kilogram
        volume_ltr: Volume in liters
        volume_rate: Rate per liter
        
    Returns:
        Tax amount (rounded to whole number)
    """
    tax_mass = Decimal(str(net_mass_kg)) * Decimal(str(mass_rate))
    tax_volume = Decimal(str(volume_ltr)) * Decimal(str(volume_rate))
    total = tax_mass + tax_volume
    return round_to_whole_number(total)


# ================================================================
# FEES FORMULAS
# ================================================================

def calculate_processing_fee(
    declaration_type: str,
    fixed_amount: Union[float, Decimal] = Decimal('0')
) -> Decimal:
    """
    Calculate fixed processing fee for customs declaration.
    
    Formula: fixed_amount
    
    Args:
        declaration_type: Type of declaration
        fixed_amount: Fixed fee amount (default 0)
        
    Returns:
        Processing fee amount
    """
    return Decimal(str(fixed_amount))


def calculate_inspection_fee(
    base_fee: Union[float, Decimal],
    cif_value: Union[float, Decimal],
    percentage_fee: Union[float, Decimal]
) -> Decimal:
    """
    Calculate inspection fee for customs scanning or physical inspection.
    
    Formula: base_fee + (cif_value * percentage_fee)
    
    Args:
        base_fee: Base inspection fee
        cif_value: CIF value in USD
        percentage_fee: Percentage fee as decimal
        
    Returns:
        Inspection fee amount
    """
    fee = Decimal(str(base_fee)) + (Decimal(str(cif_value)) * Decimal(str(percentage_fee)))
    return round_to_whole_number(fee)


# ================================================================
# TOTAL CALCULATION FORMULAS
# ================================================================

def calculate_total_duties_and_taxes(
    import_duty: Union[float, Decimal],
    excise_tax: Union[float, Decimal],
    vat: Union[float, Decimal],
    specific_tax: Union[float, Decimal] = Decimal('0')
) -> Decimal:
    """
    Sum of all applicable duties and taxes (excluding fees).
    This is the tax base amount - rounded to whole number (NOT to 100).
    
    Formula: import_duty + excise_tax + vat + specific_tax
    
    Args:
        import_duty: Import duty amount
        excise_tax: Excise tax amount
        vat: VAT amount
        specific_tax: Specific tax amount (default 0)
        
    Returns:
        Total duties and taxes (rounded to whole number, NOT to 100)
    """
    total = (
        Decimal(str(import_duty)) +
        Decimal(str(excise_tax)) +
        Decimal(str(vat)) +
        Decimal(str(specific_tax))
    )
    return round_to_whole_number(total)


def calculate_total_payable(
    total_duties_taxes: Union[float, Decimal],
    processing_fee: Union[float, Decimal] = Decimal('0'),
    inspection_fee: Union[float, Decimal] = Decimal('0'),
    other_fees: Union[float, Decimal] = Decimal('0')
) -> Decimal:
    """
    Total amount payable including all duties, taxes, and fees.
    ROUNDED UP to nearest 100 when ready to pay.
    This is the final payment amount shown on the payment receipt (Box B of SAD).
    
    Formula: CEILING((total_duties_taxes + processing_fee + inspection_fee + other_fees) / 100) * 100
    
    Args:
        total_duties_taxes: Total duties and taxes amount
        processing_fee: Processing fee (default 0)
        inspection_fee: Inspection fee (default 0)
        other_fees: Other fees (default 0)
        
    Returns:
        Total payable amount (ALWAYS rounded UP to nearest 100)
    """
    total = (
        Decimal(str(total_duties_taxes)) +
        Decimal(str(processing_fee)) +
        Decimal(str(inspection_fee)) +
        Decimal(str(other_fees))
    )
    return round_up_to_hundred(total)


# ================================================================
# DQ (DEAL/QUOTE) ADJUSTMENT FORMULAS
# ================================================================

def calculate_dq_adjustment(
    government_agreed_price: Union[float, Decimal],
    market_price: Union[float, Decimal]
) -> Decimal:
    """
    DQ (Deal/Trade Agreement) - real agreement between one company and the
    government. Cambodia Customs-specific, not formal in other countries.
    
    Formula: government_agreed_price - market_price
    
    Args:
        government_agreed_price: Price agreed with government
        market_price: Current market price
        
    Returns:
        DQ adjustment amount (can be positive or negative)
    """
    return Decimal(str(government_agreed_price)) - Decimal(str(market_price))


# ================================================================
# SOP AND COP CALCULATION FORMULAS
# ================================================================

def calculate_sop_amount(
    cif_value: Union[float, Decimal],
    import_duty: Union[float, Decimal],
    excise_tax: Union[float, Decimal],
    vat: Union[float, Decimal]
) -> Decimal:
    """
    SOP Amount - Calculated result WITHOUT DQ adjustment.
    ALWAYS rounded UP to nearest 100.
    
    Formula: CEILING((cif_value + import_duty + excise_tax + vat) / 100) * 100
    
    Args:
        cif_value: CIF value in USD
        import_duty: Import duty amount
        excise_tax: Excise tax amount
        vat: VAT amount
        
    Returns:
        SOP amount (ALWAYS rounded UP to nearest 100)
    """
    total = (
        Decimal(str(cif_value)) +
        Decimal(str(import_duty)) +
        Decimal(str(excise_tax)) +
        Decimal(str(vat))
    )
    return round_up_to_hundred(total)


def calculate_cop_amount(
    cif_value: Union[float, Decimal],
    customs_duty_rate: Union[float, Decimal]
) -> Decimal:
    """
    COP Amount - Calculated WITH Customs Duty Rate applied.
    ALWAYS rounded UP to nearest 100.
    
    Formula: CEILING((cif_value * customs_duty_rate) / 100) * 100
    
    Args:
        cif_value: CIF value in USD
        customs_duty_rate: Customs duty rate as decimal
        
    Returns:
        COP amount (ALWAYS rounded UP to nearest 100)
    """
    cop = Decimal(str(cif_value)) * Decimal(str(customs_duty_rate))
    return round_up_to_hundred(cop)


# ================================================================
# NORMAL CASE FORMULAS
# ================================================================

def calculate_normal_case_customs_value(
    exchange_rate: Union[float, Decimal],
    item_price: Union[float, Decimal]
) -> Decimal:
    """
    NORMAL CASE: Calculate customs value from item price and exchange rate.
    
    Formula: exchange_rate * item_price
    
    Args:
        exchange_rate: Exchange rate (exact value, do not round)
        item_price: Item price in foreign currency
        
    Returns:
        Customs value (rounded to whole number after conversion)
    """
    customs_value = Decimal(str(exchange_rate)) * Decimal(str(item_price))
    return round_to_whole_number(customs_value)


def calculate_normal_case_cop(
    customs_value: Union[float, Decimal],
    cop_rate: Union[float, Decimal]
) -> Decimal:
    """
    NORMAL CASE: COP (Customs of Payment) = customs value × rate.
    ALWAYS rounded UP to nearest 100 per rounding_rules.json RULE_003.
    
    Formula: CEILING(customs_value * cop_rate / 100) * 100
    
    Args:
        customs_value: Customs value
        cop_rate: COP rate as decimal
        
    Returns:
        COP amount (ALWAYS rounded UP to nearest 100)
    """
    cop = Decimal(str(customs_value)) * Decimal(str(cop_rate))
    return round_up_to_hundred(cop)


def calculate_normal_case_sop(
    customs_value: Union[float, Decimal],
    cop_amount: Union[float, Decimal],
    sop_rate: Union[float, Decimal]
) -> Decimal:
    """
    NORMAL CASE: SOP (Special tax/Excise) = (customs value + COP amount) × rate.
    ALWAYS rounded UP to nearest 100 per rounding_rules.json RULE_003.
    
    Formula: CEILING((customs_value + cop_amount) * sop_rate / 100) * 100
    
    Args:
        customs_value: Customs value
        cop_amount: COP amount
        sop_rate: SOP rate as decimal
        
    Returns:
        SOP amount (ALWAYS rounded UP to nearest 100)
    """
    base = Decimal(str(customs_value)) + Decimal(str(cop_amount))
    sop = base * Decimal(str(sop_rate))
    return round_up_to_hundred(sop)


def calculate_normal_case_vop(
    customs_value: Union[float, Decimal],
    cop_amount: Union[float, Decimal],
    sop_amount: Union[float, Decimal],
    vop_rate: Union[float, Decimal]
) -> Decimal:
    """
    NORMAL CASE: VOP (VAT on Payment) - CONDITIONAL base based on goods taxability.
    ALWAYS rounded UP to nearest 100 per rounding_rules.json RULE_003.
    
    Formulas:
        - Non-taxable goods (SOP=0): CEILING((CIF + COP) × rate / 100) × 100
        - Taxable goods (SOP>0): CEILING((CIF + COP + SOP) × rate / 100) × 100
    
    Args:
        customs_value: Customs value
        cop_amount: COP amount
        sop_amount: SOP amount (0 for non-taxable, >0 for taxable)
        vop_rate: VOP rate as decimal (typically 0.10)
        
    Returns:
        VOP amount (ALWAYS rounded UP to nearest 100)
    """
    # CRITICAL: Check SOP to determine VAT base (non-taxable vs taxable)
    sop_decimal = Decimal(str(sop_amount))
    
    if sop_decimal == 0:
        # Non-taxable goods: VOP = (CIF + COP) × 10%
        base = Decimal(str(customs_value)) + Decimal(str(cop_amount))
    else:
        # Taxable goods: VOP = (CIF + COP + SOP) × 10%
        base = Decimal(str(customs_value)) + Decimal(str(cop_amount)) + sop_decimal
    
    vop = base * Decimal(str(vop_rate))
    return round_up_to_hundred(vop)


# ================================================================
# PETROLEUM CASE FORMULAS
# ================================================================

def calculate_petroleum_phase1_cpp_base(
    dv: Union[float, Decimal],
    exchange_rate: Union[float, Decimal],
    net_mass: Union[float, Decimal]
) -> Decimal:
    """
    PETROLEUM PHASE 1: CPP base calculation.
    
    Formula: (dv * exchange_rate * net_mass) / 1000
    
    Args:
        dv: Declared Value
        exchange_rate: Exchange rate (exact value)
        net_mass: Net mass in kg
        
    Returns:
        CPP base amount
    """
    cpp_base = (Decimal(str(dv)) * Decimal(str(exchange_rate)) * Decimal(str(net_mass))) / Decimal('1000')
    return round_to_whole_number(cpp_base)


def calculate_petroleum_phase1_cpp(
    cpp_base: Union[float, Decimal],
    cpp_rate: Union[float, Decimal]
) -> Decimal:
    """
    PETROLEUM PHASE 1: CPP (Customs Petroleum Payment).

    Formula: cpp_base * cpp_rate
    Rounding: round to whole number, then round UP to nearest 100 (SAD standard)

    Args:
        cpp_base: CPP base amount
        cpp_rate: CPP rate as decimal

    Returns:
        CPP amount
    """
    cpp = Decimal(str(cpp_base)) * Decimal(str(cpp_rate))
    return round_up_to_hundred(round_to_whole_number(cpp))


def calculate_petroleum_phase1_atp(
    atp_base: Union[float, Decimal],
    atp_rate: Union[float, Decimal],
    exchange_rate: Union[float, Decimal]
) -> Decimal:
    """
    PETROLEUM PHASE 1: ATP (Additional Tax Petroleum).
    ATP base = LTR (liter volume).

    Formula: atp_base * atp_rate * exchange_rate
    Rounding: round to whole number, then round UP to nearest 100 (SAD standard)

    Args:
        atp_base: ATP base (liters)
        atp_rate: ATP rate
        exchange_rate: Exchange rate (exact value)

    Returns:
        ATP amount
    """
    atp = Decimal(str(atp_base)) * Decimal(str(atp_rate)) * Decimal(str(exchange_rate))
    return round_up_to_hundred(round_to_whole_number(atp))


def calculate_petroleum_phase1_spp(
    cpp_base: Union[float, Decimal],
    cpp_amount: Union[float, Decimal],
    atp_amount: Union[float, Decimal],
    spp_rate: Union[float, Decimal]
) -> Decimal:
    """
    PETROLEUM PHASE 1: SPP (Special tax Petroleum).

    Formula: (cpp_base + cpp_amount + atp_amount) * spp_rate
    Rounding: round to whole number, then round UP to nearest 100 (SAD standard)

    Args:
        cpp_base: CPP base amount
        cpp_amount: CPP amount
        atp_amount: ATP amount
        spp_rate: SPP rate as decimal

    Returns:
        SPP amount
    """
    base = Decimal(str(cpp_base)) + Decimal(str(cpp_amount)) + Decimal(str(atp_amount))
    spp = base * Decimal(str(spp_rate))
    return round_up_to_hundred(round_to_whole_number(spp))


def calculate_petroleum_phase1_vpp_base(
    spp_base: Union[float, Decimal],
    spp_amount: Union[float, Decimal]
) -> Decimal:
    """
    PETROLEUM PHASE 1: VPP base calculation.
    SPP base = CPP base + CPP + ATP
    
    Formula: spp_base + spp_amount
    
    Args:
        spp_base: SPP base (cpp_base + cpp + atp)
        spp_amount: SPP amount
        
    Returns:
        VPP base amount
    """
    return Decimal(str(spp_base)) + Decimal(str(spp_amount))


def calculate_petroleum_phase1_vpp(
    vpp_base: Union[float, Decimal],
    vpp_rate: Union[float, Decimal]
) -> Decimal:
    """
    PETROLEUM PHASE 1: VPP (VAT Petroleum).

    Formula: vpp_base * vpp_rate
    Rounding: round to whole number, then round UP to nearest 100 (SAD standard)

    Args:
        vpp_base: VPP base amount
        vpp_rate: VPP rate as decimal (typically 0.10)

    Returns:
        VPP amount
    """
    vpp = Decimal(str(vpp_base)) * Decimal(str(vpp_rate))
    return round_up_to_hundred(round_to_whole_number(vpp))


def calculate_petroleum_dpp(
    phase1_total: Union[float, Decimal],
    phase2_total: Union[float, Decimal]
) -> Decimal:
    """
    PETROLEUM: DPP (partial subsidy by the state).
    Calculated from the difference between two-phase petroleum calculations.

    The importer ALWAYS pays Phase 1. DPP is handled separately by the state:
    - If Phase 2 > Phase 1: DPP is an "Additional charge" (state collects)
    - If Phase 1 > Phase 2: DPP is a "Subsidy by the state" (state pays)
    - DPP itself is NOT added to or subtracted from the importer's payable amount

    Formula: ABS(phase1_total - phase2_total)

    Args:
        phase1_total: Phase 1 total amount (DV basis)
        phase2_total: Phase 2 total amount (CIF basis)

    Returns:
        DPP amount (always >= 0)
    """
    diff = Decimal(str(phase1_total)) - Decimal(str(phase2_total))
    return abs(diff)


# ================================================================
# RUBBER CASE FORMULAS
# ================================================================

def calculate_rubber_etr(
    dv: Union[float, Decimal],
    exchange_rate: Union[float, Decimal],
    net_mass: Union[float, Decimal]
) -> Decimal:
    """
    RUBBER CASE: ETR (Export Tax on Rubber).
    
    Formula: (dv * exchange_rate * net_mass) / 1000
    
    Args:
        dv: Declared Value
        exchange_rate: Exchange rate (exact value)
        net_mass: Net mass in kg
        
    Returns:
        ETR amount
    """
    etr = (Decimal(str(dv)) * Decimal(str(exchange_rate)) * Decimal(str(net_mass))) / Decimal('1000')
    return round_to_whole_number(etr)


# ================================================================
# FTA/DV CASE FORMULAS
# ================================================================

def calculate_fta_dv_case_cop(
    customs_value: Union[float, Decimal],
    cop_rate: Union[float, Decimal] = Decimal('0')
) -> Decimal:
    """
    FTA/DV CASE: COP = Customs Value × Rate = 0 (typically).
    
    Formula: customs_value * cop_rate
    
    Args:
        customs_value: Customs value
        cop_rate: COP rate (typically 0 for FTA)
        
    Returns:
        COP amount (typically 0)
    """
    cop = Decimal(str(customs_value)) * Decimal(str(cop_rate))
    return round_to_whole_number(cop)


def calculate_fta_dv_case_cop_amount(
    customs_value: Union[float, Decimal],
    customs_duty_rate: Union[float, Decimal]
) -> Decimal:
    """
    FTA/DV CASE: COP Amount = Customs Value × Customs Duty Rate.
    Even when duty is 0%, this shows the calculated customs duty amount.
    ALWAYS rounded UP to nearest 100 per rounding_rules.json RULE_003.
    
    Formula: CEILING(customs_value * customs_duty_rate / 100) * 100
    
    Args:
        customs_value: Customs value
        customs_duty_rate: Customs duty rate as decimal
        
    Returns:
        COP amount (ALWAYS rounded UP to nearest 100)
    """
    cop = Decimal(str(customs_value)) * Decimal(str(customs_duty_rate))
    return round_up_to_hundred(cop)


def calculate_fta_dv_case_sop(
    customs_value: Union[float, Decimal],
    cop_amount: Union[float, Decimal],
    sop_rate: Union[float, Decimal]
) -> Decimal:
    """
    FTA/DV CASE: SOP = (Custom Value + COP Amount) × Rate.
    ALWAYS rounded UP to nearest 100 per rounding_rules.json RULE_003.
    
    Formula: CEILING((customs_value + cop_amount) * sop_rate / 100) * 100
    
    Args:
        customs_value: Customs value
        cop_amount: COP amount
        sop_rate: SOP rate as decimal
        
    Returns:
        SOP amount (ALWAYS rounded UP to nearest 100)
    """
    base = Decimal(str(customs_value)) + Decimal(str(cop_amount))
    sop = base * Decimal(str(sop_rate))
    return round_up_to_hundred(sop)


def calculate_fta_dv_case_vop(
    customs_value: Union[float, Decimal],
    cop_amount: Union[float, Decimal],
    sop_amount: Union[float, Decimal],
    vop_rate: Union[float, Decimal]
) -> Decimal:
    """
    FTA/DV CASE: VOP = (Customs Value + COP Amount + SOP Amount) × Rate.
    ALWAYS rounded UP to nearest 100 per rounding_rules.json RULE_003.
    
    Formula: CEILING((customs_value + cop_amount + sop_amount) * vop_rate / 100) * 100
    
    Args:
        customs_value: Customs value
        cop_amount: COP amount
        sop_amount: SOP amount
        vop_rate: VOP rate as decimal
        
    Returns:
        VOP amount (ALWAYS rounded UP to nearest 100)
    """
    base = Decimal(str(customs_value)) + Decimal(str(cop_amount)) + Decimal(str(sop_amount))
    vop = base * Decimal(str(vop_rate))
    return round_up_to_hundred(vop)


# ================================================================
# FTA/DV & DQ CASE FORMULAS
# ================================================================

def calculate_fta_dv_dq_case_cop(
    cop_base: Union[float, Decimal],
    cop_rate: Union[float, Decimal] = Decimal('0')
) -> Decimal:
    """
    FTA/DV & DQ CASE: COP = COP base × Rate = 0.
    
    Formula: cop_base * cop_rate
    
    Args:
        cop_base: COP base
        cop_rate: COP rate (0 under FTA)
        
    Returns:
        COP amount (0)
    """
    cop = Decimal(str(cop_base)) * Decimal(str(cop_rate))
    return round_to_whole_number(cop)


def calculate_fta_dv_dq_case_sop_base(
    customs_value: Union[float, Decimal],
    cop_amount: Union[float, Decimal]
) -> Decimal:
    """
    FTA/DV & DQ CASE: SOP base = Customs Value + COP Amount.
    
    Formula: customs_value + cop_amount
    
    Args:
        customs_value: Customs value
        cop_amount: COP amount
        
    Returns:
        SOP base amount
    """
    return Decimal(str(customs_value)) + Decimal(str(cop_amount))


def calculate_fta_dv_dq_case_sop(
    sop_base: Union[float, Decimal],
    cop_base: Union[float, Decimal],
    sop_rate: Union[float, Decimal],
    dq: Union[float, Decimal]
) -> Decimal:
    """
    FTA/DV & DQ CASE: SOP = (SOP base + COP base) × Rate × DQ.
    ALWAYS rounded UP to nearest 100 per rounding_rules.json RULE_003.
    
    Formula: CEILING((sop_base + cop_base) * sop_rate * dq / 100) * 100
    
    Args:
        sop_base: SOP base
        cop_base: COP base
        sop_rate: SOP rate as decimal
        dq: DQ (Deal/Trade Agreement) factor
        
    Returns:
        SOP amount with DQ adjustment (ALWAYS rounded UP to nearest 100)
    """
    base = Decimal(str(sop_base)) + Decimal(str(cop_base))
    sop = base * Decimal(str(sop_rate)) * Decimal(str(dq))
    return round_up_to_hundred(sop)


def calculate_fta_dv_dq_case_vop_base(
    customs_value: Union[float, Decimal],
    cop_amount: Union[float, Decimal],
    sop_amount: Union[float, Decimal]
) -> Decimal:
    """
    FTA/DV & DQ CASE: VOP base = Customs Value + COP Amount + SOP Amount.
    
    Formula: customs_value + cop_amount + sop_amount
    
    Args:
        customs_value: Customs value
        cop_amount: COP amount
        sop_amount: SOP amount
        
    Returns:
        VOP base amount
    """
    return Decimal(str(customs_value)) + Decimal(str(cop_amount)) + Decimal(str(sop_amount))


def calculate_fta_dv_dq_case_vop(
    vop_base: Union[float, Decimal],
    vop_rate: Union[float, Decimal]
) -> Decimal:
    """
    FTA/DV & DQ CASE: VOP = VOP base × Rate.
    ALWAYS rounded UP to nearest 100 per rounding_rules.json RULE_003.
    
    Formula: CEILING(vop_base * vop_rate / 100) * 100
    
    Args:
        vop_base: VOP base amount
        vop_rate: VOP rate as decimal
        
    Returns:
        VOP amount (ALWAYS rounded UP to nearest 100)
    """
    vop = Decimal(str(vop_base)) * Decimal(str(vop_rate))
    return round_up_to_hundred(vop)


# ================================================================
# HIGH-LEVEL CALCULATION CASES
# ================================================================

def calculate_normal_case(
    exchange_rate: Union[float, Decimal],
    item_price: Union[float, Decimal],
    cop_rate: Union[float, Decimal],
    sop_rate: Union[float, Decimal],
    vop_rate: Union[float, Decimal] = Decimal('0.10')
) -> Dict[str, Decimal]:
    """
    NORMAL CASE: Standard import calculation for regular goods.
    
    Sequence:
        1. Customs Value = Exchange Rate × Item Price
        2. COP = Customs Value × COP Rate
        3. SOP = (Customs Value + COP) × SOP Rate
        4. VOP = (Customs Value + COP + SOP) × VOP Rate
        5. Apply final rounding (round UP to 100)
    
    Args:
        exchange_rate: Exchange rate (exact value)
        item_price: Item price in foreign currency
        cop_rate: COP rate as decimal
        sop_rate: SOP rate as decimal
        vop_rate: VOP rate as decimal (default 0.10)
        
    Returns:
        Dict with all calculated values
    """
    customs_value = calculate_normal_case_customs_value(exchange_rate, item_price)
    cop_amount = calculate_normal_case_cop(customs_value, cop_rate)
    sop_amount = calculate_normal_case_sop(customs_value, cop_amount, sop_rate)
    vop_amount = calculate_normal_case_vop(customs_value, cop_amount, sop_amount, vop_rate)
    
    total_base = cop_amount + sop_amount + vop_amount
    total_payable = round_up_to_hundred(total_base)
    
    return {
        'customs_value': customs_value,
        'cop': cop_amount,
        'sop': sop_amount,
        'vop': vop_amount,
        'total_base': total_base,
        'total_payable': total_payable
    }


def calculate_fta_dv_case(
    customs_value: Union[float, Decimal],
    customs_duty_rate: Union[float, Decimal],
    sop_rate: Union[float, Decimal],
    vop_rate: Union[float, Decimal] = Decimal('0.10')
) -> Dict[str, Decimal]:
    """
    FTA/DV CASE: Free Trade Agreement with Declared Value (duty typically 0%) with CONDITIONAL VAT base.
    
    Sequence:
        1. Currency Conversion: Already done (customs_value provided)
        2. COP = Customs Value × FTA Rate = 0 (typically)
        3. COP Amount = Customs Value × Customs Duty Rate (shows 0 for FTA)
        4. SOP = (CIF + COP Amount) × SOP Rate
        5. VAT Calculation (CONDITIONAL):
           - Non-taxable FTA goods (SOP=0): VOP = (CIF + COP) × 10%
           - Taxable FTA goods (SOP>0): VOP = (CIF + COP + SOP) × 10%
        6. Total Duties & Taxes: TDT = COP Amount + SOP + VOP
        7. Final Total: Round UP to nearest 100
    
    Args:
        customs_value: Customs value (CIF in KHR)
        customs_duty_rate: Customs duty rate as decimal (0 for FTA)
        sop_rate: SOP rate as decimal
        vop_rate: VOP rate as decimal (default 0.10)
        
    Returns:
        Dict with all calculated values
    """
    # Step 2: COP = 0 for FTA (conceptual only)
    cop = calculate_fta_dv_case_cop(customs_value, Decimal('0'))
    
    # Step 3: COP Amount shows what duty would be calculated
    cop_amount = calculate_fta_dv_case_cop_amount(customs_value, customs_duty_rate)
    
    # Step 4: SOP = (CIF + COP) × SOP Rate
    sop_amount = calculate_fta_dv_case_sop(customs_value, cop_amount, sop_rate)
    
    # Step 5: VOP - CONDITIONAL on whether SOP applies
    # Non-taxable FTA goods: VOP = (CIF + COP) × 10%
    # Taxable FTA goods (e.g., smartphones with ATIGA Form D): VOP = (CIF + COP + SOP) × 10%
    sop_decimal = Decimal(str(sop_amount))
    if sop_decimal == 0:
        # Non-taxable: base = CIF + COP
        vop_base = Decimal(str(customs_value)) + Decimal(str(cop_amount))
    else:
        # Taxable: base = CIF + COP + SOP
        vop_base = Decimal(str(customs_value)) + Decimal(str(cop_amount)) + sop_decimal
    
    vop_amount = vop_base * Decimal(str(vop_rate))
    vop_amount = round_to_whole_number(vop_amount)
    
    # Step 6: Total Duties & Taxes
    total_duties_and_taxes = cop_amount + sop_amount + vop_amount
    
    # Step 7: Final Total (rounded UP to 100)
    total_payable = round_up_to_hundred(total_duties_and_taxes)
    
    return {
        'customs_value': customs_value,
        'cop': cop,
        'cop_amount': cop_amount,
        'sop': sop_amount,
        'vop': vop_amount,
        'total_duties_and_taxes': total_duties_and_taxes,
        'total_payable': total_payable
    }


# ================================================================
# UTILITY FUNCTIONS
# ================================================================

def convert_currency(
    amount: Union[float, Decimal],
    exchange_rate: Union[float, Decimal]
) -> Decimal:
    """
    Convert currency using exchange rate (DO NOT round the rate itself).
    
    Args:
        amount: Amount in foreign currency
        exchange_rate: Exchange rate (exact value, do not round)
        
    Returns:
        Converted amount (rounded to whole number after conversion)
    """
    converted = Decimal(str(amount)) * Decimal(str(exchange_rate))
    return round_to_whole_number(converted)


def validate_positive(value: Union[float, Decimal], field_name: str) -> None:
    """
    Validate that a value is positive.
    
    Args:
        value: Value to validate
        field_name: Name of the field for error message
        
    Raises:
        ValueError: If value is not positive
    """
    if Decimal(str(value)) <= 0:
        raise ValueError(f"{field_name} must be positive, got {value}")


def validate_rate(rate: Union[float, Decimal], field_name: str) -> None:
    """
    Validate that a rate is between 0 and 1 (0% to 100%).
    
    Args:
        rate: Rate to validate (as decimal, e.g., 0.10 for 10%)
        field_name: Name of the field for error message
        
    Raises:
        ValueError: If rate is not between 0 and 1
    """
    rate_decimal = Decimal(str(rate))
    if rate_decimal < 0 or rate_decimal > 1:
        raise ValueError(f"{field_name} must be between 0 and 1, got {rate}")

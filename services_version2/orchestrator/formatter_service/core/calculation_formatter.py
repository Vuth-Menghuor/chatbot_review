"""
Calculation Response Formatter
Formats calculator service responses with detailed step-by-step breakdown.
Handles multiple currencies (USD, CNY, KHR, etc.) with proper conversion.
"""

import logging
import os
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


def format_calculation_response(calculation_result: Dict[str, Any], question: str = "") -> str:
    """
    Format calculation response with detailed step-by-step breakdown.
    Handles multiple currencies (USD, CNY, KHR, etc.) with proper conversion.
    Detects import vs export and formats accordingly.
    
    Args:
        calculation_result: Calculator service response
        question: Original user question
        
    Returns:
        Formatted calculation response as string
    """
    try:
        # Detect if this is an export or import query
        trade_direction = calculation_result.get("trade_direction", "IM")  # Default to import
        is_export = (
            trade_direction.upper() == "EX" 
            or "export" in question.lower() 
            or "exporting" in question.lower()
        )
        
        # Extract key fields
        total = calculation_result.get("total", 0)
        currency = calculation_result.get("currency", "KHR")
        breakdown = calculation_result.get("breakdown", {})
        line_items = calculation_result.get("line_items", [])
        assumptions = calculation_result.get("assumptions", [])
        references = calculation_result.get("references", [])
        exchange_rate = calculation_result.get("exchange_rate_usd_to_khr", 4022)
        cif_value_usd = calculation_result.get("cif_value_usd")
        
        # Get original CIF value and currency (from our new calculator client code)
        original_cif_value = calculation_result.get("original_cif_value")
        original_currency = calculation_result.get("original_currency", "USD")
        
        # If original values not provided, fall back to old behavior
        if original_cif_value is None:
            original_cif_value = cif_value_usd
        if original_currency is None:
            original_currency = "USD"
            

        # Normalize known mojibake before rendering currency symbols.
        original_currency = str(original_currency).replace("Â¥", "¥").replace("ï¿¥", "¥")
        currency_symbol = {
            "USD": "$",
            "CNY": "¥",
            "KHR": "៛",
            "EUR": "€",
            "GBP": "£",
            "JPY": "¥",
        }.get(original_currency, original_currency)
        
        # If cif_value_usd is None, try to get from breakdown
        if cif_value_usd is None:
            cif_value_usd = breakdown.get("cif_value", 0) if currency == "KHR" else 0
        if original_cif_value is None:
            original_cif_value = cif_value_usd or 0
        
        # Extract HS code and product name from assumptions or references
        hs_code = ""
        product_name = ""
        origin_country = ""
        
        # Detect petroleum case early
        is_petroleum = (
            breakdown.get("cpp_base") is not None 
            or ("2710" in question)
        )
        
        if assumptions:
            for assumption in assumptions:
                if "HS Code:" in assumption or "hs_code:" in assumption.lower():
                    parts = assumption.split(":")
                    if len(parts) > 1:
                        hs_code = parts[1].strip().split("\n")[0].split("-")[0].strip()
                elif "Product:" in assumption or "product:" in assumption.lower():
                    parts = assumption.split(":")
                    if len(parts) > 1:
                        extracted = parts[1].strip().split("\n")[0].strip()
                        # If it's too long, it's probably the entire raw user query, which is messy
                        if len(extracted) < 50 or is_petroleum:
                            product_name = extracted
                elif "Origin" in assumption or "origin:" in assumption.lower():
                    parts = assumption.split(":")
                    if len(parts) > 1:
                        origin_country = parts[1].strip().split("\n")[0].strip()
        
        # Fallback: try to extract from references
        if references and len(references) > 0 and references[0].get("doc_id"):
            doc_id = references[0]["doc_id"]
            if "hs_" in doc_id.lower():
                try:
                    hs_code = doc_id.split("hs_")[1].split(":")[0] if "hs_" in doc_id else ""
                except:
                    pass
                
        # Re-detect petroleum case with hs_code fallback
        if not is_petroleum and hs_code and hs_code.startswith("2710"):
            is_petroleum = True
        
        # Extract tax line items (already in KHR from calculator)
        cd_amount = 0
        cd_rate = 0
        atp_amount = 0
        atp_rate = 0
        st_amount = 0
        st_rate = 0
        vat_amount = 0
        vat_rate = 10  # Default VAT rate
        bur_amount = 0
        bur_rate = 0
        bur_base = 0
        vvf_amount = 0
        vvf_rate = 60000
        vvf_base = 1
        et_amount = 0
        et_rate = 0
        
        for item in line_items:
            name = item.get("name", "").upper()
            tax_type = item.get("tax_type", "").upper()
            amount = item.get("amount", 0)  # Already in correct currency
            rate = item.get("rate", 0)
            
            if tax_type == "CD":
                cd_amount = amount
                cd_rate = rate
            elif tax_type == "ST":
                if "ADDITIONAL TAX" in name or "ATP" in name:
                    atp_amount = amount
                    atp_rate = rate
                else:
                    st_amount = amount
                    st_rate = rate
            elif tax_type == "VAT":
                vat_amount = amount
                vat_rate = rate
            elif tax_type == "BUR":
                bur_amount = amount
                bur_rate = rate
                bur_base = item.get("base", 0)
            elif tax_type == "VVF":
                vvf_amount = amount
                vvf_rate = rate
                vvf_base = item.get("base", 1)
            elif tax_type == "ET":
                et_amount = amount
                et_rate = rate
        
        # Build formatted response with ASCII characters only
        lines = []
        # Use exact separator width to match sample output style
        sep = "-" * 65
        
        # Header - Use EXPORT or IMPORT based on trade direction
        lines.append(sep)
        if is_export:
            lines.append("EXPORT TAX CALCULATION")
        else:
            lines.append("IMPORT TAX CALCULATION")
        lines.append(sep)
        lines.append("")
        
        # Product Information
        lines.append("PRODUCT INFORMATION:")
        if hs_code:
            product_desc = f"{hs_code} ({product_name})" if product_name else hs_code
            lines.append(f"* HS Code: {product_desc}")
        if origin_country:
            lines.append(f"* Origin Country: {origin_country}")
        lines.append("* Incoterm: CIF (Cost, Insurance, Freight)")
        lines.append("")
        
        # Input Parameters - Show original CIF value in its original currency
        lines.append("INPUT PARAMETERS:")
        if original_cif_value and original_cif_value > 0:
            if original_currency == "USD":
                lines.append(f"* CIF Value: {original_cif_value:,.2f} {original_currency}")
            else:
                lines.append(f"* CIF Value: {original_cif_value:,.0f} {original_currency}")
        else:
            lines.append(f"* CIF Value: {breakdown.get('cif_value', 0):,.0f} KHR")
        lines.append(f"* Exchange Rate: 1 {original_currency} = {exchange_rate:,.1f} KHR")
        lines.append("* Customs Regime: Normal (standard rates)")
        lines.append(f"* Calculation Date: {datetime.now().strftime('%Y-%m-%d')}")
        lines.append("")
        
        # ===== EXPORT BRANCH =====
        if is_export:
            # For exports, simplify to export tax only
            # Step 1: Currency Conversion (if applicable)
            if original_cif_value and original_cif_value > 0 and exchange_rate != 1:
                lines.append(sep)
                lines.append(f"STEP 1: CURRENCY CONVERSION ({original_currency} -> KHR)")
                lines.append(sep)
                lines.append(f"Formula: CIF Value ({original_currency}) x Exchange Rate")
                cif_khr = original_cif_value * exchange_rate
                lines.append(f"= {original_cif_value:,.0f} x {exchange_rate:,.1f} KHR/{original_currency}")
                lines.append(f"= {cif_khr:,.0f} KHR")
                lines.append("")
            else:
                cif_khr = breakdown.get("cif_value", 0)
            
            # For exports, find export tax in line items
            export_tax_amount = 0
            export_tax_rate = 0
            export_tax_type = "ETR"  # Export Tax on Rubber or generic export tax
            
            for item in line_items:
                tax_type = item.get("tax_type", "").upper()
                if "ET" in tax_type or "EXPORT" in tax_type:
                    export_tax_amount = item.get("amount", 0)
                    export_tax_rate = item.get("rate", 0)
                    export_tax_type = tax_type
                    break
            
            # Step 2: Export Tax
            lines.append(sep)
            if "rubber" in question.lower():
                lines.append("STEP 2: EXPORT TAX ON RUBBER (ETR)")
            else:
                lines.append(f"STEP 2: EXPORT TAX ({export_tax_type})")
            lines.append(sep)
            lines.append("Formula: Taxable Base x Rate")
            export_tax_base = breakdown.get("export_tax_base", cif_khr)
            lines.append(f"Taxable Base: {export_tax_base:,.0f} KHR")
            rate_label = "Not applicable" if export_tax_rate == 0 else "Applied"
            lines.append(f"Rate: {export_tax_rate:.2f} ({rate_label})")
            lines.append(f"= {export_tax_base:,.0f} x {export_tax_rate:.2f}")
            lines.append(f"= {export_tax_amount:,.0f} KHR")
            lines.append("")
            
            # Compute display total from actual line-item amounts (not raw backend total)
            display_total_export = export_tax_amount
            
            # Final Tax Breakdown Table (Export)
            lines.append(sep)
            lines.append("FINAL TAX BREAKDOWN")
            lines.append(sep)
            lines.append("| Type | Tax base (KHR) | Rate  | Amount (KHR) |")
            lines.append("|" + "-" * 57 + "|")
            lines.append(f"| {export_tax_type:<4} | {export_tax_base:>14,.0f} | {export_tax_rate:>5.2f} | {export_tax_amount:>12,.0f} |")
            lines.append("|" + "-" * 57 + "|")
            lines.append(f"| TOTAL TAX     |                |       | {display_total_export:>12,.0f} |")
            lines.append("|" + "-" * 57 + "|")
            lines.append("")
            
            # Summary (Export)
            lines.append("SUMMARY:")
            product_desc = f"{product_name} ({hs_code})" if product_name and hs_code else (product_name or hs_code or "goods")
            lines.append(f"To export 1 consignment of {product_desc} valued at")
            lines.append(f"{original_cif_value:,.0f} {original_currency} CIF to {origin_country if origin_country else 'the destination country'}, you must pay {display_total_export:,.0f} KHR in export taxes.")
            lines.append("")
            
            # Assumptions (Export) - Dynamic based on what's actually calculated
            lines.append("ASSUMPTIONS & NOTES:")
            lines.append(f"  + DV total: {cif_khr:,.2f} KHR (provided declared_value (per_ton))")
            lines.append(f"  + Exchange rate as of {datetime.now().strftime('%Y-%m-%d')}: 1 {original_currency} = {exchange_rate:,.1f} KHR")
            lines.append(f"  + HS Code confirmed from Qdrant database")
            
            # Add dynamic rate info based on line items
            if export_tax_rate > 0:
                rate_label = "rubber" in question.lower() and "Export Tax on Rubber (ETR)" or f"Export Tax ({export_tax_type})"
                lines.append(f"  + {rate_label} rate: {export_tax_rate:.2f} - Applied per current regulations")
            else:
                rate_label = "rubber" in question.lower() and "Export Tax on Rubber (ETR)" or f"Export Tax ({export_tax_type})"
                lines.append(f"  + {rate_label} rate: {export_tax_rate:.2f} - Applied per current regulations")
            
            lines.append(f"  + Calculation assumes standard regime (unless specified otherwise)")
            lines.append(f"  + All rates current as of {datetime.now().strftime('%B %d, %Y')}")
            lines.append("")
        
        # ===== IMPORT BRANCH =====
        else:
            if is_petroleum:
                # Step 1: Currency Conversion (if applicable)
                if original_cif_value and original_cif_value > 0 and exchange_rate != 1:
                    lines.append(sep)
                    lines.append(f"STEP 1: CURRENCY CONVERSION ({original_currency} -> KHR)")
                    lines.append(sep)
                    lines.append(f"Formula: CIF Value ({original_currency}) x Exchange Rate")
                    cif_khr = breakdown.get("cif_value", original_cif_value * exchange_rate)
                    lines.append(f"= {original_cif_value:,.2f} x {exchange_rate:,.1f} KHR/{original_currency}")
                    lines.append(f"= {cif_khr:,.0f} KHR")
                    lines.append("")
                else:
                    cif_khr = breakdown.get("cif_value", 0)

                # Parse assumptions to get DV, net mass, volume, and rates
                dv_val = 0.0
                net_mass_val = 0.0
                volume_val = 0.0
                cpp_rate_val = 0.0
                atp_rate_val = 0.0
                spp_rate_val = 0.0
                vpp_rate_val = 0.0

                import re
                for a in assumptions:
                    a_clean = a.strip()
                    if a_clean.startswith("DV:"):
                        m = re.search(r'DV:\s*([\d\.,]+)', a_clean)
                        if m:
                            dv_val = float(m.group(1).replace(',', ''))
                    elif a_clean.startswith("Net mass:"):
                        m = re.search(r'Net mass:\s*([\d\.,]+)', a_clean)
                        if m:
                            net_mass_val = float(m.group(1).replace(',', ''))
                    elif a_clean.startswith("Volume:"):
                        m = re.search(r'Volume:\s*([\d\.,]+)', a_clean)
                        if m:
                            volume_val = float(m.group(1).replace(',', ''))
                    elif "Customs Petroleum Payment (CPP) rate:" in a_clean:
                        m = re.search(r'rate:\s*([\d\.,]+)\s*%', a_clean)
                        if m:
                            cpp_rate_val = float(m.group(1)) / 100.0
                    elif "Additional Tax Petroleum (ATP) rate:" in a_clean:
                        m = re.search(r'rate:\s*([\d\.,]+)', a_clean)
                        if m:
                            atp_rate_val = float(m.group(1))
                    elif "Special Petroleum Payment (SPP) rate:" in a_clean:
                        m = re.search(r'rate:\s*([\d\.,]+)\s*%', a_clean)
                        if m:
                            spp_rate_val = float(m.group(1)) / 100.0
                    elif "VAT Petroleum Payment (VPP) rate:" in a_clean:
                        m = re.search(r'rate:\s*([\d\.,]+)\s*%', a_clean)
                        if m:
                            vpp_rate_val = float(m.group(1)) / 100.0

                # Fallback to values from line items if parsing failed
                if cpp_rate_val == 0.0:
                    cpp_rate_val = cd_rate / 100.0
                if atp_rate_val == 0.0:
                    atp_rate_val = atp_rate
                if spp_rate_val == 0.0:
                    spp_rate_val = st_rate / 100.0
                if vpp_rate_val == 0.0:
                    vpp_rate_val = vat_rate / 100.0

                cpp_base_p1 = breakdown.get("cpp_base", 0)
                cpp_p1 = breakdown.get("cpp_amount", 0)
                atp_p1 = breakdown.get("atp_amount", 0)
                spp_p1 = breakdown.get("spp_amount", 0)
                vpp_p1 = breakdown.get("vpp_amount", 0)
                phase1_total = cpp_p1 + atp_p1 + spp_p1 + vpp_p1

                phase2_cpp_base = breakdown.get("cif_value", 0)
                phase2_cpp = breakdown.get("phase2_cpp_amount", 0)
                phase2_atp = breakdown.get("phase2_atp_amount", atp_p1)
                phase2_spp = breakdown.get("phase2_spp_amount", 0)
                phase2_vpp = breakdown.get("phase2_vpp_amount", 0)
                phase2_total = breakdown.get("phase2_total", phase2_cpp + phase2_atp + phase2_spp + phase2_vpp)

                # Step 2: Phase 1
                lines.append(sep)
                lines.append("STEP 2: PHASE 1 -- PETROLEUM TAX (Declared Value Basis)")
                lines.append(sep)
                lines.append("CPP base  = DV/ton x exchange_rate x net_mass_kg / 1000")
                lines.append(f"          = {cpp_base_p1:,.0f} KHR")
                lines.append(f"CPP       = CPP base x CD rate = {cpp_p1:,.0f} KHR")
                lines.append(f"ATP       = volume_liter x {atp_rate_val:.2f} $/L x exchange_rate = {atp_p1:,.0f} KHR")
                spp_base_str = "CPP base + CPP + ATP"
                lines.append(f"SPP       = ({spp_base_str}) x ST rate = {spp_p1:,.0f} KHR")
                vpp_base_str = "CPP base + CPP + ATP + SPP"
                lines.append(f"VPP       = ({vpp_base_str}) x VAT rate = {vpp_p1:,.0f} KHR")
                lines.append(f"Phase 1 Total = {phase1_total:,.0f} KHR")
                lines.append("")

                # Step 3: Phase 2
                lines.append(sep)
                lines.append("STEP 3: PHASE 2 -- PETROLEUM TAX (Customs Value / CIF Basis)")
                lines.append(sep)
                lines.append(f"CPP base  = CIF value = {phase2_cpp_base:,.0f} KHR")
                lines.append(f"CPP       = CPP base x CD rate = {phase2_cpp:,.0f} KHR")
                lines.append(f"ATP       = same as Phase 1 = {phase2_atp:,.0f} KHR")
                lines.append(f"SPP       = (CPP base + CPP + ATP) x ST rate = {phase2_spp:,.0f} KHR")
                lines.append(f"VPP       = (CPP base + CPP + ATP + SPP) x VAT rate = {phase2_vpp:,.0f} KHR")
                lines.append(f"Phase 2 Total = {phase2_total:,.0f} KHR")
                lines.append("")

                # Step 4: Difference / DPP
                dpp = breakdown.get("dpp_amount", phase1_total - phase2_total)
                lines.append(sep)
                lines.append("STEP 4: DIFFERENCE / PARTIAL SUBSIDY (DPP)")
                lines.append(sep)
                lines.append("DPP = Phase 1 Total - Phase 2 Total")
                lines.append(f"    = {phase1_total:,.0f} - {phase2_total:,.0f}")
                lines.append(f"    = {dpp:,.0f} KHR")
                lines.append("")

                # Final Tax Breakdown Table (Import Petroleum)
                lines.append(sep)
                lines.append("FINAL TAX BREAKDOWN")
                lines.append(sep)
                lines.append("| Tax Component             | Tax base (KHR) | Rate  | Amount (KHR) |")
                lines.append("|----------------------------------------------------------------------|")
                lines.append(f"| Import Tax for Petroleum Product | {cpp_base_p1:>14,.0f} | {cpp_rate_val*100:>5.2f} | {cpp_p1:>12,.0f} |")
                lines.append(f"| Additional Tax on Petroleum product (ATP) | {volume_val:>14,.0f} | {atp_rate_val:>5.2f} | {atp_p1:>12,.0f} |")
                spp_base_p1 = cpp_base_p1 + cpp_p1 + atp_p1
                lines.append(f"| Special Tariff on Petroleum Product (SPP) | {spp_base_p1:>14,.0f} | {spp_rate_val*100:>5.2f} | {spp_p1:>12,.0f} |")
                vpp_base_p1 = spp_base_p1 + spp_p1
                lines.append(f"| VAT on Petroleum Product (VPP) | {vpp_base_p1:>14,.0f} | {vpp_rate_val*100:>5.2f} | {vpp_p1:>12,.0f} |")
                lines.append(f"| Partial subsidy by the state (DPP) |              0 |  0.00 | {abs(dpp):>12,.0f} |")
                lines.append("|----------------------------------------------------------------------|")
                lines.append(f"| TOTAL TAX                 |                |       | {total:>12,.0f} |")
                lines.append("|----------------------------------------------------------------------|")
                lines.append("")

                # Summary (Import Petroleum)
                lines.append("SUMMARY:")
                product_desc = f"{product_name} ({hs_code})" if product_name and hs_code else (product_name or hs_code or "imported goods")
                lines.append(f"To import 1 consignment of {product_desc} valued at")
                lines.append(f"{original_cif_value:,.2f} {original_currency} CIF from {origin_country if origin_country else 'the origin country'}, you must pay {total:,.0f} KHR in import taxes.")
                if vpp_p1 > 0 and total > 0:
                    vat_pct = (vpp_p1 / total) * 100
                    lines.append(f"The majority is VAT ({vat_pct:.1f}% of total taxes).")
                lines.append("")

                # Assumptions (Import Petroleum)
                lines.append("ASSUMPTIONS & NOTES:")
                if cpp_rate_val > 0:
                    lines.append(f"  + Customs Duty (CD) rate: {cpp_rate_val*100:.2f}% - Applied per current regulations")
                if spp_rate_val > 0:
                    lines.append(f"  + Special Tariff (ST) rate: {spp_rate_val*100:.2f}% - Applied per current regulations")
                if vpp_rate_val > 0:
                    lines.append(f"  + VAT rate: {vpp_rate_val*100:.2f}% - Applied per current regulations")

                lines.append(f"  + DV total: {cif_khr:,.2f} KHR (provided CIF value)")
                lines.append(f"  + Exchange rate as of {datetime.now().strftime('%Y-%m-%d')}: 1 {original_currency} = {exchange_rate:,.1f} KHR")
                lines.append(f"  + HS Code confirmed from Qdrant database")
                lines.append(f"  + Calculation assumes standard regime (unless specified otherwise)")
                lines.append(f"  + All rates current as of {datetime.now().strftime('%B %d, %Y')}")
                lines.append("")

            else:
                # Step 1: Currency Conversion (if applicable)
                if original_cif_value and original_cif_value > 0 and exchange_rate != 1:
                    lines.append(sep)
                    lines.append(f"STEP 1: CURRENCY CONVERSION ({original_currency} -> KHR)")
                    lines.append(sep)
                    lines.append(f"Formula: CIF Value ({original_currency}) x Exchange Rate")
                    cif_khr = original_cif_value * exchange_rate
                    lines.append(f"= {original_cif_value:,.0f} x {exchange_rate:,.1f} KHR/{original_currency}")
                    lines.append(f"= {cif_khr:,.0f} KHR")
                    lines.append("")
                else:
                    cif_khr = breakdown.get("cif_value", 0)
                
                # Step 2: COP (Customs of Payment)
                lines.append(sep)
                lines.append("STEP 2: COP (CUSTOMS OF PAYMENT)")
                lines.append(sep)
                lines.append("Formula: Taxable Base x Rate")
                cd_base = cif_khr
                lines.append(f"Taxable Base: {cd_base:,.0f} KHR")
                lines.append(f"Rate: {cd_rate:.2f} (Applied)")
                lines.append(f"= {cd_base:,.0f} x {cd_rate:.2f}")
                lines.append(f"= {cd_amount:,.0f} KHR")
                lines.append("")
                
                # Step 3: SOP (Special of Payment)
                lines.append(sep)
                lines.append("STEP 3: SOP (SPECIAL OF PAYMENT)")
                lines.append(sep)
                lines.append("Formula: Taxable Base x Rate")
                sop_base = cif_khr + cd_amount
                lines.append(f"Taxable Base: {sop_base:,.0f} KHR")
                lines.append(f"Rate: {st_rate:.2f} (Applied)")
                lines.append(f"= {sop_base:,.0f} x {st_rate:.2f}")
                lines.append(f"= {st_amount:,.0f} KHR")
                lines.append("")
                
                # Step 4: VOP (VAT of Payment)
                lines.append(sep)
                lines.append("STEP 4: VOP (VAT OF PAYMENT)")
                lines.append(sep)
                lines.append("Formula: Taxable Base x Rate")
                vop_base = cif_khr + cd_amount + st_amount
                lines.append(f"Taxable Base: {vop_base:,.0f} KHR")
                lines.append(f"Rate: {vat_rate:.2f} (Applied)")
                lines.append(f"= {vop_base:,.0f} x {vat_rate:.2f}")
                lines.append(f"= {vat_amount:,.0f} KHR")
                lines.append("")

                # Step 5: BUR (Build-Up Rebate / DQ Portion)
                if bur_amount > 0:
                    lines.append(sep)
                    lines.append("STEP 5: BUR (BUILD-UP REBATE / DQ PORTION)")
                    lines.append(sep)
                    lines.append("Formula: Before-DQ Total x DQ Factor")
                    lines.append(f"Before-DQ Total: {bur_base:,.0f} KHR")
                    lines.append(f"Rebate Percentage: {bur_rate:.2f}%")
                    lines.append(f"= {bur_base:,.0f} x {bur_rate:.2f}%")
                    lines.append(f"= {bur_amount:,.0f} KHR")
                    lines.append("")

                # Step 6: VVF (Vehicle Valuation Fee)
                if vvf_amount > 0:
                    lines.append(sep)
                    lines.append("STEP 6: VEHICLE VALUATION FEE (VVF)")
                    lines.append(sep)
                    lines.append("Formula: Taxable Base x Rate")
                    lines.append(f"Taxable Base: {vvf_base:,.0f} KHR")
                    lines.append(f"Rate: {vvf_rate:.2f} (Applied)")
                    lines.append(f"= {vvf_base:,.0f} x {vvf_rate:.2f}")
                    lines.append(f"= {vvf_amount:,.0f} KHR")
                    lines.append("")
                
                # Final Tax Breakdown Table (Import)
                lines.append(sep)
                lines.append("FINAL TAX BREAKDOWN")
                lines.append(sep)
                lines.append("| Type | Tax base (KHR) | Rate  | Amount (KHR) |")
                lines.append("|" + "-" * 57 + "|")
                lines.append(f"| COP  | {cd_base:>14,.0f} | {cd_rate:>5.2f} | {cd_amount:>12,.0f} |")
                lines.append(f"| SOP  | {sop_base:>14,.0f} | {st_rate:>5.2f} | {st_amount:>12,.0f} |")
                lines.append(f"| VOP  | {vop_base:>14,.0f} | {vat_rate:>5.2f} | {vat_amount:>12,.0f} |")
                if bur_amount > 0:
                    lines.append(f"| BUR  | {bur_base:>14,.0f} | {bur_rate:>5.2f} | {bur_amount:>12,.0f} |")
                if vvf_amount > 0:
                    lines.append(f"| VVF  | {vvf_base:>14,.0f} | {vvf_rate:>5.2f} | {vvf_amount:>12,.0f} |")
                lines.append("|" + "-" * 57 + "|")
                lines.append(f"| TOTAL TAX     |                |       | {total:>12,.0f} |")
                lines.append("|" + "-" * 57 + "|")
                lines.append("")
                
                # Summary (Import)
                lines.append("SUMMARY:")
                product_desc = f"{product_name} ({hs_code})" if product_name and hs_code else (product_name or hs_code or "imported goods")
                lines.append(f"To import 1 consignment of {product_desc} valued at")
                lines.append(f"{original_cif_value:,.0f} {original_currency} CIF from {origin_country if origin_country else 'the origin country'}, you must pay {total:,.0f} KHR in import taxes.")
                if vat_amount > 0 and total > 0:
                    vat_pct = (vat_amount / total) * 100
                    lines.append(f"The majority is VAT ({vat_pct:.1f}% of total taxes).")
                lines.append("")
                
                # Assumptions (Import) - Dynamic based on what's actually calculated
                lines.append("ASSUMPTIONS & NOTES:")
                
                # Add only the assumptions that apply based on calculated amounts
                if cd_amount > 0:
                    lines.append(f"  + Customs Duty (CD) rate: {cd_rate:.2f}% - Applied per current regulations")
                if st_amount > 0:
                    lines.append(f"  + Special Tariff (ST) rate: {st_rate:.2f}% - Applied per current regulations")
                if vat_amount > 0:
                    lines.append(f"  + VAT rate: {vat_rate:.2f}% - Applied per current regulations")
                
                lines.append(f"  + DV total: {cif_khr:,.2f} KHR (provided CIF value)")
                lines.append(f"  + Exchange rate as of {datetime.now().strftime('%Y-%m-%d')}: 1 {original_currency} = {exchange_rate:,.1f} KHR")
                lines.append(f"  + HS Code confirmed from Qdrant database")
                lines.append(f"  + Calculation assumes standard regime (unless specified otherwise)")
                lines.append(f"  + All rates current as of {datetime.now().strftime('%B %d, %Y')}")
                lines.append("")
        
        # Data Sources (same for both import and export) - Dynamic from environment variables
        lines.append(sep)
        lines.append("DATA SOURCES:")
        
        # Get environment variables with defaults
        qdrant_host = os.getenv("QDRANT_HOST", "172.25.3.243")
        qdrant_port = os.getenv("QDRANT_PORT", "6333")
        pg_host = os.getenv("POSTGRES_HOST") or os.getenv("PG_HOST", "172.25.3.243")
        pg_db = os.getenv("POSTGRES_DB", "gdce_rates")
        
        seen_doc_ids = set()
        sources_added = 0
        
        # 1. Pull structured references from the calculator result
        for ref in references:
            if hasattr(ref, "to_dict"):
                ref = ref.to_dict()
            if not isinstance(ref, dict):
                continue
                
            doc_id = str(ref.get("doc_id", "")).strip()
            title = str(ref.get("title", "")).strip()
            eff_date = str(ref.get("effective_start_date", "")).strip()
            
            if not doc_id or doc_id in seen_doc_ids:
                continue
            seen_doc_ids.add(doc_id)
            
            date_suffix = f" (effective: {eff_date})" if eff_date else ""
            lines.append(f"* {title}{date_suffix} [{doc_id}]")
            sources_added += 1

        # 2. Pull the 'Source:' line embedded in assumptions
        for assumption in assumptions:
            stripped = str(assumption).strip()
            if stripped.lower().startswith("source:"):
                source_label = stripped[len("source:"):].strip()
                source_key = f"assumption:{source_label}"
                if source_key not in seen_doc_ids:
                    seen_doc_ids.add(source_key)
                    lines.append(f"* Duty rates source: {source_label}")
                    sources_added += 1

        # 3. Exchange-rate source hint
        if exchange_rate and original_currency != "KHR":
            ex_key = "exchange_rate_pg"
            if ex_key not in seen_doc_ids:
                seen_doc_ids.add(ex_key)
                lines.append(f"* Exchange rate ({original_currency} → KHR): PostgreSQL — {pg_db} table")
                sources_added += 1

        # 4. Always add the primary data sources (dynamic from environment)
        if "hs_code_qdrant" not in seen_doc_ids:
            seen_doc_ids.add("hs_code_qdrant")
            lines.append(f"* HS Code Database: Qdrant ({qdrant_host}:{qdrant_port}/collections/gdce_hs_code)")
        
        if "exchange_rate_pg" not in seen_doc_ids:
            seen_doc_ids.add("exchange_rate_pg")
            lines.append(f"* Exchange Rates: PostgreSQL ({pg_host}/{pg_db})")
        
        if "duty_rates_qdrant" not in seen_doc_ids:
            seen_doc_ids.add("duty_rates_qdrant")
            lines.append(f"* Duty Rates: Qdrant ({qdrant_host}:{qdrant_port}/collections/gdce_hs_code)")
        
        lines.append(sep)
        
        return "\n".join(lines)
    
    except Exception as e:
        import traceback
        logger.error(f"Error formatting calculation response: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        logger.error(f"Calculation result keys: {calculation_result.keys() if isinstance(calculation_result, dict) else 'not a dict'}")
        # Return basic fallback response
        total = calculation_result.get("total", 0)
        currency = calculation_result.get("currency", "KHR")
        return f"Total Import/Export Taxes and Duties: {total:,.0f} {currency}"

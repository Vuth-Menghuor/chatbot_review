# Calculator Service Response Quality Report

## Test Case

Endpoint:

```text
POST http://127.0.0.1:8002/query
```

Request body:

```json
{
  "question": "calculate import tax for car cif 400,000,000khr from china"
}
```

```json
{
  "answer": "-----------------------------------------------------------------\nIMPORT TAX CALCULATION\n-----------------------------------------------------------------\n\nPRODUCT INFORMATION:\n* HS Code: 8702.40.49 (Motor vehicles for the transport of ten or more persons, including the driver. > With only electric motor for propulsion : > Completely Knocked Down : > Other : > Other)\n* Origin Country: CN\n* Incoterm: CIF (Cost, Insurance, Freight)\n\nINPUT PARAMETERS:\n* CIF Value: 400,000,000 KHR\n* Exchange Rate: 1 KHR = 1.00 KHR\n* Customs Regime: Normal (standard rates)\n* Calculation Date: 2026-08-05\n\n-----------------------------------------------------------------\nSTEP 1: CURRENCY CONFIRMATION (KHR)\n-----------------------------------------------------------------\nCIF Value = 400,000,000 KHR (already in local currency)\n\n-----------------------------------------------------------------\nSTEP 2: IMPORT TAXES (COP)\n-----------------------------------------------------------------\nImport Taxes (COP) = Customs Value x Import Tax Rate\n= 400,000,000 x 15.00%\n= 60,000,000 KHR\n\n-----------------------------------------------------------------\nSTEP 3: SPECIAL TARIFF (SOP)\n-----------------------------------------------------------------\nSpecial Tariff (SOP) = (Customs Value + Import Tax) x Special Tariff Rate\n= (400,000,000 + 60,000,000) x 10.00%\n= 46,000,000 KHR\n\n-----------------------------------------------------------------\nSTEP 4: VOP\n-----------------------------------------------------------------\nVOP = (Customs Value + Import Tax + Special Tariff) x 10% (For general taxable goods)\n= (400,000,000 + 60,000,000 + 46,000,000) x 10.00%\n= 50,600,000 KHR\n\n-----------------------------------------------------------------\nSTEP 5: TOTAL DUTIES AND TAXES\n-----------------------------------------------------------------\nTotal Duties and Taxes = Import Taxes (COP) + Special Tariff (SOP) + VOP (For general taxable goods)\n= 60,000,000 + 46,000,000 + 50,600,000\n= 156,660,000 KHR\n\n-----------------------------------------------------------------\nSTEP 6: VEHICLE VALUATION FEE (VVF)\n-----------------------------------------------------------------\nFee = 60,000 KHR per vehicle unit\n= 60,000 KHR\n\n|-------------------------------------------------------------------------------------|\nFINAL TAX BREAKDOWN\n|-------------------------------------------------------------------------------------|\n| Tax Component                          | Tax base (KHR) | Rate       | Amount (KHR) |\n|-------------------------------------------------------------------------------------|\n| Import Taxes (COP)                     | 400,000,000    | 15.00      | 60,000,000   |\n| Special Tariff (SOP)                   | 460,000,000    | 10.00      | 46,000,000   |\n| VOP (VAT of Payment)                   | 506,000,000    | 10.00      | 50,600,000   |\n| Vehicle Valuation Fee (VVF)            | 1              | 60000.00   | 60,000       |\n|-------------------------------------------------------------------------------------|\n| TOTAL TAX                              |                |            | 156,660,000  |\n|-------------------------------------------------------------------------------------|\n\nSUMMARY:\nTo import 1 consignment of Motor vehicles for the transport of ten or more persons, including the driver. > With only electric motor for propulsion : > Completely Knocked Down : > Other : > Other (8702.40.49) valued at\n400,000,000 KHR CIF from CN, you must pay 156,660,000 KHR in import taxes.\nThe majority is VOP (32.3% of total taxes).\n\n-----------------------------------------------------------------\nASSUMPTIONS & NOTES\n-----------------------------------------------------------------\n  + ⚠️  HS code 8702.40.49 was auto-resolved from the product description 'Motor vehicles for the transport of ten or more persons, including the driver. > With only electric motor for propulsion : > Completely Knocked Down : > Other : > Other' via semantic search. Please verify the HS code with customs or provide the exact HS code for an accurate calculation.\n  + HS Code: 8702.40.49\n  + Product: Motor vehicles for the transport of ten or more persons, including the driver. > With only electric motor for propulsion : > Completely Knocked Down : > Other : > Other\n  + Origin country: CN\n  + \n  + === APPLICABLE RATES ===\n  + Import Tax (COP) rate: 15.00%\n  + Special Tariff (SOP) rate: 10.00%\n  + VAT rate: 10.00%\n  + Exchange rate: 1 KHR = 1.00 KHR\n  + Source: Calculator PostgreSQL (gdce_calculator_local)\n\n-----------------------------------------------------------------\nREFERENCES & CITATIONS\n-----------------------------------------------------------------\n  * [1] HS Code 8702.40.49 - Duty Rates (CD, ST, VAT) — Official Tariff Website (ID: gdce_calculator_local.duty_rates:8702.40.49) | https://gdce.gov.kh/tariff-search | Effective: 2026-08-05\n  * [2] Exchange Rate USD to KHR — National Bank of Cambodia (ID: gdce_calculator_local.exchange_rates:USD) | https://nbc.gov.kh/ | Effective: 2026-08-05\n\n-----------------------------------------------------------------\nDATA SOURCES\n-----------------------------------------------------------------\n* HS Codes & Descriptions: PostgreSQL (gdce_calculator_local.hs_codes)\n* Duty Rates (CD, ST, VAT, ET): PostgreSQL (gdce_calculator_local.duty_rates)\n* ATP Rates (Petroleum): PostgreSQL (gdce_calculator_local.duty_rates.atp_rate)\n* Exchange Rates: PostgreSQL (gdce_calculator_local.exchange_rates)\n* Deduction Values (DV): PostgreSQL (gdce_calculator_local.declared_values)\n* Dynamic Rules (Formulas, Rounding, Policies): PostgreSQL (gdce_calculator_local)\n* Calculation History: PostgreSQL (gdce_calculator_local.calculation_history)\n* Official Tariff Lookup: https://gdce.gov.kh/tariff-search\n* Exchange Rate Source: https://nbc.gov.kh/\n",
  "success": true,
  "needs_clarification": false,
  "error": null,
  "confidence": 0.98,
  "source": "llm",
  "result": {
    "calculation_id": "calc_2026-08-05_20260805_060626_000050",
    "currency": "KHR",
    "total": 156660000,
    "breakdown": {
      "cif_value": 400000000,
      "cop_amount": 60000000,
      "sop_amount": 46000000,
      "vop_amount": 50600000,
      "vvf_amount": 60000,
      "fees": 60000
    },
    "line_items": [
      {
        "name": "Import Taxes (COP)",
        "tax_type": "CD",
        "amount": 60000000,
        "currency": "KHR",
        "base": 400000000,
        "rate": 15
      },
      {
        "name": "Special Tariff (SOP)",
        "tax_type": "ST",
        "amount": 46000000,
        "currency": "KHR",
        "base": 460000000,
        "rate": 10
      },
      {
        "name": "VOP (VAT of Payment)",
        "tax_type": "VAT",
        "amount": 50600000,
        "currency": "KHR",
        "base": 506000000,
        "rate": 10
      },
      {
        "name": "Vehicle Valuation Fee (VVF)",
        "tax_type": "VVF",
        "amount": 60000,
        "currency": "KHR",
        "base": 1,
        "rate": 60000
      }
    ],
    "assumptions": [
      "⚠️  HS code 8702.40.49 was auto-resolved from the product description 'Motor vehicles for the transport of ten or more persons, including the driver. > With only electric motor for propulsion : > Completely Knocked Down : > Other : > Other' via semantic search. Please verify the HS code with customs or provide the exact HS code for an accurate calculation.",
      "HS Code: 8702.40.49",
      "Product: Motor vehicles for the transport of ten or more persons, including the driver. > With only electric motor for propulsion : > Completely Knocked Down : > Other : > Other",
      "Origin country: CN",
      "",
      "=== APPLICABLE RATES ===",
      "Import Tax (COP) rate: 15.00%",
      "Special Tariff (SOP) rate: 10.00%",
      "VAT rate: 10.00%",
      "Exchange rate: 1 KHR = 1.00 KHR",
      "Source: Calculator PostgreSQL (gdce_calculator_local)"
    ],
    "references": [
      {
        "doc_id": "gdce_calculator_local.duty_rates:8702.40.49",
        "title": "HS Code 8702.40.49 - Duty Rates (CD, ST, VAT)",
        "effective_start_date": "2026-08-05",
        "effective_end_date": null,
        "source_url": "https://gdce.gov.kh/tariff-search",
        "section_title": "Official Tariff Website"
      },
      {
        "doc_id": "gdce_calculator_local.exchange_rates:USD",
        "title": "Exchange Rate USD to KHR",
        "effective_start_date": "2026-08-05",
        "effective_end_date": null,
        "source_url": "https://nbc.gov.kh/",
        "section_title": "National Bank of Cambodia"
      }
    ],
    "exchange_rate_usd_to_khr": 1,
    "cif_value_usd": null,
    "currency_note": null,
    "hs_code_info": {
      "hs_code": "8702.40.49",
      "description": "Motor vehicles for the transport of ten or more persons, including the driver. > With only electric motor for propulsion : > Completely Knocked Down : > Other : > Other",
      "unit": "u",
      "level": "subchapter"
    },
    "preferential_rate_missing": null,
    "requested_agreement": null,
    "human_readable": "-----------------------------------------------------------------\nIMPORT TAX CALCULATION\n-----------------------------------------------------------------\n\nPRODUCT INFORMATION:\n* HS Code: 8702.40.49 (Motor vehicles for the transport of ten or more persons, including the driver. > With only electric motor for propulsion : > Completely Knocked Down : > Other : > Other)\n* Origin Country: CN\n* Incoterm: CIF (Cost, Insurance, Freight)\n\nINPUT PARAMETERS:\n* CIF Value: 400,000,000 KHR\n* Exchange Rate: 1 KHR = 1.00 KHR\n* Customs Regime: Normal (standard rates)\n* Calculation Date: 2026-08-05\n\n-----------------------------------------------------------------\nSTEP 1: CURRENCY CONFIRMATION (KHR)\n-----------------------------------------------------------------\nCIF Value = 400,000,000 KHR (already in local currency)\n\n-----------------------------------------------------------------\nSTEP 2: IMPORT TAXES (COP)\n-----------------------------------------------------------------\nImport Taxes (COP) = Customs Value x Import Tax Rate\n= 400,000,000 x 15.00%\n= 60,000,000 KHR\n\n-----------------------------------------------------------------\nSTEP 3: SPECIAL TARIFF (SOP)\n-----------------------------------------------------------------\nSpecial Tariff (SOP) = (Customs Value + Import Tax) x Special Tariff Rate\n= (400,000,000 + 60,000,000) x 10.00%\n= 46,000,000 KHR\n\n-----------------------------------------------------------------\nSTEP 4: VOP\n-----------------------------------------------------------------\nVOP = (Customs Value + Import Tax + Special Tariff) x 10% (For general taxable goods)\n= (400,000,000 + 60,000,000 + 46,000,000) x 10.00%\n= 50,600,000 KHR\n\n-----------------------------------------------------------------\nSTEP 5: TOTAL DUTIES AND TAXES\n-----------------------------------------------------------------\nTotal Duties and Taxes = Import Taxes (COP) + Special Tariff (SOP) + VOP (For general taxable goods)\n= 60,000,000 + 46,000,000 + 50,600,000\n= 156,660,000 KHR\n\n-----------------------------------------------------------------\nSTEP 6: VEHICLE VALUATION FEE (VVF)\n-----------------------------------------------------------------\nFee = 60,000 KHR per vehicle unit\n= 60,000 KHR\n\n|-------------------------------------------------------------------------------------|\nFINAL TAX BREAKDOWN\n|-------------------------------------------------------------------------------------|\n| Tax Component                          | Tax base (KHR) | Rate       | Amount (KHR) |\n|-------------------------------------------------------------------------------------|\n| Import Taxes (COP)                     | 400,000,000    | 15.00      | 60,000,000   |\n| Special Tariff (SOP)                   | 460,000,000    | 10.00      | 46,000,000   |\n| VOP (VAT of Payment)                   | 506,000,000    | 10.00      | 50,600,000   |\n| Vehicle Valuation Fee (VVF)            | 1              | 60000.00   | 60,000       |\n|-------------------------------------------------------------------------------------|\n| TOTAL TAX                              |                |            | 156,660,000  |\n|-------------------------------------------------------------------------------------|\n\nSUMMARY:\nTo import 1 consignment of Motor vehicles for the transport of ten or more persons, including the driver. > With only electric motor for propulsion : > Completely Knocked Down : > Other : > Other (8702.40.49) valued at\n400,000,000 KHR CIF from CN, you must pay 156,660,000 KHR in import taxes.\nThe majority is VOP (32.3% of total taxes).\n\n-----------------------------------------------------------------\nASSUMPTIONS & NOTES\n-----------------------------------------------------------------\n  + ⚠️  HS code 8702.40.49 was auto-resolved from the product description 'Motor vehicles for the transport of ten or more persons, including the driver. > With only electric motor for propulsion : > Completely Knocked Down : > Other : > Other' via semantic search. Please verify the HS code with customs or provide the exact HS code for an accurate calculation.\n  + HS Code: 8702.40.49\n  + Product: Motor vehicles for the transport of ten or more persons, including the driver. > With only electric motor for propulsion : > Completely Knocked Down : > Other : > Other\n  + Origin country: CN\n  + \n  + === APPLICABLE RATES ===\n  + Import Tax (COP) rate: 15.00%\n  + Special Tariff (SOP) rate: 10.00%\n  + VAT rate: 10.00%\n  + Exchange rate: 1 KHR = 1.00 KHR\n  + Source: Calculator PostgreSQL (gdce_calculator_local)\n\n-----------------------------------------------------------------\nREFERENCES & CITATIONS\n-----------------------------------------------------------------\n  * [1] HS Code 8702.40.49 - Duty Rates (CD, ST, VAT) — Official Tariff Website (ID: gdce_calculator_local.duty_rates:8702.40.49) | https://gdce.gov.kh/tariff-search | Effective: 2026-08-05\n  * [2] Exchange Rate USD to KHR — National Bank of Cambodia (ID: gdce_calculator_local.exchange_rates:USD) | https://nbc.gov.kh/ | Effective: 2026-08-05\n\n-----------------------------------------------------------------\nDATA SOURCES\n-----------------------------------------------------------------\n* HS Codes & Descriptions: PostgreSQL (gdce_calculator_local.hs_codes)\n* Duty Rates (CD, ST, VAT, ET): PostgreSQL (gdce_calculator_local.duty_rates)\n* ATP Rates (Petroleum): PostgreSQL (gdce_calculator_local.duty_rates.atp_rate)\n* Exchange Rates: PostgreSQL (gdce_calculator_local.exchange_rates)\n* Deduction Values (DV): PostgreSQL (gdce_calculator_local.declared_values)\n* Dynamic Rules (Formulas, Rounding, Policies): PostgreSQL (gdce_calculator_local)\n* Calculation History: PostgreSQL (gdce_calculator_local.calculation_history)\n* Official Tariff Lookup: https://gdce.gov.kh/tariff-search\n* Exchange Rate Source: https://nbc.gov.kh/\n"
  },
  "extracted_request": {
    "calculation_date": "2026-08-05",
    "regime": "import",
    "goods": {
      "description": "Motor vehicles for the transport of ten or more persons, including the driver. > With only electric motor for propulsion : > Completely Knocked Down : > Other : > Other",
      "hs_code": "8702.40.49",
      "origin_country": "CN",
      "quantity": null,
      "unit": null,
      "net_mass_kg": null,
      "net_mass_tons": null,
      "volume_liter": null,
      "container_type": null
    },
    "valuation": {
      "customs_value": 400000000,
      "currency": "KHR",
      "exchange_rate_to_khr": null,
      "declared_value": null,
      "declared_value_basis": "total",
      "dq_factor": null
    },
    "flags": {
      "fta_applicable": false,
      "fta_certificate_type": null,
      "duty_quota_applicable": false,
      "dq_applicable": false,
      "dq_factor": null,
      "petroleum_case": false,
      "rubber_case": false,
      "qip_exemption": false,
      "sez_applicable": false,
      "diplomatic_exemption": false,
      "ngo_humanitarian": false,
      "educational_exemption": false,
      "medical_exemption": false,
      "passenger_allowance": false,
      "preferential_cd_rate": null
    },
    "requested_breakdown": null
  }
}
```

import re
from typing import Any

from app.schemas.normalized_chat import DetailsBlock, DetailsItem
from app.services.normalizers.calculator.extraction import extract_final_tax_breakdown_table, is_ascii_table_rule_line
from app.services.normalizers.calculator.formatting import (
    is_ascii_dash_rule_line,
    title_case_preserving_step,
)


# Parse section-oriented legacy calculator text so older orchestrator responses still produce rich blocks.
def parse_calculator_text_sections(content: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current_title: str | None = None

    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or is_ascii_dash_rule_line(stripped) or is_ascii_table_rule_line(stripped):
            continue
        if stripped.startswith("|"):
            continue

        title = normalized_calculator_section_title(stripped)
        if title:
            current_title = title
            sections.setdefault(current_title, [])
            continue

        if current_title:
            sections[current_title].append(line)

    return sections


# Normalize the known legacy section headings while preserving Step headings.
def normalized_calculator_section_title(line: str) -> str | None:
    title = line.strip().rstrip(":")
    upper = title.upper()
    known = {
        "IMPORT TAX CALCULATION",
        "EXPORT TAX CALCULATION",
        "PRODUCT INFORMATION",
        "INPUT PARAMETERS",
        "FINAL TAX BREAKDOWN",
        "SUMMARY",
        "ASSUMPTIONS & NOTES",
        "REFERENCES & CITATIONS",
        "DATA SOURCES",
    }
    if upper in known:
        return upper
    if upper.startswith("STEP "):
        return title
    return None


# Keep the legacy report title matching the existing import/export behavior.
def calculator_report_title(sections: dict[str, list[str]]) -> str:
    if "EXPORT TAX CALCULATION" in sections:
        return "Export Tax Calculation"
    return "Import Tax Calculation"


# Extract summary fields from legacy text without changing the visible answer content.
def calculator_summary_data(sections: dict[str, list[str]], content: str) -> dict[str, str | int | float | bool | None]:
    data: dict[str, str | int | float | bool | None] = {}
    table_section = extract_final_tax_breakdown_table(content)
    if table_section:
        total_row = next(
            (row for row in table_section.table.rows if str(row.get("tax_component", "")).upper() == "TOTAL TAX"),
            None,
        )
        if total_row:
            data["total_tax"] = total_row.get("amount_khr")
            data["currency"] = "KHR"

    product = section_key_value_map(sections.get("PRODUCT INFORMATION", []))
    inputs = section_key_value_map(sections.get("INPUT PARAMETERS", []))
    hs_code_value = product.get("HS Code")
    if hs_code_value:
        hs_code, description = split_hs_code_description(hs_code_value)
        data["hs_code"] = hs_code
        if description:
            data["product"] = description
    if product.get("Origin Country"):
        data["origin_country"] = product["Origin Country"]
    if inputs.get("CIF Value"):
        data["cif_value"] = inputs["CIF Value"]
    if inputs.get("Customs Regime"):
        data["calculation_method"] = inputs["Customs Regime"]

    summary_text = " ".join(line.strip() for line in sections.get("SUMMARY", []) if line.strip())
    if summary_text:
        data["summary"] = first_sentence(summary_text)
        majority = regex_group(r"The majority is\s+([^.]+)", summary_text)
        if majority:
            data["majority_component"] = majority
    return data


# Turn bullet-style key/value text sections into lookup maps for legacy extraction.
def section_key_value_map(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        cleaned = line.strip().lstrip("*+").strip()
        if ":" not in cleaned:
            continue
        key, value = cleaned.split(":", 1)
        if key.strip() and value.strip():
            values[key.strip()] = value.strip()
    return values


# Split legacy HS-code lines that combine the code and product description.
def split_hs_code_description(value: str) -> tuple[str, str | None]:
    match = re.match(r"^([0-9.]+)\s*\(([^)]+)\)", value.strip())
    if not match:
        return value, None
    return match.group(1), match.group(2)


# Preserve the current one-sentence summary extraction from legacy paragraphs.
def first_sentence(value: str) -> str:
    match = re.match(r"(.+?\.)\s+", value)
    return match.group(1) if match else value


# Keep regex extraction readable in summary/assumption parsing.
def regex_group(pattern: str, value: str) -> str | None:
    match = re.search(pattern, value, flags=re.IGNORECASE)
    return match.group(1).strip() if match else None


# Convert legacy Step sections into details rows for the frontend details block.
def details_items_from_sections(sections: dict[str, list[str]]) -> list[DetailsItem]:
    items: list[DetailsItem] = []
    for title, lines in sections.items():
        if not title.upper().startswith("STEP "):
            continue
        content = "\n".join(line.rstrip() for line in lines if line.strip())
        if content:
            items.append(DetailsItem(title=title_case_preserving_step(title), content=content))
    return items


# Build the legacy Assumptions & Notes block and its structured frontend data.
def assumptions_block_from_sections(
    sections: dict[str, list[str]],
    content: str,
    payload: dict[str, Any],
) -> DetailsBlock | None:
    lines = [line.strip().lstrip("*+").strip() for line in sections.get("ASSUMPTIONS & NOTES", []) if line.strip()]
    if not lines:
        return None

    notes = "\n".join(line for line in lines if not is_rates_heading(line))
    items = [DetailsItem(title="Notes", content=notes)] if notes else []
    return DetailsBlock(title="Assumptions & Notes", items=items)


# Read one exact key from legacy bullet lines.
def key_value_from_lines(lines: list[str], key_name: str) -> str | None:
    wanted = key_name.strip().lower()
    for line in lines:
        cleaned = line.strip().lstrip("*+").strip()
        if ":" not in cleaned:
            continue
        key, value = cleaned.split(":", 1)
        if key.strip().lower() == wanted and value.strip():
            return value.strip()
    return None


# Identify decorative rates headings so they do not become user-facing notes.
def is_rates_heading(line: str) -> bool:
    return bool(re.fullmatch(r"=+\s*applicable rates\s*=+", line.strip(), flags=re.IGNORECASE))


# Preserve the current definition of a legacy rate line.
def is_rate_line(line: str) -> bool:
    return bool(re.search(r"\brate\s*:", line, flags=re.IGNORECASE))


# Filter source lines out of assumptions notes because citations handle them separately.
def is_source_line(line: str) -> bool:
    return line.lower().startswith("source:")


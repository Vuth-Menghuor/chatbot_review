import re
from typing import Any

from app.schemas.normalized_chat import (
    ChatContentBlock,
    ChatTableColumn,
    KeyValueItem,
    MarkdownBlock,
    TableBlock,
)


# Split legacy calculator markdown around the tax table so the table can render as a real UI table.
def normalize_markdown_content_blocks(content: str) -> list[ChatContentBlock]:
    from app.services.normalizers.calculator.extraction import extract_final_tax_breakdown_table

    table_section = extract_final_tax_breakdown_table(content)
    if not table_section:
        return [MarkdownBlock(text=format_calculator_markdown(content))]

    blocks: list[ChatContentBlock] = []
    before = format_calculator_markdown(content[:table_section.start]).strip()
    after = format_calculator_markdown(content[table_section.end:]).strip()

    if before:
        blocks.append(MarkdownBlock(text=before))
    blocks.append(table_section.table)
    if after:
        blocks.append(MarkdownBlock(text=after))

    return blocks or [MarkdownBlock(text=content)]


# Format legacy calculator all-caps sections into readable markdown headings without changing non-calculator text.
def format_calculator_markdown(content: str) -> str:
    if not is_calculator_markdown_text(content):
        return content

    lines = content.splitlines()
    formatted: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if is_ascii_dash_rule_line(stripped):
            title_index = i + 1
            while title_index < len(lines) and not lines[title_index].strip():
                title_index += 1

            next_rule_index = title_index + 1
            if (
                title_index < len(lines)
                and next_rule_index < len(lines)
                and is_calculator_section_title(lines[title_index].strip())
                and is_ascii_dash_rule_line(lines[next_rule_index].strip())
            ):
                append_blank_once(formatted)
                formatted.append(markdown_heading_for_calculator_title(lines[title_index].strip()))
                append_blank_once(formatted)
                i = next_rule_index + 1
                while i < len(lines) and not lines[i].strip():
                    i += 1
                continue

            i += 1
            continue

        if is_calculator_label_heading(stripped):
            append_blank_once(formatted)
            formatted.append(f"### {title_case_preserving_step(stripped.rstrip(':'))}")
            append_blank_once(formatted)
            i += 1
            continue

        formatted.append(line)
        i += 1

    return re.sub(r"\n{3,}", "\n\n", "\n".join(formatted).strip())


# Detect legacy calculator text so plain answers keep their original content.
def is_calculator_markdown_text(content: str) -> bool:
    markers = (
        # English
        "IMPORT TAX CALCULATION",
        "EXPORT TAX CALCULATION",
        "PRODUCT INFORMATION:",
        "INPUT PARAMETERS:",
        "STEP ",
        "FINAL TAX BREAKDOWN",
        "SUMMARY:",
        "ASSUMPTIONS & NOTES",
        "REFERENCES & CITATIONS",
        "DATA SOURCES",

        # Khmer
        "ការគណនាពន្ធនាំចូល",
        "ការគណនាពន្ធនាំចេញ",
        "ព័ត៌មានផលិតផល",
        "ប៉ារ៉ាម៉ែត្របញ្ចូល",
        "ជំហានទី",
        "សេចក្តីសង្ខេបនៃការគណនាពន្ធចុងក្រោយ",
        "សេចក្តីសង្ខេប",
        "ការសន្មត និងកំណត់សម្គាល់",
        "ប្រភពទិន្នន័យ",
    )

    return any(marker in content for marker in markers)


# Detect decorative dashed separators around legacy calculator headings.
def is_ascii_dash_rule_line(line: str) -> bool:
    return len(line) >= 8 and set(line) == {"-"}


# Detect all-caps calculator section titles and Step headings.
def is_calculator_section_title(line: str) -> bool:
    if not line:
        return False
    if line.startswith("STEP "):
        return True
    return line == line.upper() and any(char.isalpha() for char in line)


# Detect label-style calculator headings such as PRODUCT INFORMATION:.
def is_calculator_label_heading(line: str) -> bool:
    return line.endswith(":") and line == line.upper() and any(char.isalpha() for char in line)


# Preserve the existing heading level choice for calculator report titles.
def markdown_heading_for_calculator_title(title: str) -> str:
    if title == "IMPORT TAX CALCULATION":
        return f"## {title_case_preserving_step(title)}"
    return f"### {title_case_preserving_step(title)}"


# Title-case headings while preserving Step prefixes and customs acronyms.
def title_case_preserving_step(value: str) -> str:
    if value.startswith("STEP "):
        step, _, detail = value.partition(":")
        return f"{step.title()}: {calculator_title_case(detail.strip())}" if detail else step.title()
    return calculator_title_case(value)


# Preserve customs acronyms while formatting legacy headings.
def calculator_title_case(value: str) -> str:
    acronyms = {"ATP", "CIF", "COP", "CPP", "DPP", "DV", "HS", "KHR", "SOP", "SPP", "USD", "VAT", "VOP", "VPP"}
    lowercase_words = {"and", "as", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with"}
    parts = re.split(r"(\W+)", value.strip())
    word_index = 0
    formatted: list[str] = []
    for part in parts:
        if not part or re.fullmatch(r"\W+", part):
            formatted.append(part)
            continue
        upper = part.upper()
        lower = part.lower()
        if upper in acronyms:
            formatted.append(upper)
        elif word_index > 0 and lower in lowercase_words:
            formatted.append(lower)
        else:
            formatted.append(lower[:1].upper() + lower[1:])
        word_index += 1
    return "".join(formatted)


# Avoid accumulating repeated blank lines while formatting markdown.
def append_blank_once(lines: list[str]) -> None:
    if lines and lines[-1] != "":
        lines.append("")


def split_key_value_line(value: str) -> tuple[str, str] | None:
    match = re.match(r"^\s*([^:៖]+?)\s*[:៖]\s*(.+?)\s*$", value)

    if not match:
        return None

    return match.group(1).strip(), match.group(2).strip()

# Convert bullet lines into key/value block items for legacy calculator sections.
def key_value_items_from_bullets(lines):
    items = []

    for line in lines:
        cleaned = line.strip().lstrip("*+").strip()

        parsed = split_key_value_line(cleaned)

        if not parsed:
            continue

        key, value = parsed

        items.append(
            KeyValueItem(
                key=key,
                value=value,
            )
        )

    return items

# Convert structured mappings into key/value block items without rendering nested data by accident.
def key_value_items_from_mapping(value: dict[str, Any]) -> list[KeyValueItem]:
    items: list[KeyValueItem] = []
    for key, item in value.items():
        if isinstance(item, dict | list):
            continue
        cell = scalar_to_cell(item)
        if cell is not None:
            items.append(KeyValueItem(key=str(key), value=cell))
    return items


# Local copy of scalar conversion used by calculator-specific blocks.
def scalar_to_cell(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


# Local text picker used only for calculator assumption extraction.
def first_text(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


# Calculator structured results need a small table builder without importing the main normalizer.
def normalize_table(value: Any) -> TableBlock | None:
    if not isinstance(value, dict):
        return None

    rows = first_list(value, "rows", "data", "records", "items")
    columns = value.get("columns")
    normalized_columns: list[ChatTableColumn] = []

    if isinstance(columns, list):
        for column in columns:
            if isinstance(column, dict):
                key = str(column.get("key") or column.get("field") or column.get("name") or "")
                label = str(column.get("label") or column.get("title") or key)
            else:
                key = str(column)
                label = key
            if key:
                normalized_columns.append(ChatTableColumn(key=key, label=label))

    if not normalized_columns and rows and isinstance(rows[0], dict):
        normalized_columns = [ChatTableColumn(key=str(key), label=str(key).replace("_", " ").title()) for key in rows[0]]

    normalized_rows = [row for row in rows if isinstance(row, dict)]
    if not normalized_columns and not normalized_rows:
        return None

    return TableBlock(title=value.get("title") or value.get("name"), columns=normalized_columns, rows=normalized_rows)


# Pick the first list-valued key from flexible structured payloads.
def first_list(payload: dict[str, Any], *keys: str) -> list[Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []

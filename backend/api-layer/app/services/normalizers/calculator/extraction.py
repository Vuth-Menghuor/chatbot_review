import re

from app.schemas.normalized_chat import ChatTableColumn, TableBlock


class ExtractedTable:
    def __init__(self, *, start: int, end: int, table: TableBlock) -> None:
        self.start = start
        self.end = end
        self.table = table


# Extract the legacy final tax breakdown table while preserving the text ranges around it.
def extract_final_tax_breakdown_table(content: str) -> ExtractedTable | None:
    marker_match = re.search(r"(?im)^FINAL TAX BREAKDOWN\s*$", content)
    if not marker_match:
        return None

    lines = content.splitlines(keepends=True)
    positions: list[tuple[int, str]] = []
    offset = 0
    for line in lines:
        positions.append((offset, line))
        offset += len(line)

    marker_index = next(
        (
            index
            for index, (line_start, line) in enumerate(positions)
            if line_start <= marker_match.start() < line_start + len(line)
        ),
        None,
    )
    if marker_index is None:
        return None

    start_index = marker_index
    while start_index > 0 and is_ascii_table_rule_line(positions[start_index - 1][1]):
        start_index -= 1

    end_index = marker_index + 1
    while end_index < len(positions):
        line = positions[end_index][1]
        if not is_tax_table_line(line):
            break
        end_index += 1

    table_lines = [line.strip() for _, line in positions[marker_index + 1 : end_index]]
    table = parse_pipe_table_lines("Final Tax Breakdown", table_lines)
    if not table:
        return None

    start = positions[start_index][0]
    end = positions[end_index][0] if end_index < len(positions) else len(content)
    return ExtractedTable(start=start, end=end, table=table)


# Detect lines that are part of the old pipe-table tax breakdown.
def is_tax_table_line(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and (stripped.startswith("|") or is_ascii_table_rule_line(stripped))


# Detect markdown table separator rows so they are skipped during parsing.
def is_ascii_table_rule_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and set(stripped) <= {"|", "-"}


# Parse a markdown pipe table into the existing TableBlock contract.
def parse_pipe_table_lines(title: str, lines: list[str]) -> TableBlock | None:
    rows = [split_pipe_row(line) for line in lines if line.startswith("|") and not is_ascii_table_rule_line(line)]
    if len(rows) < 2:
        return None

    headers = rows[0]
    data_rows = rows[1:]
    if not headers or not data_rows:
        return None

    keys = [table_header_key(header, index) for index, header in enumerate(headers)]
    normalized_rows: list[dict[str, str | int | float | bool | None]] = []
    for row in data_rows:
        normalized_row = {
            key: normalize_table_cell(key, row[index].strip() if index < len(row) else "")
            for index, key in enumerate(keys)
        }
        if any(value for value in normalized_row.values()):
            normalized_rows.append(normalized_row)

    if not normalized_rows:
        return None

    return TableBlock(
        title=title,
        columns=[ChatTableColumn(key=key, label=headers[index].strip()) for index, key in enumerate(keys)],
        rows=normalized_rows,
    )


# Split one markdown pipe-table row into cells.
def split_pipe_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


# Convert table headers into stable snake_case row keys.
def table_header_key(header: str, index: int) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_")
    return key or f"column_{index + 1}"


# Preserve old behavior where numeric rate cells become percentages.
def normalize_table_cell(key: str, value: str) -> str:
    if key == "rate" and value and "%" not in value and "$" not in value and "/" not in value:
        if re.fullmatch(r"-?\d+(?:,\d{3})*(?:\.\d+)?", value.strip()):
            return f"{value.strip()}%"
    return value

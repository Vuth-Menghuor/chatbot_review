from typing import Any

from app.schemas.normalized_chat import SummaryBlock
from app.services.normalizers.calculator.formatting import scalar_to_cell
from app.services.normalizers.calculator.legacy import calculator_report_title, calculator_summary_data


def summary_block_from_structured_result(result: dict[str, Any]) -> SummaryBlock | None:
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    data = {key: scalar_to_cell(value) for key, value in summary.items()}
    if not data:
        return None
    return SummaryBlock(
        title="Import Tax Calculation",
        data=data,
    )


def summary_block_from_legacy_sections(sections: dict[str, list[str]], content: str) -> SummaryBlock:
    return SummaryBlock(
        title=calculator_report_title(sections),
        data=calculator_summary_data(sections, content),
    )

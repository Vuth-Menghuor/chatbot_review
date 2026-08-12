from app.schemas.normalized_chat import ChatContentBlock, MarkdownBlock
from app.services.normalizers.calculator.formatting import is_calculator_markdown_text


def calculator_markdown_fallback_blocks(content: str) -> list[ChatContentBlock]:
    return [MarkdownBlock(text=content)]

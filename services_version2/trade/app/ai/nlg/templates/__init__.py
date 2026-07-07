"""NLG templates package."""

from app.ai.nlg.templates.breakdown_template import render_breakdown
from app.ai.nlg.templates.comparison_template import render_comparison
from app.ai.nlg.templates.growth_template import render_growth
from app.ai.nlg.templates.ranking_template import render_ranking
from app.ai.nlg.templates.summary_template import render_summary
from app.ai.nlg.templates.trade_balance_template import render_trade_balance
from app.ai.nlg.templates.trend_template import render_trend

__all__ = [
    "render_summary",
    "render_ranking",
    "render_trend",
    "render_comparison",
    "render_breakdown",
    "render_growth",
    "render_trade_balance",
]

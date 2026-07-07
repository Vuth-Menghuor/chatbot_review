"""
Metadata-driven SQL builder.

This module is the core of the DAL query engine. It constructs safe SQL
from pre-validated metadata fragments only. No user-supplied SQL is ever
accepted. Values are always parameterized.
"""

from __future__ import annotations
from datetime import date
import re

from alembic.environment import Any

from app.core.errors import DALError, ErrorCode
from app.core.logging import get_logger
from app.core.config import get_settings
from app.schemas.metadata import DatasetConcept, DimensionConcept, FilterKeyConcept, MeasureConcept, QueryCase, SQLValueConcept
from app.schemas.query import NormalizedQuery, NormalizedDatasetInfoQuery
from app.utils.period_parser import split_period
# from app.utils.period_parser import build_period_filter_sql, match_period_pattern

logger = get_logger(__name__)
settings = get_settings()

# SQL operator mapping for dimension filters
_SQL_OPS = {
    "eq": " = ",
    "ne": " != ",
    "gt": " > ",
    "ge": " >= ",
    "lt": " < ",
    "le": " <= ",
    "like": " LIKE ",
    "ilike": " ILIKE ",
}


class BuiltQuery:
    """Result of SQL compilation: text + parameter dict."""

    def __init__(self, sql: str = "", params: dict = {}, data: Any = None):
        self.sql = sql
        self.params = params
        self.data = data


def build_query(query: NormalizedQuery, concept: DatasetConcept) -> BuiltQuery:
    """
    Build a safe SQL query from a normalized request and dataset concept.

    Only emits SQL fragments defined in metadata. User-supplied values
    are always parameterized.
    """
    if not settings.is_production:
        logger.info(f"Building query for dataset {concept.dataset_code}")
        logger.info(f"Query: {query}")
        logger.info(f"Concept: {concept}")
    
    # Dimension Code Value
    DIMENSION_CODE_VALUE = {}
        
    # --- Helper functions ---
    # Test input value against patterns and return matching pattern key and expression    
    def pattern_matcher(value: str, patterns: dict[str, str]) -> str | None:
        for pattern_key, pattern_regex in patterns.items():
            if re.match(pattern_regex, value):
                return pattern_key
        return None
    
    def expression_parser(
        expr: QueryCase | str | dict[str, str], 
        pattern_test: dict[str, str] | None = None, 
        aggregation: str | None = None,
        value: str | None = None,
        default: str | None = None) -> str:
        # Break value by comma or hyphen to  VALUE, VALUE0, VALUE1... for replacement in SQL templates
        _local_params = {}
        _value = value if value is not None else default
        if _value is not None:
            _local_params["VALUE"] = _value
            for i, v in enumerate(re.split(r"[,|-]", _value)):
                _local_params[f"VALUE{i}"] = v.strip()
        
        _expression = None
        
        if isinstance(expr, str):
            _expression = expr
        elif isinstance(expr, dict):
            if pattern_test:
                pattern_key = pattern_matcher(_value if _value is not None else "", pattern_test)
                if pattern_key is None:
                    raise DALError(
                        ErrorCode.INVALID_VALUE,
                        f"Input value '{_value}' does not match any expected patterns",
                    )
                matched_expr = expr.get(pattern_key)
                if matched_expr is None:
                    raise DALError(
                        ErrorCode.INVALID_VALUE,
                        f"No expression defined for matched pattern '{pattern_key}'",
                    )
                _expression = matched_expr
            else:
                raise DALError(
                    ErrorCode.INTERNAL_ERROR,
                    "Expression is a dict but no pattern test provided",
                )
        elif isinstance(expr, QueryCase):
            # Looking for the base parameter in the query.filters
            _base = expr.base.lower()
            filter_value = None
            filter_item = next((f for f in query.filters if f.field.lower() == _base), None)
            if filter_item:
                filter_value = filter_item.value
            if filter_value is None:
                filter_value = DIMENSION_CODE_VALUE.get(expr.base, None)
            
            if filter_value is None:
                raise DALError(
                    ErrorCode.INVALID_FILTER,
                    f"Expression requires filter on '{_base}' but none found in query",
                )
            else:
                filter_value = str(filter_value) # Convert to string for pattern matching and SQL template replacement
            # Use the filter value as key to select the expression variant
            matched_expr = expr.case.get(filter_value.lower())
            if matched_expr is None:
                raise DALError(
                    ErrorCode.INVALID_FILTER,
                    f"No expression defined for filter value '{filter_value}'",
                )
            _expression = matched_expr
        
        if _expression is None:
            raise DALError(
                ErrorCode.INTERNAL_ERROR,
                f"Invalid expression type: {type(expr)}",
            )
        _expression = _expression.format(**_local_params)
        return _expression if aggregation is None else f"{aggregation}({_expression})"

    
    # --- Resolve metadata lookups ---
    dim_map: dict[str, DimensionConcept] = {d.code: d for d in concept.dimensions}
    meas_map: dict[str, MeasureConcept] = {m.code: m for m in concept.measures}

    # --- SELECT clause ---
    select_parts: list[str] = []
    group_parts: list[str] = []
    params: dict = {}

    # Frequency dimension (always included as the first select)
    DIMENSION_CODE_VALUE[concept.frequency.code] = query.frequency
    freq_expr = expression_parser(
        expr=concept.frequency.query,
        default=concept.frequency.default
        )
    if freq_expr is None:
        raise DALError(
            ErrorCode.INVALID_FREQUENCY,
            f"No valid expression for frequency '{query.frequency}'",
        )
    select_parts.append(f"{freq_expr} AS \"{concept.frequency.code}\"")
    group_parts.append(f"\"{concept.frequency.code}\"")
    period_expr = expression_parser(expr=concept.period.query, default=concept.period.default)
    if period_expr is None:
        raise DALError(
            ErrorCode.INVALID_FREQUENCY,
            f"No period expression for frequency '{query.frequency}'",
        )
    select_parts.append(f"{period_expr} AS \"{concept.period.code}\"")
    group_parts.append(f"\"{concept.period.code}\"")
    DIMENSION_CODE_VALUE[concept.period.code] = period_expr

    # Requested dimensions
    for dim_code in query.dimensions:
        if dim_code == concept.frequency.code:
            continue  # Already handled above
        dim = dim_map.get(dim_code)
        if dim is None:
            raise DALError(
                ErrorCode.INVALID_DIMENSION,
                f"Unknown dimension '{dim_code}'",
            )
        select_expr = expression_parser(
            expr=dim.query, 
            pattern_test=dim.pattern_test,
            aggregation=dim.aggregate,
            default=dim.default
        )
        select_parts.append(f"{select_expr} AS \"{dim.code}\"")
        if dim.aggregate is None:
            group_parts.append(f"\"{dim.code}\"")

    # Requested measures (with aggregation)
    for meas_code in query.measures:
        meas = meas_map.get(meas_code)
        if meas is None:
            raise DALError(
                ErrorCode.INVALID_MEASURE,
                f"Unknown measure '{meas_code}'",
            )
        select_expr = expression_parser(
            expr=meas.query, 
            pattern_test=meas.pattern_test, 
            aggregation=meas.aggregate
            )
        select_parts.append(f"{select_expr} AS \"{meas.code}\"")
        if meas.aggregate is None:
            group_parts.append(f"\"{meas.code}\"")

        # If measure has a unit, include it
        if meas.unit:
            unit_expr = expression_parser(
                expr=meas.unit.query,
                pattern_test=meas.unit.pattern_test,
            )
            select_parts.append(f"{unit_expr} AS \"{meas.unit.code}\"")
            group_parts.append(f"\"{meas.unit.code}\"")

    # --- FROM clause ---
    source = concept.source
    from_clause = f"{source.table}"

    # --- JOIN clause ---
    join_clauses: list[str] = []
    for join in source.join:
        jtype = join.type.upper()
        join_clauses.append(f"{jtype} JOIN {join.table} ON {join.on}")

    # --- WHERE clause ---
    where_parts: list[str] = []
    param_idx = 0

    # Result filters
    for filt in (source.result_filter if source.result_filter else []):
        if filt.query:
            where_expression = expression_parser(
                expr=filt.query,
                pattern_test=filt.pattern_test,
            )
            where_parts.append(where_expression)

    # Period filters (start/end) # to check or remove
    _start_period = None
    _end_period = None
    if query.period:
        _start_period, _end_period = split_period(query.period)
    elif query.start_period and query.end_period:
        _start_period = query.start_period
        _end_period = query.end_period
    else:
        # Default Current Year
        current_year = date.today().year
        _start_period = current_year
        _end_period = current_year
    # Start Period filter
    start_period = concept.period.filters.get("start-period") if concept.period.filters else None
    if start_period and _start_period:
        filter_expr = expression_parser(
            expr=start_period.query,
            pattern_test=start_period.pattern_test,
            value=str(_start_period)
        )
        where_parts.append(filter_expr)
    
    # End Period filter
    end_period = concept.period.filters.get("end-period") if concept.period.filters else None
    if end_period and _end_period:
        filter_expr = expression_parser(
            expr=end_period.query,
            pattern_test=end_period.pattern_test,
            value=str(_end_period)
        )
        where_parts.append(filter_expr)

    # Note: frequency is not a physical DB column — it's encoded in the period
    # Expression selection (monthly, quarterly, etc.) so no WHERE filter is needed.
    
    # Dimension filters
    for filt in query.filters:
        dim = concept.filters.get(filt.field, concept.filters.get(filt.field.lower(), None))  # Check if it's a filter key concept or a regular dimension
        if dim is None:
            dim = dim_map.get(filt.field, dim_map.get(filt.field.lower(), None))  # Try to find it as a regular dimension
        if dim is None:
            raise DALError(
                ErrorCode.INVALID_FILTER,
                f"Cannot filter on unknown field '{filt.field}'",
            )

        # Normalize/map filter values (e.g. EX -> EXPORT, IM -> IMPORT for FLOW filter)
        filter_value = filt.value
        if filt.field.upper() == "FLOW":
            if filter_value.upper() == "EX":
                filter_value = "EXPORT"
            elif filter_value.upper() == "IM":
                filter_value = "IMPORT"

        param_name = f"p_filter_{param_idx}"
        param_idx += 1
        params[filt.field] = filter_value  # Add normalized value for potential use in expression parsing

        filter_expr = ""
        if isinstance(dim, FilterKeyConcept):
            filter_expr = expression_parser(
                expr=dim.query,
                pattern_test=dim.pattern_test,
                aggregation=None,
                default=dim.default,
                value=filter_value
            )
            
        else:
            filter_expr = expression_parser(
                expr=dim.query,
                pattern_test=dim.pattern_test,
                aggregation=None,
                default=dim.default,
                value=filter_value
            )
        
        # Test if filter_expr contains parameter placeholders, if so, we assume it's already a complete expression and do not add more conditions.
        # If filter_expr contains operators in _SQL_OPS, we also assume it's a complete expression.
        # Else, we need to add the operator base on filt.operator and parameter placeholder.
        if any(op in filter_expr for op in _SQL_OPS.values()):
            where_parts.append(filter_expr)
        else:
            if filt.operator == "in":
                # IN operator: split comma-separated values
                values = [v.strip() for v in filter_value.split(",")]
                in_params = []
                for i, v in enumerate(values):
                    pn = f"{param_name}_{i}"
                    params[pn] = v
                    in_params.append(f":{pn}")
                where_parts.append(f"{dim.query} IN ({', '.join(in_params)})")
            elif filt.operator in ("like", "ilike"):
                # LIKE operator: add wildcards if not present
                value = filter_value
                if not (value.startswith("%") or value.endswith("%")):
                    value = f"%{value}%"
                params[param_name] = value
                sql_op = _SQL_OPS.get(filt.operator)
                where_parts.append(f"{dim.query} {sql_op} :{param_name}")
            else:
                sql_op = _SQL_OPS.get(filt.operator)
                if sql_op is None:
                    raise DALError(
                        ErrorCode.INVALID_FILTER,
                        f"Unsupported operator '{filt.operator}'",
                    )
                params[param_name] = filter_value
                where_parts.append(f"{dim.query} {sql_op} :{param_name}")
            
    

    # --- ORDER BY clause ---
    order_parts: list[str] = []
    for sort in query.sort:
        # Must be a known dimension or measure
        if sort.field in dim_map:
            col_expr = dim_map[sort.field].query
        elif sort.field in meas_map:
            m = meas_map[sort.field]
            col_expr = f"{m.aggregate}({m.query})"
        elif sort.field == concept.period.code:
            col_expr = period_expr
        elif sort.field == concept.frequency.code:
            col_expr = f"'{query.frequency}'"
        else:
            raise DALError(
                ErrorCode.INVALID_SORT,
                f"Cannot sort on unknown field '{sort.field}'",
            )
        direction = sort.direction.upper()
        order_parts.append(f"{col_expr} {direction}")

    # --- Assemble SQL ---
    sql_parts = [f"SELECT {', '.join(select_parts)}"]
    sql_parts.append(f"FROM {from_clause}")
    for jc in join_clauses:
        sql_parts.append(jc)
    if where_parts:
        sql_parts.append(f"WHERE {' AND '.join(where_parts)}")
    if group_parts:
        sql_parts.append(f"GROUP BY {', '.join(group_parts)}")
    if order_parts:
        sql_parts.append(f"ORDER BY {', '.join(order_parts)}")

    # LIMIT / OFFSET
    sql_parts.append(f"LIMIT :p_limit OFFSET :p_offset")
    params["p_limit"] = query.limit
    params["p_offset"] = query.offset

    sql = " ".join(sql_parts)
    
    if not settings.is_production:
        logger.debug("Built SQL", extra={"sql": sql, "params": {k: str(v) for k, v in params.items()}})
    return BuiltQuery(sql=sql, params=params)


def build_query_dataset_codelist(concept: DatasetConcept) -> dict[str, BuiltQuery | dict[str, BuiltQuery] | None ] | None:
    """
    Build a SQL query for dataset info (metadata) endpoint.
    """
    # Build Frequency
    frequency = None
    if concept.frequency.metadata:
        if concept.frequency.metadata.data:
            if isinstance(concept.frequency.metadata.data, list):
                frequency = BuiltQuery(data=concept.frequency.metadata.data)
            if isinstance(concept.frequency.metadata.data, SQLValueConcept):
                frequency = BuiltQuery(sql=concept.frequency.metadata.data.sql)
        else:
            frequency = None

    # Build Period
    period = None
    if concept.period.metadata:
        if concept.period.metadata.data:
            if isinstance(concept.period.metadata.data, list):
                period = BuiltQuery(data=concept.period.metadata.data)
            if isinstance(concept.period.metadata.data, SQLValueConcept):
                period = BuiltQuery(sql=concept.period.metadata.data.sql)
        else:
            period = None
    
    # Build Dimension
    dimension = {}
    for dim in concept.dimensions:
        if dim.metadata and dim.metadata.data:
            if isinstance(dim.metadata.data, list):
                dimension[dim.code] = BuiltQuery(data=dim.metadata.data)
            if isinstance(dim.metadata.data, SQLValueConcept):
                dimension[dim.code] = BuiltQuery(sql=dim.metadata.data.sql)
        else:
            dimension[dim.code] = None
    
    # Build Measure
    measure = {}
    for meas in concept.measures:
        if meas.metadata and meas.metadata.data:
            if isinstance(meas.metadata.data, list):
                measure[meas.code] = BuiltQuery(data=meas.metadata.data)
            if isinstance(meas.metadata.data, SQLValueConcept):
                measure[meas.code] = BuiltQuery(sql=meas.metadata.data.sql)
        else:
            measure[meas.code] = None
        if meas.unit and meas.unit.metadata and meas.unit.metadata.data:
            unit_key = f"{meas.code}.{meas.unit.code}"
            if isinstance(meas.unit.metadata.data, list):
                measure[unit_key] = BuiltQuery(data=meas.unit.metadata.data)
            if isinstance(meas.unit.metadata.data, SQLValueConcept):
                measure[unit_key] = BuiltQuery(sql=meas.unit.metadata.data.sql)
    
    
    # Package results
    package = {
        "frequency": frequency,
        "period": period,
        "dimensions": dimension if dimension else None,
        "measures": measure if measure else None,
    }
    
    if not settings.is_production:
        logger.debug("Built SQL for dataset info", extra={"data": package})
    
    return package
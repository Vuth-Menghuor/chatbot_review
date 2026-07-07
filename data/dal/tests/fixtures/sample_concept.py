"""Sample dataset concept for test fixtures."""

TRADE_VOLUME_CONCEPT = {
    "dataset_code": "trade_volume",
    "version": "1.0",
    "frequency": {
        "code": "FREQ",
        "query": {
            "base": "FREQ",
            "case": {
                "a": "'A'",
                "m": "'M'",
                "q": "'Q'",
                "s": "'S'",
            },
        },
        "default": "A"
    },
    "period": {
        "code": "PERIOD",
        "query": {
            "base": "FREQ",
            "case": {
                "a": "td.ref_year::TEXT",
                "m": "td.ref_year || '-' || LPAD(td.ref_month::TEXT, 2, '0')",
                "q": "td.ref_year || '-Q' || CEIL(td.ref_month / 3.0)::TEXT",
                "s": "td.ref_year || '-S' || CEIL(td.ref_month / 6.0)::TEXT",
            },
        },
        "filters": {
            "start-period": {
                "pattern-test": {
                    "yyyy": r"\d{4}$",
                    "yyyy-mm": r"\d{4}-\d{2}$",
                    "yyyy-q1": r"\d{4}-[Qq]1$",
                    "yyyy-q2": r"\d{4}-[Qq]2$",
                    "yyyy-q3": r"\d{4}-[Qq]3$",
                    "yyyy-q4": r"\d{4}-[Qq]4$",
                    "yyyy-s1": r"\d{4}-[Ss]1$",
                    "yyyy-s2": r"\d{4}-[Ss]2$",
                },
                "query": {
                    "yyyy": "td.ref_year >= {VALUE}",
                    "yyyy-mm": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer >= replace(({VALUE})::text, '-', '')::integer",
                    "yyyy-q1": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer >= concat(({VALUE0})::text,'01')::integer",
                    "yyyy-q2": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer >= concat(({VALUE0})::text,'04')::integer",
                    "yyyy-q3": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer >= concat(({VALUE0})::text,'07')::integer",
                    "yyyy-q4": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer >= concat(({VALUE0})::text,'10')::integer",
                    "yyyy-s1": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer >= concat(({VALUE0})::text,'01')::integer",
                    "yyyy-s2": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer >= concat(({VALUE0})::text,'07')::integer",
                },
            },
            "end-period": {
                "pattern-test": {
                    "yyyy": r"\d{4}$",
                    "yyyy-mm": r"\d{4}-\d{2}$",
                    "yyyy-q1": r"\d{4}-[Qq]1$",
                    "yyyy-q2": r"\d{4}-[Qq]2$",
                    "yyyy-q3": r"\d{4}-[Qq]3$",
                    "yyyy-q4": r"\d{4}-[Qq]4$",
                    "yyyy-s1": r"\d{4}-[Ss]1$",
                    "yyyy-s2": r"\d{4}-[Ss]2$",
                },
                "query": {
                    "yyyy": "td.ref_year <= {VALUE}",
                    "yyyy-mm": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer <= replace(({VALUE})::text, '-', '')::integer",
                    "yyyy-q1": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer <= concat(({VALUE0})::text,'03')::integer",
                    "yyyy-q2": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer <= concat(({VALUE0})::text,'06')::integer",
                    "yyyy-q3": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer <= concat(({VALUE0})::text,'09')::integer",
                    "yyyy-q4": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer <= concat(({VALUE0})::text,'12')::integer",
                    "yyyy-s1": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer <= concat(({VALUE0})::text,'06')::integer",
                    "yyyy-s2": "concat(ref_year::text,LPAD(ref_month::text, 2, '0'))::integer <= concat(({VALUE0})::text,'12')::integer",
                },
            },
        }
    },
    "dimensions": [
        {"code": "PARTNER_COUNTRY", "query": "c.name_en"},
        {"code": "MODE_OF_TRANSPORT", "query": "mot.name_en"},
        {"code": "FLOW", "query": "td.flow"},
    ],
    "measures": [
        {"code": "VALUE_USD", "query": "td.value_usd", "aggregate": "SUM"},
        {"code": "NETWEIGHT", "query": "td.net_weight", "aggregate": "SUM"},
        {
            "code": "QUANTITY",
            "query": "COALESCE(td.quantity, td.net_weight)",
            "aggregate": "SUM",
            "unit": {"code": "UNIT", "query": "COALESCE(td.supp_unit, 'KGM')"},
        },
    ],
    "source": {
        "connection-key": "operational_db",
        "schema": "public",
        "table": "trade_data as td",
        "join": [
            {
                "table": "countries as c",
                "type": "inner",
                "on": "td.partner_country = c.country_code",
            },
            {
                "table": "mode_of_transport as mot",
                "type": "inner",
                "on": "td.mode_of_transport = mot.mode_of_transport_code",
            },
        ],
    },
    "filters": {
        "partner_country": {
            "query": "c.country_code"
        }
    },
    "security": {"allow-raw-sql": False},
}

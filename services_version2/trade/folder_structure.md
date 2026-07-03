trade/
│
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI entry
│
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   ├── endpoints.py
│   │   ├── schemas.py
│   │   ├── validators.py
│   │   └── exceptions.py
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── exceptions.py
│   │   ├── logging.py
│   │   └── settings.py
│   │
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── llm_extractor.py
│   │   ├── prompt_builder.py
│   │   └── nlg/
│   │       ├── generator.py
│   │       ├── formatters.py
│   │       └── suggestions.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── trade_service.py
│   │   ├── query_service.py
│   │   ├── enrichment_service.py
│   │   └── visualization_service.py
│   │
│   ├── dal/
│   │   ├── __init__.py
│   │   ├── dal_client.py
│   │   ├── dal_models.py
│   │   ├── dal_request_builder.py
│   │   ├── url_builder.py
│   │   └── exceptions.py
│   │
│   ├── processing/
│   │   ├── __init__.py
│   │   ├── normaliser.py
│   │   ├── validation.py
│   │   ├── enrichment.py
│   │   ├── query_plan.py
│   │   ├── semantic_registry.py
│   │   ├── product_resolver.py
│   │   ├── countries.py
│   │   └── transport_modes.py
│   │
│   ├── handlers/
│   │   ├── scopes.py
│   │   └── strategies.py
│   │
│   ├── visualization/
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── chart_mapper.py
│   │   └── transformers.py
│   │
│   └── utils/
│       ├── helpers.py
│       └── constants.py
│
├── prompts/
│
├── tests/
│
├── docs/
│
├── scripts/
│
├── logs/
│
├── uploads/
│
├── .env
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
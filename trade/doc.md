I will check the current permissions to see if we can access the `trade10` directory to analyze its design.

Used tool: list_permissions

I will request permission to read files in the `D:\User\DSO intern\trade10` directory so that I can inspect the trade10 application code and check how dynamic it is.

Used tool: ask_permission

I will list the contents of the `D:\User\DSO intern\trade10` directory to understand the layout and locate the main components of the service.

Listed directory trade10

I will read the `trade_service_architecture.md` file, which should give us a good architectural overview of the service.

Viewed trade_service_architecture.md:1-100

I will view the next section of the trade service architecture document to understand the rest of the stages and how the overall pipeline is designed.

Viewed trade_service_architecture.md:100-250

I will view the remaining section of the trade service architecture document, specifically focusing on the NLG stage and overall design constraints.

Viewed trade_service_architecture.md:250-350

I will list the directories and files within the `app` directory of the `trade10` service to find where configurations are stored.

Listed directory app

I will list the files in `app/core` to identify semantic registries, config files, and core logic components.

Listed directory core

I will view the contents of `app/core/semantic_registry.py` to understand how dimensions, measures, intents, and business rules are registered and configured.

Viewed semantic_registry.py:1-200

I will view the rest of the `semantic_registry.py` file to see the registration of intents and rules.

Viewed semantic_registry.py:200-368

I will read `app/handlers/scopes.py` to see how business rules and intents are dynamically scoped and processed in Stage 3.

Viewed scopes.py:1-200

I will view the rest of `app/handlers/scopes.py` to see the logic for defaulting metrics, group_by dimensions, and intent rules routing.

Viewed scopes.py:200-339

I will view `app/handlers/strategies.py` to see the per-intent scoping strategies.

Viewed strategies.py:1-91

I will list the contents of the `app/ai` directory to see the layout of the NLG and template code.

Listed directory ai

I will list the files in the `app/ai/nlg` directory to check how the NLG generation is structured.

Listed directory nlg

I will list the files in the `app/ai/nlg/templates` directory to see the available intent templates.

Listed directory templates

I will read the `app/ai/nlg/templates/__init__.py` file to see how template dispatching is implemented.

Viewed __init__.py:1-20

I will read `app/ai/nlg/generator.py` to see how the system dynamically dispatches templates when rendering the natural language messages.

Viewed generator.py:1-150

I will view the rest of the file to see how these render functions are selected based on the intent.

Viewed generator.py:150-235

The `trade10` service is designed to be **highly dynamic, modular, and metadata-driven**. 

Instead of hardcoding paths or sql generation logic for specific questions, it separates business logic, metadata configurations, and prompt templates into centralized layers. This ensures that when a manager or developer wants to add new features (such as a new intent, dimension, measure, or product mapping), **they do not need to refactor the core execution pipeline**.

Here is a breakdown of where to make changes when adding different types of features:

---

### 1. Adding a New Dimension (e.g. `PORT_OF_ENTRY` or `PROVINCE`)
If you need to support querying by a new database dimension:
* **Step 1: Define the Structure**: In [semantic_registry.py](file:///D:/User/DSO%20intern/trade10/app/core/semantic_registry.py#L53), add your dimension (type, values, description) under `STRUCTURE["dimensions"]`.
* **Step 2: Add Synonym Aliases**: In [semantic_registry.py](file:///D:/User/DSO%20intern/trade10/app/core/semantic_registry.py#L148), add user synonym mappings (e.g. `"port"`, `"customs checkpoint"`) under `SEMANTIC["dimensions"]`. This lets Stage 2 (Semantic Enrichment) auto-resolve words in natural language questions to the canonical dimension name.
* **Step 3: Bind to Dataset**: In [semantic_registry.py](file:///D:/User/DSO%20intern/trade10/app/core/semantic_registry.py#L257), add the new dimension name to the active dataset configuration (e.g. `"trade_volume_1.0"`).
* **Step 4: Update extraction instructions**: Update the Gemini extraction instructions in your prompt files (typically under `prompts/parameter_extraction.yaml`) so the LLM knows to extract the new dimension from natural language.
* **Step 5: Map to Database (DAL)**: Ensure your Data Access Layer (DAL) metadata concept registry (e.g. `dataset-concept.json` on the DAL side) has a query field matching this dimension and maps it to a database column.

---

### 2. Adding a New Intent (e.g. `market_share` or `forecasting`)
If you want the system to understand a new type of query intent:
* **Step 1: Normalize aliases**: In [semantic_registry.py](file:///D:/User/DSO%20intern/trade10/app/core/semantic_registry.py#L306), update `normalize_intent()` to map plural versions or synonyms of the intent to a single canonical name (e.g. `"market share"` $\rightarrow$ `"market_share"`).
* **Step 2: Add Scoping Strategy**: In [strategies.py](file:///D:/User/DSO%20intern/trade10/app/handlers/strategies.py#L25), add a new `IntentStrategy` defining:
  * Default group-by/dimensions (e.g. `PARTNER_COUNTRY`).
  * Default metrics, limits, and sort order.
  * Suggested visualizations (e.g. `pie_chart`, `table`).
* **Step 3: Add Intent Rules**: In [semantic_registry.py](file:///D:/User/DSO%20intern/trade10/app/core/semantic_registry.py#L216), register validation rules (such as required dimensions or time constraints) under `INTENT_RULES`.
* **Step 4: Create Fallback NLG Template**: 
  1. Add a new template script (e.g. `app/ai/nlg/templates/market_share_template.py`) and implement a `render_market_share(facts)` fallback renderer.
  2. Expose the function in the templates index file: [app/ai/nlg/templates/\_\_init\_\_.py](file:///D:/User/DSO%20intern/trade10/app/ai/nlg/templates/__init__.py).
  3. Wire the renderer under `_generate_fallback_template()` in [generator.py](file:///D:/User/DSO%20intern/trade10/app/ai/nlg/generator.py#L167) so it is dispatched dynamically when the intent matches.
* **Step 5: Teach the Extraction LLM**: Update your `parameter_extraction` prompt configuration to describe the new intent so Gemini can extract it.

---

### 3. Adding Product Synonyms (e.g. "rubber", "garments")
If the manager wants the service to better resolve products to specific HS/SITC classification codes:
* Make edits inside [product_resolver.py](file:///D:/User/DSO%20intern/trade10/app/core/product_resolver.py). Here you can write search patterns and regex maps that match text (e.g. `"banana"`) and resolve it to code definitions (e.g. `"0803"`).

---

### 4. Adding Country Synonyms (e.g. "viet nam", "america")
* Add custom name resolution, regional expansions, or spelling variations to the dictionaries located in [countries.py](file:///D:/User/DSO%20intern/trade10/app/core/countries.py).

---

### Why this design is powerful:
1. **Centralized changes**: To add new datasets or dimensions, you only change structural configuration registries in `semantic_registry.py`. You do not write new SQL builder query constructors or routing handlers.
2. **Safe Fallbacks**: Separating templates by intent files in the `nlg/templates/` folder keeps natural language string templating maintainable. If the primary generative LLM (Gemini) times out or has a network failure, the dispatcher fallback guarantees a user-facing reply is built dynamically using local template rules.


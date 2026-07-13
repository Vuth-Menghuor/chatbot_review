# Trade Query Service — Subintent Parameter & Structural Scopes

Below is the precise parameter and structural scope that each subintent is designed to handle. A query's question is dynamic, but it must map to one of these scopes to be processed under the respective subintent. Template questions are provided for each scope to demonstrate how metadata variables (Flow, Country, Period, Frequency, Transport, Product HS/SITC, and Measures) are naturally referenced.

---

## 1. `summary` Scope
Handles single-point aggregate trade metrics.
* **Flow/Direction**: Exports (`EX`), Imports (`IM`), or Total Trade (both).
* **Target Entities**: Cambodia overall (default), or filtered by a single partner country (e.g., `CN`, `US`).
* **Time Dimensions**:
  * Single year (e.g., `2023`)
  * Relative year (e.g., `this year`, `last year` resolving to a single year)
  * Specific calendar month (e.g., `March`)
  * Specific quarter (e.g., `Q1`)
  * Specific semester (e.g., `H1` / `semester 1`, `H2` / `semester 2`)
* **Transport Modes**: Air, sea, land, etc. (single or multiple).
* **Product Filters**: Specific product or broad HS chapters, or SITC sectors.
* **Template Questions**:
  * *“What was Cambodia's total [FLOW] value in [PERIOD]?”*
  * *“Total trade with [PARTNER_COUNTRY] [PERIOD]”*
  * *“Summary of [FLOW] by [MODE_OF_TRANSPORT] in [PERIOD]”*
  * *“How much [HS_HEADING/HS_CHAPTER] did Cambodia [FLOW] in [PERIOD]?”*
  * *“What was the net weight (in kg/tonnes) of [FLOW] to [PARTNER_COUNTRY] in [PERIOD]?”*
  * *“Total [FLOW] value of [SITC_SECTION/SITC_DIVISION] in [PERIOD]”*
  * *“Summary of [FLOW] to [PARTNER_COUNTRY] by [MODE_OF_TRANSPORT] in [MONTH] [YEAR]”*
  * *“Trade value with [PARTNER_COUNTRY]”*
  * *“What was the net weight/quantity of [FLOW] in [PERIOD]?”*

---

## 2. `ranking` Scope
Handles ordering and limiting lists of entities.
* **Flow/Direction**: Exports (`EX`), Imports (`IM`), or Total Trade (both).
* **Grouping Dimensions**: Group by partner countries, HS chapters, HS headings, or transport modes.
* **Sorting & Limits**:
  * Top N (`limit` + `desc` order)
  * Bottom N (`limit` + `asc` order)
* **Time Dimensions**: Single year, quarter, or relative year.
* **Filters**: Can be combined with transport mode filters or specific product filters.
* **Template Questions**:
  * *“Top/Bottom [LIMIT] [FLOW] partners in [PERIOD]”*
  * *“Which countries does Cambodia [FLOW] the most to?”*
  * *“Top [LIMIT] products [FLOW] in [PERIOD]”*
  * *“Top [LIMIT] [MODE_OF_TRANSPORT] used for [FLOW] in [PERIOD]”*
  * *“Top [LIMIT] [FLOW] partners for [HS_HEADING/HS_CHAPTER] in [PERIOD]”*
  * *“Top [LIMIT] [FLOW] partners by weight/quantity in [PERIOD]”*
  * *“Top [LIMIT] economic sectors/SITC divisions for [FLOW] in [PERIOD]”*
  * *“Which mode of transport had the highest [FLOW] value in [PERIOD]?”*
  * *“Which [GROUP_DIMENSION] had the highest/lowest [FLOW] value in [PERIOD]?”*
  * *“Best performing [PARTNER_COUNTRY] markets in [PERIOD]”*
  * *“Top [LIMIT] partners by weight/quantity”*
  

---

## 3. `trend` Scope
Handles tracking metrics over a time series.
* **Flow/Direction**: Exports (`EX`), Imports (`IM`), or Total Trade (both).
* **Target Entities**: Cambodia overall, or filtered by a single partner country.
* **Time Resolution (Frequency)**: Monthly (`M`), Quarterly (`Q`), Semester (`S`), or Annual (`A`).
* **Time Intervals**:
  * Closed multi-year range (e.g., `2018` to `2023`)
  * Relative multi-year range (e.g., `past 5 years`, `last decade`)
  * Multi-year trends restricted to a specific period (e.g., `Q1 each year from 2020-2023`)
* **Filters**: Can be combined with transport mode filters or specific product filters.
* **Template Questions**:
  * *“Show the [FREQUENCY] [FLOW] trend in [PERIOD]”*
  * *“How has trade with [PARTNER_COUNTRY] changed from [START_PERIOD] to [END_PERIOD]?”*
  * *“Trend of [FLOW] by [MODE_OF_TRANSPORT] in [PERIOD]”*
  * *“Track [FLOW] of [HS_HEADING/HS_CHAPTER] monthly in [PERIOD]”*
  * *“Show the trend of [FLOW] weight for [HS_HEADING] over time”*
  * *“Track the monthly trend of [FLOW] to [PARTNER_COUNTRY] by [MODE_OF_TRANSPORT] from [START_PERIOD] to [END_PERIOD]”*
  * *“Quarterly trend of [SITC_SECTION] exports since [YEAR]”*
  * *“How has [FLOW] trade with [PARTNER_COUNTRY] changed over the past [N] years?”*
  * *“Compare this year's [FLOW] to last year”*
  * *“Show [FLOW] trend for [QUARTER] each year from [START_YEAR] to [END_YEAR]”*
  * *“Trend of trade balance with [PARTNER_COUNTRY]”*
---

## 4. `comparison` Scope
Handles side-by-side comparison of metrics between multiple partner countries.
* **Flow/Direction**: Exports (`EX`), Imports (`IM`), or Total Trade (both).
* **Target Entities**: Must involve **two or more distinct partner countries** (e.g., `CN` vs. `JP`, or `VN`, `TH`, and `LA`).
* **Time Dimensions**: Single year or current/relative year.
* **Template Questions**:
  * *“Compare [FLOW] to [PARTNER_COUNTRY_1] vs [PARTNER_COUNTRY_2] in [PERIOD]”*
  * *“Compare [FLOW] between [PARTNER_COUNTRY_1] and [PARTNER_COUNTRY_2]”*
  * *“How does trade with [PARTNER_COUNTRY_1] compare to [PARTNER_COUNTRY_2]?”*
  * *“Compare [FLOW] of [HS_CHAPTER/SITC_SECTION] between [PARTNER_COUNTRY_1] and [PARTNER_COUNTRY_2]”*
  * *“Compare the volume/weight of [FLOW] to [PARTNER_COUNTRY_1] vs [PARTNER_COUNTRY_2] in [PERIOD]”*
  * *“Comparison of [FLOW] to [PARTNER_COUNTRY_1], [PARTNER_COUNTRY_2], and [PARTNER_COUNTRY_3]”*
  * *“[PARTNER_COUNTRY_1] vs [PARTNER_COUNTRY_2]: which is the bigger trade partner?”*
  * *“Trade value with [PARTNER_COUNTRY_1] relative to [PARTNER_COUNTRY_2]”*
  * *“Compare monthly/quarterly trends between [PARTNER_COUNTRY_1] and [PARTNER_COUNTRY_2]”*
  

---

## 5. `breakdown` Scope
Handles slicing a total metric into its component parts.
* **Flow/Direction**: Exports (`EX`), Imports (`IM`), or Total Trade (both).
* **Target Entities**: Cambodia overall, or filtered by a single partner country.
* **Grouping Dimensions**: Group by product (HS chapter, HS heading), mode of transport, economic sector (SITC section, SITC division), or partner country.
* **Time Dimensions**: Single year, quarter, or relative year.
* **Filters**: Can be combined with transport mode filters or specific product filters.
* **Template Questions**:
  * *“Breakdown of [FLOW] by product/sector in [PERIOD]”*
  * *“Show [FLOW] broken down by [MODE_OF_TRANSPORT] in [PERIOD]”*
  * *“Breakdown of trade with [PARTNER_COUNTRY] by [HS_CHAPTER/SITC_SECTION] in [PERIOD]”*
  * *“Distribution of [FLOW] of [HS_HEADING/HS_CHAPTER] by partner country in [PERIOD]”*
  * *“How are imports from [PARTNER_COUNTRY] distributed by mode of transport in [PERIOD]?”*
  * *“Economic sector/SITC breakdown of [FLOW] in [PERIOD]”*

---

## 6. `growth` Scope
Handles percentage changes, growth rates, or comparison over time.
* **Flow/Direction**: Exports (`EX`), Imports (`IM`), or Total Trade (both).
* **Target Entities**: Cambodia overall, or filtered by a single partner country.
* **Time Dimensions**:
  * Year-over-Year (YoY) comparison (comparing two consecutive years or a period range)
  * Month-over-Month (MoM) growth (frequency `M`)
  * Relative historical growth (e.g., `since 2018`)
* **Filters**: Can be combined with transport mode filters, specific product filters, or sector filters.
* **Template Questions**:
  * *“What was the [FLOW] growth rate in [PERIOD_1] compared to [PERIOD_2]?”*
  * *“How much did [FLOW] from [PARTNER_COUNTRY] grow year-over-year?”*
  * *“[FLOW] growth for [PARTNER_COUNTRY] from [START_PERIOD] to [END_PERIOD]”*
  * *“Growth rate of [FLOW] of [HS_HEADING/HS_CHAPTER] in [PERIOD]”*
  * *“[FREQUENCY] growth in [FLOW] for [PERIOD]”*
  * *“Did the weight of [FLOW] to [PARTNER_COUNTRY] increase or decrease in [YEAR] vs [YEAR]?”*
  * *“YoY growth of the [SITC_DIVISION] sector in [PERIOD]”*
  * *“Did [FLOW] increase or decrease in [PERIOD_1] compared to [PERIOD_2]?”*
  * *“How has Cambodia's trade grown since [YEAR]?"*
  * *“Growth comparison of [FLOW] for [PARTNER_COUNTRY_1] and [PARTNER_COUNTRY_2]”*

---

## 7. `trade_balance` Scope
Handles calculating net trade position (Exports minus Imports).
* **Target Entities**: Cambodia overall, or filtered by a single partner country.
* **Time Dimensions**: Single year, relative year, quarter, or semester.
* **Output Metrics**: Calculated surplus, deficit, or net trade.
* **Template Questions**:
  * *“What is Cambodia's trade balance with [PARTNER_COUNTRY] in [PERIOD]?”*
  * *“Trade surplus or deficit with [PARTNER_COUNTRY]?”*
  * *“Net trade with [PARTNER_COUNTRY] in [PERIOD]”*
  * *“Is Cambodia importing more than exporting from [PARTNER_COUNTRY]?”*
  * *“What is the overall trade balance for [PERIOD]?”*
  * *“What is the trade surplus or deficit of [HS_CHAPTER] with [PARTNER_COUNTRY]?”*
  * *“Cambodia's net trade balance by [MODE_OF_TRANSPORT] in [PERIOD]”*
  * *“Track the trade balance with [PARTNER_COUNTRY] monthly in [PERIOD]”*
  * *“Compare exports and imports with [PARTNER_COUNTRY]”*
  * *“Track trade balance with [PARTNER_COUNTRY] over time”*


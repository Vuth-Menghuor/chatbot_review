## 🚨 Critical — data is wrong, stated with false confidence

1. **Partial-year (current-year) data is compared against full prior years as if complete.** Whenever a query's date range includes the current, still-in-progress year, that year's total is a partial-period figure but gets plotted/narrated identically to full completed years — producing large fake "declines" (commonly 50–80%) with no YTD/partial-period flag anywhere in `summary.data_quality`. This affects growth, trend, and trade_balance intents alike and is the single most consequential defect found.

2. **The system doesn't reliably resolve "this year," "last year," or unspecified periods to the actual current date.** Confirmed inconsistent: one phrasing ("this year") resolved to the wrong year while a nearly identical phrasing ("this year vs last year") resolved correctly. This points to relative-date resolution being hardcoded or resolved differently per code path rather than uniformly anchored to a single source of truth for "today." **This is especially risky for a chatbot meant to run indefinitely** — if "current year" is ever hardcoded or falls back to a stale default instead of reading the actual system clock, every relative-date query will silently drift wrong the moment the calendar turns over, with no error to signal it.

3. **Requested year sometimes gets silently swapped for a different year's data**, confirmed reproducible multiple times (e.g., a query explicitly scoped to one year returns another year's figures instead). Metadata sometimes self-reports the mismatch (`period_mismatch`, `requested_period`, `returned_period`) but nothing corrects it, and the generated message sometimes compounds the error further.

4. **Breakdown/ranking queries silently truncate at their row limit and report the partial sum as the full total.** Confirmed via cross-check against a query with no limit applied — a "top 20" truncated total undercounted the true full total by a meaningful margin. No `has_more`/`truncated` flag exists anywhere in the response to warn that the total is partial.

5. **Multi-period requests (e.g., "trade balance over the years," "last decade," "past N years") get silently truncated to whatever narrow window of data actually exists**, without disclosing that most of the requested range wasn't returned. Suggestions and parts of the generated message continue referencing the full originally-requested range even when it wasn't delivered.

## ⚠️ Significant — wrong metric, wrong intent, or misleading visualization

6. **"Volume" is ambiguous and inconsistently resolved.** Sometimes triggers a weight-based sort paired with a value-based chart/message (mismatched); explicit "by weight" phrasing works cleanly and consistently. The system needs a single, consistent rule for what "volume" means.

7. **"Trend" questions sometimes collapse into a single-value summary/KPI** instead of an actual multi-point trend, when the intent classifier picks "summary" instead of "trend" for phrasing that clearly asks for a trend.

8. **Trade-balance NLG doesn't compute the actual balance for monthly/multi-period breakdowns** — returns clean underlying export/import data but the narrative only restates peaks separately, never synthesizing the month-by-month deficit/surplus that a "track the balance" question is actually asking for.

9. **Bare error records with no graceful fallback** (`{"status":"error","error":"..."}` with no message, no suggestions) — confirmed reproducible more than once, not a one-off blip.

10. **Some intent+frequency combinations return no_data despite equivalent data existing elsewhere** in the system for the same underlying scope — suggests a gap in how certain intent/frequency pairs are queried rather than genuine data absence.

11. **Aggregated-bloc questions (e.g., about a multi-country group) don't aggregate to bloc level** — a yes/no bloc-level question gets a list of individual country figures instead of one bloc-level answer.

12. **Inconsistent/misfiring data-availability disclaimers** — a caveat about limited data coverage appears on some queries but not others with identical underlying conditions, and occasionally appears on a query that doesn't actually touch the affected period at all.

## 🔹 Minor / polish issues (recurring throughout)

13. **Raw, unmapped internal codes surfaced instead of human-readable labels** (e.g., transport-mode codes never resolved to their names anywhere visible to the user).

14. **Unspecified years silently default without disclosure** — see new recommendation below.

15. **Suggestions for multi-entity comparisons only address the first-ranked entity**, ignoring the others in a 3+-way comparison.

16. **Suggestion text quality** — some suggestions concatenate long category descriptions into unreadable chip strings, or contain garbled/duplicated phrasing.

17. **Chart labels are ambiguous for multi-flow bloc comparisons** — comparing an aggregated bloc against a country across imports/exports can produce duplicate labels with no way to tell which bar represents which flow.

## ✅ Resolved / inconsistent — worth re-verifying rather than re-flagging as new

- Category code→label mapping (e.g., SITC codes) does work correctly in some intents but not others — suggests the gap is in one specific generation path, not a missing lookup capability overall.
- A couple of previously known bugs (growth-sorting by the wrong metric; a specific intent misclassification) did not reproduce in this round — worth confirming whether genuinely fixed or just intermittent.
- Clean, unambiguous weight-vs-value handling works well in several cases — useful as the reference pattern for fixing the "volume" ambiguity bug above.

---

## New recommendation: don't silently default the year

When a question doesn't specify a year (or any period), the system currently guesses — usually the most recent complete year, sometimes inconsistently the current year — without telling the user a guess was made. Given this system needs to keep working correctly as real time moves forward, I'd suggest:

1. **Never silently assume a year.** If the question is ambiguous about period, either state the assumption plainly in the message ("Showing 2025 data — the most recent full year") or, better:
2. **Add a standing suggestion whenever no year was specified**, prompting the user to confirm or narrow it — e.g., *"Specify a year for more precise results (e.g., 'in 2025')"* — appended to the existing suggestion list rather than replacing it. This keeps the default answer useful while giving the user an easy way to correct scope.
3. **Anchor all "current/this year/last year/recent" resolution to one single, dynamically-read system clock value**, not a hardcoded or cached year, so behavior doesn't quietly drift wrong after any deploy that isn't refreshed, and so "this year" and "current" phrasing resolve identically everywhere in the pipeline.
4. **Flag partial-current-year data explicitly wherever it appears** (not just in NLG disclaimers, but as a machine-readable field like `is_partial_period: true` in `summary.data_quality`) so downstream chart/message logic can consistently avoid presenting an in-progress year as if it were complete — this is the fix that would prevent the most serious issue on this whole list.
# BizIntel AI

A local business analytics workspace for a fifth-semester college project. Upload a business CSV or Excel file (.xlsx) to get
safe type interpretation, an automatic dashboard, supported KPIs, findings and suggested actions.
Customization is optional; saved templates reuse settings on new data.

Uses **Python + Streamlit + Pandas + Plotly**. No separate API server, React, paid AI service or account is
required. Findings use calculation rules. Advanced modules use explained statistical/ML methods.
The application suggests actions but never executes business transactions.

## Run in Windows PowerShell

From this project folder:

~~~powershell
cd C:\Work\Projects\BizIntel-AI
.\.bav5\Scripts\python.exe -m pip install -r requirements.txt
.\.bav5\Scripts\python.exe -m streamlit run app.py
~~~

Open the printed local address, normally http://localhost:8501. Keep PowerShell open; press Ctrl+C to stop.
Using the environment's Python directly avoids activation-script restrictions.

For a new checkout only, install Python/Git, check them, and create the environment:

~~~powershell
python --version
git --version
python -m venv .bav5
~~~

Do not recreate a working environment. Development was checked with Python 3.13.
PDF charts also need Chrome/Chromium, already present on the development machine.
Kaleido renders the same Plotly figures; HTML/CSV remain available if PDF rendering fails.
See [Plotly's export documentation](https://plotly.com/python/static-image-export/).

## Quick demonstration

1. Data -> **Use sample data** -> **Open automatic dashboard**.
2. Expect 8 records, **5,180.00 INR revenue**, **3,260.00 cost**, **1,920.00 gross profit**,
   **8 orders** and approximately **37.1% gross margin**.
3. In Shared filters, select region and keep North. Revenue becomes **480.00 INR**.
   Charts, findings, Intelligence and reports share this scope.
4. In Explore, customize a chart, save it to the dashboard, and change inclusion/order or layout.
5. Save a named reusable template. Restart the server, load the sample again, then load the template.
   Settings return; results are recalculated.
6. In Prepare, preview an operation before applying it. Reset restores exact original text;
   re-running safe interpretation restores automatic types.
7. Load **Use extended demo** for 18 months and 30 customers. Visit Intelligence for eligible analyses.
   The eight-row sample deliberately does not satisfy advanced model minimums.
8. In Reports, select evidence/charts, accept/edit/reject actions, add your interpretation, preview and export.

All demo data is fictional. See the [learning guide](docs/LEARNING_GUIDE.md) for presentation notes and questions.

## Pages

| Page | Purpose |
| --- | --- |
| Data | CSV/sample/demo, previews, interpretation log, optional mappings/currency, reusable templates |
| Prepare | Missingness/duplicates/types, preview/apply/reset, original comparison, action history |
| Explore | Bar/line/histogram/scatter/box; aggregation, labels, grouping, palette, top-N, chart selection/order |
| Dashboard | Shared filters, supported KPIs, matching charts, formulas, calculated findings and suggestions |
| Intelligence | Chronological forecasts, customer RFM groups, IQR anomaly investigation |
| Reports | Scope-bound evidence, reviewed actions, final interpretation, CSV/HTML/PDF |

## Fixed 20-field catalogue

The approved contract is in [DATA_CATALOGUE.md](docs/DATA_CATALOGUE.md).
Data shows all 20 roles, detected mappings and columns outside analysis scope.
Download the fictional 20-field example in Data or upload `sample_sales_catalogue.csv`.
Not all fields are mandatory; missing prerequisites disable dependent features.

The six main cards are Sales, Reported/Gross Profit, corresponding Margin, Orders,
Units Sold and Average Order Value. Extra columns remain in previews, preparation
and CSV exports; charts, filters and model inputs use mapped catalogue fields.

## Data and calculation rules

- One comma-separated UTF-8 CSV or Excel workbook (.xlsx), optional BOM, at most 10 MiB; unique nonempty headers and consistent row widths.
- Original bytes/text remain unchanged in session memory. IDs, leading zeros and literal NA/null codes are retained.
- Only unambiguous finite numbers and ISO dates are automatically interpreted. No silent deletion or imputation.
- Generic amount/cost fields need explicit mapping. Unit costs and line-total costs are distinct.
- Unknown currency has no guessed symbol. Mixed/incomplete currency blocks monetary totals until explicitly resolved.
  Choosing a label does not convert exchange rates.
- Sales uses supplied row sales, otherwise quantity × realized unit price. Discount is never applied again.
- Supplied profit is labeled Reported profit; otherwise calculate Gross profit only with complete corresponding costs.
  Profit and margin use the matching valid-sales cohort. Partial profit coverage is not silently filled.
  Supplied/calculated discrepancies are disclosed. See the catalogue for precise assumptions.
- Orders count distinct nonblank IDs; row counts are Records. Average order value requires a complete matched cohort.
- Monthly growth requires consecutive completed months, adequate observed boundaries and a positive baseline.
- Filters combine with AND; endpoints are included; missing values require explicit inclusion.
- Changed data/settings cause fresh results. Old report interpretations become outdated drafts requiring review.
- Spreadsheet-safe CSV protects risky text in the download only; legitimate numeric negatives stay numbers.

## Advanced methods and limits

Forecasting needs at least 12 regular, complete periods with valid dates/target values. Missing intervals are
unknown, not zero. The last approximately 20% (minimum 3 periods) is held out chronologically.
Naive, moving-average and linear-trend baselines report MAE/RMSE, never invented accuracy.
The recommendation uses that same holdout; it is not independent final evaluation.
Future projections refit all history. Source completeness cannot be proved from timestamps alone.

Customer segmentation uses recency, distinct-order frequency and monetary total. Incomplete/ambiguous transactions
exclude the affected customer. At least 20 eligible customers, varying features and enough distinct profiles are
needed. Standardized K-means uses seed 42. Silhouette describes separation, not customer worth or accuracy.
Returns remain in net monetary values.

Anomalies use Q1/Q3 fences with default multiplier 1.5 × IQR, at least 20 finite records and nonzero spread.
Flags invite investigation, not a fraud conclusion. Original record numbers identify parsed data rows,
not physical CSV lines.

## Saved settings and privacy

Versioned JSON templates live in ignored data/templates/. Atomic writes prevent partially saved files.
They store mappings, approved preparation, currency, filters, chart/model settings and report structure.
They do not store uploaded rows, predictions, calculated findings or user interpretations.
Loading checks names/types/categories/dates and explains skipped incompatible settings.

Uploads and report drafts are session-only; restarting/refreshing may require uploading again.
Exports contain the chosen data and are downloaded when requested. Private data, templates, reports,
logs and verification artifacts are excluded from Git. Nothing is published online.

## Tests and verification

~~~powershell
.\.bav5\Scripts\python.exe -m unittest discover -s tests -v
.\.bav5\Scripts\python.exe -m pip check
~~~

Tests cover CSV/cleaning/chart regressions, mathematical edge cases, automatic analysis, filters/navigation,
templates across processes, model gates, report invalidation and safe export handling.
See [verification evidence](docs/VERIFICATION.md) for checks actually performed.

Optional PDF verification requires a development-only package:

~~~powershell
.\.bav5\Scripts\python.exe -m pip install pymupdf
.\.bav5\Scripts\python.exe tests\verify_exports.py
~~~

This creates only fictional artifacts under ignored .verification/.
The optional tests/verify_browser.cjs needs Node, Playwright and Chrome, with a local app on port 8510.
Those browser-testing tools are not required to run the application.

## Code map

| Files | Responsibility |
| --- | --- |
| app.py, app_state.py | Page routing, data/settings, session preservation and revisioning |
| ui_style.py, ui_controls.py | Visual shell and shared filters |
| csv_loader.py, automation.py | Validation, safe types, semantic roles, scope fingerprint |
| catalogue.py | Fixed 20-field vocabulary, aliases, analysis scope and legacy mapping compatibility |
| data_cleaning.py, cleaning_ui.py | Pure preparation functions and preview/apply interface |
| analysis.py, kpi.py | One scoped table and coverage-aware calculations |
| dashboard.py, charts.py | Reusable filters and chart preparation/specifications |
| dashboard_ui.py, kpi_ui.py | Chart editor and automatic dashboard |
| insights.py | Reproducible findings and separate suggestions |
| forecasting.py, intelligence.py, forecasting_ui.py | Forecast math, suitability gates, RFM and IQR |
| templates.py, template_ui.py | Validated local JSON and template controls |
| reports.py, reports_ui.py | Review, snapshot, safe exports |
| demo_data.py, sample_sales.csv | Fictional demonstrations |
| AGENTS.md, PROJECT_PROGRESS.md | Agreed guidance, current authorization and progress |

NumPy supports numerical calculations; scikit-learn supplies scaling/K-means; ReportLab lays out PDFs;
Kaleido renders chart images. The direct versions are recorded in requirements.txt.

Read [the PRD](docs/BIZINTEL_AI_PRD.md), [the learning guide](docs/LEARNING_GUIDE.md), and
[the progress record](PROJECT_PROGRESS.md). Power BI and online publishing remain outside this build.


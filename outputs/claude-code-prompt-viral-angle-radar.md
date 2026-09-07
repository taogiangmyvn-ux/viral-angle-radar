# Master prompt for Claude Code: Viral Angle Radar

You are a senior full-stack engineer, data engineer, and product designer. Build a production-quality MVP named **Viral Angle Radar** for a performance creative team.

Do not stop at a plan. Inspect the repository, implement the application, run it locally, test the important paths, fix issues, and document how to operate it. Make sensible assumptions when details are missing, but record them in the README.

## 1. Product goal

Create a tool that automatically discovers and maintains a daily-updated library of viral short-form video references, initially focused on TikTok skincare content made by US-based creators using natural American English.

The tool must:

1. Find source videos matching configurable markets, categories, creators, formats, keywords, and content angles.
2. Preserve the exact original video URL and observable evidence for every result.
3. Identify the video's hook, angle, format, product/category, audience, proof mechanism, CTA, and why it may be performing.
4. Rank videos and angles using transparent trend and relevance scores.
5. Track metric snapshots over time so momentum can be distinguished from old accumulated popularity.
6. Generate a usable creative brief for a selected brand using its brand book, current relevance, product information, and prior briefs.
7. Publish the results as a fast static dashboard deployable to GitHub Pages.
8. Export the same normalized data to an Excel workbook.
9. Run the collection, enrichment, scoring, site build, and Excel export automatically every day with GitHub Actions.

The system must never invent URLs, creators, captions, metrics, dates, quotes, or source evidence. Unknown values must remain null and be visibly labeled as unavailable.

## 2. MVP technology

Use a simple monorepo structure:

- `pipeline/`: Python 3.12 data collection, normalization, scoring, enrichment, brief generation, and exports.
- `web/`: Vite + React + TypeScript static dashboard.
- `data/`: versioned JSON/JSONL and SQLite data.
- `brands/`: one folder per brand containing brand book, product notes, extracted context, and prior briefs.
- `exports/`: generated `.xlsx` files and daily reports.
- `.github/workflows/daily-update.yml`: scheduled automation.
- `tests/`: focused unit and integration tests.

Prefer boring, dependable dependencies. Use SQLite for local normalized storage, JSON for the static site, pandas/openpyxl or xlsxwriter for Excel, Pydantic for schemas, and pytest for tests.

The GitHub Pages site must not require a server at runtime. The daily workflow should generate static JSON and then build the frontend.

## 3. Source acquisition and compliance

Implement a provider/adaptor interface instead of coupling the project to one scraping method.

Required adapters:

- `manual_csv`: always available; imports manually collected source URLs and metadata.
- `search_engine`: discovers public TikTok URLs through a configurable search provider when credentials are present.
- `tiktok_provider`: optional provider implementation enabled only when a legitimate API/service credential is configured.
- `fixture`: deterministic local demo data for development and tests.

Examples of legitimate optional providers may include an approved TikTok API, a user-configured commercial data provider, or a search API. Keep provider-specific code isolated. Do not bypass authentication, CAPTCHA, rate limits, robots restrictions, paywalls, or platform security. Do not commit credentials. Do not pretend an unavailable provider succeeded.

Every collected record must contain:

- provider name
- canonical source URL
- discovery query
- collection timestamp in UTC
- raw observable fields
- evidence status
- any provider error or missing-field reason

Deduplicate by canonical video URL/video ID. Preserve historical metric snapshots instead of overwriting them.

## 4. Search configuration

Create editable YAML configuration with defaults for:

- platform: TikTok first, extensible to Reels and Shorts
- country/market: United States
- language: English
- creator requirement: US-based or clearly US-market-facing
- category: skincare
- formats: talking head, expert review, UGC review, ranking, reaction, comparison, routine audit
- angles: brutally honest review, dermatologist rates, best vs worst, product regret, worth the hype, affordable alternative, products I trust, hidden gem, viral but overrated, routine audit, problem/solution, before/after
- keywords and negative keywords
- minimum/maximum content age
- minimum evidence threshold
- scoring weights
- maximum results per query/provider

Make the system usable for other markets/categories by changing config rather than code.

## 5. Normalized data model

Create Pydantic models and matching SQLite tables for at least:

### Video

- `video_id`
- `platform`
- `canonical_url`
- `creator_handle`
- `creator_name`
- `creator_country`
- `creator_country_evidence`
- `language`
- `caption`
- `published_at`
- `duration_seconds`
- `thumbnail_url`
- `product_names`
- `brand_names`
- `category`
- `format`
- `paid_partnership`
- `collected_at`
- `last_verified_at`
- `evidence_quality`
- `source_provider`

### MetricSnapshot

- `video_id`
- `observed_at`
- `views`
- `likes`
- `comments`
- `shares`
- `saves`
- `followers`
- `field_provenance`

### AngleAnalysis

- `video_id`
- `hook_verbatim` only when it is actually observable
- `hook_summary`
- `primary_angle`
- `secondary_angles`
- `creative_structure`
- `opening_visual`
- `proof_mechanism`
- `objection_handled`
- `audience`
- `pain_point`
- `promise`
- `cta`
- `why_it_works`
- `confidence`
- `analysis_model`
- `analysis_timestamp`

### TrendScore

- `video_id`
- `calculated_at`
- `trend_score`
- `velocity_score`
- `engagement_score`
- `recency_score`
- `relevance_score`
- `novelty_score`
- `evidence_score`
- `explanation`

### Brand and Brief

Store brand profile, product facts, mandatory claims, prohibited claims, tone, audience, differentiators, proof, visual identity, prior brief references, brief version, generated content, citations back to both brand material and source videos, and human approval status.

## 6. Trend scoring

Implement transparent, configurable scoring from 0–100.

Use available evidence only. Suggested initial formula:

- 30% metric velocity from consecutive snapshots
- 20% engagement quality
- 15% recency
- 20% relevance to configured category/market/format
- 10% angle novelty relative to the recent library
- 5% evidence quality

Requirements:

- Normalize metrics using log transforms so huge accounts do not dominate.
- When follower count is available, include follower-normalized engagement.
- Penalize missing evidence rather than fabricating a value.
- If only one snapshot exists, label velocity as `insufficient_history` and calculate a lower-confidence provisional score.
- Store every component and explanation so users can audit the ranking.
- Aggregate videos into an Angle leaderboard showing count, median score, maximum score, recent growth, and representative examples.

## 7. AI enrichment

Create a provider-neutral LLM interface with an Anthropic implementation driven by environment variables. The app must still operate without an LLM by keeping enrichment fields empty and showing a clear status.

Use structured JSON outputs validated through Pydantic. Retry invalid structured responses with a strict limit. Cache enrichment by content hash and prompt version.

Important rules for the analysis prompt:

- Analyze only supplied evidence.
- Do not infer spoken words from a caption alone.
- Distinguish observed facts from interpretation.
- Do not claim a creator is American/native solely from their accent or appearance.
- US-based status must have profile/provider evidence; otherwise use `unverified`.
- Never create fake performance metrics.
- Keep verbatim excerpts short and store source attribution.

## 8. Brand knowledge ingestion

Allow each brand folder to include `.pdf`, `.docx`, `.txt`, `.md`, `.csv`, `.xlsx`, and prior briefs.

Create commands to:

1. Extract text locally.
2. Record filename, page/sheet when available, and content hash.
3. Generate a reviewable `brand_profile.json` containing:
   - positioning
   - audience
   - tone and vocabulary
   - product facts
   - approved claims
   - prohibited claims
   - mandatory disclaimers
   - differentiators
   - proof points
   - visual guidance
   - CTA preferences
4. Never silently treat model-inferred claims as approved facts.
5. Mark conflicts between current brand book and prior briefs.

Do not use a vector database for the first MVP unless clearly necessary. Start with sectioned text, metadata, keyword filtering, and embeddings only behind an optional interface.

## 9. Brief generator

From the dashboard or CLI, the user must be able to select:

- brand
- product
- target audience
- objective
- desired number of concepts
- selected angle(s) or “top trending relevant angles”
- desired creator type
- channel and duration
- mandatory source videos

Generate a brief containing:

- brief title and objective
- target audience and tension
- selected trend/angle with freshness explanation
- links to 3–5 source videos
- explicit explanation of why each source is relevant
- key brand/product truth
- single-minded message
- 3 hook options in natural American English
- recommended 15/30/45-second structure
- scene/shot guidance
- talking points, proof, and demonstration
- on-screen text
- CTA options
- tone and creator direction
- do/don't list
- mandatory claims/disclaimers
- adaptation notes explaining what is inspired by the pattern versus what must not be copied
- citations to brand-book passages and prior briefs
- assumptions and missing information
- confidence level

Generate both Markdown and JSON. Provide a “Regenerate hooks only” command that does not rewrite the entire brief.

## 10. Static dashboard

Build a polished but simple responsive dashboard with these pages:

### Overview

- last successful update
- data freshness and provider health
- top rising videos
- top rising angles
- alerts for missing/failed sources

### Video Library

- searchable/filterable table or cards
- filters for date, market, language, creator, brand, product, angle, format, score, evidence quality, paid/organic
- source link opens the exact original video
- sortable trend components
- historical metric sparkline when snapshots exist
- visual labels separating observed and AI-inferred fields

### Angle Radar

- ranked angle leaderboard
- trend direction
- representative video sources
- angle detail page showing hooks, structures, audiences, and related products

### Brand Workspace

- brand profile summary
- imported files and freshness
- previous briefs
- relevance matches between brand and current angles

### Brief Builder

- form to select brand/product/objective/angles
- preview generated Markdown
- download JSON and Markdown

### Data Quality

- duplicates
- stale records
- unverified creator location
- missing metrics
- failed providers
- malformed URLs

The UI must display a clickable source list similar to:

| Trend | Creator | Video | Angle | Hook | Key metric | Observed | Relevance | Evidence |
|---|---|---|---|---|---:|---|---:|---|

Do not embed or download copyrighted videos. Use links and permitted thumbnails only.

## 11. Excel export

Generate `exports/viral-angle-radar.xlsx` with frozen headers, filters, sensible widths, date/number formatting, hyperlinks, and conditional formatting.

Required sheets:

- `Top Videos`
- `Angle Radar`
- `Creators`
- `Metric History`
- `Brand Relevance`
- `Generated Briefs`
- `Data Quality`
- `Run Log`

The workbook must contain real hyperlinks to original videos and be regenerated on every successful run.

## 12. CLI

Provide commands similar to:

```bash
python -m pipeline discover --config config/skincare-us.yml
python -m pipeline snapshot
python -m pipeline enrich --only-missing
python -m pipeline ingest-brand --brand demo-brand
python -m pipeline score
python -m pipeline generate-brief --brand demo-brand --product demo-product --top-angles 3
python -m pipeline export-site
python -m pipeline export-excel
python -m pipeline daily
```

Commands must return non-zero status on genuine failure and write structured run logs.

## 13. GitHub Actions and deployment

Create:

- a daily scheduled workflow using UTC cron
- manual `workflow_dispatch`
- concurrency protection so runs do not overlap
- dependency caching
- secret-driven optional providers and Anthropic API
- fixture/demo mode for forks without secrets
- artifact upload for the Excel workbook and run logs
- GitHub Pages deployment for the static dashboard
- an optional pull-request mode for data changes; default to committing generated data only when configured

Use minimal GitHub token permissions. Never print secrets in logs. Document how to change the schedule and timezone expectation.

## 14. Reliability and security

- Validate TikTok URLs and canonicalize tracking parameters.
- Escape untrusted captions and brand-book text in the frontend.
- Add request timeouts, bounded retries, rate limiting, and provider backoff.
- Add content hashes and idempotent upserts.
- Preserve the last successful dataset when a daily provider fails.
- Surface partial failures without breaking the entire dashboard.
- Add `.env.example`; never commit `.env`, credentials, raw cookies, or browser profiles.
- Do not use browser automation to bypass sign-in, CAPTCHA, or access controls.
- Include clear medical-claims safeguards for skincare briefs.

## 15. Demo data

Seed fixture mode with clearly labeled synthetic metadata plus several valid public URL-shaped examples. Synthetic records must use `is_fixture: true` and must never be presented as live trend evidence.

Also provide a `manual_sources.csv` template so a researcher can paste verified video URLs and metrics.

## 16. Tests and quality gates

At minimum test:

- URL canonicalization and deduplication
- metric snapshot preservation
- scoring with full and missing data
- Pydantic validation of LLM output
- brand document provenance
- brief citations
- Excel hyperlinks and required sheets
- static JSON generation
- frontend build
- fixture-mode daily pipeline

Run formatting, linting, type checks, tests, and a production frontend build before declaring completion.

## 17. README and handoff

Write a practical README covering:

- product overview and architecture
- local setup
- environment variables
- provider setup and compliance limitations
- adding a new category/market/angle
- importing manual sources
- adding a brand book and prior briefs
- generating a brief
- viewing the dashboard
- exporting Excel
- configuring daily GitHub Actions
- deploying GitHub Pages
- troubleshooting and data-quality interpretation

Include a Mermaid system diagram and a short “MVP limitations / next improvements” section.

## 18. Implementation sequence

Implement in this order:

1. Inspect repo and state assumptions.
2. Scaffold schemas, SQLite migrations, fixture/manual adapters, and CLI.
3. Implement snapshots, scoring, and data-quality checks.
4. Implement Excel export.
5. Implement brand ingestion and citation-aware brief generation.
6. Implement the static React dashboard.
7. Add daily workflow and GitHub Pages deployment.
8. Add tests, sample config, demo brand, and documentation.
9. Run the entire fixture-mode daily pipeline and production build.
10. Report created files, commands run, test results, remaining limitations, and the exact next step for enabling a legitimate live data provider.

## 19. Acceptance criteria

The task is complete only when:

- `python -m pipeline daily --fixture` succeeds from a clean setup.
- At least two metric snapshots can be stored without overwriting history.
- The Angle Radar is derived from normalized records and transparent scores.
- A demo brand book and prior brief can produce a cited Markdown/JSON creative brief.
- `viral-angle-radar.xlsx` contains every required sheet and clickable source links.
- The static dashboard builds successfully and renders fixture data.
- GitHub Actions can run without paid-provider secrets in fixture mode.
- Missing credentials or provider failures are shown clearly and do not produce fabricated live results.

Begin now. First inspect the repository and any existing instructions. Then implement the MVP end-to-end.

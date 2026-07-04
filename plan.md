# plan.md — Future work

`SPEC.md` describes the system as built; this file tracks what comes next.
Updated 2026-07-04 after wiring the events collector to the Ticketmaster
Discovery API (key-gated; History now captures `event_count` and
`next_event_starts_at`, migration 0002).

## Next up

1. **PostGIS (only if needed).** `/nearby` uses a bounding-box prefilter +
   haversine, fine for hundreds of places. If OSM imports grow the table to
   thousands, swap to PostGIS — queries are already dialect-neutral.

## ML phase

Prerequisites before training anything: enough places (raise
`OSM_IMPORT_LIMIT` progressively) and **4–6 weeks of accumulated History**
with the raw signals now being captured (temperature, rain mm, traffic
speeds, event counts and dates, rating snapshots).

In order of feasibility:

1. **Activity forecasting** ("what time should I go on Saturday?"). Predict
   `activity_score` per place for the next hours/days. Features: hour of day,
   day of week, Colombian holiday flag (`holidays` library), History lags and
   rolling means, Open-Meteo weather *forecast* (free). Start with a non-ML
   baseline (average hourly profile per place), then
   `HistGradientBoostingRegressor` (scikit-learn — boring, no new infra).
   Expose as `GET /forecast/{place_id}` with the same graceful-degradation
   contract. Evaluate with MAE against the baseline before shipping.
2. **NLP on Google reviews.** Sentiment and "quiet/noisy/crowded" signal
   extraction with spaCy / sentence-transformers is technically viable, but
   Google Places ToS restricts storing review text — store only the derived
   per-place scores, never the text. Google "Popular Times" has no official
   API and is excluded.
3. **Learned blend weights & ML discovery ranking.** Replacing the fixed
   40/25/20/15 weights or the discovery heuristic needs ground truth (real
   crowd levels or user feedback), which does not exist yet. The enabler is
   already in place: every `/discover/*` request is logged with the
   recommended ids (`discover_request` events), so a learning-to-rank dataset
   can accumulate. Revisit once there is signal.
4. **Anomaly detection (optional).** Flag unusual days per place from History
   with simple statistics (rolling z-score) — useful and nearly free, no
   model required.

The engine stays pure (`engine/score.py`) precisely so any of these models can
replace a function without touching collectors, services or the API.

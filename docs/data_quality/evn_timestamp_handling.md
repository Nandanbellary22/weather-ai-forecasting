# EVN historical timestamp handling

## Current handling

- `requested_date` is the date queried from EVN.
- `observation_time_raw` preserves the timestamp text extracted from the source response.
- When a source timestamp has no year and its year cannot be interpreted reliably, keep `observation_timestamp` and inferred-year metadata null. Do not infer an observation year merely from `requested_date`.
- Preserve the extracted measurements and mark these records `quality_flag=ambiguous_year`.
- If the raw timestamp's month and day differ from `requested_date`, preserve the record and measurements and flag the discrepancy for review. Do not automatically classify it as `stale_previous_observation` without sufficient evidence about EVN's timestamp semantics.

These are conservative data-handling rules. They do not confirm how EVN assigns observation times or explain any particular timestamp discrepancy.

## Unresolved example

The Lai Châu recovery record for requested date `2024-02-27` has raw timestamp `26/02 23:00`, water level `293.21 m`, inflow `311 m³/s`, `quality_flag=ambiguous_year`, and `collection_status=success`. Keep its current values and quality flag unchanged. Its observation year and the meaning of the source timestamp remain unverified.

Other project records with prior-day timestamps have sometimes been classified as `stale_previous_observation`. That precedent does not establish the correct interpretation of this specific EVN response.

## Importer and schema

The existing importer stores `requested_date`, `observation_time_raw`, and nullable `observation_timestamp` separately. No importer or database-schema change is currently required for this handling decision.

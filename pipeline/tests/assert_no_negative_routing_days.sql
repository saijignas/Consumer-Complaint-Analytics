-- Singular test: a complaint can't be routed to the company before it
-- was received. A dbt test that FAILS (returns rows) if this ever
-- happens -- catches a real data-integrity issue, not a hypothetical one.

select complaint_id, date_received, date_sent_to_company
from {{ ref('stg_complaints') }}
where days_to_route < 0

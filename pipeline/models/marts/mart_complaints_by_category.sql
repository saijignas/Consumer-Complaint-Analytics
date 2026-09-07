-- One row per product category: volume, response timeliness, and
-- narrative length -- the metrics a support-ops team would actually
-- watch to decide where to add staffing or investigate root causes.

select
    product,
    count(*) as complaint_count,
    round(avg(narrative_length), 0) as avg_narrative_length,
    round(100.0 * sum(case when was_timely then 1 else 0 end) / count(*), 1) as pct_timely_response,
    round(avg(days_to_route), 1) as avg_days_to_route,
    count(distinct company) as distinct_companies
from {{ ref('stg_complaints') }}
group by product
order by complaint_count desc

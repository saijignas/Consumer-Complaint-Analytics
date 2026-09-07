-- How companies actually resolve complaints, and whether the resolution
-- type correlates with a timely response -- e.g. does "Closed with
-- monetary relief" take longer than "Closed with explanation"?

select
    company_response,
    count(*) as complaint_count,
    round(100.0 * sum(case when was_timely then 1 else 0 end) / count(*), 1) as pct_timely_response,
    round(avg(days_to_route), 1) as avg_days_to_route
from {{ ref('stg_complaints') }}
group by company_response
order by complaint_count desc

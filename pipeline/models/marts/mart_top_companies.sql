-- Companies with the most complaint volume (min 10 complaints to avoid
-- noisy percentages from a company with 1-2 complaints) and their
-- timely-response rate -- the "who to look at first" view.

select
    company,
    count(*) as complaint_count,
    round(100.0 * sum(case when was_timely then 1 else 0 end) / count(*), 1) as pct_timely_response,
    count(distinct product) as distinct_products
from {{ ref('stg_complaints') }}
group by company
having count(*) >= 10
order by complaint_count desc
limit 25

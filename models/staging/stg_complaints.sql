-- Staging: rename/type raw columns, and drop the two real data-quality
-- issues found in this data (see the sibling Consumer-Complaint-Triage
-- project's README for the full discussion): exact-duplicate/templated
-- narratives, and narratives too short to be a real complaint (a stray
-- "N/A" or similar after the free-text field's redaction).

with source as (
    select * from {{ source('raw', 'complaints') }}
),

renamed as (
    select
        complaint_id::bigint as complaint_id,
        product,
        sub_product,
        issue,
        sub_issue,
        company,
        state,
        -- DuckDB's %z wants a numeric offset (+00), not the literal "Z"
        -- these ISO8601 timestamps actually use, so it's swapped in first.
        strptime(replace(date_received, 'Z', '+00'), '%Y-%m-%dT%H:%M:%S.%f%z')::date as date_received,
        strptime(replace(date_sent_to_company, 'Z', '+00'), '%Y-%m-%dT%H:%M:%S.%f%z')::date as date_sent_to_company,
        company_response,
        (timely = 'Yes') as was_timely,
        submitted_via,
        trim(complaint_what_happened) as narrative,
        length(trim(complaint_what_happened)) as narrative_length
    from source
),

deduped as (
    select *,
        row_number() over (partition by narrative order by complaint_id) as narrative_occurrence
    from renamed
    where narrative_length >= 20
)

select
    complaint_id,
    product,
    sub_product,
    issue,
    sub_issue,
    company,
    state,
    date_received,
    date_sent_to_company,
    date_diff('day', date_received, date_sent_to_company) as days_to_route,
    company_response,
    was_timely,
    submitted_via,
    narrative,
    narrative_length
from deduped
where narrative_occurrence = 1  -- drop exact-duplicate/templated narratives, keep first occurrence

{#
    Parses a CFPB-format ISO8601 timestamp string (e.g.
    "2024-09-03T22:07:34.000Z") into a native timestamp, per-adapter.

    DuckDB's implicit VARCHAR -> TIMESTAMP cast doesn't accept the literal
    "Z" offset marker (it wants a numeric offset like "+00"), so on DuckDB
    it's swapped in first and parsed explicitly with strptime. BigQuery's
    TIMESTAMP() function accepts this exact canonical UTC format natively,
    with no massaging needed -- this is the actual reason a per-dialect
    macro exists here instead of one clever expression: the two engines
    genuinely differ, not just in syntax but in what they accept as valid
    input.
#}
{% macro parse_iso_timestamp(column) %}
    {% if target.type == 'bigquery' %}
        timestamp({{ column }})
    {% elif target.type == 'duckdb' %}
        strptime(replace({{ column }}, 'Z', '+00'), '%Y-%m-%dT%H:%M:%S.%f%z')
    {% else %}
        {{ exceptions.raise_compiler_error(
            "parse_iso_timestamp: no implementation for adapter '" ~ target.type ~ "'"
        ) }}
    {% endif %}
{% endmacro %}

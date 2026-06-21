CREATE OR REPLACE MACRO bars_asof_spine(p_as_of) AS TABLE (
    WITH base AS (
        SELECT
            s.security_id,
            s.effective_date,
            b.* EXCLUDE (security_id, effective_date),
            p.priority AS source_priority
        FROM _spine s
        ASOF LEFT JOIN lake_bars b
            ON s.security_id = b.security_id
           AND s.effective_date >= b.effective_date
           AND p_as_of::TIMESTAMPTZ >= b.available_at
        LEFT JOIN _kernel_source_priority p
            ON p.dataset = 'bars_daily' AND p.source_id = b.source_id
        WHERE b.effective_date <= p_as_of::DATE
    )
    SELECT security_id, effective_date,
           * EXCLUDE (security_id, effective_date, source_priority)
    FROM base
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY security_id, effective_date
        ORDER BY COALESCE(source_priority, 999), available_at DESC
    ) = 1
    ORDER BY security_id, effective_date
);

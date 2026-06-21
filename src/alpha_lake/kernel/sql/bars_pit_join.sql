CREATE OR REPLACE MACRO bars_asof_join() AS TABLE (
    WITH base AS (
        SELECT
            s.security_id,
            s.effective_date,
            s.as_of::TIMESTAMPTZ AS as_of,
            b.* EXCLUDE (security_id, effective_date),
            p.priority AS source_priority,
            ROW_NUMBER() OVER (
                PARTITION BY s.security_id, s.effective_date, s.as_of::TIMESTAMPTZ
                ORDER BY COALESCE(p.priority, 999), b.available_at DESC
            ) AS rn
        FROM _spine s
        LEFT JOIN lake_bars b
            ON s.security_id = b.security_id
           AND b.effective_date <= s.effective_date
           AND b.available_at <= s.as_of::TIMESTAMPTZ
        LEFT JOIN _kernel_source_priority p
            ON p.dataset = 'bars_daily' AND p.source_id = b.source_id
    )
    SELECT * EXCLUDE (source_priority, rn)
    FROM base
    WHERE rn = 1
    ORDER BY security_id, effective_date
);

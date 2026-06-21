CREATE OR REPLACE MACRO bars_asof(
    p_security_ids, p_as_of, p_start_date, p_end_date
) AS TABLE (
    WITH per_source AS (
        SELECT
            b.security_id,
            b.effective_date,
            b.available_at,
            b.source_id,
            b.* EXCLUDE (security_id, effective_date, available_at, source_id),
            ROW_NUMBER() OVER (
                PARTITION BY b.security_id, b.effective_date
                ORDER BY b.available_at DESC
            ) AS version_rank
        FROM lake_bars b
        WHERE list_contains(p_security_ids, b.security_id)
          AND b.available_at <= p_as_of::TIMESTAMPTZ
          AND b.effective_date <= p_as_of::DATE
          AND (p_start_date IS NULL OR b.effective_date >= p_start_date::DATE)
          AND (p_end_date IS NULL OR b.effective_date <= p_end_date::DATE)
    ),
    preferred AS (
        SELECT ps.*,
               p.priority AS source_priority
        FROM per_source ps
        LEFT JOIN _kernel_source_priority p
            ON p.dataset = 'bars_daily' AND p.source_id = ps.source_id
        WHERE ps.version_rank = 1
    )
    SELECT * EXCLUDE (version_rank, source_priority)
    FROM preferred
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY security_id, effective_date
        ORDER BY COALESCE(source_priority, 999), available_at DESC
    ) = 1
    ORDER BY security_id, effective_date
);

CREATE OR REPLACE MACRO bars_asof(
    p_security_ids, p_as_of, p_start_date, p_end_date
) AS TABLE (
    SELECT b.* EXCLUDE (source_priority_rank)
    FROM (
        SELECT b.*,
               ROW_NUMBER() OVER (
                   PARTITION BY b.security_id, b.effective_date
                   ORDER BY COALESCE(p.priority, 999), b.available_at DESC
               ) AS source_priority_rank
        FROM lake_bars b
        LEFT JOIN _kernel_source_priority p
            ON p.dataset = 'bars_daily' AND p.source_id = b.source_id
        WHERE list_contains(p_security_ids, b.security_id)
          AND b.available_at  <= p_as_of::TIMESTAMPTZ
          AND b.effective_date <= p_as_of::DATE
          AND (p_start_date IS NULL OR b.effective_date >= p_start_date::DATE)
          AND (p_end_date   IS NULL OR b.effective_date <= p_end_date::DATE)
    ) b
    WHERE source_priority_rank = 1
    ORDER BY b.security_id, b.effective_date
);

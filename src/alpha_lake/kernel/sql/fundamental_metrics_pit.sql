CREATE OR REPLACE MACRO fundamental_metrics_asof(
    p_security_ids, p_as_of, p_categories, p_metric_ids
) AS TABLE (
    SELECT m.* EXCLUDE (source_priority_rank)
    FROM (
        SELECT m.*,
               ROW_NUMBER() OVER (
                   PARTITION BY m.security_id, m.metric_id
                   ORDER BY m.period_end DESC, COALESCE(p.priority, 999), m.available_at DESC
               ) AS source_priority_rank
        FROM fundamental_metrics m
        LEFT JOIN _kernel_source_priority p
            ON p.dataset = 'fundamental_metrics' AND p.source_id = m.source_id
        WHERE list_contains(p_security_ids, m.security_id)
          AND m.available_at <= p_as_of::TIMESTAMPTZ
          AND m.period_end <= p_as_of::DATE
          AND (p_categories IS NULL OR list_contains(p_categories, m.category))
          AND (p_metric_ids IS NULL OR list_contains(p_metric_ids, m.metric_id))
    ) m
    WHERE source_priority_rank = 1
    ORDER BY m.security_id, m.category, m.metric_id
);

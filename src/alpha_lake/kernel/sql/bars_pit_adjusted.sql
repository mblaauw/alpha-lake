CREATE OR REPLACE MACRO bars_adjusted_asof(
    p_security_ids, p_as_of, p_start_date, p_end_date
) AS TABLE (
    WITH bars AS (
        SELECT *
        FROM bars_asof(p_security_ids, p_as_of, p_start_date, p_end_date)
    ),
    factors AS (
        SELECT
            ca.security_id,
            EXP(SUM(LN(ca.ratio_numerator / NULLIF(ca.ratio_denominator, 0)))
                OVER (PARTITION BY ca.security_id ORDER BY ca.effective_date
                      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
            ) AS cumulative_factor
        FROM corp_actions ca
        WHERE ca.action_type = 'split'
          AND ca.available_at <= p_as_of::TIMESTAMPTZ
    ),
    latest_factor AS (
        SELECT security_id, MAX(cumulative_factor) AS factor
        FROM factors
        GROUP BY security_id
    )
    SELECT
        b.security_id,
        b.effective_date,
        b.available_at,
        b.source_id,
        round(b.open   / COALESCE(lf.factor, 1.0), 4) AS open,
        round(b.high   / COALESCE(lf.factor, 1.0), 4) AS high,
        round(b.low    / COALESCE(lf.factor, 1.0), 4) AS low,
        round(b.close  / COALESCE(lf.factor, 1.0), 4) AS close,
        CAST(round(b.volume * COALESCE(lf.factor, 1.0), 0) AS BIGINT) AS volume,
        b.version_hash,
        b.quality_status,
        COALESCE(lf.factor, 1.0) AS adjustment_factor
    FROM bars b
    LEFT JOIN latest_factor lf ON lf.security_id = b.security_id
    ORDER BY b.security_id, b.effective_date
);

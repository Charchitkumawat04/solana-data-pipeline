-- Daily swaps and unique traders per DEX
SELECT block_date, program_source,
       COUNT(*)                  AS swaps,
       COUNT(DISTINCT fee_payer) AS traders,
       ROUND(AVG(fee_sol), 6)    AS avg_fee_sol
FROM solana_swaps
WHERE success
GROUP BY 1, 2 ORDER BY 1 DESC, 3 DESC;

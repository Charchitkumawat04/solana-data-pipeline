-- Top traded pairs in the last 7 days (direction matters: sol/usdc != usdc/sol)
SELECT token_sold_symbol || '/' || token_bought_symbol AS pair,
       COUNT(*)                                        AS swaps,
       COUNT(DISTINCT fee_payer)                       AS traders,
       ROUND(SUM(token_sold_amount), 2)                AS volume_sold_units
FROM solana_swaps
WHERE success AND block_date >= CURRENT_DATE - INTERVAL 7 DAY
GROUP BY 1 ORDER BY 2 DESC LIMIT 20;

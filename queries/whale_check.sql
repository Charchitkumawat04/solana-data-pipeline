-- Mean vs median per trader: a big gap means a few wallets carry the volume
WITH per_trader AS (
  SELECT fee_payer, SUM(token_sold_amount) AS vol, COUNT(*) AS n
  FROM solana_swaps WHERE success AND token_sold_symbol IN ('USDC','USDT')
  GROUP BY 1
)
SELECT COUNT(*) traders,
       ROUND(AVG(vol), 2)                 AS mean_vol,
       ROUND(MEDIAN(vol), 2)              AS median_vol,
       ROUND(AVG(vol) / MEDIAN(vol), 1)   AS mean_to_median,
       ROUND(MAX(vol), 2)                 AS biggest_trader
FROM per_trader;

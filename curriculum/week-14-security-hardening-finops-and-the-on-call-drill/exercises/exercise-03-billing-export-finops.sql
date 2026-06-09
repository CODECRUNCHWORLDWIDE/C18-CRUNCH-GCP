-- Exercise 3 — Billing-export FinOps analysis
--
-- Goal: query a Cloud Billing export in BigQuery to (1) find the top three line
--       items by EFFECTIVE cost (list cost minus credits), and (2) quantify a
--       committed-use saving on the largest steady-state line item. By the end
--       you can defend, with a query and a number, the claim "our top three
--       SKUs are X/Y/Z and committing the Spanner/Compute floor saves $N/year."
--
-- Estimated time: 60 minutes.
--
-- HOW TO USE THIS FILE
--
--   * If your billing export EXISTS and has populated (enabled >= 24h ago):
--       set the table name in the `params` CTE below and run sections A–D against
--       it. The real table is named:
--         <project>.<dataset>.gcp_billing_export_v1_<ACCOUNT_WITH_UNDERSCORES>
--
--   * If your export has NOT populated yet (you enabled it Monday and it is now
--       Tuesday), run SECTION 0 first. It builds a small synthetic billing table
--       `finops_demo.billing` shaped exactly like the real export, so every later
--       section runs unchanged. Swap the table reference in sections A–D to
--       `finops_demo.billing` and the queries are identical.
--
-- Run sections in order with the BigQuery console or `bq query --use_legacy_sql=false`.
--
-- ACCEPTANCE CRITERIA
--   [ ] Section A returns the top 3 SKUs by effective 30-day cost, in dollars.
--   [ ] Section B shows the credit-adjusted ("effective") cost differs from list.
--   [ ] Section C computes a committed-use saving for one steady line item.
--   [ ] Section D outputs the breakeven utilization for that commitment.
--   [ ] You can name the top three SKUs and the proposed saving out loud.


-- ===========================================================================
-- SECTION 0 — synthetic billing table (run ONLY if your real export is empty)
-- ===========================================================================
-- Creates finops_demo.billing with the same schema shape as the real export:
-- a `service` STRUCT, a `sku` STRUCT, a numeric `cost`, and a REPEATED `credits`
-- STRUCT array. The real export has many more columns; these are the ones the
-- analysis needs.

CREATE SCHEMA IF NOT EXISTS finops_demo
OPTIONS (location = 'US');

CREATE OR REPLACE TABLE finops_demo.billing AS
SELECT
  STRUCT(svc AS description) AS service,
  STRUCT(sku AS description)  AS sku,
  cost,
  -- credits is a REPEATED field of STRUCT(amount FLOAT64, name STRING, type STRING)
  credits,
  usage_start_time
FROM UNNEST([
  -- (service, sku, daily_cost, credit_amount, usage_day_offset)
  STRUCT('Cloud Spanner'  AS svc, 'Spanner Node (us-central1)'           AS sku, 28.80 AS cost, [STRUCT(-2.00 AS amount, 'committed-use' AS name, 'COMMITTED_USAGE_DISCOUNT' AS type)] AS credits, TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 5 DAY) AS usage_start_time),
  STRUCT('Compute Engine',         'N2 Instance Core running in Americas',        21.50, [STRUCT(-6.45, 'sustained-use', 'SUSTAINED_USAGE_DISCOUNT')], TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 5 DAY)),
  STRUCT('Compute Engine',         'N2 Instance Ram running in Americas',          8.90, [STRUCT(-2.67, 'sustained-use', 'SUSTAINED_USAGE_DISCOUNT')], TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 5 DAY)),
  STRUCT('BigQuery',               'Analysis (on-demand) (US)',                   14.20, CAST([] AS ARRAY<STRUCT<amount FLOAT64, name STRING, type STRING>>), TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 5 DAY)),
  STRUCT('BigQuery',               'Active Storage (US)',                          3.10, CAST([] AS ARRAY<STRUCT<amount FLOAT64, name STRING, type STRING>>), TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 5 DAY)),
  STRUCT('Cloud Run',              'CPU Allocation Time (us-central1)',            5.40, CAST([] AS ARRAY<STRUCT<amount FLOAT64, name STRING, type STRING>>), TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 5 DAY)),
  STRUCT('Networking',             'Network Inter Region Egress (Americas)',       1.80, CAST([] AS ARRAY<STRUCT<amount FLOAT64, name STRING, type STRING>>), TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 5 DAY)),
  STRUCT('Cloud Storage',          'Standard Storage US Multi-region',             0.90, CAST([] AS ARRAY<STRUCT<amount FLOAT64, name STRING, type STRING>>), TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 5 DAY))
])
-- multiply each row across 30 days so the 30-day window has data
CROSS JOIN UNNEST(GENERATE_ARRAY(0, 29)) AS day_offset;
-- NOTE: the cross join replays each SKU's daily cost for 30 days. The synthetic
-- numbers are illustrative; the SHAPE matches the real export so the analysis
-- transfers unchanged.


-- ===========================================================================
-- SECTION A — top 3 line items by EFFECTIVE 30-day cost
-- ===========================================================================
-- Effective cost = list cost + credits (credits are negative). Reporting list
-- cost alone overstates the bill by discounts you already earned.
-- Swap `finops_demo.billing` for your real export table if you have one.

SELECT
  service.description AS service,
  sku.description     AS sku,
  ROUND(SUM(cost), 2) AS list_cost_usd,
  ROUND(
    SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)),
    2
  ) AS effective_cost_usd
FROM finops_demo.billing
WHERE usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
GROUP BY service, sku
ORDER BY effective_cost_usd DESC
LIMIT 3;
-- Expected (synthetic): Spanner node, then N2 Instance Core, then BigQuery
-- on-demand analysis are the top three. THOSE are what you attack.


-- ===========================================================================
-- SECTION B — list vs. effective, to show the credit you already earn
-- ===========================================================================
-- This proves the §2.1 lecture point: the discount instruments already in play
-- (sustained-use, existing CUDs) are visible in the credits field. Do not
-- propose a CUD on a line that is already mostly credited.

SELECT
  service.description AS service,
  ROUND(SUM(cost), 2) AS list_cost_usd,
  ROUND(SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)), 2)
    AS credits_usd,
  ROUND(
    SAFE_DIVIDE(
      -SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)),
      SUM(cost)
    ) * 100, 1
  ) AS pct_already_discounted
FROM finops_demo.billing
WHERE usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
GROUP BY service
ORDER BY list_cost_usd DESC;


-- ===========================================================================
-- SECTION C — quantify a committed-use saving on the steady-state floor
-- ===========================================================================
-- Take the largest STEADY line item (here: the Spanner node, which never goes
-- to zero) and model committing it for 1 year. We compare:
--   * on-demand: pay list cost minus the small SUD-style credits you get today
--   * committed: a 1-year CUD at ~37% off the on-demand RATE, paid every hour
-- The saving is real ONLY if utilization stays above the breakeven (Section D).

WITH steady AS (
  SELECT
    sku.description AS sku,
    -- effective monthly cost extrapolated from the 30-day window
    SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0))
      AS effective_30d_usd
  FROM finops_demo.billing
  WHERE usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
    AND sku.description = 'Spanner Node (us-central1)'  -- pick YOUR steady line
  GROUP BY sku
)
SELECT
  sku,
  ROUND(effective_30d_usd, 2)              AS effective_monthly_usd,
  ROUND(effective_30d_usd * 12, 2)         AS effective_annual_ondemand_usd,
  -- 1-year resource-based CUD on Spanner is ~37% off (CONFIRM on the pricing
  -- page — this number is illustrative and dated).
  ROUND(effective_30d_usd * 12 * (1 - 0.37), 2) AS committed_annual_usd,
  ROUND(effective_30d_usd * 12 * 0.37, 2)  AS estimated_annual_saving_usd
FROM steady;
-- The `estimated_annual_saving_usd` is the headline number for the FinOps memo.


-- ===========================================================================
-- SECTION D — breakeven utilization for the proposed commitment
-- ===========================================================================
-- A commitment is paid every hour whether or not you use it. It only saves if
-- your utilization floor exceeds the breakeven. With a 37%-off CUD, you pay 63%
-- of the on-demand rate UP FRONT for the term, so you break even at 63%
-- utilization. Above your demonstrated floor => commit. Below => do NOT.

SELECT
  0.37                       AS cud_discount,
  1 - 0.37                   AS committed_rate_fraction,
  ROUND((1 - 0.37) * 100, 1) AS breakeven_utilization_pct,
  -- Plug in YOUR demonstrated utilization floor (the lowest the Spanner node
  -- usage dropped over the window). If it is above breakeven, commit.
  'commit only if demonstrated floor >= breakeven_utilization_pct'
    AS decision_rule;


-- ===========================================================================
-- TEARDOWN — drop the synthetic dataset when done (skip if you used the real one)
-- ===========================================================================
-- DROP SCHEMA IF EXISTS finops_demo CASCADE;


-- ===========================================================================
-- REFLECTION (answer in a comment or notes file after running):
--
-- 1. Section B shows Compute Engine is already ~30% discounted via credits.
--    Why is proposing a Compute CUD on top of that less impactful than a CUD on
--    the Spanner node, which had only a small credit?
-- 2. Section A used EFFECTIVE cost, not list. If you ranked by list cost
--    instead, which line item would move, and why would that mislead the memo?
-- 3. Section D's breakeven is 63%. Your Spanner node runs 24/7 (100% floor).
--    Commit or not? Now suppose you plan to migrate it to AlloyDB in 6 months.
--    Does that change the answer for a 1-year commitment? For a 3-year one?
-- 4. BigQuery on-demand analysis was a top-three line. The CUD instruments do
--    not apply to on-demand BigQuery. What is the right move for that line
--    instead (hint: slot reservations / editions), and how would you size it?
-- ===========================================================================

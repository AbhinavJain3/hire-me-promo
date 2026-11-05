---
name: holdout-report
description: Compute incremental lift vs holdout for a HireMe playbook or campaign by city and period, with 95% CI, incremental rides, promo cost and ROI, optionally compared with synthetic ground truth. Use for questions like "did B2 work?" and for gate evidence.
---
# Holdout lift report

Inputs: playbook_id (or campaign_id), city_id, from and to dates (IST), compare_truth (true/false).

1. Use sql/marts/holdout_lift.sql with parameters; dry run first and report bytes.
2. Analysis is intention-to-treat on the assigned arm (treatment + exploration vs holdout), with the attribution window configured on the playbook.
3. Report:
   - n_treat, n_hold
   - conversion rate per arm
   - lift in percentage points with Newcombe 95% CI
   - incremental rides, incremental fare value, promo cost, ROI
   - "insufficient sample" if either arm has fewer than 400 decisions
4. If compare_truth is true (synthetic data only): compute the true lift from engage_sim for the same decisions and state whether it lies inside the CI.

For complex variations delegate to the bigquery-analyst agent.

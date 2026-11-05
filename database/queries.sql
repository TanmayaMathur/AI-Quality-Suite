-- Bind :key to a compatible evaluation_runs.comparison_key.
-- 1. Quality across commits
SELECT r.timestamp, r.git_sha, r.model, r.prompt_version, m.framework, m.metric, m.version,
       COUNT(m.score) AS scored, AVG(m.score) AS mean_score
FROM evaluation_runs r JOIN metric_results m USING (run_id)
WHERE r.comparison_key = :key
GROUP BY r.run_id, m.framework, m.metric, m.version ORDER BY r.timestamp;

-- 2. Lowest-scoring cases (positive metrics only)
SELECT case_id, framework, metric, version, COUNT(score) AS scored, AVG(score) AS mean_score
FROM metric_results JOIN evaluation_runs USING (run_id)
WHERE comparison_key = :key AND status = 'scored' AND metric <> 'hallucination'
GROUP BY case_id, framework, metric, version ORDER BY mean_score, case_id LIMIT 20;

-- 3. Regressions against the selected approved baseline
SELECT case_id, metric, baseline_run_id, baseline_score, current_score, deterioration
FROM regression_results WHERE run_id = :run_id ORDER BY deterioration DESC;

-- 4. Hallucination trial rate and sample count
SELECT r.run_id, r.timestamp, COUNT(m.score) AS evaluated,
       AVG(m.score > json_extract(r.run_json, '$.summary.hallucination_cutoff')) AS rate
FROM evaluation_runs r LEFT JOIN metric_results m
  ON r.run_id = m.run_id AND m.framework = 'deepeval' AND m.metric = 'hallucination'
WHERE r.comparison_key = :key GROUP BY r.run_id ORDER BY r.timestamp;

-- 5. Nearest-rank p95 for executed requests
WITH ranked AS (
    SELECT run_id, latency_ms, ROW_NUMBER() OVER (PARTITION BY run_id ORDER BY latency_ms) AS rank,
           COUNT(*) OVER (PARTITION BY run_id) AS n
    FROM performance_results
)
SELECT r.timestamp, r.run_id, p.latency_ms AS p95_ms, p.n AS requests
FROM ranked p JOIN evaluation_runs r USING (run_id)
WHERE r.comparison_key = :key AND rank = (95 * n + 99) / 100 ORDER BY r.timestamp;

-- 6. Safety categories with failures and leak counts
SELECT c.category, COUNT(s.passed) AS evaluated, SUM(s.passed = 0) AS failures,
       SUM(c.status = 'error') AS execution_errors, SUM(s.leaked) AS leaks
FROM evaluation_cases c JOIN evaluation_runs r USING (run_id)
LEFT JOIN safety_results s USING (run_id, case_id, repetition)
WHERE r.comparison_key = :key AND c.case_id LIKE 'S%'
GROUP BY c.category ORDER BY failures DESC;

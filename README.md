# jev-demo1

Two demos of **Jev** (TypeSafe AI) on SprintPulse QA data. Both send the same per-ticket QA signals to Jev's System One API and use a different question type:

| | Use case 1: Release risk scoring | Use case 2: Risk cause diagnosis |
|---|---|---|
| Question | *How risky is this release item?* | *What is the main thing driving the risk?* |
| Jev primitive | `score` (10-level rubric) | `choice` (9 labeled causes) |
| Script | `release_risk_scorer.py` | `what_causing_the_risk.py` |
| Output | `sprint_results.csv` | `sprintpulse_risk_cause_results.csv`, `sprintpulse_risk_cause_summary.csv` |
| Evaluated against | Reference `risk_score_10` in the dataset | No ground truth, so it is exploratory |

Together they answer "how risky" and "why".

## Input data

`sprintpulse_qa_quality_metrics.csv` has 70 synthetic tickets with these columns: `ticket_id`, `sprint`, `module`, `ticket_type`, `severity`, `priority`, `test_cases`, `automated_test_cases`, `automation_coverage_pct`, `defects_found`, `escaped_defects`, `avg_resolution_hours`, `reopen_count`, `blocked_days`, `story_points`, `qa_owner`, `risk_score_10`, `release_readiness`.

Each script sends the same `state` to Jev: the QA signals above, **excluding** `qa_owner`, `risk_score_10` and `release_readiness`. The two reference labels are never sent. They are used afterwards, for scoring only.

`qa_metrics.csv` is the same data without the labels. Neither script uses it.

## Use case 1: Release risk scoring

`release_risk_scorer.py` asks Jev to rate each ticket on a 1–10 risk rubric (1 = negligible, 10 = extreme). Jev returns a fractional score and a confidence value.

- **Scale:** Jev scores are zero-indexed, so the 10 levels come back as 0–9. The script adds 1 to put predictions on the 1–10 scale of the reference.
- **Metrics printed:** Mean Absolute Error, share of predictions within ±1 and ±2 points, the 10 highest-risk tickets, and a count of tickets scored versus failed.
- **Output:** `sprint_results.csv` with reference score, Jev score, absolute error, confidence and reference readiness per ticket.

Result from the latest run (70 of 70 tickets scored):

| Metric | Value |
|---|---|
| Mean Absolute Error | 0.95 |
| Within ±1 point | 67.1% |
| Within ±2 points | 90.0% |
| Mean confidence | 0.76 |
| Average bias (Jev minus reference) | −0.77 (Jev scores lower) |

Higher confidence goes with lower error (correlation −0.32), so confidence is a usable signal for flagging tickets to review.

## Use case 2: Risk cause diagnosis

`what_causing_the_risk.py` asks Jev to pick the primary driver of risk for each ticket from nine labels: `high_severity`, `low_automation_coverage`, `high_defect_count`, `escaped_defects`, `slow_resolution`, `reopened_defects`, `blocked_dependency`, `high_complexity` and `no_significant_risk`.

For each ticket it records the top two causes with their probabilities and Jev's confidence. It then prints:

- The distribution of primary risk drivers across all tickets
- A cross-tab of risk drivers by module
- Low-confidence tickets (confidence below 0.60) for human review

Outputs: `sprintpulse_risk_cause_results.csv` (per ticket) and `sprintpulse_risk_cause_summary.csv` (counts and percentages).

Result from the latest run:

| Primary risk driver | Tickets | Share |
|---|---|---|
| high_severity | 23 | 32.9% |
| low_automation_coverage | 13 | 18.6% |
| no_significant_risk | 12 | 17.1% |
| high_defect_count | 10 | 14.3% |
| escaped_defects | 10 | 14.3% |
| reopened_defects | 2 | 2.9% |

The dataset has no labeled cause, so there is no accuracy figure here. The output shows what Jev picks and how sure it is. Probabilities matter here: some tickets are close calls. For example, `SP-2001` is `high_defect_count` at 0.49 against `high_severity` at 0.43, with confidence 0.42.

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

Create a `.env` file with your key:

```
TYPESAFE_API_KEY=your-key-here
```

`.env` holds a secret, so keep it out of version control.

## Run

```bash
uv run release_risk_scorer.py     # use case 1
uv run what_causing_the_risk.py   # use case 2
```

Both scripts print per-ticket progress, skip failed API calls, and write CSVs to the project folder.

## Files

| File | Purpose |
|------|---------|
| `release_risk_scorer.py` | Use case 1: release risk score |
| `what_causing_the_risk.py` | Use case 2: primary risk cause |
| `sprintpulse_qa_quality_metrics.csv` | Input data with reference labels |
| `qa_metrics.csv` | Same data without labels (unused) |
| `sprint_results.csv` | Use case 1 output |
| `sprintpulse_risk_cause_results.csv` | Use case 2 per-ticket output |
| `sprintpulse_risk_cause_summary.csv` | Use case 2 driver counts |
| `main.py` | Placeholder, unused |

## Limitations

- The dataset is synthetic. The reference scores were not produced by real release outcomes, so use case 1 shows agreement with a rubric, not predictive accuracy on real releases.
- There is no baseline model in the repo, so MAE 0.95 can't yet be compared with a simple regression or weighted rule.
- 70 tickets is a small sample.
- Use case 2 has no labeled cause to check against.

import os
import time
import pandas as pd
import requests
from dotenv import load_dotenv
load_dotenv()

# ============================================================
# CONFIG
# ============================================================

INPUT_FILE = "sprintpulse_qa_quality_metrics.csv"
OUTPUT_FILE = "sprint_results.csv"

JEV_API_URL = "https://api.typesafe.ai/v1/systemone"
JEV_API_KEY = os.getenv("TYPESAFE_API_KEY")


if not JEV_API_KEY:
    raise ValueError(
        "TYPESAFE_API_KEY is not configured.\n"
        "Please set the environment variable with your API key."
    )


# ============================================================
# JEV QUESTION
# ============================================================

risk_question = {
    "type": "score",
    "instructions": """
Assess the overall release risk of this release work item.

Consider the evidence together rather than treating any single field
as an automatic decision.

Important signals include:
- severity
- priority
- automation coverage
- number of defects found
- escaped defects
- average defect resolution time
- defect reopen count
- blocked days
- story complexity

Higher severity, escaped defects, repeated reopening, long blocking,
low automation coverage, high defect volume and slow resolution
generally indicate higher release risk.

Return the level that best represents the overall risk of releasing
this item.
""",
    "criteria": [
        "1 - Negligible risk. Well tested, stable and no meaningful release concerns.",
        "2 - Very low risk. Minor concerns with strong testing evidence.",
        "3 - Low risk. Some small issues exist but release confidence remains high.",
        "4 - Moderate-low risk. Noticeable concerns that should be monitored.",
        "5 - Moderate risk. Multiple risk indicators exist and additional review may be useful.",
        "6 - Elevated risk. Significant concerns exist and release deserves careful review.",
        "7 - High risk. Strong evidence of release instability or insufficient quality confidence.",
        "8 - Very high risk. Multiple serious quality signals indicate substantial release danger.",
        "9 - Critical risk. Severe defects, escape patterns, blockers or instability strongly threaten release.",
        "10 - Extreme risk. Release should be considered highly unsafe based on the available evidence."
    ]
}


# ============================================================
# JEV CALL
# ============================================================

def score_release_risk(row):
    """
    Send one QA ticket to Jev and return the release-risk score.
    """

    # IMPORTANT:
    # We have intentionally excluded:
    # risk_score_10
    # release_readiness
    #
    # because these are our reference / ground-truth fields.

    state = {
        "ticket_id": row["ticket_id"],
        "sprint": row["sprint"],
        "module": row["module"],
        "ticket_type": row["ticket_type"],
        "severity": row["severity"],
        "priority": row["priority"],

        "test_cases": int(row["test_cases"]),
        "automated_test_cases": int(row["automated_test_cases"]),
        "automation_coverage_pct": float(row["automation_coverage_pct"]),

        "defects_found": int(row["defects_found"]),
        "escaped_defects": int(row["escaped_defects"]),

        "avg_resolution_hours": float(row["avg_resolution_hours"]),
        "reopen_count": int(row["reopen_count"]),
        "blocked_days": int(row["blocked_days"]),

        "story_points": int(row["story_points"])
    }

    payload = {
        "model": "jev-latest",
        "state": state,
        "questions": {
            "release_risk": risk_question
        }
    }

    headers = {
        "Authorization": f"Bearer {JEV_API_KEY}",
        "Content-Type": "application/json"
    }

    response = requests.post(
        JEV_API_URL,
        headers=headers,
        json=payload,
        timeout=60
    )

    response.raise_for_status()

    data = response.json()

    answer = data["answers"]["release_risk"]

    # Jev scores are zero-indexed (criteria position 0 = "1 - Negligible"),
    # so shift by +1 to match the 1-10 reference scale. The score is a
    # probability-weighted average, so fractional values stay valid.
    return {
        "jev_risk_score": answer["score"] + 1,
        "jev_confidence": answer.get("confidence"),
        "jev_probabilities": answer.get("probabilities"),
        "jev_model": data.get("model")
    }


# ============================================================
# LOAD DATA
# ============================================================

df = pd.read_csv(INPUT_FILE)

print(f"Loaded {len(df)} SprintPulse records")


# ============================================================
# RUN JEV
# ============================================================

results = []
failed = 0

for index, row in df.iterrows():

    print(
        f"[{index + 1}/{len(df)}] "
        f"Scoring {row['ticket_id']}..."
    )

    try:

        jev_result = score_release_risk(row)

        actual_score = float(row["risk_score_10"])
        predicted_score = float(jev_result["jev_risk_score"])

        absolute_error = abs(predicted_score - actual_score)

        results.append({
            "ticket_id": row["ticket_id"],
            "module": row["module"],
            "severity": row["severity"],

            # Reference value from synthetic dataset
            "reference_risk_score": actual_score,

            # Jev prediction
            "jev_risk_score": round(predicted_score, 2),

            # Difference
            "absolute_error": round(absolute_error, 2),

            "jev_confidence": jev_result["jev_confidence"],

            # Original label — NOT sent to Jev
            "reference_release_readiness":
                row["release_readiness"]
        })

        time.sleep(0.2)

    except Exception as e:

        failed += 1
        print(
            f"Error processing {row['ticket_id']}: {e}"
        )


# ============================================================
# RESULTS DATAFRAME
# ============================================================

results_df = pd.DataFrame(results)

print(f"\nScored {len(results_df)} of {len(df)} tickets ({failed} failed)")

if results_df.empty:
    raise SystemExit("No tickets were scored successfully; see errors above.")


# ============================================================
# EVALUATION METRICS
# ============================================================

MAE = results_df["absolute_error"].mean()

within_1 = (
    results_df["absolute_error"] <= 1
).mean() * 100

within_2 = (
    results_df["absolute_error"] <= 2
).mean() * 100


print("\n======================================")
print("        JEV RELEASE RISK RESULTS")
print("======================================")

print(
    f"Mean Absolute Error: {MAE:.2f}"
)

print(
    f"Predictions within ±1 point: "
    f"{within_1:.1f}%"
)

print(
    f"Predictions within ±2 points: "
    f"{within_2:.1f}%"
)


# ============================================================
# SHOW HIGHEST RISK ITEMS
# ============================================================

print("\nTop 10 highest-risk tickets according to Jev:\n")

top_risk = (
    results_df
    .sort_values(
        "jev_risk_score",
        ascending=False
    )
    .head(10)
)

print(
    top_risk[
        [
            "ticket_id",
            "module",
            "severity",
            "jev_risk_score",
            "reference_risk_score",
            "absolute_error"
        ]
    ].to_string(index=False)
)


# ============================================================
# SAVE OUTPUT
# ============================================================

results_df.to_csv(
    OUTPUT_FILE,
    index=False
)

print(
    f"\nResults saved to: {OUTPUT_FILE}"
)
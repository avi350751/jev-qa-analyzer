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
OUTPUT_FILE = "sprintpulse_risk_cause_results.csv"

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

risk_cause_question = {
    "type": "choice",

    "instructions": """
Identify the PRIMARY factor contributing to release risk for this
software work item.

Choose only the strongest risk driver based on the supplied QA metrics.

Consider the relationship between severity, automation coverage,
defect count, escaped defects, defect resolution time, reopened defects,
blocked days and work complexity.

Select No Significant Risk only when none of the supplied metrics
represents a meaningful release concern.
""",

    "criteria": {

        "high_severity":
            "High or Critical severity is the dominant source of release risk.",

        "low_automation_coverage":
            "Insufficient automated test coverage is the dominant source of risk.",

        "high_defect_count":
            "A high number of defects found indicates instability and is the dominant risk.",

        "escaped_defects":
            "Defects have escaped the expected QA process and this is the dominant risk.",

        "slow_resolution":
            "Long average defect resolution time is the dominant source of risk.",

        "reopened_defects":
            "Repeated reopening of defects suggests unstable fixes and is the dominant risk.",

        "blocked_dependency":
            "Blocked days or unresolved dependencies are the dominant source of risk.",

        "high_complexity":
            "High story complexity or implementation size is the dominant source of risk.",

        "no_significant_risk":
            "No individual QA signal represents a meaningful release concern."
    }
}


# ============================================================
# CALL JEV
# ============================================================

def identify_risk_cause(row):

    state = {
        "ticket_id": row["ticket_id"],
        "sprint": row["sprint"],
        "module": row["module"],
        "ticket_type": row["ticket_type"],
        "severity": row["severity"],
        "priority": row["priority"],

        "test_cases": int(row["test_cases"]),
        "automated_test_cases": int(row["automated_test_cases"]),
        "automation_coverage_pct":
            float(row["automation_coverage_pct"]),

        "defects_found":
            int(row["defects_found"]),

        "escaped_defects":
            int(row["escaped_defects"]),

        "avg_resolution_hours":
            float(row["avg_resolution_hours"]),

        "reopen_count":
            int(row["reopen_count"]),

        "blocked_days":
            int(row["blocked_days"]),

        "story_points":
            int(row["story_points"])
    }

    payload = {
        "model": "jev-latest",

        "state": state,

        "questions": {
            "primary_risk_cause":
                risk_cause_question
        }
    }

    headers = {
        "Authorization":
            f"Bearer {JEV_API_KEY}",

        "Content-Type":
            "application/json"
    }

    response = requests.post(
        JEV_API_URL,
        headers=headers,
        json=payload,
        timeout=60
    )

    response.raise_for_status()

    data = response.json()

    answer = (
        data["answers"]
        ["primary_risk_cause"]
    )

    return {
        "primary_risk_cause":
            answer["choice"],

        "confidence":
            answer["confidence"],

        "probabilities":
            answer["probabilities"]
    }


# ============================================================
# LOAD DATA
# ============================================================

df = pd.read_csv(INPUT_FILE)

print(
    f"Loaded {len(df)} SprintPulse tickets"
)


# ============================================================
# PROCESS RECORDS
# ============================================================

results = []

for index, row in df.iterrows():

    print(
        f"[{index + 1}/{len(df)}] "
        f"Analyzing {row['ticket_id']}..."
    )

    try:

        jev_result = identify_risk_cause(row)

        probabilities = (
            jev_result["probabilities"]
        )

        # Sort probabilities so we can also show
        # Jev's second-most likely explanation.
        ranked = sorted(
            probabilities.items(),
            key=lambda x: x[1],
            reverse=True
        )

        primary = ranked[0]

        secondary = (
            ranked[1]
            if len(ranked) > 1
            else ("N/A", 0)
        )

        results.append({

            "ticket_id":
                row["ticket_id"],

            "sprint":
                row["sprint"],

            "module":
                row["module"],

            "severity":
                row["severity"],

            "automation_coverage_pct":
                row["automation_coverage_pct"],

            "defects_found":
                row["defects_found"],

            "escaped_defects":
                row["escaped_defects"],

            "reopen_count":
                row["reopen_count"],

            "blocked_days":
                row["blocked_days"],

            # JEV OUTPUT

            "primary_risk_cause":
                primary[0],

            "primary_probability":
                round(primary[1], 3),

            "secondary_risk_cause":
                secondary[0],

            "secondary_probability":
                round(secondary[1], 3),

            "jev_confidence":
                round(
                    jev_result["confidence"],
                    3
                )
        })

        time.sleep(0.2)

    except Exception as e:

        print(
            f"Error processing "
            f"{row['ticket_id']}: {e}"
        )


# ============================================================
# RESULTS
# ============================================================

results_df = pd.DataFrame(results)


# ============================================================
# RISK-CAUSE DISTRIBUTION
# ============================================================

risk_summary = (
    results_df[
        "primary_risk_cause"
    ]
    .value_counts()
    .reset_index()
)

risk_summary.columns = [
    "risk_cause",
    "ticket_count"
]

risk_summary["percentage"] = (
    risk_summary["ticket_count"]
    / len(results_df)
    * 100
).round(1)


print("\n")
print("=" * 60)
print("PRIMARY RELEASE-RISK DRIVERS")
print("=" * 60)

print(
    risk_summary.to_string(
        index=False
    )
)


# ============================================================
# MODULE-LEVEL RISK ANALYSIS
# ============================================================

module_risk = pd.crosstab(
    results_df["module"],
    results_df["primary_risk_cause"]
)

print("\n")
print("=" * 60)
print("RISK DRIVERS BY MODULE")
print("=" * 60)

print(module_risk)


# ============================================================
# LOW-CONFIDENCE CASES
# ============================================================

uncertain = (
    results_df[
        results_df[
            "jev_confidence"
        ] < 0.60
    ]
    .sort_values(
        "jev_confidence"
    )
)


print("\n")
print("=" * 60)
print("LOW CONFIDENCE — HUMAN REVIEW")
print("=" * 60)

if len(uncertain) == 0:

    print(
        "No low-confidence records."
    )

else:

    print(
        uncertain[
            [
                "ticket_id",
                "module",
                "primary_risk_cause",
                "primary_probability",
                "secondary_risk_cause",
                "secondary_probability",
                "jev_confidence"
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

risk_summary.to_csv(
    "sprintpulse_risk_cause_summary.csv",
    index=False
)


print("\n")
print(
    f"Detailed output saved to: "
    f"{OUTPUT_FILE}"
)

print(
    "Summary saved to: "
    "sprintpulse_risk_cause_summary.csv"
)
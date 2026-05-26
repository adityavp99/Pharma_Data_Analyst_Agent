from __future__ import annotations

from pathlib import Path
import random
from uuid import uuid5, NAMESPACE_DNS

from faker import Faker
import numpy as np
import pandas as pd


SEED = 42
BASE_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = BASE_DIR / "data" / "raw"


PHASES = ["Phase I", "Phase II", "Phase III", "Phase IV"]
THERAPEUTIC_AREAS = ["Oncology", "Immunology", "Cardiology", "Neurology", "Rare Disease"]
DRUGS = ["Oncovex", "Immunara", "Cardioban", "Neuroquel", "Raredex", "Metabrix"]
INDICATIONS = {
    "Oncology": ["Non-small cell lung cancer", "Breast cancer", "Lymphoma"],
    "Immunology": ["Rheumatoid arthritis", "Psoriasis", "Crohn's disease"],
    "Cardiology": ["Heart failure", "Hypertension", "Atrial fibrillation"],
    "Neurology": ["Migraine", "Epilepsy", "Multiple sclerosis"],
    "Rare Disease": ["Pulmonary arterial hypertension", "Fabry disease", "Gaucher disease"],
}
COUNTRIES = ["United States", "Germany", "Japan", "Brazil", "India", "United Kingdom", "France", "Canada"]
REGIONS = {
    "United States": "North America",
    "Canada": "North America",
    "Germany": "Europe",
    "United Kingdom": "Europe",
    "France": "Europe",
    "Japan": "Asia Pacific",
    "India": "Asia Pacific",
    "Brazil": "Latin America",
}
SPONSORS = ["AsterBio", "NovaCura", "Helix Therapeutics", "Pioneer Pharma"]
STATUSES = ["Recruiting", "Active", "Completed", "Terminated"]
AGE_GROUPS = ["18-39", "40-64", "65+"]
SEXES = ["Female", "Male"]
BASELINE_CONDITIONS = ["Mild", "Moderate", "Severe"]
TREATMENT_ARMS = ["Placebo", "Low Dose", "High Dose", "Standard of Care"]
AE_TERMS = ["Headache", "Nausea", "Fatigue", "Injection site reaction", "Rash", "Dizziness", "Elevated ALT"]
SEVERITIES = ["Mild", "Moderate", "Severe"]
SERIOUSNESS = ["Non-serious", "Serious"]
OUTCOMES = ["Recovered", "Recovering", "Ongoing", "Resolved with sequelae"]
LAB_TESTS = [
    ("ALT", "U/L", 7, 56, 28, 14),
    ("AST", "U/L", 10, 40, 24, 10),
    ("Hemoglobin", "g/dL", 12, 17.5, 14.2, 1.8),
    ("Platelets", "10^9/L", 150, 450, 260, 70),
    ("Creatinine", "mg/dL", 0.6, 1.3, 0.95, 0.22),
]
CHANNELS = ["Hospital", "Retail", "Specialty Pharmacy"]


def synthetic_id(prefix: str, value: str) -> str:
    return f"{prefix}_{str(uuid5(NAMESPACE_DNS, value))[:8]}"


def make_trials(fake: Faker) -> pd.DataFrame:
    rows = []
    start_base = pd.Timestamp("2022-01-01")
    for idx in range(1, 31):
        therapeutic_area = random.choice(THERAPEUTIC_AREAS)
        start_date = start_base + pd.Timedelta(days=random.randint(0, 900))
        duration_days = random.randint(360, 1100)
        country = random.choice(COUNTRIES)
        rows.append(
            {
                "trial_id": f"TRIAL_{idx:03d}",
                "phase": random.choice(PHASES),
                "therapeutic_area": therapeutic_area,
                "drug_name": random.choice(DRUGS),
                "indication": random.choice(INDICATIONS[therapeutic_area]),
                "start_date": start_date.date().isoformat(),
                "end_date": (start_date + pd.Timedelta(days=duration_days)).date().isoformat(),
                "status": random.choice(STATUSES),
                "country": country,
                "sponsor": random.choice(SPONSORS),
                "planned_enrollment": random.randint(120, 900),
            }
        )
    return pd.DataFrame(rows)


def make_sites(trials: pd.DataFrame, fake: Faker) -> pd.DataFrame:
    rows = []
    site_counter = 1
    for trial in trials.to_dict("records"):
        for _ in range(random.randint(2, 6)):
            target = random.randint(20, 160)
            enrolled = max(0, int(np.random.normal(target * random.uniform(0.55, 1.05), target * 0.12)))
            rows.append(
                {
                    "site_id": f"SITE_{site_counter:04d}",
                    "trial_id": trial["trial_id"],
                    "country": random.choice([trial["country"], random.choice(COUNTRIES)]),
                    "investigator_name": fake.name(),
                    "enrollment_target": target,
                    "enrolled_patients": min(enrolled, int(target * 1.25)),
                }
            )
            site_counter += 1
    return pd.DataFrame(rows)


def make_patients(sites: pd.DataFrame) -> pd.DataFrame:
    rows = []
    patient_counter = 1
    for site in sites.to_dict("records"):
        for _ in range(int(site["enrolled_patients"])):
            rows.append(
                {
                    "patient_id": f"PT_{patient_counter:07d}",
                    "trial_id": site["trial_id"],
                    "site_id": site["site_id"],
                    "age_group": random.choices(AGE_GROUPS, weights=[0.25, 0.5, 0.25])[0],
                    "sex": random.choice(SEXES),
                    "baseline_condition": random.choices(BASELINE_CONDITIONS, weights=[0.35, 0.45, 0.2])[0],
                    "treatment_arm": random.choice(TREATMENT_ARMS),
                }
            )
            patient_counter += 1
    return pd.DataFrame(rows)


def make_adverse_events(patients: pd.DataFrame, trials: pd.DataFrame) -> pd.DataFrame:
    trial_dates = trials.set_index("trial_id")[["start_date", "end_date"]].to_dict("index")
    rows = []
    ae_counter = 1
    sampled = patients.sample(frac=0.36, random_state=SEED)
    for patient in sampled.to_dict("records"):
        for _ in range(np.random.poisson(1.2) + 1):
            dates = trial_dates[patient["trial_id"]]
            start = pd.Timestamp(dates["start_date"])
            end = pd.Timestamp(dates["end_date"])
            event_date = start + pd.Timedelta(days=random.randint(0, max(1, (end - start).days)))
            severity = random.choices(SEVERITIES, weights=[0.55, 0.35, 0.10])[0]
            seriousness = random.choices(SERIOUSNESS, weights=[0.86, 0.14])[0]
            rows.append(
                {
                    "ae_id": f"AE_{ae_counter:08d}",
                    "patient_id": patient["patient_id"],
                    "trial_id": patient["trial_id"],
                    "event_term": random.choice(AE_TERMS),
                    "severity": severity,
                    "seriousness": seriousness,
                    "outcome": random.choice(OUTCOMES),
                    "event_date": event_date.date().isoformat(),
                    "related_to_drug": int(random.random() < (0.23 if seriousness == "Serious" else 0.16)),
                }
            )
            ae_counter += 1
    return pd.DataFrame(rows)


def make_lab_results(patients: pd.DataFrame, trials: pd.DataFrame) -> pd.DataFrame:
    trial_starts = trials.set_index("trial_id")["start_date"].to_dict()
    rows = []
    lab_counter = 1
    sampled = patients.sample(frac=0.52, random_state=SEED + 1)
    for patient in sampled.to_dict("records"):
        for test_name, unit, normal_low, normal_high, mean, sd in random.sample(LAB_TESTS, random.randint(2, 5)):
            for visit_month in random.sample([0, 1, 3, 6, 9, 12], random.randint(1, 3)):
                value = float(np.random.normal(mean, sd))
                if random.random() < 0.08:
                    value *= random.choice([0.55, 1.65])
                result_date = pd.Timestamp(trial_starts[patient["trial_id"]]) + pd.DateOffset(months=visit_month)
                rows.append(
                    {
                        "lab_id": f"LAB_{lab_counter:08d}",
                        "patient_id": patient["patient_id"],
                        "trial_id": patient["trial_id"],
                        "test_name": test_name,
                        "result_value": round(max(value, 0.01), 2),
                        "unit": unit,
                        "normal_low": normal_low,
                        "normal_high": normal_high,
                        "result_date": result_date.date().isoformat(),
                    }
                )
                lab_counter += 1
    return pd.DataFrame(rows)


def make_drug_sales(trials: pd.DataFrame) -> pd.DataFrame:
    months = pd.date_range("2023-01-01", "2025-12-01", freq="MS")
    rows = []
    sale_counter = 1
    drugs = sorted(trials["drug_name"].unique())
    for drug in drugs:
        base_units = random.randint(1500, 9000)
        unit_price = random.uniform(120, 900)
        for country in COUNTRIES:
            country_factor = random.uniform(0.45, 1.55)
            for month_idx, month in enumerate(months):
                seasonal = 1 + 0.08 * np.sin(month_idx / 12 * 2 * np.pi)
                growth = 1 + month_idx * random.uniform(0.002, 0.012)
                for channel in CHANNELS:
                    channel_factor = {"Hospital": 0.42, "Retail": 0.34, "Specialty Pharmacy": 0.24}[channel]
                    units = max(0, int(np.random.normal(base_units * country_factor * seasonal * growth * channel_factor, base_units * 0.08)))
                    rows.append(
                        {
                            "sale_id": f"SALE_{sale_counter:09d}",
                            "drug_name": drug,
                            "country": country,
                            "region": REGIONS[country],
                            "month": month.date().isoformat(),
                            "units_sold": units,
                            "net_sales": round(units * unit_price * random.uniform(0.88, 1.08), 2),
                            "channel": channel,
                            "currency": "USD",
                        }
                    )
                    sale_counter += 1
    return pd.DataFrame(rows)


def generate() -> dict[str, int]:
    random.seed(SEED)
    np.random.seed(SEED)
    fake = Faker()
    Faker.seed(SEED)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    trials = make_trials(fake)
    sites = make_sites(trials, fake)
    patients = make_patients(sites)
    adverse_events = make_adverse_events(patients, trials)
    lab_results = make_lab_results(patients, trials)
    drug_sales = make_drug_sales(trials)

    frames = {
        "trials": trials,
        "sites": sites,
        "patients": patients,
        "adverse_events": adverse_events,
        "lab_results": lab_results,
        "drug_sales": drug_sales,
    }
    for name, frame in frames.items():
        frame.to_csv(RAW_DIR / f"{name}.csv", index=False)

    return {name: len(frame) for name, frame in frames.items()}


if __name__ == "__main__":
    counts = generate()
    print("Synthetic data generated in data/raw:")
    for table_name, row_count in counts.items():
        print(f"- {table_name}: {row_count:,} rows")

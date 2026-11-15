"""Write SCHEMA-FAITHFUL MOCK files into a raw folder, to test the data pipeline without Kaggle.
Columns copy the published schemas (asaniczka trackers: 8 columns; EMSCAD: 18 columns); the 60K,
contracts and freelancer-success column names are guesses the pipeline's aliases must cope with.
Contents are random and meaningless: never use these for results.

    python -m dev.make_mock_raw /tmp/raw
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pandas as pd

TITLES = ["Build a RAG chatbot over our PDF docs with LangChain", "Machine learning model for customer churn",
          "Python data scientist for demand forecasting", "React developer for SaaS dashboard", "Next.js and Node.js full stack app",
          "Shopify store setup and theme customization", "WordPress site speed optimization", "Django REST API for booking platform",
          "Power BI dashboard for sales data", "Excel VBA automation for monthly reports", "Web scraping of product prices with Python",
          "Tableau dashboard for healthcare KPIs", "SQL analyst for cohort analysis", "Logo design for a coffee brand",
          "SEO blog writer for fintech", "Computer vision model to detect defects", "LLM agent to extract data from invoices",
          "React Native app for field inspections", "Data entry from scanned forms", "AWS DevOps engineer for Docker deployment"]


def main(out: str, n: int = 3000, seed: int = 1):
    r = random.Random(seed)
    out = Path(out)
    rows = []
    for i in range(n):
        t = r.choice(TITLES) + ("" if r.random() < 0.6 else f" ({r.choice(['urgent', 'long term', 'quick fix', 'phase 2'])})")
        hourly = r.random() < 0.45
        rows.append({"title": t, "link": f"https://www.upwork.com/jobs/mock_{i}", "published_date": f"2024-03-{r.randint(1, 28):02d} 10:{i % 60:02d}:00",
                     "is_hourly": hourly, "hourly_low": r.choice([10, 15, 20, 30, 40]) if hourly else None,
                     "hourly_high": r.choice([25, 35, 50, 70, 90]) if hourly else None,
                     "budget": None if hourly else r.choice([50, 150, 300, 500, 1000, 2500]), "country": r.choice(["United States", "United Kingdom", "Germany", "India", "Canada"])})
    for key, part in (("upwork_jobs_2024_50k", rows[: n // 3]), ("upwork_jobs_200k", rows[n // 3: 2 * n // 3])):
        (out / key).mkdir(parents=True, exist_ok=True)
        pd.DataFrame(part).to_csv(out / key / f"{key}.csv", index=False)
    (out / "upwork_jobs_60k").mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"Title": x["title"], "Description": f"We need help: {x['title']}. Must have shipped similar work. Timeline 2 weeks.",
                   "Budget": x["budget"] or x["hourly_high"], "Job Type": "Hourly" if x["is_hourly"] else "Fixed",
                   "Skills": "Python, SQL" if "data" in x["title"].lower() else "JavaScript"} for x in rows[2 * n // 3:]]
                 ).to_csv(out / "upwork_jobs_60k" / "jobs.csv", index=False)
    (out / "contracts_1_3m").mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"job_id": i, "title": r.choice(TITLES), "freelancer_id": r.randint(1, 500), "start_date": "2023-01-01",
                   "end_date": "2023-02-01", "total_hours": r.randint(1, 120), "total_charge": r.choice([80, 200, 450, 900, 2000]),
                   "hourly_rate": r.choice([12, 18, 25, 35, 50, 75])} for i in range(4000)]
                 ).to_csv(out / "contracts_1_3m" / "contracts.csv", index=False)
    (out / "freelancer_success").mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"Hourly_Rate": r.choice([15, 25, 35, 45, 60]), "Job_Success_Score": r.randint(60, 100),
                   "Job_Category": r.choice(["Data Science", "Web Development", "Design"]), "Earnings_USD": r.randint(100, 90000)}
                  for _ in range(600)]).to_csv(out / "freelancer_success" / "freelancers.csv", index=False)
    (out / "fake_job_postings").mkdir(parents=True, exist_ok=True)
    fake = []
    for i in range(400):
        fr = int(r.random() < 0.1)
        fake.append({"job_id": i, "title": r.choice(["Data Entry Clerk", "Customer Service Rep", "Software Engineer", "Admin Assistant"]),
                     "location": "US", "department": None, "salary_range": None, "company_profile": "" if fr else "We build tools.",
                     "description": ("Work from home and earn $5000 weekly! No experience needed. Send your bank details to start immediately."
                                     if fr else "Join our team to build and maintain internal tools in Python and SQL with code review."),
                     "requirements": "None" if fr else "2 years experience with Python.", "benefits": None, "telecommuting": fr,
                     "has_company_logo": 1 - fr, "has_questions": 0, "employment_type": "Full-time", "required_experience": None,
                     "required_education": None, "industry": None, "function": None, "fraudulent": fr})
    pd.DataFrame(fake).to_csv(out / "fake_job_postings" / "fake_job_postings.csv", index=False)
    print("mock raw data written to", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/raw_mock")

"""Write SCHEMA-FAITHFUL MOCK files into a raw folder, to test the data pipeline without Kaggle.
File names and columns copy the real downloads (checked 2026-11-15 with `python -m datapipe.inspect`),
including the decoy files the pipeline must skip (60K .xlsx copy, unlabelled BERT sheet).
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
    pd.DataFrame([{"Job Title": x["title"], "Job_URL": x["link"] + "_60k", "EX_level_demand": r.choice(["Entry level", "Intermediate", "Expert"]),
                   "Description": f"We need help: {x['title']}. Must have shipped similar work. Timeline 2 weeks.",
                   "Category_1": "Python" if "data" in x["title"].lower() else "JavaScript", "Category_2": "SQL", "Category_3": None,
                   "Payment_type": "Hourly" if x["is_hourly"] else "Fixed-price",
                   "Job_Cost": None if x["is_hourly"] else f"${x['budget']:,} ", "Start_rate": x["hourly_low"] or 0,
                   "End_rate": x["hourly_high"], "Client_Country": x["country"], "Connects_Num": r.choice([2, 4, 6, 8, 12, 16]),
                   "Spent($)": r.choice([0, 1200, 25000]), "Rating": r.choice([None, 4.2, 4.9]), "Feedback_Num": r.randint(0, 50),
                   "Payment_Situation": r.choice(["Payment verified", "Payment unverified"])} for x in rows[2 * n // 3:]]
                 ).to_csv(out / "upwork_jobs_60k" / "Final_Upwork_Dataset.csv", index=False)
    (out / "contracts_1_3m").mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"job_id": i, "job_title": r.choice(TITLES), "freelancer_id": r.randint(1, 500), "start_date": "2023-01-01",
                   "end_date": "2023-02-01", "total_hours": r.randint(1, 120), "total_paid": r.choice([80, 200, 450, 900, 2000]),
                   "hourly_rate": r.choice([12, 18, 25, 35, 50, 75])} for i in range(4000)]
                 ).to_csv(out / "contracts_1_3m" / "contracts.csv", index=False)
    (out / "freelancer_success").mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"freelancer_id": f"FL_{i:06d}", "hourly_rate_usd": min(280.0, r.choice([15, 25, 35, 45, 60, 400])),
                   "job_success_rate": r.randint(60, 100), "primary_skill": r.choice(["Data Science & Analytics", "Web Development", "Graphic Design"]),
                   "total_earnings_12m_usd": r.randint(100, 90000), "years_experience": r.randint(0, 15)}
                  for i in range(600)]).to_csv(out / "freelancer_success" / "freelancer_gig_success_dataset.csv", index=False)
    (out / "fake_job_postings").mkdir(parents=True, exist_ok=True)
    fake = []
    for i in range(400):  # columns of processed_labeled_dataset_without_encoding.xlsx (lower-cased, punctuation-stripped text)
        fr = int(r.random() < 0.1)
        title = r.choice(["data entry clerk", "customer service rep", "software engineer", "admin assistant"])
        desc = ("work from home and earn 5000 weekly no experience needed send your bank details to start immediately"
                if fr else "join our team to build and maintain internal tools in python and sql with code review")
        fake.append({"job_title": title, "location": r.randint(1, 5000), "industry": r.randint(1, 700), "salary_range": None,
                     "company_profile": "" if fr else "we build tools", "job_desc": desc,
                     "skills_desc": "none" if fr else "2 years experience with python", "employment_type": "Full-time",
                     "fraudulent": fr, "text": f"{title} {desc}"})
    pd.DataFrame(fake).to_excel(out / "fake_job_postings" / "processed_labeled_dataset_without_encoding.xlsx", index=False)
    pd.DataFrame(fake[:5]).to_excel(out / "fake_job_postings" / "preprocessed_unlabelled_data_bert.xlsx", index=False)  # must be skipped
    print("mock raw data written to", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/raw_mock")

# Data Card

GigBid's data = **real job-market data from six instructor-approved Kaggle datasets** + **synthetic
data where no real source exists**, built by `python -m datapipe.build` (≈5 min on a laptop CPU).
Every record says which it is: jobs carry `source` and `synthetic_fields`; synthetic records carry
`"synthetic": true` and a `source` starting with `synthetic/`; clients list their `real_fields`.
Counts below are from `data/market/provenance.json` (build of 2026-11-15).

Reproduce: `bash scripts/download_datasets.sh` (needs `~/.kaggle/kaggle.json`) → `make data` →
`python -m datapipe.silver_labels`.

## 1. Sources (real data)
| Key (`data/raw/...`) | Kaggle dataset | Author | Rows read | Used for | Licence |
|---|---|---|---|---|---|
| upwork_jobs_2024_50k | [Upwork Job Postings 2024 (50K)](https://www.kaggle.com/datasets/asaniczka/upwork-job-postings-dataset-2024-50k-records) | asaniczka | 53,058 | job posts **with descriptions**, budgets, hourly ranges, country, date | ODC-By 1.0 |
| upwork_jobs_200k | [All Upwork Job Postings, monthly tracker](https://www.kaggle.com/datasets/asaniczka/all-jobs-on-upwork-200k-plus) | asaniczka | 180,000 (60k/file × 3) | title-only posts: market statistics, pool volume | ODC-By 1.0 |
| upwork_jobs_60k | [Upwork freelance jobs (+60k)](https://www.kaggle.com/datasets/ahmedmyalo/upwork-freelance-jobs-60k) | ahmedmyalo | 60,000 | 2023 posts with descriptions, skill tags (`Category_1..9`), **real Connects cost**, **real client spend / rating / reviews / payment verification** | Apache-2.0 |
| contracts_1_3m | [Freelance Contracts Dataset (1.3M)](https://www.kaggle.com/datasets/asaniczka/freelance-contracts-dataset-1-3-million-entries) | asaniczka | 180,000 | contract hourly rates and amounts: pricing percentiles, synthetic client spend calibration | ODC-By 1.0 |
| freelancer_success | [Freelancer Marketplace Dataset for ML & Analytics](https://www.kaggle.com/datasets/sarveshchhetri/freelancer-success-earnings-and-churn-prediction) | sarveshchhetri | 12,000 | read and inspected; **rejected for rate calibration** (see §5) | Apache-2.0 |
| fake_job_postings | [Fake-Job-Posting-Detection (trial-1)](https://www.kaggle.com/datasets/adityammantri/trial-1) | adityammantri | 60 fraudulent + 55 legitimate used | **scam ground truth** (`fraudulent` label) | **Unknown** (not stated on Kaggle) |

Licences were read from each dataset's Kaggle metadata (`kaggle datasets metadata <ref>`) and are
recorded in `datapipe/sources.yaml` and `provenance.json`. ODC-By and Apache-2.0 permit
redistribution with attribution, which this table provides. trial-1 states no licence: only the
115-row sample inside `evals/datasets/dev_*` and `data/market/jobs.json` is committed, for
non-commercial coursework evaluation, and it will be removed on request.

Files read per source are pinned with `files:` in `sources.yaml`: the 60K `.xlsx` is the same
table as the `.csv` (reading both duplicated every row), and trial-1's
`preprocessed_unlabelled_data_bert.xlsx` has no labels.

## 2. Preprocessing (`datapipe/build.py`)
1. Map each file's real columns to our fields through `sources.yaml` (`python -m datapipe.inspect`
   prints the mapping); the 60K skill tags are nine columns joined into one list.
2. Jobs: drop titles < 8 characters; normalise budget into `{min, max, type}` (`"$2,500 "` → 2500);
   collapse whitespace; truncate descriptions to 4,000 characters.
3. De-duplicate: 293,058 rows → **217,527 jobs**. Key = job URL, else normalised title + first 200
   characters of description. The 200K tracker re-lists 50K jobs *without* descriptions, so the
   URL key makes the copy with a real description win.
4. Skills: lexicon over title + description, plus the dataset's own tags; category from skills
   (ai_ml 12,767 · web_fullstack 45,884 · data_analysis 18,390 · design 20,529 · writing 38,346 ·
   devops 1,210 · other 80,401).
5. Market statistics (p25/p50/p75 of budgets per category and type) from real posts; contract
   rate/amount percentiles from `contracts_1_3m`.
6. Persona hourly rate = p75 of real posted hourly maxima in the persona's category
   (ai_ml $49, web_fullstack $49, data_analysis $50).
7. Scam set: 60 fraudulent + 55 legitimate labelled postings (5 legitimate rows were too short).
   Both get clients from the same synthetic distribution, so detection must come from the text.
8. Dev set per persona (190 jobs): 60% same category, 20% other categories, 5% fraudulent, 5%
   legitimate labelled postings, 5% planted-injection copies of real posts.
9. Pool served by the local simulator: 3,050 jobs (3,000 random + every dev job), 3,020 clients.

## 3. Real vs synthetic, field by field
| Data | Real | Synthetic (and why) |
|---|---|---|
| Job title, budget, hourly range, country, date, URL | all jobs | — |
| Job description | 105,632 jobs | 111,895 title-only tracker rows get a template restating the title and detected skills (adds no facts); `synthetic_fields` contains `description` |
| Connects cost | 55,299 jobs (60K dataset) | the rest: budget-tier rule (`connects_for`) |
| Client spend / rating / reviews / payment verified | 749 of 3,020 pool clients (`real_fields`) | the rest: seeded generator, spend sampled from real contract amounts |
| Screening questions | — | ~30% of jobs, seeded templates |
| Personas + portfolios (CV, case studies, READMEs, code notes, reviews, past proposals with outcomes) | — | `datapipe/synthetic.py`; no approved dataset contains portfolios. Display names say "(synthetic persona)" |
| Planted prompt injections | base post is real | 3 injection sentences appended to copies (`planted_injection: true`) |
| Client conversations | — | 25 threads: interview, question, negotiation, scam signal, injection |
| Client replies to proposals | — | LocalSim reply model (`mcp_servers/marketplace/adapters/local_sim.py`) |

## 4. Labels
| Label | Source | Status |
|---|---|---|
| Scam | dataset label `fraudulent` for trial-1 rows; Upwork listings are *assumed* legitimate (`label_scam_source`) | real |
| Bid / watch / skip | `datapipe/silver_labels.py`, rubric `silver_rubric_v2` (`action_source`) | **silver, not human** |
| Evidence relevance | same rubric: skill-tag or title-keyword overlap (`relevant_source`) | **silver, not human** |
| Fair price band | the job's own budget when present, else category p25–p75 of real posts | rule |

**Why silver labels, and their limits.** The assignment's instructor dev set was not available, so
the dev set is built here. Decision and relevance labels come from a fixed rubric that imports
nothing from `agent/` or `rag/`. It overlaps with the system in one signal, skill overlap, and its
umbrella-skill map covers the same domain knowledge as the Fit Matcher's taxonomy
(`data/taxonomy/skills.yaml`, written separately). Silver labels therefore **favour skill-matching
systems** and are blind to implied needs. Every eval JSON carries `label_sources`. Human labels
override silver ones: fill `label_decisions.csv` / `label_relevance.csv` (from `datapipe.pool`),
then run `python -m datapipe.apply_labels --persona <p>`. Rebuilds and silver re-runs never
overwrite `action_source: human`. Before quoting a decision F1 as final, label at least 30 jobs
per persona by hand and report agreement between human and silver labels.

## 5. Limitations found while building
* **freelancer_success rates are clipped:** `hourly_rate_usd` maxes at $280 and the median row
  sits on the cap. A median from it gave every persona $280/h, against real posted rates of
  $20–$50/h, so it is not used for rates. The dataset describes itself as "real-world style",
  i.e. partly synthetic.
* **trial-1 fraudulent rows are mostly templated:** many read "… earn 5000week immediate hiring
  contact now at <email without punctuation> … no degree required flexible hours". Text is
  lower-cased and stripped of punctuation. Scam recall on these rows is easier than on real
  marketplace scams. They are general job-board posts, not freelance posts, with no budget
  (budgets are synthetic).
* Title-only jobs (51%) give agents little to work with; most dev jobs come from the two sets
  with descriptions.
* Synthetic portfolios are cleaner than real ones, so retrieval scores are optimistic.
* LocalSim's reply model rewards specificity, skill coverage and price fit **by construction**:
  simulated reply rates show whether the agent writes such proposals, not real-world reply
  rates. A/B results inherit this.
* The Kaggle scrapes are 2023–2024 snapshots of the platform's category mix.

## 6. Handling
Raw data stays in `data/raw/` (git-ignored, ≈700 MB). The persona data introduces no personal
data. Emails in the trial-1 rows are fictitious template addresses, kept because they are the
scam signal; audit logs and traces mask emails and phones (`agent/guardrails.py`). The Kaggle
token lives in `~/.kaggle/`, never in the repo. Test fixtures in `data/fixtures/` are hand-made
and used only by tests.

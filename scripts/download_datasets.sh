#!/usr/bin/env bash
# Downloads the approved Kaggle datasets into data/raw/<key>/ (raw data is git-ignored).
# Needs a Kaggle API token: kaggle.com -> Settings -> API -> Create New Token -> save as ~/.kaggle/kaggle.json
#   pip install kaggle && chmod 600 ~/.kaggle/kaggle.json
# Or download each ZIP from the browser and unzip into the same folders.
set -euo pipefail
cd "$(dirname "$0")/.."
declare -A SRC=(
  [upwork_jobs_2024_50k]=asaniczka/upwork-job-postings-dataset-2024-50k-records
  [upwork_jobs_200k]=asaniczka/all-jobs-on-upwork-200k-plus
  [upwork_jobs_60k]=ahmedmyalo/upwork-freelance-jobs-60k
  [contracts_1_3m]=asaniczka/freelance-contracts-dataset-1-3-million-entries
  [freelancer_success]=sarveshchhetri/freelancer-success-earnings-and-churn-prediction
  [fake_job_postings]=adityammantri/trial-1
)
for key in "${!SRC[@]}"; do
  echo ">> $key"
  mkdir -p "data/raw/$key"
  kaggle datasets download -d "${SRC[$key]}" -p "data/raw/$key" --unzip || echo "   (failed: download it manually into data/raw/$key)"
done
python -m datapipe.inspect

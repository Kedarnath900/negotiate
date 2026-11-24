# Acme AI Supplier Negotiation Agent — 24-hour Hackathon MVP

## Features
- Streamlit dashboard
- Synthetic supplier negotiation dataset
- CSV/XLSX/PDF/TXT ingestion
- Configurable Acme playbook (`data/acme_playbook.json`)
- Explainable rule-based ACCEPT / COUNTER / REJECT / ESCALATE recommendations
- Similar historical negotiation lookup
- Editable counteroffer draft and downloadable decision audit

## 1. Requirements
- Python 3.10+
- VS Code
- Internet only for installing packages

## 2. Setup (Windows PowerShell)
```powershell
mkdir acme-negotiation-agent
# Extract the ZIP into this folder, then:
cd acme-negotiation-agent
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
streamlit run app.py
```

If PowerShell blocks activation:
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## 3. Setup (macOS/Linux)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

## 4. Demo flow
1. Open Overview and show synthetic historical records.
2. Open Analyze a proposal.
3. Enter a supplier offer and click Analyze negotiation.
4. Explain the decision, checks, rationale and draft counteroffer.
5. Open Bulk upload & review and download the sample CSV.
6. Upload your own CSV/XLSX file using the column names below.
7. Open Decision history and export the audit trail.

## 5. CSV columns
Required columns: `supplier, category, quoted_price, target_price, delivery_days, payment_days, outcome`
Optional: `notes`

Example:
```csv
supplier,category,quoted_price,target_price,delivery_days,payment_days,outcome
Apex Electronics,Electronics,10100,10000,18,45,ACCEPT
Northstar Components,Electronics,11200,10000,25,30,COUNTER
```

## 6. Playbook configuration
Edit `data/acme_playbook.json`. The included policy values are **fictional demo assumptions**, not real Acme rules. Replace them with the hackathon's actual playbook if supplied.

## Important limitations
- PDF/TXT files are ingested as text records; the MVP does not automatically extract every commercial field from unstructured documents.
- Similarity lookup is a simple numeric/category comparison, not production-grade semantic RAG.
- The confidence number is a heuristic, not a calibrated probability.
- All decisions are recommendations. Require human review before contacting suppliers, accepting offers, or making commitments.
- Do not upload confidential supplier data unless the hackathon organizers authorize the use of the chosen services and environment.

## Suggested team split
- Member 1: ingestion, sample dataset, data validation
- Member 2: decision engine, playbook and test cases
- Member 3: Streamlit UI, dashboard and pitch/demo

## 24-hour priorities
First make the demo work end-to-end with synthetic data. Then improve ingestion and testing. Do not spend the whole hackathon trying to process all 2,000 documents before the decision flow works.

# Requirements traceability

Every requirement from the two source documents, mapped to where it is implemented and what evidence exists.
Nothing is marked **Met** without evidence that can be re-run.

**Sources**
- **[T]** Course brief, *Cloud Computing Semester Project (15 marks)*: guidelines and suggested deliverables.
- **[P]** Our proposal, *UCS531: Cloud Computing, Project Details* (title, abstract, planned technologies, architecture diagram).

**Status key:** **Met** = implemented and verified (evidence given) · **Built** = implemented and tested locally; runs on AWS only
after deployment · **Pending** = not done yet · **N/A** = does not apply to this project.

_Last updated: 25 Nov 2026._

## 1. Course requirements [T]

| ID | Requirement | Where | Status | Evidence |
|---|---|---|---|---|
| T1 | Group of at most 3 students from the same lab group | Proposal | **Met** | 2 members, both in lab L430 |
| T2 | A simple, well-implemented solution preferred over an ambitious, incomplete one | Whole repo | **Met** | Core features complete; 14 automated tests pass (`pytest -q`) |
| T3 | Cloud is integral to development, deployment, storage, computation or service delivery | `cloud.py`, `db.py`, `deploy/` | **Built** | Storage = S3, database = RDS, compute + web = EC2. Needs the AWS deployment (D4) to be demonstrated |
| T4 | Uses a free tier or student credits | README → *Cost and teardown* | **Built** | t3.micro, db.t3.micro, 20 GB; re-check free-tier terms at sign-up |
| T5 | Evaluated on implementation, cloud use, documentation and presentation | D1–D7 below | See below | |

### Suggested deliverables

| ID | Deliverable | Where | Status | Evidence / what is left |
|---|---|---|---|---|
| D1 | Project proposal (problem statement, objectives) | Proposal PDF (submitted) | **Met** | Submitted. Keep the PDF out of the public repo: it contains phone numbers |
| D2 | System architecture diagram | README → *Architecture* (Mermaid) | **Met** | Renders on GitHub. The proposal's diagram does not show IAM, security groups, SSM or SNS; use the README version in the report |
| D3 | Working implementation | `pipeline/`, `app/` | **Met** (locally) | End to end on real data: 91,797 rows loaded, model trained, 378 forecasts written, dashboard verified in a browser |
| D4 | Cloud deployment with demonstration | `deploy/`, README → *Deploy on AWS* | **Pending** | Scripts and guide are ready but have **not been run on AWS yet**. Steps 0–9 of the README |
| D5 | Source code on GitHub with a README | This repository | **Met** | README, CI workflow running the tests on every push |
| D6 | Project report (max 5 pages) | — | **Pending** | Outline in the project plan; needs AWS screenshots from D4 |
| D7 | Final presentation and live demonstration | README → *Demo script* | **Pending** | Demo script written; slides not made; rehearsal needs D4 |

## 2. Proposal commitments [P]

| ID | Commitment in the proposal | Where | Status | Evidence / note |
|---|---|---|---|---|
| P1 | Store historical traffic data in the cloud | `pipeline/etl.py`, `db.py` | **Built** | Raw files in S3 `raw/`, records in RDS `traffic_records` |
| P2 | Cloud-hosted analytics | `pipeline/run_all.py`, `deploy/crontab.txt` | **Built** | Runs on EC2 hourly (predict) and nightly (retrain), or from the Admin page |
| P3 | Identify congestion levels | `pipeline/congestion.py` | **Met** | V/C ratio with 4 levels; boundaries tested in `tests/test_congestion.py` |
| P4 | Predict near-future traffic from historical patterns | `pipeline/train.py`, `pipeline/predict.py` | **Met** | 1-hour model, extended to 6 hours recursively |
| P5 | Public or synthetic datasets only | `pipeline/prepare_data.py` | **Met** | UCI dataset (CC BY 4.0) plus segments labelled "(synthetic)" everywhere |
| P6 | Amazon EC2 for compute | `deploy/setup_ec2.sh`, `deploy/traffic-app.service` | **Built** | Pending D4 |
| P7 | Amazon S3 for datasets and processed files | `cloud.py` | **Built** | Prefixes `raw/`, `processed/`, `models/`, `feed/` |
| P8 | Amazon RDS for structured records | `db.py` | **Built** | PostgreSQL on RDS (SQLite only in local development mode) |
| P9 | IAM access control | `deploy/iam-ec2-policy.json`, README step 5 | **Built** | Least-privilege instance role; no access keys on the server. Pending D4 |
| P10 | CloudWatch monitoring | `deploy/cloudwatch-agent.json`, `deploy/create_monitoring.sh`, `cloud.py` | **Built** | Agent metrics, app logs, custom pipeline metrics, 3 alarms, dashboard. Pending D4 |
| P11 | Python backend and data-processing modules | `pipeline/`, `app/` | **Met** | |
| P12 | Preprocess the traffic data | `pipeline/etl.py` (`normalize`, `clean`) | **Met** | Cleaning rules tested in `tests/test_features.py::test_uci_format_cleaning` |
| P13 | Compute congestion from traffic indicators | `pipeline/congestion.py` | **Met** | Uses volume; speed and occupancy are stored and shown where available (see deviation 3) |
| P14 | Lightweight ML model: Linear Regression or Random Forest | `pipeline/train.py` | **Met** | Both trained and compared, plus a naive baseline (table below) |
| P15 | Web dashboard: current and historical congestion, predictions, basic system metrics | `app/` | **Met** (locally) | Overview, Historical, Prediction, Model and System pages. System metrics need D4 to show CloudWatch data |
| P16 | Interactive charts and maps | `app/templates/` | **Met** | Chart.js hover tooltips; Leaflet map with popups |
| P17 | Features: vehicle count, speed, road occupancy, timestamp, location | `db.py` schema | **Met with deviation** | All five are stored. In the real data, speed and occupancy are missing (see deviation 3) |
| P18 | Raw datasets stored as CSV/Parquet | `cloud.py`, `pipeline/etl.py` | **Met** | Gzipped CSV |
| P19 | Demonstrate security, monitoring and scalability | README → *Security checks*, *Load test*, *Scaling* | **Built / Pending** | Security and monitoring are built. Scalability: the app tier is stateless; the load test and the optional Auto Scaling Group need D4 |

## 3. Model evaluation evidence (local run)

Time-based split (last 15% of the timeline held out). Reproduce with `python -m pipeline.prepare_data && python -m pipeline.run_all`.

| Model | MAE (veh/h) | RMSE (veh/h) | R² | Congestion level correct |
|---|---|---|---|---|
| Baseline (same hour last week) | 305.6 | 526.8 | 0.912 | 77.7% |
| Linear Regression | 294.6 | 420.2 | 0.944 | 77.4% |
| Random Forest (active) | 218.0 | 327.2 | 0.966 | 82.0% |

Train: 70,517 hours (2012-10-09 → 2018-07-11). Test: 12,446 hours (2018-07-11 → 2018-09-23).
These are numbers from one run on a laptop. The AWS run trains on the same data, but results should be re-recorded from it.

## 4. Ambiguities, deviations and decisions

| # | Issue | Decision |
|---|---|---|
| 1 | The project brief we were given also mentions attacks, ablations, negative controls and hypotheses with pre-declared directions. Our proposal contains none of these. | **N/A.** Nothing is invented to fill them. The proposal declares no formal hypotheses. The naive baseline is an added evaluation control, not a hypothesis test. |
| 2 | "Near-future" has no stated horizon. | Train a 1-hour-ahead model; extend to 6 hours by feeding each prediction back in. Error growth is noted on the Prediction page. |
| 3 | The real dataset has one station and no speed or occupancy values. | Six road segments are generated from the real pattern and **labelled "(synthetic)"** everywhere. The proposal allows synthetic data. Congestion uses volume, which every location has. |
| 4 | Road capacity is not in the data. | Capacity = 95th percentile of each location's hourly volume. This is a stated limitation. |
| 5 | The proposal diagram shows the web app separate from EC2. | The dashboard is served from EC2 (nginx + gunicorn + Flask) and reads RDS. The README diagram shows this. |
| 6 | Services beyond the proposal | SSM Parameter Store (secrets) and SNS (alarm email) were **added**. Nothing in the proposal was replaced. |
| 7 | Local development mode | SQLite and a local folder stand in for RDS and S3 **only** for development and tests. The graded deployment uses RDS and S3. |
| 8 | Future weather is unknown when forecasting. | The last observed weather is carried forward. This is a stated limitation. |

## 5. What is not yet evidenced

Nothing below may be presented as done until it has actually run:
- Deployment on AWS (D4) and every check in the README's *Security checks* table
- CloudWatch metrics, alarms and the SNS email
- The load test, and any scaling claim beyond "the app tier is stateless"
- Report (D6) and slides (D7)

# Project guide: everything about this project, from the beginning

This guide explains **what we built**, **how it meets every course requirement**, **the cloud computing ideas behind
it**, and **how each part works technically**. Read it once from top to bottom before the viva. Section 17 lists the
questions you are most likely to be asked, with answers.

**Contents**
1. [The project in one minute](#1-the-project-in-one-minute)
2. [What the teacher asked, and how we meet it](#2-what-the-teacher-asked-and-how-we-meet-it)
3. [Cloud computing basics you must know](#3-cloud-computing-basics-you-must-know)
4. [The AWS services we use, and why](#4-the-aws-services-we-use-and-why)
5. [Architecture: how the pieces fit](#5-architecture-how-the-pieces-fit)
6. [The data](#6-the-data)
7. [The analytics and machine learning](#7-the-analytics-and-machine-learning)
8. [The web application, page by page](#8-the-web-application-page-by-page)
9. [The code, file by file](#9-the-code-file-by-file)
10. [The database](#10-the-database)
11. [How the project was built, step by step](#11-how-the-project-was-built-step-by-step)
12. [Deployment on AWS](#12-deployment-on-aws)
13. [Security in detail](#13-security-in-detail)
14. [Monitoring in detail](#14-monitoring-in-detail)
15. [Testing and quality](#15-testing-and-quality)
16. [Limitations and future work](#16-limitations-and-future-work)
17. [Viva questions and answers](#17-viva-questions-and-answers)
18. [Glossary](#18-glossary)

---

## 1. The project in one minute

**Title:** Cloud-Based Traffic Data Analytics and Congestion Prediction (UCS531 Cloud Computing, Lab L430).
**Team:** Gurliv Singh, Harshpreet Singh. **Advisor:** Ishani Rana.

**Problem.** Traffic data is large and depends on time and location. On one laptop it doesn't scale and nobody else
can reach it.

**What we built.** A web application that:
1. **stores** historical traffic data in the cloud: files in **Amazon S3**, structured records in **Amazon RDS (PostgreSQL)**
2. **processes** it in the cloud on **Amazon EC2**: cleaning, then computing how congested each road is
3. **predicts** traffic up to 6 hours ahead with machine learning: **Random Forest**, compared against Linear Regression and a baseline
4. **shows** everything on a web dashboard with 7 pages: charts, a map, predictions, model accuracy, system health
5. is **secured** with IAM, security groups and SSM Parameter Store, and **monitored** with CloudWatch and SNS
6. can be **deployed with one command** using CloudFormation (infrastructure as code)

**Key result.** On 12,446 hours it never saw during training, Random Forest predicts hourly traffic with
**R² = 0.966** and a mean error of **218 vehicles/hour**. That is **38% lower error** (RMSE) than the simple baseline.

**Where things are:**
- code: <https://github.com/gurlivsingh/cloud-traffic-analytics>
- video walkthrough: `docs/video/project-walkthrough.mp4`
- requirement checklist: [REQUIREMENTS.md](REQUIREMENTS.md)
- deployment steps: [DEPLOYMENT.md](DEPLOYMENT.md)

---

## 2. What the teacher asked, and how we meet it

The course brief (15 marks) sets these rules. The full evidence-by-evidence table is in [REQUIREMENTS.md](REQUIREMENTS.md).

| The brief says | How our project meets it |
|---|---|
| Groups of up to 3 from the same lab group | 2 members, both in lab L430 |
| A simple, well-built solution beats an ambitious, unfinished one | One clear goal (congestion analytics + prediction), fully working, 14 automated tests |
| The cloud must be an **integral** part (development, deployment, storage, computation or service delivery) | **All five**: storage (S3 + RDS), computation (EC2 runs ETL, training, prediction), service delivery (dashboard served from EC2), deployment (CloudFormation), development (GitHub + CI). Without the cloud, nothing works |
| Use a free tier or student credits | AWS Academy Learner Lab credits; t3.micro and db.t3.micro, the smallest sizes |
| Evaluated on implementation, use of cloud, documentation, presentation | Implementation: working app. Cloud: 8 AWS services. Documentation: README, this guide, requirements, deployment guide, video. Presentation: demo script |

**The 7 suggested deliverables:**

| # | Deliverable | Status |
|---|---|---|
| 1 | Project proposal | ✔ Submitted (the PDF) |
| 2 | System architecture diagram | ✔ In the README ([section 5](#5-architecture-how-the-pieces-fit) explains it) |
| 3 | Working implementation | ✔ Verified end to end on the real dataset |
| 4 | Cloud deployment with demonstration | ✔ Live on AWS (CloudFormation stack `traffic-analytics`, us-east-1, 26 Nov 2026); security checks passed |
| 5 | Source code on GitHub with README | ✔ Public repository with README, docs and CI |
| 6 | Report (max 5 pages) | ✔ Written: 5 pages with screenshots from the live AWS deployment |
| 7 | Final presentation and live demo | ⏳ To do; demo script in the README |

**What our proposal promised, and where it is:**

| Proposal promise | Where in the project |
|---|---|
| Store historical traffic data | S3 `raw/` + RDS `traffic_records` ([§6](#6-the-data), [§10](#10-the-database)) |
| Cloud-hosted analytics | ETL, training and prediction run on EC2 ([§7](#7-the-analytics-and-machine-learning)) |
| Identify congestion levels | Volume/capacity ratio → Low / Moderate / High / Severe ([§7.1](#71-congestion)) |
| Predict near-future conditions | 1–6 hour forecasts ([§7.4](#74-forecasting-beyond-one-hour)) |
| Public or synthetic data only | UCI public dataset + clearly labelled synthetic roads ([§6](#6-the-data)) |
| EC2, S3, RDS, IAM, CloudWatch | All used ([§4](#4-the-aws-services-we-use-and-why)). SSM and SNS were added on top |
| Python backend and processing | Python 3.11 / 3.12: pandas, scikit-learn, Flask |
| Linear Regression or Random Forest | **Both**, plus a baseline, compared fairly |
| Dashboard: current/historical congestion, predictions, system metrics, charts and maps | 7 pages ([§8](#8-the-web-application-page-by-page)) |
| Demonstrate security, monitoring, scalability | [§13](#13-security-in-detail), [§14](#14-monitoring-in-detail); scalability in [§3.5](#35-scalability-and-elasticity) |

---

## 3. Cloud computing basics you must know

### 3.1 What cloud computing is
**Cloud computing** means renting computing resources (servers, storage, databases, networking) **on demand over
the internet**, and paying only for what you use. You don't buy or maintain physical hardware.

The standard NIST definition lists **five essential characteristics**. Here is how our project shows each one:

| Characteristic | Meaning | In our project |
|---|---|---|
| On-demand self-service | Create resources yourself, instantly, with no human at the provider | One command creates the server, database and storage |
| Broad network access | Reachable over the internet from any device | The dashboard opens in any browser, including phones |
| Resource pooling | The provider shares big hardware among many customers | Our EC2 server is a slice of a large physical machine |
| Rapid elasticity | Scale up or down quickly | Change the instance size, or add instances behind a load balancer ([§3.5](#35-scalability-and-elasticity)) |
| Measured service | Usage is metered and billed | Pay per hour; CloudWatch measures CPU, memory, storage |

### 3.2 Service models

| Model | You manage | Provider manages | Our example |
|---|---|---|---|
| **IaaS** (Infrastructure as a Service) | OS, runtime, app, data | Hardware, virtualization, network | **EC2**: we install Python, nginx and our app |
| **PaaS** (Platform as a Service) | App and data | OS, patching, backups, scaling | **RDS**: AWS runs PostgreSQL; we only create tables |
| **SaaS** (Software as a Service) | Only your usage | Everything | CloudWatch dashboards, SNS email; also GitHub |

S3 is usually called **storage as a service** (object storage).

### 3.3 Deployment models
- **Public cloud:** shared provider infrastructure such as AWS. **This is what we use.**
- **Private cloud:** dedicated to one organisation.
- **Hybrid cloud:** a mix of public and private.
- **Community cloud:** shared by organisations with common needs.

### 3.4 Virtualization
EC2 instances are **virtual machines**. A **hypervisor** (AWS Nitro) splits one physical server into many isolated
VMs. Our t3.micro has 2 virtual CPUs and 1 GB RAM. "t3" is a **burstable** type: it can briefly use more CPU than its
baseline, which suits a dashboard that is mostly idle.

### 3.5 Scalability and elasticity
- **Vertical scaling (scale up):** a bigger machine, e.g. t3.micro → t3.small. Stop, change the type, start.
- **Horizontal scaling (scale out):** more machines behind a **load balancer**, added automatically by an **Auto Scaling Group** when CPU is high.
- **Why our design can scale out:** the web server is **stateless**. All data lives in S3 and RDS, not on the server, so you can add or replace servers freely. [DEPLOYMENT.md](DEPLOYMENT.md) describes the Auto Scaling extension.
- **Elasticity** means scaling automatically *with demand*. **Scalability** is the ability to handle growth.

### 3.6 Shared responsibility model
**AWS is responsible for the security *of* the cloud.** That means data centres, hardware, the hypervisor, and the
software of managed services such as RDS.

**We are responsible for security *in* the cloud:**
- the operating system on EC2 and its updates
- our application code
- firewall rules (security groups)
- IAM permissions
- encrypting and protecting our data

The responsibility differs by service. With EC2 we patch the OS; with RDS, AWS patches the database engine.

### 3.7 Regions and Availability Zones
A **region** is a geographic area, such as us-east-1 (N. Virginia) or ap-south-1 (Mumbai). Each region has several
**Availability Zones (AZs)**: separate data centres. S3 stores data across multiple AZs, which is why it is designed
for 99.999999999% (11 nines) durability. Our RDS is single-AZ to save credits; **Multi-AZ** would add a standby copy in
another AZ.

### 3.8 Pay-as-you-go cost
Our setup costs about **$0.04/hour** (≈ $1/day) while running:
- t3.micro ≈ $0.010/h
- db.t3.micro ≈ $0.018/h
- public IPv4 ≈ $0.005/h
- storage (a few cents a day)

In the Learner Lab this comes from free credits, not from you.

---

## 4. The AWS services we use, and why

| Service | What it is | How we use it | Why this and not something else |
|---|---|---|---|
| **Amazon EC2** | Virtual servers (IaaS) | One t3.micro running Amazon Linux 2023: nginx → gunicorn → Flask web app, plus the data pipeline on a schedule | We need a long-running web app and ML training. Lambda (serverless) has a 15-minute limit and is awkward for a dashboard; EC2 is what our proposal named |
| **Amazon S3** | Object storage | Bucket with `raw/` (uploaded data), `processed/` (cleaned data), `models/` (trained models + metrics), `feed/` (held-back "live" data) | Cheap, durable, unlimited storage for files. Databases are a poor place for big files and model binaries |
| **Amazon RDS (PostgreSQL)** | Managed relational database (PaaS) | db.t3.micro; 5 tables: locations, traffic records, predictions, model runs, pipeline runs | We need SQL queries over time series (ranges, joins). AWS handles patching and backups. DynamoDB is key-value and makes range/aggregate queries harder |
| **AWS IAM** | Identity and access management | EC2 **instance role** gives the server permission to use S3, SSM and CloudWatch, so no passwords or keys are stored on the server. Learner Lab provides `LabInstanceProfile`; own accounts get a least-privilege role | Long-lived access keys on a server are the most common way AWS accounts get hacked |
| **VPC security groups** | Virtual firewalls | `traffic-ec2-sg`: only port 80 (web) open. `traffic-rds-sg`: port 5432 open **only to members of `traffic-ec2-sg`** | The database must never be reachable from the internet |
| **SSM Parameter Store** | Secure configuration storage | Encrypted (SecureString) database password, admin password and its hash, Flask session key | Keeps secrets out of code, Git and config files. Free, unlike Secrets Manager |
| **Amazon CloudWatch** | Monitoring | Agent metrics (CPU, memory, disk), 4 log groups, custom metrics from our pipeline, 3 alarms, 1 dashboard | Built in; no extra servers |
| **Amazon SNS** | Notifications | Alarms publish to the `traffic-alerts` topic, which emails subscribers | The standard way for CloudWatch alarms to alert people |
| **AWS CloudFormation** | Infrastructure as code | `deploy/cloudformation.yaml` defines every resource; `python deploy/aws.py up` creates them all | Repeatable, reviewable, one-command deploy and one-command delete |

---

## 5. Architecture: how the pieces fit

```
                    ┌───────────────────────── AWS (us-east-1) ─────────────────────────┐
 Browser ──HTTP:80──►  EC2 t3.micro (Amazon Linux 2023)                                 │
 (users, admin)     │   nginx ─► gunicorn (2 workers) ─► Flask app                       │
                    │   cron ─► pipeline: ETL → train → predict                          │
                    │   CloudWatch Agent                     IAM instance role           │
                    │        │  ▲            │                    │                      │
                    │        │  │ boto3      │ SQL :5432          │ GetParameter         │
                    │        ▼  │            ▼  (only from         ▼                      │
                    │   S3 bucket        RDS PostgreSQL       SSM Parameter Store        │
                    │   raw/ processed/  (not public)         (encrypted secrets)        │
                    │   models/ feed/                                                    │
                    │        CloudWatch: metrics · logs · alarms ─► SNS ─► email         │
                    └────────────────────────────────────────────────────────────────────┘
```

**What happens when someone opens the dashboard:**
1. The browser sends `GET /` to the server's public address (an Elastic IP, which stays the same).
2. **nginx** (the web server) receives it on port 80 and forwards it to **gunicorn** on `127.0.0.1:8000`. gunicorn runs our Flask app with 2 worker processes.
3. Flask returns the HTML page. The page's JavaScript then calls our JSON API (`/api/summary`, `/api/locations`, `/api/predictions`, …).
4. Each API call runs SQL on **RDS** through SQLAlchemy and returns JSON.
5. Chart.js draws the charts and Leaflet draws the map in the browser.

**What happens to new data** (the pipeline):
1. A CSV lands in **S3 `raw/`**, either uploaded on the Admin page or created by `prepare_data`.
2. **ETL** reads it from S3, cleans it, computes congestion, writes a cleaned copy to **S3 `processed/`**, and upserts the rows into **RDS**. "Upsert" means a duplicate is never inserted twice.
3. **Training** reads all records from RDS, trains 3 models, saves the best to **S3 `models/`**, and logs every model in RDS.
4. **Prediction** loads the active model from S3 and writes forecasts to RDS.
5. Each step records itself in `pipeline_runs` and sends metrics to CloudWatch.

**Schedule:**
- cron runs ETL + prediction at minute 5 of every hour
- cron runs ETL + retraining + prediction every night at 02:30
- the Admin page can start a run at any time

A lock file stops two runs overlapping. It is treated as stale after 1 hour, in case a run crashed.

---

## 6. The data

### 6.1 Real data
- **Source:** UCI Machine Learning Repository, *Metro Interstate Traffic Volume* (John Hogue, 2019, licence CC BY 4.0).
- **What it is:** hourly westbound traffic volume on Interstate 94 in Minneapolis–St Paul, USA, Oct 2012 – Sep 2018, about 48,000 rows.
- **Columns:** `date_time`, `traffic_volume`, `holiday`, `temp` (Kelvin), `rain_1h`, `snow_1h`, `clouds_all`, `weather_main`, `weather_description`.
- **Why this dataset:** it's real, public, and freely licensed. It has enough history (6 years) for machine learning, and it includes weather and holidays, which affect traffic.

### 6.2 Synthetic road segments
The real data has only **one** station, but a map needs several roads. `pipeline/prepare_data.py` creates **6 synthetic
segments** (e.g. "I-35W @ Lake St (synthetic)") from the last 365 days of real data. For each segment:
- **Volume** = the real hourly pattern × a scale factor (0.45–1.10), shifted by −1, 0 or +1 hour, × random noise (±8%).
- **Speed** comes from a classic speed–flow relationship: speed = 100 km/h × (1 − 0.75 × (V/C)²), with a minimum of 8 km/h.
- **Occupancy** (% of time a sensor is covered by a vehicle) ≈ 30 × V/C + noise.

The proposal allows synthetic data. Every synthetic road says **"(synthetic)"** in its name, everywhere it appears.

### 6.3 Live feed
The last **7 days** are held back in `s3://…/feed/`. `pipeline/replay_feed.py`, or the Admin page's *Stream next hour*
button, sends them in one hour at a time, exactly as if a road sensor were reporting live.

### 6.4 Cleaning (ETL)
`pipeline/etl.py` fixes real problems found in the data:

| Problem in the raw data | What we do |
|---|---|
| The same hour appears several times (one row per weather tag) | Keep one row per (location, hour) |
| Temperatures of 0 Kelvin (a broken sensor) | Treat as missing, fill from the previous hour |
| Temperature in Kelvin | Convert to °C (−273.15) |
| One rain value of 9,831 mm in an hour (impossible) | Values over 100 mm/h become missing |
| A holiday is marked only on its midnight row | Mark the whole day |
| Negative or missing volumes | Drop the row |

The ETL accepts **two formats**: the raw UCI file, or our simple format (`location, ts, volume` plus optional columns).
Anything else is rejected with a clear message.

---

## 7. The analytics and machine learning

### 7.1 Congestion
We use the **volume-to-capacity (V/C) ratio**, a standard measure in traffic engineering:

> **V/C = vehicles per hour ÷ road capacity**

Road capacity isn't in the dataset, so we estimate it as the **95th percentile** of that road's hourly volume: a level
the road reaches only on its busiest 5% of hours.

| V/C | Level |
|---|---|
| below 0.40 | Low |
| 0.40 – 0.70 | Moderate |
| 0.70 – 0.90 | High |
| 0.90 and above | Severe |

### 7.2 Features (model inputs)
For each hour, the model gets **22 inputs** (`pipeline/features.py`):
- **Time:** hour, day of week, month, weekend yes/no, holiday yes/no
- **Weather:** temperature, rain, snow, cloud cover, plus 9 yes/no flags for the weather type (Clear, Clouds, Rain, Snow, Mist, Drizzle, Haze, Thunderstorm, Fog)
- **Lags (recent history):**
  - volume 1 hour ago (`lag_1h`)
  - 24 hours ago (`lag_24h`)
  - 168 hours ago, the same hour last week (`lag_168h`)
  - the average of the previous 3 hours (`roll_3h`)

**No data leakage.** Every lag uses only *past* hours. Gaps in the data are filled with empty hours first, so "1 hour
ago" really means one hour ago. `tests/test_features.py` checks both.

### 7.3 Models and evaluation
`pipeline/train.py` trains and compares:
1. **Baseline:** "same hour last week". A model is only useful if it beats this.
2. **Linear Regression:** a weighted sum of the inputs, after scaling them.
3. **Random Forest:** 60 decision trees (max depth 14, min 3 samples per leaf), whose predictions are averaged. It captures non-linear patterns such as rush hours.

**Time-based split:** the last 15% of the timeline is the test set. Training covers Oct 2012 – Jul 2018 (70,517
hours); testing covers Jul – Sep 2018 (12,446 hours). A *random* split would let the model see the future, giving
falsely good scores.

**Metrics:**
- **MAE** (mean absolute error): the average size of the mistake, in vehicles/hour.
- **RMSE** (root mean squared error): like MAE, but punishes big mistakes more.
- **R²**: share of the variation explained; 1.0 is perfect.
- **Level accuracy**: how often the predicted congestion *level* is right.

**Results:**

| Model | MAE | RMSE | R² | Level correct |
|---|---|---|---|---|
| Baseline | 305.6 | 526.8 | 0.912 | 77.7% |
| Linear Regression | 294.6 | 420.2 | 0.944 | 77.4% |
| **Random Forest** | **218.0** | **327.2** | **0.966** | **82.0%** |

The model with the lowest RMSE becomes **active** automatically: it's saved to S3 and marked in the `model_runs` table.

**Why Random Forest wins.** Traffic isn't linear. 8 a.m. on a Monday is very different from 8 a.m. on a Sunday, and
trees can learn such combinations. The most important inputs are **same hour last week** and **one hour ago**.

### 7.4 Forecasting beyond one hour
The model predicts **one hour ahead**. For hours 2–6, `pipeline/predict.py` feeds each prediction back in as the
"1 hour ago" value and predicts again (**recursive forecasting**). Errors add up, so later hours are less certain.
Future weather is unknown, so the last observed weather is carried forward. Both points are stated on the Prediction
page.

`predict.py` also writes **1-hour-ahead predictions for the last 48 hours**, so the dashboard can draw actual against
predicted.

---

## 8. The web application, page by page

The dashboard is a **Flask** app with server-rendered HTML pages. Each page loads its data from our JSON API with
JavaScript, then draws charts with **Chart.js** and the map with **Leaflet**. The look follows a warm "research
journal" theme: parchment background, serif text, one accent button per page. Its colours were checked with a
colour-blindness validator, and every congestion colour also has a text label.

| Page | URL | What it shows | Data from |
|---|---|---|---|
| **Overview** | `/` | Latest data hour, records in RDS, model R², roads at High/Severe; a table of every road now and next hour; a 48-hour actual vs predicted chart | `/api/summary`, `/api/locations`, `/api/predictions` |
| **Historical** | `/historical` | Volume over a chosen date range (hourly/daily); speed (synthetic roads); hour × weekday heatmap; weekday vs weekend; weather effect; holiday effect; hours per congestion level | `/api/traffic`, `/api/patterns` |
| **Prediction** | `/prediction` | Actual vs predicted plus the 6-hour forecast, with labelled threshold lines; a forecast table | `/api/predictions` |
| **Map** | `/map` | Every road on OpenStreetMap, shaded by level and sized by V/C; popups with details | `/api/locations` |
| **Model** | `/model` | Test results of the 3 models; feature importance; predicted vs actual scatter; training history | `/api/model` (metrics JSON from S3 + `model_runs`) |
| **System** | `/system` | Health of the database and storage; CloudWatch charts (on AWS); every pipeline run | `/health`, `/api/system` |
| **Admin** | `/admin` (login) | Upload a CSV to S3; run the pipeline (optionally retrain); stream the next live hour | form posts |

**API endpoints** (all return JSON):
- `/health`: database and storage status (HTTP 503 if either is down)
- `/api/locations`: every road with its current state and next-hour forecast
- `/api/summary`: the four headline numbers
- `/api/traffic?location=&from=&to=&agg=`: a time series (switches to daily averages above 60 days)
- `/api/patterns?location=`: heatmap, weekday/weekend, weather, holiday, levels
- `/api/predictions?location=`: last 48 h actual and predicted, plus the forecast
- `/api/model`: model metrics and history
- `/api/system`: CloudWatch metrics and pipeline runs

---

## 9. The code, file by file

| File | What it does |
|---|---|
| `config.py` | Reads settings from environment variables or `.env`. If `S3_BUCKET` and `DB_HOST` are empty, it switches to **local mode** (SQLite + a `storage/` folder), so the same code runs on a laptop |
| `cloud.py` | All AWS calls in one place: S3 put/get/list, reading SSM secrets, sending and reading CloudWatch metrics. Each has a local fallback |
| `db.py` | The 5 database tables (SQLAlchemy). The connection: PostgreSQL on RDS, using the password from SSM, or SQLite locally. `upsert()` inserts in chunks of 1,000 and skips or overwrites duplicates |
| `pipeline/prepare_data.py` | Downloads the UCI zip, generates the synthetic roads, splits off the last 7 days as the feed, uploads to `raw/` and `feed/` |
| `pipeline/etl.py` | `normalize()` converts either CSV format, `clean()` applies the cleaning rules, `load()` computes congestion and upserts into RDS, `process_key()` runs it all for one S3 file and logs a `pipeline_runs` row plus CloudWatch metrics |
| `pipeline/congestion.py` | Capacity (95th percentile), V/C thresholds, level colours |
| `pipeline/features.py` | Builds the 22 model inputs without leakage |
| `pipeline/train.py` | Time-based split, trains baseline/LR/RF, picks the best, saves the model + metrics to S3, records `model_runs` |
| `pipeline/predict.py` | Loads the active model from S3; 48-hour backfill + 6-hour recursive forecast for every road |
| `pipeline/run_all.py` | Runs ETL → (train) → predict, with a lock file. Used by cron and the Admin button |
| `pipeline/replay_feed.py` | Streams held-back hours through S3 → ETL → predict |
| `app/app.py` | Flask routes for the 7 pages, the JSON API, admin login, upload validation, and starting pipeline runs in the background |
| `app/templates/*.html` | One template per page plus `base.html` (navigation, footer) |
| `app/static/style.css`, `app.js` | The theme; shared chart settings, the congestion colour ramp, helpers |
| `deploy/cloudformation.yaml` | Infrastructure as code: every AWS resource ([§12](#12-deployment-on-aws)) |
| `deploy/aws.py` | `up` / `status` / `admin-password` / `down` commands around CloudFormation |
| `deploy/setup_ec2.sh` | Server setup: swap, packages, Python environment, systemd service, nginx, cron, CloudWatch Agent |
| `deploy/nginx.conf`, `traffic-app.service`, `crontab.txt`, `cloudwatch-agent.json` | Configuration used by the setup script |
| `deploy/iam-ec2-policy.json`, `create_monitoring.sh` | For the manual (console) deployment route |
| `tests/` | 14 pytest tests ([§15](#15-testing-and-quality)) |
| `loadtest/locustfile.py` | Simulates many users for the load test |
| `.github/workflows/tests.yml` | GitHub Actions: runs the tests on every push |

**Libraries used:**
- **Flask**: web framework
- **gunicorn**: production server for Flask
- **pandas**: data tables
- **scikit-learn**: machine learning
- **SQLAlchemy**: database access
- **psycopg2**: PostgreSQL driver
- **boto3**: the AWS SDK for Python
- **Chart.js**, **Leaflet**: browser-side charts and map
- **pytest**, **Locust**: testing and load testing

---

## 10. The database

PostgreSQL on RDS, 5 tables:

| Table | One row per | Key columns |
|---|---|---|
| `locations` | road | name (unique), lat, lon, capacity, is_synthetic |
| `traffic_records` | road × hour | ts, volume, speed, occupancy, temp, rain, snow, clouds, weather_main, is_holiday, congestion_index (V/C), congestion_level. **Unique (location_id, ts)**, so reloading a file adds no duplicates |
| `predictions` | road × future hour | target_ts, predicted_volume, predicted_level, model_run_id. Unique (location_id, target_ts); newer predictions overwrite older ones |
| `model_runs` | trained model | model_name, MAE, RMSE, R², level accuracy, S3 key of the saved model, is_active |
| `pipeline_runs` | processed file | S3 key, start/finish time, rows in, rows loaded, status (ok/failed), error |

The tables are created automatically on the first connection.

---

## 11. How the project was built, step by step

1. **Proposal.** We chose traffic congestion because it combines big time-series data, analytics and prediction. That makes it a natural fit for cloud storage plus cloud compute. We named EC2, S3, RDS, IAM and CloudWatch.
2. **Planning.**
   - Picked a dataset that is public, real, long enough, and has weather.
   - Defined congestion precisely (V/C).
   - Kept the scope small, with a clear list of must-haves vs extras.
3. **Local-first development.** The same code runs locally (SQLite + folder) or on AWS (RDS + S3), switched only by settings. This let us build and test everything on a laptop for free.
4. **Data pipeline.** Wrote the ETL. Discovered and fixed the data problems in [§6.4](#64-cleaning-etl). Added the synthetic roads and the live feed.
5. **Machine learning.**
   - Built leakage-free features.
   - Used a time-based split.
   - Compared a baseline, LR and RF; RF won clearly.
   - Added recursive 6-hour forecasting.
6. **Dashboard.** Built the Flask app and JSON API, then 7 pages with Chart.js and Leaflet.
7. **Tests.** Wrote 14 tests, including a full end-to-end run on synthetic data.
8. **Requirements audit.** Mapped every line of the course brief and our proposal to code and evidence ([REQUIREMENTS.md](REQUIREMENTS.md)). Recorded every ambiguity and decision.
9. **Design.** Restyled the dashboard in the editorial parchment theme. Validated the chart colours for colour-blind readers. Split a two-axis chart into two charts. Made it work on phones.
10. **GitHub.**
    - Created a public repository.
    - Wrote the README.
    - Added CI (GitHub Actions runs the tests on every push).
    - Added Harshpreet as a collaborator.
11. **Deployment automation.** Wrote the CloudFormation template and the `deploy/aws.py` script for one-command deploy and teardown on the AWS Academy Learner Lab.
12. **Next:** run the deployment, take AWS screenshots, write the report, make the slides, and rehearse the demo.

---

## 12. Deployment on AWS

### 12.1 One command
```powershell
python deploy/aws.py up          # create everything (about 15–20 minutes)
python deploy/aws.py status      # website link + health check
python deploy/aws.py down        # delete everything
```

### 12.2 What `up` does
1. Checks your AWS credentials.
2. Creates the secrets in **SSM Parameter Store** if they don't exist yet: a random database password, Flask session key, admin password, and its hash.
3. Sends `deploy/cloudformation.yaml` to **CloudFormation**, which creates:
   - S3 bucket (encrypted, all public access blocked)
   - two security groups (web: port 80; database: 5432 only from the web group)
   - RDS PostgreSQL db.t3.micro (encrypted, not public, 1-day backups). It reads its password straight from SSM
   - an IAM role, only when not on Learner Lab
   - 4 CloudWatch log groups (7-day retention)
   - the EC2 t3.micro server (encrypted disk, IMDSv2 required)
   - an Elastic IP (fixed address)
   - SNS topic, 3 alarms, and the dashboard
4. **The server sets itself up** (EC2 "user data" script on first boot):
   - installs git, downloads our code from GitHub, writes its `.env` with the bucket and database names
   - runs `deploy/setup_ec2.sh` (swap, Python, nginx, systemd, cron, CloudWatch Agent)
   - loads the dataset into S3 and RDS, trains, and predicts
   - checks `/health`, then **signals CloudFormation "success"**. If any step fails, the deployment is marked failed instead of silently half-working.
5. Prints the website link.

### 12.3 AWS Academy Learner Lab specifics
- **Region:** us-east-1.
- **No IAM role creation:** Learner Lab blocks it, so the server uses the lab's `LabInstanceProfile`.
- **Sessions last 4 hours.** When a session ends, the server stops. It starts again, with the website, when you click Start Lab. The Elastic IP keeps the same address.
- **Credentials:** copy them from *AWS Details → AWS CLI* into `%USERPROFILE%\.aws\credentials`. They expire with the session.
- **Cost:** about $1/day while running, paid from lab credits. Students pay nothing.

[DEPLOYMENT.md](DEPLOYMENT.md) also covers the manual (console) route, the security checks to screenshot, the load test, and teardown.

---

## 13. Security in detail

| Layer | Protection |
|---|---|
| **Identity** | The server uses an **IAM role**, never stored access keys. The role (on own accounts) allows only: this bucket, `/traffic/*` parameters, CloudWatch metrics. That is **least privilege** |
| **Secrets** | Database password, admin password + hash, and session key are **SecureString** parameters in SSM (encrypted with KMS). They never appear in code, Git or `.env` |
| **Network** | RDS is **not publicly accessible**. Its security group allows port 5432 only from the web server's security group. The web server opens only port 80; **no SSH port** |
| **Storage** | S3 blocks all public access and encrypts objects (SSE-S3). RDS storage and the EC2 disk are encrypted |
| **Server** | IMDSv2 required (protects the instance's credentials from a common attack). The app runs as `ec2-user`, not root. nginx hides its version |
| **Application** | Admin pages need a login; the password is checked against a hash. Cookies are `HttpOnly` and `SameSite=Lax` (blocks cross-site form attacks). After login, the app only redirects to its own pages. Uploads must be `.csv`/`.csv.gz`, at most 20 MB, and parse correctly *before* they reach S3. All SQL is parameterised (no SQL injection). Error pages don't show internals |
| **Code** | `.env`, data, databases and model files are git-ignored. The proposal PDF (with phone numbers) is kept out of the public repo |

---

## 14. Monitoring in detail

| What | How |
|---|---|
| Server CPU, memory, disk | **CloudWatch Agent**, every 60 s. Memory needs the agent because the hypervisor can't see inside the VM |
| Logs | The agent ships `/var/log/traffic/app.log`, `access.log`, `pipeline.log` and nginx's access log to 4 log groups (kept 7 days) |
| Our own metrics | The pipeline publishes `RowsLoaded`, `PipelineDurationSec`, `PipelineFailures` and `ModelRMSE` (namespace `TrafficAnalytics`) |
| Alarms | `traffic-ec2-cpu-high` (CPU > 70% for 2 minutes), `traffic-rds-low-storage` (< 2 GB free), `traffic-pipeline-failed` (any failed ETL). All notify the SNS topic `traffic-alerts` |
| Dashboard | CloudWatch dashboard **TrafficAnalytics** (CPU, memory/disk, RDS CPU/connections, pipeline, alarm status) |
| In the app | The **System** page reads the same metrics with `GetMetricData` and shows every pipeline run |

**Demo idea.** Run the load test (`locust … -u 100`). CPU climbs on the System page and the CloudWatch dashboard, the
CPU alarm fires within about 2 minutes, and an email arrives.

---

## 15. Testing and quality

**14 automated tests** (`pytest -q`):

| Test file | Checks |
|---|---|
| `test_congestion.py` | Exact level boundaries (0.399 → Low, 0.40 → Moderate, …); capacity = 95th percentile and never 0 |
| `test_features.py` | Lags use only past hours (no leakage); a missing hour doesn't shift lags; every cleaning rule on a crafted UCI sample; unknown CSV formats are rejected |
| `test_end_to_end.py` | Builds 2 synthetic roads × 60 days, runs the **whole pipeline** (storage → ETL → DB → train → predict), then checks: `/health`; every road has a level and next-hour forecast; 6 future hours exist; RF beats the baseline; the test period comes after training; patterns/traffic APIs work; reloading the same file adds 0 rows; admin pages need a login; bad uploads are rejected and good ones reach storage |

Other quality work:
- **Continuous integration:** GitHub Actions runs all tests on Python 3.11 (the same version as the EC2 server) on every push.
- **Load test:** `loadtest/locustfile.py` simulates dashboard users.
- **Traceability:** [REQUIREMENTS.md](REQUIREMENTS.md) marks each requirement Met / Built / Pending, with evidence. Nothing is claimed without proof.

---

## 16. Limitations and future work

**Limitations (say these honestly in the viva):**
- **Capacity is estimated** (95th percentile), because real lane capacity isn't in the data.
- **One real station.** The other six roads are synthetic, so the map shows the method rather than a real city network.
- **Forecasts beyond 1 hour** reuse earlier predictions and carry the last weather forward, so error grows.
- **The data is historical (2012–2018).** "Now" means the latest hour in the database.
- **Single server, single-AZ database.** Fine for a demo, not highly available.

**Future work:**
- live data from a real traffic API
- a weather-forecast API for future hours
- deep learning (LSTM) models
- an Auto Scaling Group behind a load balancer
- Multi-AZ RDS
- HTTPS with a domain name, or CloudFront
- S3 event triggers with AWS Lambda instead of cron

---

## 17. Viva questions and answers

**Q1. Where exactly is the cloud in your project?**
Everywhere:
- data is stored in S3 (files) and RDS (records)
- all processing and ML runs on EC2
- the website is served from EC2
- access is controlled by IAM and security groups, with secrets in SSM
- it is monitored by CloudWatch and SNS
- it is deployed by CloudFormation

**Q2. Which service models do you use?**
IaaS: EC2, where we manage the OS and app. PaaS: RDS, where AWS manages the database engine. S3 is storage as a
service, and CloudWatch/SNS are managed services we just configure.

**Q3. Why EC2 and not Lambda?**
We run a web dashboard all the time and train models. EC2 suits long-running processes and was named in our proposal.
Lambda has a 15-minute limit and would need extra services (API Gateway) for the website. A good future step is
Lambda for event-driven ETL.

**Q4. Why RDS and not DynamoDB?**
Our data is relational time series. We filter by time ranges, join locations, and aggregate, and SQL does this
naturally. RDS also handles patching and backups for us.

**Q5. Why S3 and RDS both?**
They suit different data. S3 holds files: raw CSVs, processed copies, model files. It's cheap and durable. RDS holds
structured rows the dashboard queries quickly.

**Q6. How does the server access S3 without a password?**
Through an **IAM role** attached to the instance. AWS gives the server temporary credentials automatically through
the instance metadata service (IMDSv2), and boto3 picks them up. No keys are stored.

**Q7. How is the database protected?**
It isn't publicly accessible. Its security group allows port 5432 only from the web server's security group. Its
password is a random string in SSM, and its storage is encrypted.

**Q8. What is a security group?**
A virtual firewall for an instance. Ours allow only HTTP to the web server, and only the web server to reach the
database. Rules can name another security group as the source, as ours do.

**Q9. What is the shared responsibility model?**
AWS secures the cloud itself: hardware, data centres, and the hypervisor. We secure what we put in it: the OS on EC2,
our code, IAM permissions, firewall rules and our data.

**Q10. How would your system scale to 100× more users?**
1. The web tier is stateless, so put an Auto Scaling Group behind an Application Load Balancer.
2. Use a bigger RDS instance, or read replicas.
3. S3 scales automatically.
4. Move ETL to event-driven Lambda.

**Q11. What is CloudFormation / infrastructure as code?**
Describing infrastructure in a text template, so it can be created, reviewed, version-controlled and deleted
automatically. Our template creates about 15 resources with one command.

**Q12. How do you define congestion?**
Volume ÷ capacity. Capacity is estimated as the 95th percentile of hourly volume. The levels are < 0.4 Low, < 0.7
Moderate, < 0.9 High, ≥ 0.9 Severe.

**Q13. Why a time-based split and not a random split?**
A random split lets the model train on hours *after* the ones it's tested on, which leaks the future. A time split
tests honestly on later, unseen data, exactly like real forecasting.

**Q14. Why does Random Forest beat Linear Regression?**
Traffic patterns are non-linear and interact: hour × weekday × holiday. Trees capture this; a linear sum can't.

**Q15. What do MAE, RMSE and R² mean?**
- **MAE**: average error in vehicles/hour.
- **RMSE**: like MAE but punishes big errors more.
- **R²**: share of variation explained (1 = perfect).

Ours: MAE 218, RMSE 327, R² 0.966.

**Q16. What is data leakage, and how did you prevent it?**
Leakage is when the model sees information it wouldn't have at prediction time. All our lags look only backwards, gaps
are respected, and a test checks it.

**Q17. Why does memory monitoring need the CloudWatch Agent?**
EC2's built-in metrics come from the hypervisor, which can see CPU but not memory inside the OS. The agent runs inside
the VM and reports memory and disk.

**Q18. What happens if the pipeline fails?**
The run is recorded as "failed" with the error in `pipeline_runs`, and the `PipelineFailures` metric triggers an alarm
and an email. Other files still process. A lock prevents two runs at once.

**Q19. How much does it cost?**
About $0.04/hour ($1/day) while running, from Learner Lab credits. `python deploy/aws.py down` deletes everything so
the cost stops.

**Q20. What is the role of nginx and gunicorn?**
- gunicorn runs the Flask app with several worker processes.
- nginx is the front door on port 80: it handles connections efficiently, limits upload size, and passes requests to gunicorn.
- Flask's own server is only for development.

---

## 18. Glossary

| Term | Meaning |
|---|---|
| **AMI** | Amazon Machine Image: the OS template an EC2 instance starts from (Amazon Linux 2023) |
| **AZ** | Availability Zone: a separate data centre within a region |
| **boto3** | The official AWS library for Python |
| **CI** | Continuous integration: automatic tests on every code change |
| **cron** | Linux scheduler that runs commands at set times |
| **Elastic IP** | A fixed public IP address that stays with your instance |
| **ETL** | Extract, Transform, Load: read raw data, clean it, store it |
| **IaC** | Infrastructure as code (CloudFormation) |
| **IMDSv2** | Secure way for an instance to get its temporary role credentials |
| **Lag feature** | A past value of the target used as a model input |
| **Least privilege** | Grant only the permissions actually needed |
| **SecureString** | An encrypted parameter in SSM Parameter Store |
| **Stateless** | Keeps no data locally, so it can be replaced or copied freely |
| **systemd** | Linux service manager; keeps our web app running and restarts it |
| **Upsert** | Insert, or skip/update if the row already exists |
| **V/C ratio** | Volume ÷ capacity, the congestion measure |

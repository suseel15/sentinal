# 🛡️ SENTINEL
## AI-Powered Financial Crime Investigation Platform

> **An intelligent, multi-agent financial crime investigation platform that combines Rules, Machine Learning, Anomaly Detection, Graph Intelligence, Evidence Analysis, Regulatory RAG, and AI Agents to help investigators detect and investigate suspicious financial activity.**

---

# 📌 Overview

SENTINEL is an AI-powered **Financial Crime Investigation Platform** designed to support banks and financial institutions in investigating suspicious transactions.

Traditional Transaction Monitoring Systems (TMS) generate alerts based mainly on predefined rules. However, investigators often need to manually collect transaction history, customer information, network relationships, evidence, regulatory information, and previous investigation results.

SENTINEL solves this problem by building an automated investigation pipeline.

The platform does **not replace an existing bank Transaction Monitoring System**. Instead, it sits on top of existing monitoring systems and transforms suspicious alerts into structured, evidence-backed investigations.

The complete workflow is:

```text
Transaction / Alert
        │
        ▼
Pre-Filter & Triage
        │
        ▼
Signal Ingestion
        │
        ▼
Rules + ML + Anomaly Detection
        │
        ▼
Detection Fusion
        │
        ├───────────────┐
        ▼               ▼
Evidence Analysis   Graph Intelligence
        │               │
        └───────┬───────┘
                ▼
        Regulatory Analysis
                │
                ▼
        Investigation Report
                │
                ▼
      Action Recommendation
                │
                ▼
        Human Investigator
                │
                ▼
      Continuous Learning
```

---

# 🎯 Problem Statement

Financial institutions process millions of transactions every day.

Existing fraud and AML monitoring systems face several problems:

- Large numbers of false-positive alerts.
- Difficulty detecting new fraud patterns.
- Limited explanation for why a transaction was flagged.
- Manual investigation processes.
- Difficulty analyzing complex money-transfer networks.
- Lack of integration between fraud detection and investigation.
- Difficulty connecting suspicious accounts and entities.
- Regulatory analysis requires significant manual effort.
- Investigators spend time collecting evidence instead of analyzing cases.

SENTINEL addresses these problems by combining:

- Rule-based detection
- Supervised Machine Learning
- Unsupervised Anomaly Detection
- Behavioral Analysis
- Graph-based Network Intelligence
- Evidence Retrieval
- Regulatory RAG
- AI Agents
- Explainable AI
- Human-in-the-loop decision making

---

# 🚀 Key Features

## 🔍 Intelligent Fraud Detection

SENTINEL analyzes transactions using multiple detection techniques instead of relying on a single ML model.

The system combines:

- AML Rules Engine
- Fraud Rules Engine
- XGBoost / LightGBM / CatBoost
- Isolation Forest
- Autoencoder
- Behavioral Deviation Analysis

These signals are combined using a **Detection Fusion Model**.

---

## 🧠 Multi-Layer ML Architecture

The core ML architecture uses three major intelligence layers.

```text
                TRANSACTION DATA
                       │
                       ▼
             FEATURE ENGINEERING
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼

   XGBoost Model   Isolation Forest   Autoencoder
   Known Fraud      Novel Anomaly      Complex Pattern
        │              │              │
        └──────────────┼──────────────┘
                       ▼
               DETECTION FUSION
                       │
                       ▼
                 FINAL RISK SCORE
```

### Layer 1 — Supervised Fraud Detection

**Model: XGBoost**

Purpose:

Detect known fraud patterns using historical labeled transaction data.

Example patterns:

- Suspicious transaction amount
- High transaction velocity
- Unusual destination
- Suspicious beneficiary
- Sudden behavioral changes
- Previously confirmed fraud patterns

Output:

```text
Fraud Probability = 0.82
```

---

### Layer 2 — Unsupervised Anomaly Detection

**Model: Isolation Forest**

Purpose:

Detect unusual transactions that may represent new or unknown fraud patterns.

Isolation Forest does not depend entirely on fraud labels.

It identifies transactions that are statistically different from normal transactions.

Example:

```text
Customer normally transfers:

₹10,000 – ₹50,000

Suddenly transfers:

₹45,00,000
```

The transaction receives a high anomaly score.

---

### Layer 3 — Deep Pattern Detection

**Model: Autoencoder**

Purpose:

Learn the normal structure of financial transactions.

The Autoencoder is trained mainly on normal transactions.

```text
Input Transaction
        │
        ▼
Encoder
        │
        ▼
Latent Representation
        │
        ▼
Decoder
        │
        ▼
Reconstructed Transaction
```

If reconstruction error is high:

```text
Original Transaction
       ≠
Reconstructed Transaction
```

The transaction may represent an unusual or novel pattern.

---

# 🔥 Detection Fusion Engine

One of the most important innovations in SENTINEL is the **Detection Fusion Engine**.

Instead of simply using:

```python
if model1 or model2 or model3:
    fraud = True
```

SENTINEL combines all signals intelligently.

Inputs include:

```text
AML Rule Score
Fraud Rule Score
XGBoost Probability
Isolation Forest Score
Autoencoder Reconstruction Error
Behavioral Deviation Score
Peer Group Deviation
Transaction Velocity
```

These values are passed to a meta-model.

```text
RULES
  │
  ├──────────────┐
  │              │
ML MODELS        │
  │              ▼
  ├──────► DETECTION FUSION MODEL
  │              │
ANOMALY MODELS   │
  │              ▼
  └──────────► FINAL RISK SCORE
```

The output contains:

```json
{
  "risk_score": 87,
  "confidence": 0.91,
  "risk_level": "HIGH",
  "detected_typologies": [
    "UNUSUAL_TRANSACTION",
    "POSSIBLE_MONEY_LAUNDERING"
  ]
}
```

---

# 🤖 Multi-Agent Architecture

SENTINEL uses specialized AI agents.

Each agent has one responsibility.

```text
One Responsibility
        ↓
One Owner
        ↓
One Calculation
        ↓
One Canonical Result
```

---

# 🧩 A1 — Signal Ingestion Agent

### Responsibilities

- Receive transaction data
- Validate required fields
- Normalize data
- Detect duplicates
- Create canonical transaction IDs
- Create investigation IDs

Example:

```text
Transaction ID:

TXN202600001

Investigation ID:

INV202600001
```

---

# 🚨 A2 — Anomaly Detection Agent

A2 is the main detection intelligence layer.

It combines:

### AML Rules

Detects patterns such as:

- Structuring
- Rapid movement of funds
- Unusual transaction behavior
- High-value transfers
- Circular transactions

### Fraud Rules

Detects:

- Account takeover
- Suspicious UPI behavior
- Card fraud
- Device anomalies
- Velocity attacks

### Machine Learning

Uses:

- XGBoost
- Isolation Forest
- Autoencoder
- Behavioral Analysis

### Detection Fusion

Combines all signals into one canonical result.

Output:

```json
{
  "risk_score": 87,
  "confidence": 0.91,
  "model_version": "v1.0",
  "rule_version": "v1.0"
}
```

---

# 📂 A3 — Evidence Gathering Agent

The Evidence Agent collects supporting information.

Sources include:

### Internal Sources

- KYC information
- Transaction history
- Previous alerts
- Previous investigations
- Account information
- Device history

### External Sources

- Sanctions information
- PEP information
- Adverse media
- Public registries

### Historical Sources

- Similar previous fraud cases

The agent follows:

```text
Retrieve Evidence
        ↓
Validate Evidence
        ↓
Score Evidence
        ↓
Attach Evidence ID
```

The system never allows unsupported evidence to be presented as fact.

---

# 🕸️ A4 — Entity Resolution and Graph Intelligence Agent

A4 analyzes relationships between:

- Customers
- Accounts
- Transactions
- Devices
- Phone numbers
- IP addresses
- Companies
- Beneficiaries

Example:

```text
Customer A
    │
    ▼
Account A
    │
    ▼
Account B
    │
    ▼
Account C
```

The system can identify:

- Mule account chains
- Fan-in patterns
- Fan-out patterns
- Circular transactions
- Shared identities
- Suspicious communities
- Rapid money movement

---

# 🌐 Graph Explosion Protection

Financial graphs can contain thousands of connected accounts.

SENTINEL avoids dangerous unbounded traversal.

The graph strategy is:

```text
Flagged Account
       │
       ▼
Super-Node Check
       │
   ┌───┴────┐
   │        │
 HUB      NORMAL
   │        │
   ▼        ▼
Hub-Aware  Bounded
Analysis   Traversal
           │
           ▼
      Max 4 Hops
      Max 2,000 Nodes
```

If the graph becomes too large:

```text
GRAPH_ANALYSIS_INCOMPLETE
        │
        ▼
Manual Investigation Required
```

The system does not generate false conclusions from excessively large graphs.

---

# ⚖️ A5 — Regulatory Risk Agent

The Regulatory Agent uses **RAG (Retrieval Augmented Generation)**.

The process is:

```text
Investigation Findings
        │
        ▼
Regulatory Document Retrieval
        │
        ▼
Relevant Regulations
        │
        ▼
AI Interpretation
        │
        ▼
Citation Verification
```

The system provides:

```text
Potential Regulatory Relevance
```

It does **not provide autonomous legal decisions**.

---

# 📜 A6 — Audit Trail Agent

Every important action is recorded.

The audit system stores:

- Agent ID
- Timestamp
- Input artifacts
- Output artifacts
- Model version
- Rule version
- Evidence IDs
- Risk scores
- Human decisions

Example:

```json
{
  "investigation_id": "INV202600001",
  "agent": "A2",
  "model_version": "xgboost_v1",
  "risk_score": 87,
  "timestamp": "2026-09-05T10:00:00"
}
```

---

# 📝 A7 — Narrative Generation Agent

A7 generates the investigation report.

The report is created using:

```text
Structured Data
        +
Evidence
        +
Graph Findings
        +
Regulatory Analysis
        ↓
Investigation Report
```

The LLM is used mainly for explanation and narrative generation.

The LLM does not independently calculate fraud scores.

---

# 🎯 A8 — Action Recommendation Agent

A8 recommends actions such as:

```text
CLEAR

MONITOR

FURTHER INVESTIGATION

ESCALATE

COMPLIANCE REVIEW

STR REVIEW
```

The final decision always belongs to a human investigator.

---

# 👨‍⚖️ Human-in-the-Loop

SENTINEL is designed to assist humans, not replace them.

```text
AI Recommendation
        │
        ▼
Human Investigator
        │
 ┌──────┼───────┐
 ▼      ▼       ▼
ACCEPT OVERRIDE ESCALATE
```

The investigator decision is stored and used for future learning.

---

# 🔄 Continuous Learning System

SENTINEL improves over time.

```text
Human Decision
       │
       ▼
Outcome Label Store
       │
       ├────────► ML Retraining
       │
       ├────────► Rule Optimization
       │
       ├────────► Threshold Tuning
       │
       └────────► Performance Monitoring
```

---

# 📊 Feature Engineering

The ML models use engineered features.

## Transaction Features

```text
transaction_amount
transaction_type
transaction_channel
transaction_time
sender_balance
receiver_balance
```

## Velocity Features

```text
transactions_last_1_hour
transactions_last_24_hours
amount_last_1_hour
amount_last_24_hours
unique_beneficiaries
```

## Behavioral Features

```text
amount_vs_customer_average
amount_vs_customer_median
time_deviation
location_deviation
beneficiary_novelty
```

## Peer Group Features

```text
peer_group_id
amount_vs_peer_average
amount_percentile_in_peer_group
```

## Risk Features

```text
aml_rule_score
fraud_rule_score
device_risk_score
behavior_risk_score
```

---

# 🗄️ Database Architecture

SENTINEL uses **Supabase** as the main database platform.

Supabase provides:

- PostgreSQL
- Authentication
- Realtime capabilities
- Storage
- REST APIs

Main tables include:

```text
transactions
customers
accounts
investigations
rule_results
model_results
evidence
graph_entities
graph_relationships
regulatory_results
reports
actions
audit_logs
feedback
```

---

# ⚡ Real-Time Transaction Streaming

Transactions can be received as a live stream.

```text
Transaction Dataset
        │
        ▼
Transaction Producer
        │
        ▼
FastAPI Backend
        │
        ▼
Pre-Filter
        │
        ▼
Feature Engineering
        │
        ▼
ML Detection
        │
        ▼
Supabase Storage
        │
        ▼
Frontend Dashboard
```

---

# 🛠️ Technology Stack

## Frontend

```text
Next.js
React
TypeScript
Tailwind CSS
```

## Backend

```text
Python
FastAPI
Pydantic
Uvicorn
```

## Machine Learning

```text
Python
XGBoost
LightGBM
CatBoost
Scikit-learn
PyTorch
SHAP
```

## Database

```text
Supabase
PostgreSQL
```

## Graph Intelligence

```text
Neo4j Community Edition
NetworkX
```

## AI / LLM

```text
NVIDIA Free Tier Models
NVIDIA NIM
Open-source LLMs
```

## Orchestration

```text
LangGraph
```

## Vector Search

```text
pgvector
ChromaDB
```

## Monitoring

```text
Prometheus
Grafana
```

---

# 📁 Project Structure

```text
sentinel/
│
├── backend/
│   │
│   ├── main.py
│   │
│   ├── api/
│   │   ├── transactions.py
│   │   ├── investigations.py
│   │   ├── reports.py
│   │   └── agents.py
│   │
│   ├── ml/
│   │   ├── xgboost_model.py
│   │   ├── isolation_forest.py
│   │   ├── autoencoder.py
│   │   ├── behavioral_model.py
│   │   └── fusion_model.py
│   │
│   ├── rules/
│   │   ├── aml_rules.py
│   │   └── fraud_rules.py
│   │
│   ├── agents/
│   │   ├── a1_ingestion.py
│   │   ├── a2_detection.py
│   │   ├── a3_evidence.py
│   │   ├── a4_graph.py
│   │   ├── a5_regulatory.py
│   │   ├── a6_audit.py
│   │   ├── a7_narrative.py
│   │   └── a8_action.py
│   │
│   ├── services/
│   │   ├── supabase_service.py
│   │   ├── feature_service.py
│   │   └── stream_service.py
│   │
│   └── requirements.txt
│
├── frontend/
│   │
│   ├── app/
│   ├── components/
│   ├── lib/
│   └── package.json
│
├── datasets/
│
├── notebooks/
│   ├── 01_data_analysis.ipynb
│   ├── 02_feature_engineering.ipynb
│   ├── 03_xgboost_training.ipynb
│   ├── 04_anomaly_detection.ipynb
│   ├── 05_autoencoder_training.ipynb
│   └── 06_fusion_model.ipynb
│
├── models/
│
├── docs/
│
└── README.md
```

---

# 🚀 Installation

## 1. Clone the Project

```bash
git clone <your-repository-url>
cd sentinel
```

---

# 🐍 Backend Setup

Navigate to the backend folder:

```bash
cd backend
```

Create a virtual environment:

```bash
python -m venv venv
```

Activate it.

Windows:

```bash
venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the backend:

```bash
uvicorn main:app --reload
```

The backend should start on:

```text
http://localhost:8000
```

API documentation:

```text
http://localhost:8000/docs
```

---

# 💻 Frontend Setup

Navigate to the frontend folder:

```bash
cd frontend
```

Install dependencies:

```bash
npm install
```

Create:

```text
.env.local
```

Add:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Run:

```bash
npm run dev
```

Open:

```text
http://localhost:3000
```

---

# 🗄️ Supabase Configuration

Create a Supabase project.

Add environment variables:

```env
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
```

For frontend:

```env
NEXT_PUBLIC_SUPABASE_URL=your_url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key
```

---

# 📡 API Architecture

Example transaction request:

```json
{
  "transaction_id": "TXN001",
  "sender_account": "ACC1001",
  "receiver_account": "ACC2001",
  "amount": 4500000,
  "transaction_type": "BANK_TRANSFER",
  "timestamp": "2026-09-05T10:00:00"
}
```

The backend processes:

```text
Transaction
      ↓
Validation
      ↓
Feature Engineering
      ↓
Rules Engine
      ↓
XGBoost
      ↓
Isolation Forest
      ↓
Autoencoder
      ↓
Fusion Model
      ↓
Risk Score
```

---

# 📈 Example Detection Result

```json
{
  "investigation_id": "INV2026-00001",
  "transaction_id": "TXN001",

  "risk_score": 87,

  "risk_level": "HIGH",

  "confidence": 0.91,

  "ml_results": {
    "xgboost_probability": 0.81,
    "isolation_score": 0.93,
    "autoencoder_error": 0.78
  },

  "rules_triggered": [
    "AML_UNUSUAL_AMOUNT",
    "RAPID_FUND_MOVEMENT"
  ],

  "recommended_action": "ESCALATE"
}
```

---

# 🧪 Machine Learning Evaluation

Because fraud datasets are highly imbalanced, SENTINEL does not rely only on accuracy.

The models are evaluated using:

```text
Precision
Recall
F1 Score
ROC-AUC
PR-AUC
Precision@K
Recall@K
```

The most important objective is:

> Detect more real suspicious transactions while minimizing unnecessary alerts.

---

# 🔐 Security Principles

SENTINEL follows:

- Role-Based Access Control
- Human-in-the-loop decision making
- Audit logging
- Model version tracking
- Rule version tracking
- Evidence-backed AI
- PII protection
- Data minimization
- Explainable AI

---

# 🧠 Explainable AI

SENTINEL uses **SHAP** to explain ML predictions.

Example:

```text
Risk Score: 87

Top Contributing Factors:

1. Transaction amount significantly above normal
2. New beneficiary
3. High transaction velocity
4. Behavioral deviation
5. AML structuring rule triggered
```

This allows investigators to understand:

> Why did the system flag this transaction?

---

# 🗺️ Development Roadmap

## ✅ Phase 1 — Core Detection

- Dataset preparation
- Feature engineering
- AML rules
- Fraud rules
- XGBoost model
- Isolation Forest
- Autoencoder
- Detection Fusion

## ✅ Phase 2 — Real-Time Backend

- FastAPI
- Live transaction ingestion
- ML inference APIs
- Supabase integration

## ✅ Phase 3 — Investigation Dashboard

- Next.js frontend
- Risk dashboard
- Transaction monitoring
- Investigation details

## 🚧 Phase 4 — Evidence Intelligence

- Evidence gathering
- KYC integration
- Historical cases
- Evidence scoring

## 🚧 Phase 5 — Graph Intelligence

- Neo4j
- Entity resolution
- Money-flow analysis
- Mule-chain detection
- Hub-aware graph traversal

## 🚧 Phase 6 — Regulatory Intelligence

- Regulatory document database
- RAG pipeline
- Citation verification

## 🚧 Phase 7 — AI Investigation Agents

- LangGraph orchestration
- NVIDIA LLM integration
- Agent workflows

## 🚧 Phase 8 — Continuous Learning

- Investigator feedback
- Model retraining
- Drift detection
- Rule optimization

---

# 🏆 Key Innovation

The main innovation of SENTINEL is that it does not depend on only one fraud detection technique.

Instead:

```text
                 RULES
                   │
                   ▼
             Known Patterns

                 +
                 │

             XGBOOST
                   │
                   ▼
             Known Fraud

                 +
                 │

          ISOLATION FOREST
                   │
                   ▼
             Unknown Anomalies

                 +
                 │

            AUTOENCODER
                   │
                   ▼
          Complex Hidden Patterns

                 +
                 │

         DETECTION FUSION
                   │
                   ▼
           EXPLAINABLE RISK SCORE

                 +
                 │

          AI INVESTIGATION
                   │
                   ▼
       EVIDENCE + GRAPH + REGULATION

                 +
                 │

          HUMAN INVESTIGATOR
```

This makes SENTINEL an **intelligent investigation platform**, rather than just another fraud classifier.

---

# ⚠️ Important Disclaimer

SENTINEL is an **investigation support system**.

It does not:

- Automatically declare a person guilty.
- Make autonomous legal decisions.
- Replace compliance officers.
- Replace human investigators.

All high-risk recommendations require human review.

---

# 👨‍💻 Author

**Suseel P S**

B.Tech — Artificial Intelligence and Data Science

---

# 📄 License

This project is developed for educational, research, and academic purposes.

---

# 🌟 Final Vision

> **SENTINEL transforms financial crime detection from a simple alert-generation system into a complete AI-powered investigation ecosystem.**

```text
Detect
   ↓
Understand
   ↓
Investigate
   ↓
Collect Evidence
   ↓
Analyze Networks
   ↓
Check Regulatory Relevance
   ↓
Generate Report
   ↓
Recommend Action
   ↓
Human Decision
   ↓
Learn and Improve
```

# 🛡️ SENTINEL

### **Detect Smarter. Investigate Deeper. Decide with Evidence.**
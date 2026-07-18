# 🔬 Ramesh Saini v7.1 — Architecture Proof-of-Concept Monorepo

**5 Isolated PoCs** to mathematically and technically validate the core architectural claims of "Ramesh Saini v7.1" — a next-gen AI desktop application framework.

## Structure

```
ramesh-saini-v7.1-poc/
├── poc-ipc/             # PoC 1: Size & IPC Test (Electron + Python FastIPC)
├── poc-memory/          # PoC 2: Unified Memory (SQLite + sqlite-vec + JSONB)
├── poc-agent/           # PoC 3: Stateful Agent (LangGraph + SqliteSaver)
├── poc-control/         # PoC 4: Browser & OS Control (Raw CDP + UIA)
├── poc-security/        # PoC 5: Pre-Crime Security (AST Analysis)
├── .github/workflows/   # CI/CD pipeline
│   ├── verify-architecture.yml  # Main CI workflow
│   └── generate-report.py       # Report generator
└── README.md
```

## The 5 PoCs

| PoC | Claim | Technology | Success Criteria |
|-----|-------|-----------|-----------------|
| **1** | Embedded Python IPC | Electron + FastAPI stdio | < 50ms latency, 10MB payload, < 200MB installer |
| **2** | Unified Memory Store | SQLite + sqlite-vec + JSONB | 10K inserts, hybrid search < 100ms |
| **3** | Crash Recovery | LangGraph + SqliteSaver | Resume exact checkpoint after crash |
| **4** | OS/Browser Control | Raw CDP + UIA (no Playwright) | Coordinate-free element targeting |
| **5** | Pre-Crime Security | AST parser | 100% block rate (malicious), 100% pass rate (safe) |

## Running Locally

```bash
# PoC 1: IPC
cd poc-ipc && pip install -r requirements.txt && node test/ipc-test.js

# PoC 2: Memory
cd poc-memory && pip install -r requirements.txt && python -m pytest test/ -v

# PoC 3: Agent
cd poc-agent && pip install -r requirements.txt && python -m pytest test/ -v

# PoC 4: Control
cd poc-control && node test/cdp-test.js && python -m pytest test/test_uia.py -v

# PoC 5: Security
cd poc-security && python -c "import sys; sys.path.insert(0,'src'); from precrime_analyzer import create_test_fixtures; create_test_fixtures()"
python -m pytest test/ -v
```

## CI Pipeline

GitHub Actions workflow (`.github/workflows/verify-architecture.yml`):
- Runs all 5 PoCs on `ubuntu-latest` AND `windows-latest`
- Generates `verification-report.md` with Pass/Fail + metrics
- Security gate validates 100% block/pass rate

## Architecture Claims

| # | Claim | Verification |
|---|-------|-------------|
| 1 | IPC < 50ms latency | `poc-1-ipc` — pytest benchmark |
| 2 | Single DB for all memory patterns | `poc-2-memory` — SQLite + vec + JSONB |
| 3 | Process crash → resume from checkpoint | `poc-3-agent` — LangGraph SqliteSaver |
| 4 | UIA by properties > clicks by coords | `poc-4-control` — Raw CDP + accessibility |
| 5 | 100% malicious code detection | `poc-5-security` — AST scanner, 50/50 fixtures |

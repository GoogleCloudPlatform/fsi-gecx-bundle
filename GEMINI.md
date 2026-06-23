# Gemini CLI Context: FSI GECX Bundle

This project is a comprehensive solution for the Financial Services Industry (FSI) demonstrating Gemini Enterprise for Customer Experience (GECX) capabilities through a Mortgage Preapproval assistant.

## Project Overview

The solution consists of:
- **Banking Service (`banking-service/`)**: A FastAPI backend providing core banking functionality, artifact management (PDF processing), and identity integration. It uses Google Cloud Storage, BigQuery, and Secret Manager.
- **Banking UI (`banking-ui/`)**: A React/Vite frontend providing a user interface for interacting with the banking services and the GECX agent.
- **GECX Configurations (`gecx/`)**: YAML and JSON definitions for Gemini agents, tools, and guardrails, specifically for the "Mortgage Preapproval" use case.
- **Infrastructure (`deployment/`)**: Terraform configurations to deploy the entire stack on Google Cloud, including Cloud Run, IAP-secured Load Balancing, and BigQuery.

### Core Technologies
- **Language**: Python (Backend), JavaScript/React (Frontend), HCL (Terraform)
- **Frameworks**: FastAPI, React 19, Vite, Tailwind CSS
- **GCP Services**: Cloud Run, Cloud Build, BigQuery, Secret Manager, IAP, Vertex AI, Dialogflow
- **AI**: Gemini Enterprise for Customer Experience (GECX)

## Building and Running

### Backend (`banking-service`)
Requires `uv` for python environment management.
```bash
cd banking-service
./run.sh
```
Alternatively:
```bash
cd banking-service
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

### Frontend (`banking-ui`)
```bash
cd banking-ui
npm install
npm run dev
```

### Infrastructure Deployment
Refer to the root `README.md` for detailed manual setup steps (OAuth client, Secrets) before running Terraform.
```bash
cd deployment/terraform
terraform init -backend-config=./environment/[BACKEND_FILE]
terraform apply -var-file ./terraform.tfvars
```

## Development Conventions

### Backend
- **Structure**: Follows a standard FastAPI layout with `routers/`, `models/`, and `utils/`.
- **Authentication**: Uses Identity-Aware Proxy (IAP) for user context. Local development can bypass this via environment flags.
- **Testing**: Use `pytest` for backend testing.
- **MCP**: Supports Model Context Protocol (MCP) via `fastmcp`.

### Frontend
- **Styling**: Uses Tailwind CSS (v4) for utility-first styling.
- **Icons**: Uses `lucide-react`.

### GECX
- Agents and tools are defined in both JSON and YAML formats within the `gecx/` directory.
- The "Home Loan Assistant" is the root agent for the Mortgage Preapproval flow.

## 🤖 AI Developer Guardrails & Behavioral Guidelines

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## 5. Objective Communication & Tone

**Maintain a direct, neutral, and matter-of-fact tone. Avoid flattery, excessive formalities, and subjective praise.**

When writing PR descriptions, reviews, commit messages, or communicating with the team:
- Use plain, direct, and purely technical language.
- Avoid subjective adjectives and exaggerated praise (e.g., "fantastic job", "outstanding commit", "flawless refactor").
- Present engineering facts and verified outcomes without self-congratulation or empty pleasantries.
- Frame feedback around code metrics and clear logical arguments rather than personal compliments.

## 6. Git Commit & Deployment Lifecycle Control

**Iterate fast locally. Do NOT automatically commit, push, or redeploy without explicit instruction.**

To prevent Git history clutter and optimize cloud build compute costs:
- Focus entirely on local file editing, validation, and local unit testing.
- Do NOT run git commit, git push, or GCP deployment commands automatically.
- Await an explicit request from the user before staging, committing, pushing, or triggering a new cloud build/redeployment.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

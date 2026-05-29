# PRD — Secrets Management and Environment Variables configuration

> **Stage 2 of 3 — Documentation Hierarchy**
> Owner: Winston (Architect) | Target Location: `docs/prd/secrets_management_prd.md`
> Status: `Draft` | Sign-off: Engineering Lead: _[Approved]_

---

## 1. Overview

**One-liner**:
Ensure all sensitive configuration is loaded from environment variables and untrack/ignore Streamlit secrets file `.streamlit/secrets.toml`.

**Brief / Problem Reference**:
Remediation of security review findings regarding Git-tracked secrets patterns in `.streamlit/secrets.toml`.

**What we are building** (What):
A configuration safeguard by moving all sensitive or environment-specific config variables to environment variables (e.g. loaded via `python-dotenv`), adding `.streamlit/secrets.toml` to `.gitignore`, untracking it from git, and providing a `.streamlit/secrets.toml.example` file for developers.

**Why now** (Strategic context):
Having `.streamlit/secrets.toml` tracked in git (even if it currently has non-sensitive identifiers) introduces a severe risk of developers accidentally committing real secrets or API keys.

---

## 2. Goals & Success Metrics

| Goal | Success Metric | Baseline | Target | Owner |
|------|---------------|----------|--------|-------|
| Prevent secret leaks | `.streamlit/secrets.toml` is untracked and ignored by Git | Tracked in Git | Untracked and ignored | Dev |
| Standardized configuration template | Developer template file provided | No template | `.streamlit/secrets.toml.example` exists | Dev |

**Anti-Goals**:
- We are not implementing a cloud secret store integration (e.g. AWS Secrets Manager or HashiCorp Vault) for this local application context.

---

## 3. Target Users & Personas

| Persona | Job-to-be-Done | Key Frustration | v1 Priority |
|---------|---------------|-----------------|-------------|
| Developer | Set up local configurations quickly without leaking credentials | Git tracks local configurations/secrets files by default | Primary |
| Security Auditor | Ensure the codebase contains no tracked/trackable secrets files | Risk of secret leak due to git-tracked `.toml` pattern | Primary |

---

## 4. User Stories

| ID | User Story | Priority (MoSCoW) | FR Reference |
|----|-----------|-------------------|--------------|
| US-001 | As a **Developer**, I want to copy a configuration example file so that I can configure my local environment quickly. | Must Have | FR-001 |
| US-002 | As a **Security Auditor**, I want all credentials/secret configuration files ignored by Git so that keys are never committed. | Must Have | FR-002, FR-003 |

---

## 5. Functional Requirements

| ID | Requirement | User Story | Priority |
|----|-------------|------------|----------|
| FR-001 | The system MUST provide a template configuration at `.streamlit/secrets.toml.example`. | US-001 | Must Have |
| FR-002 | The project's `.gitignore` MUST ignore `.streamlit/secrets.toml`. | US-002 | Must Have |
| FR-003 | Any active configuration MUST fallback to environment variables loaded via `.env` or system environment. | US-002 | Must Have |

---

## 6. Non-Functional Requirements

| Category | Requirement | Metric |
|----------|-------------|--------|
| **Security** | Zero files named `secrets.toml` tracked in Git | 100% compliance |

---

## 7. Scope

**v1 — In Scope**:
- Rename `.streamlit/secrets.toml` to `.streamlit/secrets.toml.example`.
- Untrack `.streamlit/secrets.toml` from Git (`git rm --cached`).
- Update `.gitignore` to include `.streamlit/secrets.toml`.

**v1 — Explicitly Out of Scope**:
- Rewriting the Streamlit app configuration parser if it does not use `secrets.toml`.

---

## 8. Acceptance Criteria

### User Acceptance Criteria (UAC)
- **UAC-001**: Given a developer starts a fresh checkout of the repo, when they look for Streamlit config, then they find `.streamlit/secrets.toml.example` and can copy it.
- **UAC-002**: Given a developer modifies `.streamlit/secrets.toml`, when they run `git status`, then they verify the file is not tracked by Git.

### Technical Acceptance Criteria (TAC)
- **TAC-001**: Git tracking audit shows `.streamlit/secrets.toml` is absent from tracked indexes.

---

## 9. Epic & Ballpark Estimation

### Component Breakdown
- **Untrack & Rename File**: Simple - 0.25 Day.
- **Gitignore Update**: Simple - 0.1 Day.

**Ballpark Estimate**: 0.35 Day
**Assumptions**: We do not need to rewrite any Python logic since no python module uses `st.secrets` directly.

---

## 10. Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1 | 2026-05-29 | Winston | Initial draft for secrets handling remediation |

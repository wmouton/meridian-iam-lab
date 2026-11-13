# 00 - Lab Setup Guide

Two tracks. Track A runs offline and needs only Python. Track B deploys the same design to an Entra ID tenant.

## Track A: offline (about 10 minutes)

```bash
git clone https://github.com/wmouton/meridian-iam-lab.git && cd meridian-iam-lab
uv sync                    # installs Python 3.12 if needed + locked dev tools into .venv
uv run pytest              # 30 tests
make demo                  # JML day 0 -> day 30, access review, remediation, re-review
```
No `make` (Windows)? Run the commands listed under `demo:` in the Makefile directly. Install [uv](https://docs.astral.sh/uv/) first (`curl -LsSf https://astral.sh/uv/install.sh | sh`, or `winget install astral-sh.uv` on Windows). Python 3.10+ is required (`.python-version` pins 3.12; uv downloads it automatically); there are no runtime dependencies, only dev tools (pytest, ruff).

## Track B: Microsoft Entra lab tenant

### 1. Get a tenant
* a Microsoft 365 Developer Program sandbox (check current eligibility; Microsoft has tightened it), or
* a free Azure account (it creates an Entra tenant), then start the Entra ID P2 trial (30 days) under Entra -> Licenses.
Never use your employer's or a production tenant.

### 2. Licences by feature
| Feature | Needs |
|---|---|
| Users, groups, SSO to enterprise apps (limited) | Free |
| Security Defaults | Free (can't run alongside Conditional Access; turn it off before deploying CA001-CA008) |
| Conditional Access, group-based app assignment, sign-in log export | P1 |
| PIM, risk-based CA (CA004/005), access reviews | P2 / ID Governance |
| Sentinel | Azure subscription; free trial / pay-as-you-go (set a budget alert) |

### 3. Tools
```powershell
Install-Module Microsoft.Graph -Scope CurrentUser         # PowerShell 7.2+
```
Create a separate admin account (`adm-yourname`) and use it for the lab. Keep two break-glass accounts (cloud-only, FIDO2 or very long random passwords stored offline).

### 4. Build order
| Step | Command / action | Evidence to capture |
|---|---|---|
| 1 | `./scripts/powershell/New-LabGroups.ps1 -WhatIf` then without `-WhatIf` | Group list screenshot |
| 2 | Edit `data/role_catalog.json` `company.domain` to your verified domain (e.g. `yourlab.onmicrosoft.com`), regenerate: `make data` | Diff of the change |
| 3 | `./scripts/powershell/Invoke-JmlSync.ps1 -HrFeed ./data/hr_feed_day0.csv -WhatIf` then real run | Console output, 200 users created |
| 4 | Register 2-3 SSO apps (one SAML, one OIDC; e.g. a free SaaS trial, the Entra gallery "SAML Toolkit" or a local OIDC sample) and assign `grp-app-*` groups | Enterprise app assignments; SAML assertion and OIDC token traces |
| 5 | `./scripts/powershell/New-ConditionalAccessPolicies.ps1 -BreakGlassGroupName grp-iam-breakglass` (report-only) | Insights workbook |
| 6 | Enforce CA policies per [04](04-authentication-and-conditional-access.md) | What-if results |
| 7 | `./scripts/powershell/New-PimEligibleAssignment.ps1 ...`, configure PIM role settings | PIM settings, activation audit entry |
| 8 | `./scripts/powershell/Invoke-JmlSync.ps1 -HrFeed ./data/hr_feed_day30.csv -AsOf 2026-10-30` | Movers/leavers output; groups before/after |
| 9 | `./scripts/powershell/Start-AccessReviewCampaign.ps1 ...` | Campaign and decisions |
| 10 | Diagnostic settings -> Log Analytics -> Sentinel; deploy `detections/kql/*.kql`; trigger per the test plan | Alert screenshots |
| 11 | Run the three audit scripts; save reports before and after remediation | CSV outputs |

> The HR feed uses a fictional domain. In a real tenant UPNs must use one of your verified domains. Regenerate data after editing the catalog domain, or find/replace `meridian-lab.example` in the CSVs.

### 5. Cleaning up
Delete test users (`Get-MgUser -Filter "endswith(userPrincipalName,'@yourlab...')"`), remove Sentinel/Log Analytics to stop charges, and let the P2 trial expire.

## Troubleshooting
| Symptom | Likely cause |
|---|---|
| `Insufficient privileges` | Missing admin consent for a Graph scope. Sign in with an account that can consent, or consent in the prompt |
| `signInActivity` returns null | No P1/P2, or user never signed in |
| JML run aborts with CIRCUIT BREAKER | Too many leavers in one run, or (Python engine) the feed shrank; see RB-07 |
| New users cannot sign in on day 1 | No TAP issued (RB-01) or CA007 blocking registration from untrusted location |
| CA script refuses to enforce | Break-glass group needs 2+ members |

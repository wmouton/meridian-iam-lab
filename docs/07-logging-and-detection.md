# 07 - Logging, Monitoring and Detection

Detection rules: [`detections/`](../detections) (README has setup, MITRE mapping, and a safe test plan).

## 1. Log sources

| Source | Table | Used by | Notes |
|---|---|---|---|
| Entra interactive sign-ins | `SigninLogs` | DET-001, 002, 004, 005, 006, 008 | Needs P1+ to export |
| Entra non-interactive sign-ins | `AADNonInteractiveUserSignInLogs` | Token-replay hunting | High volume; consider a separate retention tier |
| Entra audit logs | `AuditLogs` | DET-003, 007; JML evidence | Role changes, CA changes, user lifecycle |
| Identity Protection | `AADUserRiskEvents`, `AADRiskyUsers` | CA004/005 correlation | P2 |
| JML engine | `out/audit.jsonl` | Lifecycle evidence | Ship to the SIEM in production |

Retention: 180 days hot (search), 1 year archive (audit), 7 years for SOX-relevant evidence outside the SIEM.

## 2. Detection catalogue

| ID | Name | Attack pattern | Response (first action) |
|---|---|---|---|
| DET-001 | MFA fatigue | Push bombing then approval | Revoke sessions, reset password, contact user out-of-band |
| DET-002 | Impossible travel | Stolen credentials/session | Confirm with user, revoke sessions, check inbox rules |
| DET-003 | Role granted | Privilege escalation | Verify ticket; if none, remove role and investigate actor |
| DET-004 | Dormant account active | Forgotten-account takeover | Disable, review activity, check HR status |
| DET-005 | Legacy auth success | CA002 gap / spray | Find client, block, enforce CA002 |
| DET-006 | Disabled-account attempts | Ex-employee / credential reuse | Revoke sessions again, notify HR and manager |
| DET-007 | CA policy tampering | Defence evasion | Verify change ticket; restore policy |
| DET-008 | Break-glass used | Emergency or compromise | Call the owner, start RB-05 |

Known gap: DET-004 can't see accounts that have been dormant for longer than its 180-day history window (details in the rule header).

## 3. Triage fields every alert should carry
User, IP and country, app, client app, device compliance, CA result, auth method, risk level, related correlation ID, and the matching HR status (active/terminated).
Enrich with the `BreakGlassAccounts` watchlist and an HR-terminations watchlist exported from the JML engine output.

## 4. Detection engineering lifecycle
Hypothesis -> write query -> test on lab data -> document false positives -> tune -> deploy with owner and runbook -> review metrics quarterly (true-positive rate, mean time to acknowledge) -> retire or improve.

## 5. Metrics
Alerts per rule per week, true-positive %, mean time to detect and respond, % of identity incidents with a closed-loop lifecycle fix (e.g. DET-006 hit led to a leaver-process correction).

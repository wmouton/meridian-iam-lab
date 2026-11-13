# Detections

Eight Sentinel (KQL) analytics rules for the identity attacks this lab is built around.

| ID | Detection | Table | Severity | MITRE ATT&CK | Responds to |
|---|---|---|---|---|---|
| DET-001 | MFA fatigue (push bombing) | SigninLogs | High | T1621 | Weak MFA, user approves to stop prompts |
| DET-002 | Impossible travel | SigninLogs | Medium | T1078 | Credential theft, session hijack |
| DET-003 | Directory role granted | AuditLogs | High/Critical | T1098.003 | Privilege escalation, persistence |
| DET-004 | Dormant account reactivated | SigninLogs | High | T1078.004 | Forgotten account takeover |
| DET-005 | Legacy authentication success | SigninLogs | Medium | T1078, T1110.003 | Gap in CA002 |
| DET-006 | Sign-ins to disabled accounts | SigninLogs | Medium/High | T1078 | Leaver still holds credentials |
| DET-007 | Conditional Access tampering | AuditLogs | High | T1556, T1562 | Defence evasion by an admin or attacker |
| DET-008 | Break-glass account used | SigninLogs | Critical | T1078.004 | Emergency account abuse |

## Setup

1. Entra ID -> Diagnostic settings -> send **SignInLogs, NonInteractiveUserSignInLogs, AuditLogs, RiskyUsers, UserRiskEvents** to a Log Analytics workspace with Sentinel enabled. (Exporting sign-in logs needs Entra ID P1/P2.)
2. Set workspace retention to **at least 180 days** (DET-004 needs it).
3. Create the `BreakGlassAccounts` watchlist (DET-008).
4. In Sentinel -> Analytics -> Create -> Scheduled query rule, paste each file and use the cadence in its header. Map entities: Account = `UserPrincipalName`, IP = `IPAddress`.
5. Generate test events (below) and confirm each alert fires.

## Test plan (lab tenant only, never production)

| Detection | How to trigger safely |
|---|---|
| DET-001 | Sign in as a test user and deny 5+ Authenticator prompts, then approve |
| DET-002 | Sign in from home, then from a commercial VPN exit in another continent |
| DET-003 | Make a test user eligible then permanently active for *User Administrator* |
| DET-004 | Use a test account that has not signed in for 90+ days (or lower `dormant_days` to 1d for the demo) |
| DET-005 | Lower scope of CA002 to report-only and sign in with an IMAP client against a test mailbox |
| DET-006 | Disable a test user and try to sign in |
| DET-007 | Switch CA001 from report-only to disabled |
| DET-008 | Sign in with a break-glass test account |

## Deployment notes

The queries target the documented `SigninLogs` and `AuditLogs` schemas. Column names and `ResultType` codes occasionally change, so validate each
rule in Log Analytics -> Logs against your own data before enabling alerting, then tune thresholds and allow-lists. DET-002 is noisy until VPN and
egress ranges are added to an exclusion watchlist. DET-004 has a blind spot for accounts dormant longer than its 180-day history window; see the rule header.

# 11 - Roadmap and Production Considerations

The lab covers the full identity lifecycle against a CSV HR source and a single IdP. Below is what I'd change for production, and what I'd add next.

## 1. Near-term

| Item | Description |
|---|---|
| Dynamic-group variant | Option to derive `grp-role-*` membership from `jobTitle` using Entra dynamic groups, with the JML engine limited to joiner/leaver and exception handling. |
| Exception register | Structured store (CSV/JSON) for approved access exceptions with expiry, feeding the analyzer so that approved exceptions are suppressed until they expire. |
| Analyzer input adapters | Importers for real entitlement exports (Entra enterprise-app assignments, Okta app assignments, SailPoint certifications). |
| Detection test harness | Replay of synthetic sign-in events into a Log Analytics workspace to assert that each rule fires. |
| Reporting | HTML summary of the access-review report with trend lines across cycles. |

## 2. Production architecture

| Area | Production approach |
|---|---|
| HR integration | Workday / SAP SuccessFactors inbound provisioning or API-driven provisioning, with attribute mapping and scoping filters, replacing the CSV feed. |
| Leaver latency | Event-driven (webhook) terminations for high-risk leavers instead of a scheduled batch; Entra Lifecycle Workflows for mailbox, licence and manager hand-over tasks. |
| Entitlement management | Entra access packages with approval, expiry and periodic review in place of manual group requests. |
| Workload identities | Inventory, ownership and credential-expiry governance for service principals and managed identities. |
| Secrets and infrastructure access | Vault-based credential checkout and rotation, session recording and just-in-time server access (CyberArk, BeyondTrust, HashiCorp Vault). |
| Multi-IdP | Okta or SailPoint as an additional source; the role catalog and SoD rules are IdP-neutral and can be reused. |
| Pipeline | Scheduled runs (GitHub Actions or Azure Automation) authenticating with a certificate-based app registration; `audit.jsonl` shipped to the SIEM. |

## 3. Known limitations

* The Python JML engine is the tested version and works on a local directory snapshot; `Invoke-JmlSync.ps1` applies the same rules to Entra ID via Microsoft Graph.
* `Invoke-JmlSync.ps1` has no truncated-feed check (it keeps no state between runs), and its circuit breaker counts disables but not deletes. The Python engine does both.
* The analyzer and engine are tested against data from the generator that planted the defects. A pass shows they are consistent with it, not that they cope with a messy real export.
* DET-004 misses accounts that have been dormant for longer than its 180-day history window.
* Group membership is managed as assigned membership. Nested groups and role-assignable groups are not modelled.
* SoD rules are pairwise. Rules over three or more entitlements and cross-application attribute conditions are not supported.
* The access export is a flat CSV; time-bound (just-in-time) grants are represented only through PIM, not in the analyzer.

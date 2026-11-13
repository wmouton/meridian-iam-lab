# 08 - Control Mapping

How each lab control maps to common frameworks. Each row names the control, where its evidence lives in this repository, and the requirement it supports.
References: NIST SP 800-53 Rev. 5, ISO/IEC 27001:2022 Annex A, AICPA SOC 2 Trust Services Criteria (Common Criteria), SOX IT General Controls (access domain).
SOX has no numbered control catalogue; the "SOX ITGC" column names the audit objective.

| # | Lab control | Evidence in this repo | NIST 800-53 | ISO 27001:2022 | SOC 2 | SOX ITGC objective |
|---|---|---|---|---|---|---|
| 1 | HR-driven account creation with documented role | `jml_engine.py`, `Invoke-JmlSync.ps1`, `audit.jsonl` | AC-2, AC-2(1), IA-4 | A.5.16, A.5.18 | CC6.2 | Provisioning authorised before access granted |
| 2 | Automated leaver disable + session revocation | DISABLE action, tests | PS-4, AC-2, AC-2(3) | A.6.5 | CC6.2 | Timely removal of terminated users |
| 3 | Mover removes old-role access | MOVER action, `sod_conflicts_prevented` | AC-2, AC-6, PS-5 | A.6.5, A.5.18 | CC6.3 | Access modified on role change |
| 4 | Role-based access model | `role_catalog.json`, `role_matrix.csv` | AC-2(7), AC-6, AC-3 | A.5.15, A.8.3 | CC6.3 | Access based on job function |
| 5 | Segregation of duties rules | `sod_rules.json`, catalog test, analyzer | AC-5 | A.5.3 | CC6.3 | SoD in financial applications |
| 6 | Least privilege through birthright/role/exception layers | RBAC doc, exception process | AC-6, AC-6(1) | A.5.15 | CC6.3 | Restricted access to programs and data |
| 7 | MFA for all, phishing-resistant for admins | CA001, CA003 | IA-2(1), IA-2(2), IA-2(6) | A.8.5 | CC6.1 | Authentication strength |
| 8 | Block legacy authentication | CA002, DET-005 | IA-2, AC-17 | A.8.5 | CC6.1 | Authentication strength |
| 9 | Protected MFA registration | CA007, TAP runbook | IA-5, IA-4 | A.5.17 | CC6.1 | Credential issuance control |
| 10 | Risk-based access | CA004, CA005 | AC-2(12), SI-4 | A.8.16 | CC6.1, CC7.2 | - |
| 11 | Periodic access recertification, default deny | access review template, analyzer | AC-2(j), CA-7 | A.5.18 | CC6.3 | Periodic user access review |
| 12 | Dormant account detection and disablement | analyzer, `Audit-StaleAccounts.ps1`, DET-004 | AC-2(3) | A.5.18 | CC6.2 | Inactive user management |
| 13 | Orphan account detection | analyzer, JML `FLAG_ORPHAN` | AC-2, AC-2(3) | A.5.16 | CC6.2 | Completeness of user population |
| 14 | Just-in-time privileged access (PIM) | `New-PimEligibleAssignment.ps1` | AC-6(1), AC-6(5), AC-2(7) | A.8.2 | CC6.3 | Privileged access restricted and monitored |
| 15 | Standing-privilege audit | `Audit-PrivilegedRoles.ps1` | AC-6(5), AC-6(7) | A.8.2 | CC6.3 | Privileged access review |
| 16 | Break-glass control | CA exclusions, DET-008, RB-05 | AC-2(2), CP-2 | A.8.2 | CC6.1 | - |
| 17 | Identity event logging | Diagnostic settings, `audit.jsonl` | AU-2, AU-3, AU-12 | A.8.15 | CC7.2 | Audit trail of access changes |
| 18 | Detection and response on identity threats | DET-001..008 | AU-6, SI-4, IR-4 | A.8.16, A.5.25 | CC7.2, CC7.3 | - |
| 19 | Change control for authentication policy | CA change log, DET-007 | CM-3, CM-5 | A.8.32 | CC8.1 | Change management over access config |
| 20 | Data-integrity safeguards on lifecycle automation | Circuit breaker, quarantine, tests | SI-10, CM-3 | A.8.32 | CC7.2 | Interface/batch integrity |

## Using this with an auditor
* **Population completeness:** the analyzer's first step joins the app export to HR, which answers "how do you know your user list is complete?".
* **Timeliness:** `audit.jsonl` plus `end_date` give the leaver-to-disable interval; target same day (P1 leavers: within 1 hour).
* **Operating effectiveness vs design:** design = this documentation; operating effectiveness = the dated outputs in `out/` each cycle.

# Access Review Report - as of 2026-09-30

Reviewed **226** accounts / **303** entitlement assignments. Found **93** findings across **79** accounts.

## Findings by type

| Type | Count | Recommended action |
|---|---:|---|
| DORMANT_ACCOUNT | 23 | Disable; remove access if no business justification within 14 days |
| EXCESS_ENTITLEMENT | 28 | Revoke entitlement unless manager provides documented exception |
| LEAVER_ACTIVE_ACCESS | 9 | Revoke all access; run leaver checklist; confirm HR end date |
| LEAVER_POST_TERMINATION_LOGIN | 3 | Open security incident; revoke access; review activity since end date |
| ORPHAN_ACCOUNT | 14 | Disable immediately; identify owner or delete after retention period |
| PRIVILEGED_NO_MFA | 5 | Require MFA registration within 24h or suspend privileged access |
| SOD_VIOLATION | 11 | Remove one side of the conflict or record an approved compensating control |

## Findings by severity

| Severity | Count |
|---|---:|
| Critical | 33 |
| High | 12 |
| Medium | 48 |

## Critical findings

| ID | Type | Account | Detail |
|---|---|---|---|
| F-0001 | LEAVER_ACTIVE_ACCESS | ayesha.radebe@meridian-lab.example | Terminated 2026-05-24; 1 entitlement(s) still active |
| F-0002 | LEAVER_ACTIVE_ACCESS | emma.ndlovu@meridian-lab.example | Terminated 2026-05-31; 2 entitlement(s) still active |
| F-0003 | LEAVER_ACTIVE_ACCESS | lindiwe.botha@meridian-lab.example | Terminated 2026-05-29; 1 entitlement(s) still active |
| F-0004 | LEAVER_ACTIVE_ACCESS | pieter.mokoena@meridian-lab.example | Terminated 2026-03-23; 1 entitlement(s) still active |
| F-0005 | LEAVER_ACTIVE_ACCESS | ryan.dlamini@meridian-lab.example | Terminated 2026-05-30; 1 entitlement(s) still active |
| F-0006 | LEAVER_ACTIVE_ACCESS | samuel.cele@meridian-lab.example | Terminated 2026-07-24; 1 entitlement(s) still active |
| F-0007 | LEAVER_ACTIVE_ACCESS | samuel.govender@meridian-lab.example | Terminated 2026-03-28; 1 entitlement(s) still active |
| F-0008 | LEAVER_ACTIVE_ACCESS | sarah.fourie@meridian-lab.example | Terminated 2026-07-06; 2 entitlement(s) still active |
| F-0009 | LEAVER_ACTIVE_ACCESS | sipho.patel@meridian-lab.example | Terminated 2026-05-28; 1 entitlement(s) still active |
| F-0010 | LEAVER_POST_TERMINATION_LOGIN | emma.ndlovu@meridian-lab.example | Last login 2026-06-14 is 14 day(s) after termination |
| F-0011 | LEAVER_POST_TERMINATION_LOGIN | samuel.govender@meridian-lab.example | Last login 2026-04-01 is 4 day(s) after termination |
| F-0012 | LEAVER_POST_TERMINATION_LOGIN | sarah.fourie@meridian-lab.example | Last login 2026-07-21 is 15 day(s) after termination |
| F-0013 | ORPHAN_ACCOUNT | ctr-kwezi@meridian-lab.example | No HR record, no owner; last login 2026-05-04; privileged: ITSM:Admin |
| F-0014 | ORPHAN_ACCOUNT | ctr-lumen@meridian-lab.example | No HR record, no owner; last login 2026-06-06; privileged: ITSM:Admin |
| F-0015 | ORPHAN_ACCOUNT | ctr-northgate@meridian-lab.example | No HR record, no owner; last login 2026-06-27; privileged: ITSM:Admin |
| F-0016 | ORPHAN_ACCOUNT | ctr-tidewater@meridian-lab.example | No HR record, no owner; last login 2025-09-21; privileged: ITSM:Admin |
| F-0017 | ORPHAN_ACCOUNT | former-vendor-audit@meridian-lab.example | No HR record, no owner; last login 2026-06-25; privileged: ITSM:Admin |
| F-0018 | ORPHAN_ACCOUNT | former-vendor-travel@meridian-lab.example | No HR record, no owner; last login 2026-08-29; privileged: CRM:Admin |
| F-0019 | ORPHAN_ACCOUNT | test.user1@meridian-lab.example | No HR record, no owner; last login 2026-04-24; privileged: ITSM:Admin |
| F-0020 | PRIVILEGED_NO_MFA | daniel.wilson@meridian-lab.example | Privileged entitlement without MFA registration |
| F-0021 | PRIVILEGED_NO_MFA | ethan.moyo@meridian-lab.example | Privileged entitlement without MFA registration |
| F-0022 | PRIVILEGED_NO_MFA | johan.dlamini@meridian-lab.example | Privileged entitlement without MFA registration |
| F-0023 | PRIVILEGED_NO_MFA | mpho.evans@meridian-lab.example | Privileged entitlement without MFA registration |
| F-0024 | PRIVILEGED_NO_MFA | themba.radebe@meridian-lab.example | Privileged entitlement without MFA registration |
| F-0025 | SOD_VIOLATION | jacob.jansen@meridian-lab.example | SOD-001: One person must not both enter and approve a supplier payment (payment fraud). |
| F-0026 | SOD_VIOLATION | jacob.mthembu@meridian-lab.example | SOD-001: One person must not both enter and approve a supplier payment (payment fraud). |
| F-0027 | SOD_VIOLATION | liam.khumalo@meridian-lab.example | SOD-003: Creating or changing employees and running payroll enables ghost-employee fraud. |
| F-0028 | SOD_VIOLATION | lindiwe.nkosi@meridian-lab.example | SOD-003: Creating or changing employees and running payroll enables ghost-employee fraud. |
| F-0029 | SOD_VIOLATION | lindiwe.pretorius@meridian-lab.example | SOD-001: One person must not both enter and approve a supplier payment (payment fraud). |
| F-0030 | SOD_VIOLATION | nathan.cele@meridian-lab.example | SOD-001: One person must not both enter and approve a supplier payment (payment fraud). |
| F-0031 | SOD_VIOLATION | riaan.smith@meridian-lab.example | SOD-003: Creating or changing employees and running payroll enables ghost-employee fraud. |
| F-0032 | SOD_VIOLATION | samuel.brown@meridian-lab.example | SOD-001: One person must not both enter and approve a supplier payment (payment fraud). |
| F-0033 | SOD_VIOLATION | sipho.wilson@meridian-lab.example | SOD-001: One person must not both enter and approve a supplier payment (payment fraud). |

_Produced by access_review_analyzer.py. Reviewer decisions go in findings.csv._

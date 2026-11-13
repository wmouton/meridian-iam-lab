# 05 - Access Reviews and Recertification

Tooling: [`access_review_analyzer.py`](../src/meridian_iam/access_review_analyzer.py) (offline analysis of an entitlement export) and
[`Start-AccessReviewCampaign.ps1`](../scripts/powershell/Start-AccessReviewCampaign.ps1) (Entra Access Reviews, template in `policies/access-reviews/`).

## 1. Why reviews exist
Provisioning controls what gets granted. Reviews check that access is still right, and they catch what automation can't see: manual grants,
stale accounts, access outside the role baseline. Auditors (SOX ITGC, SOC 2 CC6.3, ISO 27001 A.5.18) expect evidence of periodic review with
documented decisions and timely removals.

## 2. Review calendar

| Scope | Reviewer | Frequency | Default if no response |
|---|---|---|---|
| Privileged entitlements and admin roles | Resource owner + IAM lead | Quarterly | Deny (auto-remove) |
| Finance (ERP) and Payroll entitlements (SOX scope) | Controller | Quarterly | Deny |
| All other application access | Line manager | Semi-annually | Deny |
| Service accounts and owners | Named owner | Quarterly | Disable |
| Guests and contractors | Sponsor | Quarterly (end date enforced) | Deny |

## 3. Campaign procedure

1. **Prepare (T-10 days):** export entitlements; run the analyzer to pre-identify defects (clean obvious orphans *before* sending to reviewers so they review signal, not noise).
2. **Launch (T-0):** create the campaign (Entra template or exported `findings.csv` worksheet). Reviewers get a 14-day window, a reminder at day 7 and day 12.
3. **Decide:** per entitlement: certify (with justification), revoke or modify. Recommendations (last sign-in, role baseline) are shown to reviewers.
4. **Apply:** decisions auto-apply; "no response" = deny. Escalate to the reviewer's manager at day 12.
5. **Verify (T+3):** confirm revocations in the directory and re-run the analyzer; target is zero open findings.
6. **Evidence:** retain `findings.csv` (decisions, reviewer, date), the report, and the post-remediation run for 7 years (SOX) or per policy.

## 4. What the analyzer detects

| Finding | Rule | Severity | Recommended action |
|---|---|---|---|
| ORPHAN_ACCOUNT | No HR record and no owner (service accounts with an owner are excluded) | High; Critical if privileged | Disable now; find owner or delete after retention |
| LEAVER_ACTIVE_ACCESS | HR says terminated, access still present | Critical | Revoke everything, review leaver process failure |
| LEAVER_POST_TERMINATION_LOGIN | Terminated *and* last login after end date | Critical | Security incident |
| DORMANT_ACCOUNT | Active employee, no login > 90 days (or none on record) | Medium; High if privileged | Disable, remove after 14 days |
| EXCESS_ENTITLEMENT | Entitlement outside the role baseline (includes SoD additions) | Medium; High if privileged | Revoke unless exception on file |
| SOD_VIOLATION | Toxic pair from `sod_rules.json` | Rule severity | Remove one side or add compensating control |
| PRIVILEGED_NO_MFA | Privileged entitlement, MFA not registered | Critical | Enforce registration in 24h |
| SERVICE_ACCOUNT_NO_OWNER | Non-human account without accountable owner | High | Assign owner or decommission |

Every finding carries NIST / ISO / SOC 2 control references and blank `decision`, `reviewer`, `decision_date` columns, so `findings.csv`
doubles as the reviewer worksheet.

## 5. Running the lab review

```bash
uv run iam-access-review                                              # -> out/findings.csv, findings_summary.json, access_review_report.md
uv run iam-remediate                                                  # applies recommended fixes to a copy of the export
uv run iam-access-review --access out/app_access_export_remediated.csv --out out/after   # expect 0 findings
```

The dataset is seeded with known defects: 14 orphans, 9 leavers with access (3 of them logged in after termination), 11 SoD violations,
23 dormant accounts, 17 privilege-creep cases and 5 privileged accounts without MFA. It also holds 3 legitimate service accounts that must not
be flagged. `tests/test_access_review.py` asserts the analyzer's output equals the seeded answer key exactly: no misses, no false positives.
The key comes from the generator that planted the defects, so this proves consistency, not coverage.

## 6. Entra campaign
```powershell
./scripts/powershell/Start-AccessReviewCampaign.ps1 -GroupName grp-app-erp-ap-approve -FallbackReviewerUpn controller@yourtenant.onmicrosoft.com -WhatIf
```
Template highlights: recurrence every 3 months, manager as reviewer with fallback, justification required on approval, recommendations on,
`defaultDecision: Deny` with `autoApplyDecisionsEnabled: true`.

## 7. Metrics
Completion rate (target >= 95%), time to complete (<= 14 days), revocation rate (a rate near 0% suggests rubber-stamping), time from
revoke decision to removal (<= 3 days), repeat findings per cycle (should fall).

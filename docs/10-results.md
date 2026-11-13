# 10 - Results and Metrics

All figures below come from running this repository against its synthetic, seeded dataset (`make demo`; reproduced in CI on every push).
They measure the tooling's behaviour against a known answer key. They are not production outcomes.

## 1. Lifecycle automation (JML)

| Metric | Result |
|---|---|
| Accounts provisioned from HR on day 0 | 200 of 200 active employees; 9 historical leavers correctly received no account |
| Idempotency (re-run of same feed) | 0 actions |
| Day-30 changes processed | 6 joiners (3 enabled, 3 pre-boarded), 8 movers, 4 leavers disabled |
| Bad HR rows handled | 3 rows quarantined (1 duplicate ID pair, 1 malformed date); 0 actions taken on them |
| SoD conflicts prevented at move time | 2 (SOD-001 and SOD-003) |
| Pre-boarded accounts enabled on start date | 3 of 3 |
| Leavers deleted after 30-day retention | 4 of 4 |
| Mass-termination test (30 terminations in one feed) | Circuit breaker aborted, 0 changes; explicit override required |
| Truncated feed test (100 of 209 rows) | Aborted, 0 changes |

## 2. Access review (seeded defects vs detection)

| Finding type | Seeded | Detected | False positives |
|---|---:|---:|---:|
| Orphan accounts (no HR record, no owner) | 14 | 14 | 0 |
| Leavers with active access | 9 | 9 | 0 |
| ...of which logged in after termination | 3 | 3 | 0 |
| Dormant accounts (> 90 days) | 23 | 23 | 0 |
| SoD violations | 11 | 11 | 0 |
| Excess entitlements (creep 17 + SoD additions 11) | 28 | 28 | 0 |
| Privileged accounts without MFA | 5 | 5 | 0 |
| Owned service accounts (must not be flagged) | 3 | 0 flagged | 0 |

Before remediation: 226 accounts / 303 assignments reviewed; 93 findings (33 Critical, 12 High, 48 Medium) on 79 accounts.
After simulated remediation: 180 accounts / 205 assignments; 0 findings (46 accounts disabled, 98 assignments removed, 5 MFA gaps closed).


## 3. KPIs to track in a real programme

| KPI | Target | Source |
|---|---|---|
| Leaver-to-disable time | Same day; P1 <= 1 h | HR end date vs `audit.jsonl` |
| Orphan accounts | 0 | analyzer / JML `FLAG_ORPHAN` |
| Standing privileged assignments (non-break-glass) | 0 | `Audit-PrivilegedRoles.ps1` |
| MFA registration (all / admins) | >= 99% / 100% | `Audit-MfaGaps.ps1` |
| Phishing-resistant MFA for admins | 100% | `Audit-MfaGaps.ps1` |
| Access review completion | >= 95% in 14 days | Entra access reviews |
| SoD violations open | 0 without compensating control | analyzer |
| Dormant accounts > 90 d | < 1% | `Audit-StaleAccounts.ps1` |
| Exceptions outstanding | falling trend | exception register |
| Mean time to acknowledge identity alerts | < 15 min | Sentinel |

## 4. Reproduce
```bash
uv run pytest   # 30 tests
make demo       # regenerates everything under out/
```
Sample outputs from a clean run are checked in under [`examples/sample-output/`](../examples/sample-output).

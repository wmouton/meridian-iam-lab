# 04 - Authentication, MFA and Conditional Access

Policies as code: [`policies/conditional-access/`](../policies/conditional-access) | Deploy: [`New-ConditionalAccessPolicies.ps1`](../scripts/powershell/New-ConditionalAccessPolicies.ps1) | Gap audit: [`Audit-MfaGaps.ps1`](../scripts/powershell/Audit-MfaGaps.ps1)

## 1. Authentication standard

| Population | Minimum | Target |
|---|---|---|
| All users | MFA (Authenticator number matching) | Passkeys / passwordless |
| Administrators | Phishing-resistant MFA (FIDO2, Windows Hello for Business, certificate) | Same, hardware-bound |
| Break-glass | Two FIDO2 keys each, stored apart | Same |
| Service accounts | Managed identity or certificate; no passwords | Same |
| Disallowed | SMS/voice as sole factor for privileged users; legacy protocols (IMAP, POP, SMTP AUTH, ActiveSync basic) | - |

Registering security info is itself protected (CA007): attackers who obtain a password must not be able to enrol their own MFA device. New joiners register using a Temporary Access Pass issued after identity verification (RB-01).

## 2. Policy baseline

| ID | Policy | Target | Grant | Licence | Why it exists |
|---|---|---|---|---|---|
| CA001 | Require MFA | All users, all apps (excl. break-glass) | MFA | P1 | Baseline against password-only attacks (NIST IA-2(1)/(2)) |
| CA002 | Block legacy authentication | Exchange ActiveSync + other clients | Block | P1 | Legacy protocols cannot perform MFA; main password-spray vector |
| CA003 | Admins: phishing-resistant MFA | 10 privileged directory roles | Auth strength *Phishing-resistant MFA* | P1 | Admin compromise = tenant compromise; defeats AiTM phishing |
| CA004 | Sign-in risk >= medium | All users | MFA | **P2** | Step-up on suspicious sign-ins |
| CA005 | User risk = high | All users | MFA + password change | **P2** | Leaked-credential remediation |
| CA006 | Azure management | Azure Service Management API | MFA | P1 | Protects the control plane |
| CA007 | Security-info registration | User action `registersecurityinfo` | MFA | P1 | Prevents attacker enrolling own factor |
| CA008 | Non-approved countries | Named location (countries list) | Block | P1 | Reduces attack surface; needs a named location you create (see below) |

Every policy excludes the break-glass group. Role IDs in CA003 are Microsoft's well-known directory role template IDs.

CA008 includes the named location you pass in, so that location must list the countries to block. For an allow-list, flip it: include all locations and exclude the approved ones.

## 3. Rollout procedure (never enforce blind)

1. Create two break-glass accounts, add to `grp-iam-breakglass`, register FIDO2, verify sign-in works.
2. Deploy in report-only: `./New-ConditionalAccessPolicies.ps1 -BreakGlassGroupName grp-iam-breakglass` (use `-Exclude CA004,CA005` without P2; for CA008 create a Named Location and pass `-BlockedCountriesLocationId`).
3. Let report-only run for 7-14 days. Review Sign-in logs -> Conditional Access and the Conditional Access Insights workbook: how many users would be blocked, which apps, which legacy clients.
4. Remediate the blockers (register MFA, retire legacy mail clients, allow-list service flows).
5. Enforce one policy at a time in this order: CA002 -> CA001 -> CA007 -> CA003 -> CA006 -> risk policies. The script applies `-State` to every policy it deploys, so hold the rest back with `-Exclude`. It refuses `-State enabled` unless the break-glass group has 2+ members.
6. Record the change (date, reviewer, evidence) in the change log below.

## 4. What-if test matrix

| Scenario | Expected result | Policy |
|---|---|---|
| Standard user, browser, no MFA registered | Prompted to register using TAP | CA001, CA007 |
| IMAP client with correct password | Blocked | CA002 |
| Admin with only Authenticator push | Blocked until FIDO2 registered | CA003 |
| Sign-in from blocked country | Blocked | CA008 |
| Break-glass account | Allowed, and alert DET-008 fires | exclusions |
| Leaked-credential simulation (Entra test risk) | Password change required | CA005 |

## 5. Change log template

| Date | Policy | Change | State | Approved by | Evidence |
|---|---|---|---|---|---|
| YYYY-MM-DD | CA002 | Created | Report-only | name | link to insights export |

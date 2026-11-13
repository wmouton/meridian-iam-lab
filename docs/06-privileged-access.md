# 06 - Privileged Access Management (PAM)

Tooling: [`New-PimEligibleAssignment.ps1`](../scripts/powershell/New-PimEligibleAssignment.ps1), [`Audit-PrivilegedRoles.ps1`](../scripts/powershell/Audit-PrivilegedRoles.ps1), detections DET-003 / DET-007 / DET-008.
Licence: Entra ID P2 (or ID Governance) for PIM; a 30-day trial is enough for the lab.

## 1. Model

| Control | Standard |
|---|---|
| Separate admin identity | `adm-*` cloud-only account, no mailbox, never used for email/browsing |
| No standing privilege | Roles are eligible; activate just in time via PIM |
| Activation requirements | MFA at activation, justification + ticket number, max duration 4h (Global Admin 1h), approval for Global Admin / Privileged Role Admin |
| Assignment expiry | Eligibility reviewed quarterly and expires after 6 months unless renewed |
| Phishing-resistant MFA | Enforced by CA003 |
| Break-glass | 2 permanent Global Admins, FIDO2, excluded from CA, monitored by DET-008, tested every 6 months |
| Least-privilege roles | Use the narrowest role (e.g. *User Administrator* or *Helpdesk Administrator* rather than Global Administrator); admin units to scope by department |
| Limit Global Admin | <= 5 eligible; never use for routine work |

## 2. PIM configuration per role (portal: Entra ID -> Identity Governance -> PIM -> Roles -> Settings)

| Setting | Global Admin | Privileged Role Admin | Other admin roles |
|---|---|---|---|
| Activation maximum duration | 1 h | 2 h | 4-8 h |
| Require MFA on activation | Yes | Yes | Yes |
| Require justification | Yes | Yes | Yes |
| Require ticket information | Yes | Yes | Yes |
| Require approval | Yes (2 approvers) | Yes | No |
| Allow permanent eligible | No (6 months) | No (6 months) | No (12 months) |
| Allow permanent active | **No** | **No** | No |
| Notify on activation | Security team + approvers | Same | Role owner |

## 3. Procedure

1. Create `adm-` accounts (not synced from HR; owned by IAM, linked to the employee in the ticket).
2. Make eligible: `./New-PimEligibleAssignment.ps1 -UserPrincipalName adm-alex@... -RoleName 'User Administrator' -Months 6 -Justification 'IAM analyst - TKT-1042'`.
3. Weekly: `./Audit-PrivilegedRoles.ps1 -BreakGlassUpn bg1@...,bg2@...`; any `STANDING_PRIVILEGE` row is a finding, fixed within 5 business days.
4. Quarterly: access review of every privileged role (see 05) with default-deny.
5. Emergency: break-glass procedure RB-05; every use is followed by a post-incident review and credential rotation.

## 4. Evidence to retain
Capture: PIM role settings; an activation request with justification; the activation audit-log entry; `Audit-PrivilegedRoles` output before (standing admin) and after (eligible only); the DET-003 alert triggered by granting a role.

## 5. Beyond Entra roles (not built)
Privileged *infrastructure* and secrets: vaulting shared and service credentials with rotation and session recording (CyberArk, BeyondTrust, Delinea,
HashiCorp Vault community edition), just-in-time server access, and check-out/check-in workflows. The same principles apply: no shared standing credentials,
approval and reason on checkout, full session audit, rotate after use.

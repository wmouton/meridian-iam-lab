# 09 - Runbooks

Short procedures. Each has a trigger, an owner, steps and the evidence to keep.

## RB-01 Joiner: first sign-in and MFA bootstrap
**Trigger:** account reaches start date | **Owner:** Service desk | **SLA:** before 09:00 on day 1
1. Confirm identity (manager call-back or on-site verification with photo ID). No identity check, no credential.
2. Issue a Temporary Access Pass (one-time, 1-8 hours): Entra -> user -> Authentication methods -> Add -> Temporary Access Pass.
3. User signs in at `aka.ms/mysecurityinfo`, registers Authenticator (number matching) and a second method (passkey/FIDO2 where available).
4. Confirm CA001/CA007 applied (sign-in log shows MFA satisfied). Close ticket with TAP issuance time.

## RB-02 Leaver: standard and urgent
**Trigger:** HR termination | **Owner:** IAM | **SLA:** standard = end of last working day; urgent (hostile or involuntary) = within 1 hour
1. Standard: JML sync handles disable, session revocation, group removal. Verify in the next-day run summary (`DISABLE` count matches HR list).
2. Urgent: do not wait for the batch. Run `Invoke-JmlSync.ps1` immediately with the updated HR feed, or manually: block sign-in, revoke sessions, reset password, remove MFA methods, remove PIM eligibility, disable admin account.
3. Reassign mailbox/OneDrive to manager; convert mailbox to shared if needed (retention 30 days).
4. Check app-local accounts that bypass SSO (ERP, CRM local logins). These are the usual leaver leaks.
5. After 30 days, deletion occurs automatically; confirm `DELETE` in the audit log.
**Evidence:** HR termination timestamp, disable timestamp, session revocation entry, owner reassignment.

## RB-03 Access request exception (beyond role baseline)
1. Manager request with business justification; resource owner approval.
2. IAM runs the SoD check (`sod_rules.json`). Conflict -> compensating control signed by risk owner, else reject.
3. Grant with an expiry; record in the exception register; it appears in the next review.

## RB-04 Quarterly access review
Follow [05-access-reviews.md](05-access-reviews.md) section 3. Close only when the post-remediation analyzer run shows zero open findings or each has a signed exception.

## RB-05 Break-glass use
**Trigger:** DET-008 alert or declared emergency | **Owner:** Security lead
1. Confirm whether an emergency was declared (call the on-call manager; don't trust email).
2. If legitimate: record reason, time and approver; limit work to restoring normal admin access.
3. After use: rotate credentials, re-seal the FIDO2 keys, review sign-in and audit logs for the whole session, write a short post-incident report.
4. If not legitimate: treat it as a Critical incident. Revoke sessions, rotate, isolate, notify the CISO.
5. Test both accounts every 6 months and after any CA change.

## RB-06 Suspected account compromise (e.g. DET-001 MFA fatigue)
1. Contact the user out of band; ask whether they approved prompts.
2. Revoke sessions; reset password; remove unknown MFA methods; require re-registration with TAP.
3. Review last 7 days: sign-ins (IP, country, app), inbox rules, OAuth app consents, forwarding, role assignments, file downloads.
4. If an admin: assume tenant impact; review AuditLogs for role and CA changes (DET-003, DET-007).
5. Root cause: why did MFA fatigue work? (number matching on? SMS enabled? user training?) Fix the control, not just the account.

## RB-07 JML circuit breaker tripped
**Trigger:** `exit code 2` / "CIRCUIT BREAKER" | Nothing was changed.
1. Open `out/jml_summary.json` and `out/jml_actions.json`: which accounts would be disabled? Is it a plausible number (a layoff) or an artefact (truncated feed, status column defaulted to Terminated)?
2. Ask HR for confirmation and a fresh export. Compare row count to the previous run.
3. If genuine, an authorised IAM lead re-runs with `--force` / `-Force` and records the approver in the ticket.
4. If a data defect, fix at source and re-run; add a feed validation to the HR export if it recurs.

## RB-08 Orphan account investigation
1. Check creation date, last sign-in, owner attributes, group and app assignments, any service dependency (sign-in logs by app).
2. Contact likely owners (creator in audit log, department head). Allow 5 business days.
3. No owner and no dependency: disable, wait 30 days, delete. Dependency found: assign owner, convert to a service identity, document.
4. Root-cause the creation path (manual creation outside HR/JML) and close it.

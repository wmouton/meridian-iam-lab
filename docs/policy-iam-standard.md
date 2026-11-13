# Identity and Access Management Standard

**Owner:** Head of IT Security | **Approver:** CISO | **Version:** 1.0 | **Review:** annually | **Applies to:** all workforce identities and systems of Meridian Financial Services (fictional lab company)

Key words **MUST**, **SHOULD**, **MAY** are used as in RFC 2119.

## 1. Identity lifecycle
1.1 HR MUST be the authoritative source for workforce identity attributes (name, title, department, manager, start and end dates, status).
1.2 Accounts MUST be created only from an HR record and MUST be matched on the immutable employee ID.
1.3 Accounts MUST be created disabled no more than 7 days before start and enabled on the start date.
1.4 Termination MUST be entered in HR no later than the employee's last working day; involuntary terminations MUST be notified to IAM before the meeting.
1.5 On termination, accounts MUST be disabled and sessions revoked by end of the last working day (within 1 hour for involuntary terminations), and deleted after 30 days.
1.6 On role change, access of the previous role MUST be removed unless an approved, expiring exception exists.
1.7 Contractors and guests MUST have a sponsor and an end date no longer than 12 months.
1.8 Accounts without an HR record or accountable owner MUST be disabled after investigation within 10 business days.
1.9 Non-human accounts MUST have a named owner, a purpose, and MUST NOT use interactive sign-in or shared passwords where a managed identity or certificate is available.

## 2. Authorisation
2.1 Access MUST be granted through business roles derived from job function; direct grants are exceptions.
2.2 Access MUST follow least privilege and need to know.
2.3 Segregation-of-duties rules (`sod_rules.json`) MUST be enforced at design, provisioning and review time. A conflict MAY exist only with a documented compensating control approved by the risk owner.
2.4 Exceptions MUST have an expiry (privileged <= 90 days, other <= 12 months), an owner and a justification.

## 3. Authentication
3.1 MFA MUST be required for all users on all cloud applications.
3.2 Administrators MUST use phishing-resistant MFA.
3.3 Legacy authentication protocols MUST be blocked.
3.4 Registration of authentication methods MUST require MFA or a Temporary Access Pass issued after identity verification.
3.5 Passwords, where still used, MUST be at least 14 characters, checked against breached-password lists, and MUST NOT require periodic rotation absent evidence of compromise.

## 4. Privileged access
4.1 Privileged roles MUST be eligible-only (just in time) with MFA, justification and a maximum activation duration.
4.2 Administrators MUST use a separate admin account that is not used for email or web browsing.
4.3 Permanent active privileged assignments are prohibited except for two break-glass accounts.
4.4 Break-glass accounts MUST be excluded from Conditional Access, protected with phishing-resistant credentials stored separately, tested every 6 months, and alerted on every use.
4.5 Shared privileged credentials MUST be vaulted, rotated after use, and checked out with a recorded reason.

## 5. Review and recertification
5.1 Privileged and financial-system access MUST be reviewed quarterly; other access at least semi-annually.
5.2 Unreviewed access MUST default to removal.
5.3 Revocations MUST be completed within 3 business days of the decision; evidence MUST be retained for 7 years.
5.4 Accounts inactive for 90 days MUST be disabled.

## 6. Logging and monitoring
6.1 Authentication, authorisation changes and lifecycle events MUST be logged centrally and retained 180 days online and 1 year archived.
6.2 Detections for the scenarios in `detections/README.md` MUST be enabled and reviewed quarterly.
6.3 Changes to authentication policy MUST follow change control and generate an alert.

## 7. Roles and responsibilities
| Role | Responsibility |
|---|---|
| HR | Accurate, timely identity data |
| Line manager | Request and review team access; initiate leavers and movers |
| Resource owner | Approve access to their application; review quarterly |
| IAM team | Operate lifecycle automation, reviews, PIM; maintain this standard |
| Security operations | Monitor and respond to identity alerts |
| Internal audit | Independently test operating effectiveness |

## 8. Compliance and exceptions
Deviations require a written risk acceptance signed by the CISO and are recorded in the exception register. Violations are reported to HR and Security.

# Security

This is a lab built on fictional data. Don't point the scripts at a production tenant without reading them and running with `-WhatIf` first.

* No secrets in the repo. Automation authenticates with an app registration and a certificate (or a managed identity), never a client secret or a user password. `.gitignore` excludes `.env`, `*.pfx`, `*.pem` and `*.key`.
* Two cloud-only break-glass accounts, excluded from Conditional Access, protected by FIDO2 keys stored in separate physical locations, and alerted on (DET-008).
* Each script requests only the Graph scopes it needs; they are listed in its header. Use a separate admin account for lab work.

## Reporting a problem

If you find a flaw in the scripts, policies or detections, report it privately first. The disclosure policy is at <https://wmouton.gitlab.io/contact/#disclosure>. For anything minor, a GitHub issue is fine. Leave tenant identifiers out of public reports.

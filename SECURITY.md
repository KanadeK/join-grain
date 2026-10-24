# Security

Version 0.1.x is the supported release line. Do not include real data in issues.
Report a suspected vulnerability through
[GitHub private vulnerability reporting](https://github.com/KanadeK/join-grain/security/advisories/new).
If reporting is unavailable, open a content-free issue asking for a private route;
do not publish exploit details or credentials. There is no guaranteed response SLA.

See README limits and semantics before treating a passing report as evidence.
The tool has no telemetry or runtime network calls. Use stable local inputs;
this is not an isolation boundary against hostile concurrent writers. The Python
runtime and operating system remain part of the trusted computing base.

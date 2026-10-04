# Security policy

## Supported versions

Before 1.0, only the latest released version receives security fixes.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub's private vulnerability
reporting feature in the repository Security tab. Include the affected version, deployment mode,
reproduction steps, impact, and any suggested mitigation.

Maintainers should acknowledge a complete report within seven days, investigate it privately, and
coordinate a fixed release and advisory when confirmed. This is a response target, not a warranty.

## Deployment responsibility

The SDK treats local paths as trusted input. The optional API requires explicit authentication and
does not provide TLS termination, rate limiting, backups, or a complete crash-recovery state machine.
Review `docs/DEPLOYMENT.md` before exposing a service to untrusted users.

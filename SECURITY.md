# Security Policy

## Supported Versions

This repository currently supports security fixes on the `main` branch until formal releases are published.

## Reporting a Vulnerability

Please do not open public issues for suspected vulnerabilities involving credential exposure, unsafe artifact handling, command execution, or dependency compromise.

Use GitHub private vulnerability reporting when it is enabled for the repository. If private reporting is not available, contact the repository maintainers through the GitHub repository owner profile and include:

- affected commit or release;
- reproduction steps;
- impact and affected platform;
- whether any credentials or private research artifacts may have been exposed.

The maintainers will acknowledge valid reports as soon as practical and coordinate a fix before public disclosure.

## Credential Handling

Co-Scientist reads optional provider credentials from environment variables. Do not paste API keys into config templates, run artifacts intended for sharing, issue reports, or pull requests.


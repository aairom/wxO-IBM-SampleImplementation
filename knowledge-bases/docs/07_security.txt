# IBM Bob Security Guidelines

Source: https://bob.ibm.com/docs/ide/security/bob-security-guidance

## Overview

Bob is an AI coding assistant designed to help IBMers write secure, maintainable code. This document defines mandatory security standards that MUST be followed in all code suggestions, architecture recommendations, and technical guidance.

## Data Restrictions

The following data types should **not** be processed with Bob:

- SPI (Sensitive Personal Information)
- Personal Health Information (PHI)
- Export control code marked as 'Red' or 'Gray'
- Non-IBM IP (Open source is allowed, but review the license first)
- Sensitive Financial Data (banking numbers, PANs, credit card numbers)
- Material Non-Public Information (MNPI)

## Security Hardening

You can apply additional security rules to Bob by creating custom rules files. These are stored in `.bob/rules/` or `.bob/rules-{mode-slug}/` directories.

See [Custom rules](https://bob.ibm.com/docs/ide/configuration/rules) and [Security hardening](https://bob.ibm.com/docs/ide/security/security-hardening) for more information.

## Auto-Approve Settings

With Bob, you can automatically approve various actions without confirmation prompts. While this speeds up your workflow, it significantly increases security risks.

**Warning:** Auto-approve settings bypass confirmation prompts, giving Bob direct access to your system. This can result in **data loss, file corruption, or worse**. Command line access is particularly dangerous, as it can potentially run harmful operations.

Configure auto-approval with care:

- **Manual approval** — Review and approve every action Bob takes (safest setting).
- **Auto-approve** — Grant Bob the ability to run specific tasks without interruption.
- **Hybrid approach** — Auto-approve low-risk actions while requiring confirmation for riskier tasks.

## Using .bobignore

The `.bobignore` file lets you specify files and directories that Bob should not access or modify:

1. Create a `.bobignore` file in your project root.
2. Add patterns for sensitive files, build artifacts, and large assets.
3. Use the same syntax as `.gitignore`.

This helps protect sensitive information and prevent accidental changes to generated files.

See [Using .bobignore](https://bob.ibm.com/docs/ide/configuration/bobignore) for more information.

## Using MCP Securely

When using MCP servers:

- **Authentication** — Verify the identity of users accessing the server.
- **Encryption** — Secure data in transit between Bob and the server.
- **Access controls** — Limit what actions the server can perform.
- **Auditing** — Track all actions for accountability.

Remote MCP servers must adhere to the same security requirements as any traditional server infrastructure.

## Proxy Configuration

For enterprise environments with network restrictions, configure proxy settings for IBM Bob IDE.

See [Configuring proxy settings](https://bob.ibm.com/docs/ide/troubleshooting/ts-proxy) for more information.

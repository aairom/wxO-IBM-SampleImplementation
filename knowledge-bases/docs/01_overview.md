# IBM Bob — Overview and General FAQ

Source: https://bob.ibm.com/docs/

## What is IBM Bob?

IBM Bob is an AI SDLC (Software Development Lifecycle) partner that augments your existing workflows and helps you understand, plan, improve, and work confidently with real codebases—while offering proactive insights that keep you in control every step.

IBM Bob is an **agentic integrated development environment (IDE)** that helps you write, test, upgrade, and secure software across the entire software development lifecycle (SDLC).

## How does Bob work?

Bob uses large language models (LLMs) to understand your requests and translate them into actions. It can:

- Read and write files in your project.
- Execute commands in your terminal.
- Perform web browsing (if enabled).
- Use external tools via the Model Context Protocol (MCP).

You interact with Bob through a chat interface, where you provide instructions and review/approve its proposed actions.

## What can Bob do?

Bob can help with a variety of coding tasks, including:

- Generating code from natural language descriptions.
- Refactoring existing code.
- Fixing bugs.
- Writing documentation.
- Explaining code.
- Answering questions about your codebase.
- Automating repetitive tasks.
- Creating new files and projects.

## Can I use Bob on my IBM code?

Bob has been approved for use on **all IBM product codebases**.

## Are there any restrictions on processing certain data types with Bob?

The following data types should **not** be processed with Bob:

- SPI (Sensitive Personal Information)
- Personal Health Information (PHI)
- Export control code that are marked as 'Red' or 'Gray' (i.e., export-controlled code up to Orange zone is permitted)
- Non-IBM IP (Open source is allowed, but review the license first and remove any Bob tags)
- Sensitive Financial Data (banking numbers, PANs, credit card numbers)
- Material Non-Public Information (MNPI), such as financial data that has not been made public

## Can I choose which model Bob uses?

No. Bob **automatically selects** the most appropriate language model for each task based on complexity, required capabilities, and cost-efficiency. This intelligent routing ensures you receive high-quality responses while optimizing resource usage.

Bob's model selection considers:

- **Task complexity** — Simple tasks use faster, more cost-effective models.
- **Required capabilities** — Specialized tasks route to models with specific strengths.
- **Context size** — Large codebases may require models with extended context windows.
- **Cost optimization** — Balances performance with efficient resource usage.

## Getting Started with Bob IDE

1. **Install Bob** — Get Bob installed on your system. See [Installing Bob](https://bob.ibm.com/docs/ide/getting-started/install).
2. **Learn best practices** — Review the best practices guide. See [Best practices for using Bob](https://bob.ibm.com/docs/ide/getting-started/best-practices).
3. **Review security guidelines** — Consult the security guidelines. See [Security guidelines](https://bob.ibm.com/docs/ide/security/bob-security-guidance).

**Tip:** Start with something you are currently working on. Bob learns best when helping with real problems rather than hypothetical scenarios.

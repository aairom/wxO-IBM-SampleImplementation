# IBM Bob Modes (Built-in and Custom)

Source: https://bob.ibm.com/docs/ide/features/modes

## What are Modes?

Modes are **specialized personas** that tailor Bob's behavior for your specific tasks. Each mode offers different capabilities and access levels to help you accomplish particular goals more efficiently.

## Built-in Modes

Bob ships with several built-in modes:

- **Code** — For implementation tasks, writing and editing code.
- **Plan** — For architecture design and planning features before implementation.
- **Ask** — For asking questions about your codebase without making changes.
- **Advanced** — For more complex, multi-step tasks.
- **Orchestrator** — For coordinating multiple agents and tools.

## Custom Modes

Custom modes extend modes by letting teams and developers define specialized personas with tailored instructions and specific tool access. A custom mode combines:

- A **role definition** — what Bob is in this mode.
- **Behavioral instructions** — how Bob acts in this mode.
- A **deterministic set of permitted tools** — what tools Bob can use.

**Rules** apply to every conversation regardless of mode. A custom mode does not override or bypass rules.

### Creating a Custom Mode

You can override default Bob modes (such as Agent, Ask, or Plan) by creating a custom mode with the same slug in your project configuration.

**To create or edit custom modes:**

1. Click the Settings icon in the Bob panel to open Settings.
2. Select the **Modes** tab.
3. Click **Edit Project Modes** to edit the `.bob/custom_modes.yaml` file.
4. Add your mode configuration:

```yaml
customModes:
  - slug: ask  # Matches default Ask mode
    name: ❓ Ask
    roleDefinition: You are a knowledgeable assistant for this React and TypeScript codebase.
    whenToUse: Use this mode to ask questions about the codebase.
    customInstructions: Always reference relevant files when answering.
    groups:
      - read
      - mcp
      - skill
```

**Priority:** Project-specific overrides take precedence over global overrides, which take precedence over defaults.

## Custom Modes in Bob Shell

Custom modes in Bob Shell work similarly to Bob IDE modes. The key properties are:

- `slug` — Unique internal identifier; used in command-line arguments (e.g., `bob --chat-mode=my-mode`).
- `name` — Display name in the UI.
- `description` — Short description shown in the mode selector.
- `roleDefinition` — Defines the core identity and expertise.
- `groups` — Specifies allowed toolsets and file access.
- `whenToUse` — Mode selection guidance.
- `customInstructions` — Specific behavioral guidelines or rules for the mode.

## Mode Switching

- In the IDE: Use the mode selector in the Bob panel.
- In Bob Shell: Use slash commands (e.g., `/mode code`, `/mode ask`).
- Custom modes appear as slash commands (e.g., a mode with slug `reviewer` becomes `/reviewer`).

## Further Information

- [Custom modes documentation](https://bob.ibm.com/docs/ide/configuration/custom-modes)
- [Custom modes in Bob Shell](https://bob.ibm.com/docs/shell/configuration/custom-modes-bobshell)
- [Tutorial: Add Bob capabilities (create a product-manager mode)](https://bob.ibm.com/docs/ide/getting-started/tutorials/add-bob-capabilities)

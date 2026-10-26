# IBM Bob MCP — Model Context Protocol

Source: https://bob.ibm.com/docs/ide/configuration/mcp/

## What is MCP?

The **Model Context Protocol (MCP)** extends Bob's capabilities by connecting to external tools and services. MCP allows Bob to communicate with external servers, extending its capabilities with custom tools and resources.

An MCP server acts as a bridge between Bob and external services like databases, APIs, or custom scripts.

MCP servers provide Bob with:

- **Tool discovery** — Access to available tools with their descriptions and parameters.
- **Tool invocation** — The ability to call specific tools with arguments and receive structured responses.
- **Resource access** — The capability to read data from specific resources.

## Why Use MCP?

- **Extend functionality** — Add custom capabilities to Bob that aren't available out-of-the-box.
- **Integrate with services** — Connect Bob to your databases, APIs, and other systems.
- **Automate workflows** — Create specialized tools for your specific needs.
- **Share capabilities** — Distribute useful tools across your team.

## MCP in Bob IDE

The Model Context Protocol (MCP) extends Bob's capabilities with custom tools and integrations:

- **Understanding MCP** — Learn how MCP works and its role in extending Bob's capabilities.
- **Server transports** — Choose between local and remote deployment models for your MCP servers.
- **MCP server management** — Add, configure, and remove MCP servers directly from the settings panel.

For more information, see [Using MCP in Bob](https://bob.ibm.com/docs/ide/configuration/mcp/mcp-in-bob).

## MCP in Bob Shell

Bob Shell supports MCP, allowing you to extend Bob's capabilities by connecting to external services and tools:

- Connect to databases and APIs from the terminal.
- Access specialized development and operations tools.
- Integrate with your organization's internal systems.
- Create custom automation workflows for DevOps tasks.

For more information, see [MCP in Bob Shell](https://bob.ibm.com/docs/shell/configuration/mcp/mcp-bobshell).

## Using MCP Securely

Model Context Protocol extends Bob's functionality by connecting to external tools and services. While powerful, MCP connections require careful security consideration.

When using MCP servers, follow these guidelines:

- **Authentication** — Verify the identity of users accessing the server.
- **Encryption** — Secure data in transit between Bob and the server.
- **Access controls** — Limit what actions the server can perform.
- **Auditing** — Track all actions for accountability.

Remote MCP servers must adhere to the same security requirements as any traditional server infrastructure, including endpoint protection, network restrictions, and proper access controls.

For shared MCP servers, ensure proper auditability and accountability so actions can be traced.

## Auto-Approve for MCP

Bob can use configured MCP servers without asking permission if auto-approve is enabled for MCP. The risk level depends on what the specific MCP servers can access and modify. Use with caution.

## FAQ

**Can I create my own MCP servers?**
Yes. You can create your own MCP servers to add custom functionality to Bob. See [Using MCP in Bob](https://bob.ibm.com/docs/ide/configuration/mcp/mcp-in-bob).

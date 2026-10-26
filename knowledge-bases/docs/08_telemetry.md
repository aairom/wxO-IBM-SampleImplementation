# IBM Bob Telemetry

Source: https://bob.ibm.com/docs/ide/configuration/telemetry-data

## IBM Bob IDE Telemetry

IBM Bob collects telemetry data **by default** to help improve the product. You can opt out to disable telemetry data collection at any time.

**Note:** Enterprise plan users must keep telemetry enabled to view data in Bobalytics. Disabling telemetry will prevent your usage data from appearing in analytics dashboards.

### What data is collected?

When telemetry is enabled, IBM Bob collects:

- Actions you take in IBM Bob.
- Features you use and how they perform.
- Error and diagnostic information.

**Privacy:** IBM Bob does **not** collect your code, prompts, or other sensitive information as part of telemetry data.

### How is the data used?

This data helps IBM:

- Identify which features are most useful to users.
- Prioritize future development efforts.
- Diagnose and fix issues.
- Improve overall product quality.

### How to configure telemetry

1. Click the settings gear icon in the Bob panel.
2. Select the **General** tab.
3. Toggle **Telemetry** on or off.

## Bob Shell Telemetry

IBM Bob does **not** collect telemetry data by default in Bob Shell. You must **opt in** to enable telemetry data collection.

When enabled in Bob Shell:

- Actions are recorded that you take in IBM Bob.
- It helps identify which features are the most useful to users.
- You can enable or disable the collection of this data at any time.

### Collected data categories

Bob Shell telemetry can collect:

- Records the action of a task being opened, completed, or reopened.
- Records the generation, acceptance, or rejection of inline code completion.
- Records the initiation, successful completion, or failure of a scheduled scan.
- Records confirmation, clarification, or approval of tasks.
- Records the action of a message being sent from you to Bob or Bob to you.
- Records the use of tool invocations, such as `execute_command`, `read_file`, and others.

### Opting out of Bob Shell usage statistics

Bob Shell collects anonymous usage statistics (tool usage patterns, API request metrics, session configuration information). No personal information, prompt content, or file content is collected.

To opt out, add this to your settings:

```json
{
  "privacy": {
    "usageStatisticsEnabled": false
  }
}
```

# IBM Bob Assistant — Web Chat Integration Guide

**Agent:** `ibm_bob_assistant` · **Region:** eu-de · **Channel:** web chat (embedded)

---

## Table of Contents

1. [Architecture](#1-architecture)
2. [Prerequisites](#2-prerequisites)
3. [Getting the Embed Snippet](#3-getting-the-embed-snippet)
4. [Running the Demo Page Locally](#4-running-the-demo-page-locally)
5. [Configuration Reference](#5-configuration-reference)
6. [JavaScript API Reference](#6-javascript-api-reference)
7. [Embedding in a Production Site](#7-embedding-in-a-production-site)
8. [Security](#8-security)
9. [Accessibility](#9-accessibility)
10. [Troubleshooting](#10-troubleshooting)
11. [CLI Quick Reference](#11-cli-quick-reference)

---

## 1. Architecture

### 1.1 End-to-end data flow

```
Browser (index.html)
    │
    │  loads
    ▼
webchat-config.js
    │
    │  sets window.wxOConfiguration { orchestrationID, agentId, … }
    │  dynamically appends <script src="…/wxoLoader.js?embed=true">
    │
    ▼
wxoLoader.js  (IBM Cloud CDN, eu-de)
    │
    │  wxoLoader.init() → reads window.wxOConfiguration
    │  renders floating chat bubble + widget iframe
    │
    ▼
User opens chat → types question
    │
    ▼
wxO platform (api.eu-de.watson-orchestrate.cloud.ibm.com)
    │
    ▼
ibm_bob_assistant (native agent, react_core)
    │
    ├─► KB vector search → ibm_bob_docs (Milvus, 11 docs)
    ├─► tool call: search_bob_documentation(query) → Bob API passages
    └─► tool call: get_bob_doc_section(section_name) → local .txt file
    │
    ▼
Grounded answer with source citation → Browser
```

### 1.2 Component roles

| Component | Location | Purpose |
|---|---|---|
| `index.html` | `web/` | Host page — IBM-styled demo site |
| `webchat-config.js` | `web/` | **Generated** — holds platform IDs + loads wxoLoader |
| `webchat-config.js.template` | `web/` | Template with `%%PLACEHOLDER%%` tokens |
| `get_webchat_embed.sh` | `scripts/` | Generates `webchat-config.js` from live platform |
| `wxoLoader.js` | IBM Cloud CDN | Renders the chat widget (not in this repo) |
| `ibm_bob_assistant` | wxO platform | The agent that answers questions |
| `ibm_bob_docs` | wxO platform | Milvus-indexed knowledge base |

### 1.3 What `window.wxOConfiguration` contains

```javascript
window.wxOConfiguration = {
  orchestrationID:    "...",   // web-chat integration ID (from wxO)
  hostURL:            "https://api.eu-de.watson-orchestrate.cloud.ibm.com",
  rootElementID:      "wxo-chat-root",  // DOM element to mount widget
  showLauncher:       true,             // show floating bubble icon
  crn:                "crn:v1:bluemix:public:...", // IBM Cloud CRN
  deploymentPlatform: "ibmcloud",
  chatOptions: {
    agentId:            "...",  // ibm_bob_assistant UUID
    agentEnvironmentId: "..."   // live environment UUID
  }
};
```

---

## 2. Prerequisites

- The project venv activated: `source venv/bin/activate`
- `ibm_bob_assistant` **deployed (Live)** on the platform
- `.env` contains `ORCHESTRATE_API_KEY` (needed to re-activate the wxO session)
- IBM Cloud CRN for the wxO instance (see §3.2)

---

## 3. Getting the Embed Snippet

The embed snippet contains IDs that tie your web page to the specific agent
and environment. There are two ways to get it.

### 3.1 Automated (recommended)

```bash
source venv/bin/activate
bash scripts/get_webchat_embed.sh
```

The script:
1. Re-activates the wxO environment using `ORCHESTRATE_API_KEY` from `.env`
2. Calls `orchestrate channels webchat embed --agent-name ibm_bob_assistant --env live`
3. Parses the returned JSON for all IDs
4. Injects them into `web/webchat-config.js` (replacing `%%PLACEHOLDER%%` tokens)

Expected output:

```
[INFO]  Checking prerequisites...
[OK]    Prerequisites OK
[INFO]  Activating wxO environment 'aam-wxo-be'...
[OK]    Environment activated
[INFO]  Checking ibm_bob_assistant is deployed (Live)...
[OK]    Agent found on platform
[INFO]  Generating web-chat embed snippet...
[INFO]  Values to embed:
[INFO]    orchestrationID    = cf4d3293-xxxx-xxxx-xxxx-xxxxxxxxxxxx
[INFO]    hostURL            = https://api.eu-de.watson-orchestrate.cloud.ibm.com
[INFO]    crn                = crn:v1:bluemix:public:...
[INFO]    agentId            = 5c3c69c8-xxxx-xxxx-xxxx-xxxxxxxxxxxx
[INFO]    agentEnvironmentId = d754a48c-xxxx-xxxx-xxxx-xxxxxxxxxxxx
[OK]    webchat-config.js written
```

### 3.2 Manual (via wxO UI)

If the CLI command returns an error or you need to retrieve the CRN:

1. **Get the CRN** from IBM Cloud:
   ```bash
   ibmcloud resource service-instance <your-wxo-instance-name> --id
   # Output: crn:v1:bluemix:public:watson-orchestrate:eu-de:a/…
   ```
   Or: IBM Cloud UI → Resource list → your wxO instance → CRN field.

2. **Run the ADK embed command manually:**
   ```bash
   source venv/bin/activate
   orchestrate channels webchat embed \
     --agent-name ibm_bob_assistant \
     --env live
   # Prompts for CRN if not cached
   ```

3. **Copy the output** and manually update `web/webchat-config.js`:
   Replace each `PLACEHOLDER_*` value with the real value from the snippet.

### 3.3 What the embed snippet looks like

The ADK generates a JavaScript object like this (actual values redacted):

```javascript
window.wxOConfiguration = {
  orchestrationID: "cf4d3293-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  hostURL: "https://api.eu-de.watson-orchestrate.cloud.ibm.com",
  rootElementID: "root",
  showLauncher: true,
  crn: "crn:v1:bluemix:public:watson-orchestrate:eu-de:a/...",
  deploymentPlatform: "ibmcloud",
  chatOptions: {
    agentId: "5c3c69c8-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    agentEnvironmentId: "d754a48c-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  }
};
setTimeout(function () {
  const script = document.createElement('script');
  script.src = `${window.wxOConfiguration.hostURL}/wxochat/wxoLoader.js?embed=true`;
  script.addEventListener('load', function () { wxoLoader.init(); });
  document.head.appendChild(script);
}, 0);
```

> **Note:** `orchestrationID`, `agentId`, and `agentEnvironmentId` are **not secrets**.
> They cannot be used to modify the agent, view logs, or access your IBM Cloud account.
> See §8 for full security details.

---

## 4. Running the Demo Page Locally

### 4.1 After generating `webchat-config.js`

```bash
# Option A — macOS open
open web/index.html

# Option B — local HTTP server (avoids CORS issues with file:// protocol)
python3 -m http.server 8080 --directory web
# Open: http://localhost:8080
```

### 4.2 What you should see

1. The IBM-styled page loads with a status bar, hero section, and prompt cards
2. A floating chat bubble (💬) appears in the bottom-right corner
3. Clicking the bubble opens the chat window connected to `ibm_bob_assistant`
4. Clicking any prompt card opens the chat and sends the preset question

### 4.3 Testing each retrieval path

| Prompt card | Retrieval path exercised | Expected behaviour |
|---|---|---|
| "What is IBM Bob?" | KB vector search | Overview answer citing `01_overview.txt` |
| "Bob Shell commands" | `search_bob_documentation` tool | List of `/` commands |
| "How do Bobcoins work?" | `get_bob_doc_section("bobcoins")` | Budget tier explanation |
| "Create a custom skill" | `search_bob_documentation` tool | SKILL.md format steps |
| "MCP server setup" | `get_bob_doc_section("mcp")` | MCP configuration guide |
| "Enterprise features" | KB + `search_bob_documentation` | Enterprise plan details |

---

## 5. Configuration Reference

### 5.1 `window.wxOConfiguration` properties

| Property | Type | Required | Description |
|---|---|---|---|
| `orchestrationID` | string | ✅ | Web-chat integration ID. Generated by the platform. |
| `hostURL` | string | ✅ | Base URL of the wxO platform. For eu-de: `https://api.eu-de.watson-orchestrate.cloud.ibm.com` |
| `rootElementID` | string | ✅ | ID of the DOM element that hosts the widget. Must exist on the page. |
| `showLauncher` | boolean | ✅ | `true` = show floating bubble; `false` = widget opens only programmatically. |
| `crn` | string | ✅ | IBM Cloud Resource Name of the wxO service instance. |
| `deploymentPlatform` | string | ✅ | Always `"ibmcloud"` for IBM Cloud hosted instances. |
| `chatOptions.agentId` | string | ✅ | UUID of the `ibm_bob_assistant` agent. |
| `chatOptions.agentEnvironmentId` | string | ✅ | UUID of the live environment. |
| `cspNonce` | string | ❌ | Server-generated nonce if your page has a `Content-Security-Policy`. |

### 5.2 Loading strategy options

```javascript
// Default: load on page load (current implementation)
setTimeout(function() { /* load script */ }, 0);

// Alternative: load on user interaction (reduces initial payload)
document.getElementById("chat-trigger").addEventListener("click", function() {
  if (!window._wxoLoaded) {
    window._wxoLoaded = true;
    /* load script */
  }
  wxoLoader.openWindow();
});

// Pin to a specific loader version (prevents auto-updates)
script.src = `${hostURL}/wxochat/wxoLoader.js?version=1.2.3&embed=true`;
```

### 5.3 Agent YAML web-chat settings

You can configure the chat widget's welcome message and starter prompts
directly in the agent YAML. Add this to `agents/ibm_bob_assistant.agent.yaml`:

```yaml
# Optional: web-chat UI customisation
welcome_content:
  message: "Hi! I'm the IBM Bob Documentation Assistant."
  subtext: "Ask me anything about IBM Bob features, Bob Shell, skills, MCP, and more."

starter_prompts:
  - "What is IBM Bob?"
  - "How do I create a custom skill?"
  - "What are the Enterprise plan features?"
  - "How does Bob Shell work?"
```

After adding these, re-import and re-deploy:

```bash
python scripts/import_agent.py --force
orchestrate agents deploy -n ibm_bob_assistant
```

### 5.4 Context variables (advanced)

To pass user identity or page context into the agent:

```yaml
# In agents/ibm_bob_assistant.agent.yaml
context_access_enabled: true
context_variables:
  - clientID    # user identifier passed from the host page
  - channel     # always "web_chat" when embedded
```

Then pass them from the host page:

```javascript
// Before wxoLoader.init(), inject context:
window.wxOConfiguration.context = {
  clientID: "user-12345",
  channel:  "web_chat"
};
```

---

## 6. JavaScript API Reference

`webchat-config.js` exposes these global functions after the widget loads:

### `openChat()`

Opens the chat window programmatically (e.g. triggered by a button).

```javascript
document.getElementById("my-chat-button").addEventListener("click", openChat);
```

### `closeChat()`

Closes the chat window.

```javascript
// Auto-close after 10 minutes of inactivity
setTimeout(closeChat, 600_000);
```

### `sendChatMessage(message)`

Sends a message to the agent as if the user typed it.

```javascript
// Pre-fill a query based on current page context
sendChatMessage("Tell me about Bob Shell slash commands");
```

### `showChatLoadError()`

Called automatically if the wxO loader fails to load. Injects a fallback
error message into `#wxo-chat-root`. Override to customise the error UI.

```javascript
// Custom error handler
window.showChatLoadError = function() {
  document.getElementById("wxo-chat-root").textContent =
    "Chat is temporarily unavailable. Please try again later.";
};
```

---

## 7. Embedding in a Production Site

### 7.1 Minimal snippet (any framework)

Paste this just before `</body>` in any HTML page:

```html
<!-- Mount point -->
<div id="wxo-chat-root"></div>

<!-- wxO Web Chat embed — generated by: bash scripts/get_webchat_embed.sh -->
<script>
window.wxOConfiguration = {
  orchestrationID:    "YOUR_ORCHESTRATION_ID",
  hostURL:            "https://api.eu-de.watson-orchestrate.cloud.ibm.com",
  rootElementID:      "wxo-chat-root",
  showLauncher:       true,
  crn:                "YOUR_CRN",
  deploymentPlatform: "ibmcloud",
  chatOptions: {
    agentId:            "YOUR_AGENT_ID",
    agentEnvironmentId: "YOUR_AGENT_ENV_ID"
  }
};
setTimeout(function () {
  var s = document.createElement("script");
  s.src = window.wxOConfiguration.hostURL + "/wxochat/wxoLoader.js?embed=true";
  s.addEventListener("load", function() { wxoLoader.init(); });
  document.head.appendChild(s);
}, 0);
</script>
```

### 7.2 React integration

```jsx
// components/BobChat.jsx
import { useEffect } from "react";

export default function BobChat() {
  useEffect(() => {
    window.wxOConfiguration = {
      orchestrationID:    process.env.NEXT_PUBLIC_WXO_ORCHESTRATION_ID,
      hostURL:            process.env.NEXT_PUBLIC_WXO_HOST_URL,
      rootElementID:      "wxo-chat-root",
      showLauncher:       true,
      crn:                process.env.NEXT_PUBLIC_WXO_CRN,
      deploymentPlatform: "ibmcloud",
      chatOptions: {
        agentId:            process.env.NEXT_PUBLIC_WXO_AGENT_ID,
        agentEnvironmentId: process.env.NEXT_PUBLIC_WXO_AGENT_ENV_ID,
      },
    };

    const script = document.createElement("script");
    script.src = `${window.wxOConfiguration.hostURL}/wxochat/wxoLoader.js?embed=true`;
    script.onload = () => { if (window.wxoLoader) wxoLoader.init(); };
    document.head.appendChild(script);

    return () => {
      // Cleanup on unmount
      if (window.wxoLoader?.destroy) wxoLoader.destroy();
    };
  }, []);

  return <div id="wxo-chat-root" aria-label="IBM Bob chat" />;
}
```

Environment variables for Next.js (`.env.local`):

```
NEXT_PUBLIC_WXO_ORCHESTRATION_ID=...
NEXT_PUBLIC_WXO_HOST_URL=https://api.eu-de.watson-orchestrate.cloud.ibm.com
NEXT_PUBLIC_WXO_CRN=crn:v1:bluemix:public:...
NEXT_PUBLIC_WXO_AGENT_ID=...
NEXT_PUBLIC_WXO_AGENT_ENV_ID=...
```

> ⚠️ These variables start with `NEXT_PUBLIC_` which means they ARE exposed
> to the browser. That is correct — these IDs are not secrets (see §8).

### 7.3 Content Security Policy

If your site has a strict CSP, add these directives:

```
script-src  'self' https://api.eu-de.watson-orchestrate.cloud.ibm.com
            https://*.eu-de.watson-orchestrate.cloud.ibm.com
            https://*.watson.appdomain.cloud;
connect-src 'self' https://api.eu-de.watson-orchestrate.cloud.ibm.com
            https://*.eu-de.watson-orchestrate.cloud.ibm.com;
style-src   'self' 'unsafe-inline' https://fonts.googleapis.com;
font-src    'self' https://fonts.gstatic.com https://1.www.s81c.com;
```

If using a `nonce`-based CSP:

```javascript
window.wxOConfiguration = {
  // ... other config ...
  cspNonce: "<server-generated-nonce>"
};
```

---

## 8. Security

### 8.1 IDs are not secrets

The `orchestrationID`, `agentId`, and `agentEnvironmentId` in the embed
snippet are **client-visible identifiers**, not credentials. Per IBM documentation:

> These identifiers are not considered secret, and are visible to anyone who
> has access to your website. Anyone who has these IDs can use them to send
> messages to your assistant and receive its replies. However, these IDs
> cannot be used to log in to your account, make changes to your assistant,
> or retrieve logs or analytics information about your assistant.

### 8.2 What IS secret

Keep these out of client-side code and never commit them to git:

| Secret | Where it lives | How it's protected |
|---|---|---|
| `ORCHESTRATE_API_KEY` | `.env` only | `.gitignore` excludes `.env` |
| `ORCHESTRATE_TOKEN` | `.env` only | `.gitignore` + short expiry (~60 min) |
| `BOB_SEARCH_API_TOKEN` | `.env` only | `.gitignore` |

### 8.3 Transport security

All chat traffic between the browser and the wxO platform is encrypted with
**TLS 1.2+**. The `hostURL` must always be `https://`.

### 8.4 Optional: enhanced web-chat security (JWT mode)

IBM wxO embed security is **ON by default**. Without configuration, every
widget auth request returns HTTP 401 `WXO-PROXY-10080E`. Two fix paths exist:

**Path A — Unsecured (development / low-risk public agents)**

1. Open your wxO tenant: `Administration → Settings → Embed Security`
2. Toggle **Security: OFF** → Save

No backend changes required. The embed snippet works as-is.

**Path B — Secured with JWT (production / user-authenticated agents)**

Generates short-lived RS256 JWTs so only your backend can authorise chat sessions.

```bash
# Step 1: Generate RSA-2048 key pair
bash scripts/generate_rsa_keys.sh
# Outputs: keys/wxo_embed_private.pem (server only) + keys/wxo_embed_public.pem

# Step 2: Upload public key to wxO UI
#   Administration → Settings → Embed Security → Security: ON
#   Paste the contents of keys/wxo_embed_public.pem → Save

# Step 3: Start the JWT signing backend
source venv/bin/activate
python scripts/jwt_server.py   # listens on :3001; EMBED_PRIVATE_KEY_FILE from .env

# Step 4: Add identityToken to wxOConfiguration in your page
```

```js
window.wxOConfiguration = {
  // ... same fields as unsecured ...
  chatOptions: {
    agentId:            "YOUR_AGENT_ID",
    agentEnvironmentId: "YOUR_ENV_ID",
    identityToken: {
      getToken: async function() {
        const res  = await fetch("http://localhost:3001/api/token");
        const data = await res.json();
        return data.token;  // raw RS256-signed JWT
      }
    }
  }
};
```

See `scripts/jwt_server.py` for the full server implementation and
`web/demo-secured.html` for a live demo with token inspector.

For production, replace `localhost:3001` with your authenticated backend URL and
add user identity (`userId`, `name`) to the token request body via POST.

See also: [IBM docs — web-chat security](https://www.ibm.com/docs/en/watsonx/watson-orchestrate/current?topic=overview-how-web-chat-works#security)

### 8.5 SSRF protection in tools

The `search_bob_documentation` tool enforces an allowlist of hostnames for
the Bob Search API (`internal.bob.ibm.com`, `bob.ibm.com`). Arbitrary URLs
cannot be passed to the tool.

---

## 9. Accessibility

`web/index.html` implements:

| Feature | Implementation |
|---|---|
| Skip link | `<a href="#main-content" class="skip-link">` — visible on focus |
| Landmark roles | `<header role="banner">`, `<main>`, `<footer role="contentinfo">`, `role="complementary"` on chat root |
| ARIA labels | All interactive elements have `aria-label` |
| Keyboard navigation | All buttons/links operable via Tab + Enter/Space |
| Focus indicators | `:focus-visible` outlines on all interactive elements |
| Reduced motion | `@media (prefers-reduced-motion: reduce)` disables transitions |
| Colour contrast | IBM Design Language palette — all text meets WCAG 2.1 AA (4.5:1 minimum) |
| Semantic HTML | `<article>`, `<section>`, `<nav>`, `<h1>`–`<h3>` hierarchy |
| `role="list"` | Applied to grids used as lists |
| `aria-live="polite"` | Status bar updates announced to screen readers |

The wxO chat widget itself is WCAG 2.1 AA compliant per IBM's accessibility
statement.

---

## 10. Troubleshooting

### 10.1 Chat bubble not appearing

| Symptom | Cause | Fix |
|---|---|---|
| No bubble after page load | `webchat-config.js` has placeholder values | Run `bash scripts/get_webchat_embed.sh` |
| Script 404 in console | `hostURL` is wrong | Verify `hostURL` matches active environment URL |
| Console: `wxoLoader is not defined` | Loader script failed to load | Check network tab; ensure CSP allows the hostURL domain |
| `orchestrationID` error | ID mismatch or agent not deployed | Confirm `orchestrate agents deploy -n ibm_bob_assistant` succeeded |

### 10.2 Chat loads but agent doesn't respond

| Symptom | Cause | Fix |
|---|---|---|
| "Agent unavailable" message | `agentEnvironmentId` points to draft env | Re-run `get_webchat_embed.sh` with `--env live` |
| Responses have no citations | KB not attached | Check `knowledge_base: - ibm_bob_docs` in agent YAML; re-import |
| Tool not called | Tool import failed | Run `orchestrate tools list \| cat \| grep bob` to verify tools exist |

### 10.3 `get_webchat_embed.sh` fails

```
[ERROR] orchestrate channels webchat embed returned an error
```

| Error text | Cause | Fix |
|---|---|---|
| `token expired` | wxO session stale | Refresh `ORCHESTRATE_API_KEY` in `.env` |
| `agent not found` | Agent in draft or missing | `orchestrate agents deploy -n ibm_bob_assistant` |
| `no channel configured` | Web-chat channel not created | Use wxO UI to create a web-chat channel for the agent first |

### 10.4 CORS errors in browser console

The wxO loader makes cross-origin requests. Ensure your page is served over
`http://` or `https://` — `file://` protocol blocks CORS.

```bash
# Use Python's built-in server instead of opening the file directly
python3 -m http.server 8080 --directory web
```

### 10.5 CSP violations

```
Refused to load script from 'https://api.eu-de.watson-orchestrate.cloud.ibm.com/...'
```

Add the wxO domain to your `script-src` CSP directive (see §7.3).

---

## 11. CLI Quick Reference

```bash
# Generate web-chat embed snippet → web/webchat-config.js
bash scripts/get_webchat_embed.sh

# Manual embed snippet generation (interactive)
orchestrate channels webchat embed --agent-name ibm_bob_assistant --env live

# List all channels configured for the agent
orchestrate channels list-channels --agent-name ibm_bob_assistant --env live

# Create a web-chat channel (if none exists)
orchestrate channels create --agent-name ibm_bob_assistant --env live --type webchat

# Deploy agent to Live state
orchestrate agents deploy -n ibm_bob_assistant

# Check agent status
orchestrate agents list | cat | grep ibm_bob

# Serve demo page locally
python3 -m http.server 8080 --directory web
# Open: http://localhost:8080

# Run all tests
python -m pytest tests/ -v    # Expected: 141 passed
```

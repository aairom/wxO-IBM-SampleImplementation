PRESENTATION OUTLINE
============================================================
Template: IBM-Template_AI-Ready.pptx
Total Slides: 20

Slide 1: cover (COVER-01)
------------------------------------------------------------
• title: "Embedded chat agent implementation" [34/70 chars] ✓
• name_and_job_title: "IBM watsonx Orchestrate — technical deep dive" [45/40 chars] ✗
• contact_details: "From sample agent to production-secured JWT embed" [49/50 chars] ✓

Slide 5: agenda (TOC-01)
------------------------------------------------------------
• title: "Agenda" [6/40 chars] ✓
• table_of_contents_01: "01  Sample agent foundation
Architecture, components, baseline setup

02  Pyt..." [223/50 chars] ✗ ⚠️ IBM-BRAND
• table_of_contents_02: "04  Secured embed chat (JWT)
RSA key pair, token signing, and enterprise secu..." [150/50 chars] ✗ ⚠️ IBM-BRAND

Slide 20: section_sample (SECTION-03)
------------------------------------------------------------
• title: "Sample agent foundation" [23/60 chars] ✓
• number: "01" [2/4 chars] ✓
• subtitle: "Initial architecture and baseline setup" [39/80 chars] ✓
• body_copy: "IBM watsonx Orchestrate native agent
Knowledge base (Milvus vector store)
ADK..." [103/800 chars] ✓ ⚠️ IBM-BRAND

Slide 22: sample_arch (CONTENT-2COL)
------------------------------------------------------------
• title: "Sample agent architecture" [25/80 chars] ✓
• body_copy_01: "Agent layer
The ibm_bob_assistant native agent is defined as a react_core age..." [384/600 chars] ✓ ⚠️ IBM-BRAND
• body_copy_02: "Tool layer
Two @tool-decorated Python functions — search_bob_documentation an..." [382/600 chars] ✓ ⚠️ IBM-BRAND

Slide 28: sample_comps (GRID-4UP-01)
------------------------------------------------------------
• header: "Key components" [14/30 chars] ✓
• title: "Sample agent — component inventory" [34/80 chars] ✓
• body_copy_title_01: "Agent YAML" [10/20 chars] ✓
• body_copy_01: "agents/ibm_bob_assistant.agent.yaml — defines the agent, model, KB reference,..." [115/150 chars] ✓
• body_copy_title_02: "Knowledge base" [14/20 chars] ✓
• body_copy_02: "knowledge-bases/ibm_bob_docs.kb.yaml — references 11 .txt files. Milvus index..." [115/150 chars] ✓ ⚠️ IBM-BRAND
• body_copy_title_03: "Python tools" [12/20 chars] ✓
• body_copy_03: "tools/live_bob_search.py — defines search_bob_documentation and get_bob_doc_s..." [114/150 chars] ✓
• body_copy_title_04: "Config script" [13/20 chars] ✓
• body_copy_04: "scripts/get_webchat_embed.sh — fetches live embed IDs from wxO API and writes..." [100/150 chars] ✓

Slide 20: section_python (SECTION-03)
------------------------------------------------------------
• title: "Python built agent" [18/60 chars] ✓
• number: "02" [2/4 chars] ✓
• subtitle: "Production implementation with ADK tooling" [42/80 chars] ✓
• body_copy: "orchestrate CLI deployment
PyJWT + cryptography stack
Automated import pipeli..." [97/800 chars] ✓

Slide 24: python_arch (CONTENT-2COL-HEADERS)
------------------------------------------------------------
• title: "Production agent architecture" [29/80 chars] ✓
• body_copy_title_01: "Backend services" [16/50 chars] ✓
• body_copy_01: "scripts/import_tools.py and scripts/import_agent.py orchestrate the full impo..." [281/600 chars] ✓
• body_copy_title_02: "Runtime dependencies" [20/50 chars] ✓
• body_copy_02: "requirements.txt pins orchestrate CLI, PyJWT >= 2.8.0, and cryptography >= 41..." [303/600 chars] ✓ ⚠️ IBM-BRAND

Slide 17: python_tools (CONTENT-3COL-DIVIDERS)
------------------------------------------------------------
• title: "Tool and script reference" [25/80 chars] ✓
• body_copy_title_01: "Import pipeline" [15/50 chars] ✓
• body_copy_01: "scripts/start.sh
Full 9-step idempotent deploy. Flags: --force-reimport, --sk..." [195/600 chars] ✓ ⚠️ IBM-BRAND
• body_copy_title_02: "Agent tooling" [13/50 chars] ✓
• body_copy_02: "scripts/import_tools.py
Imports @tool functions, validates, writes JSON repor..." [183/600 chars] ✓
• body_copy_title_03: "KB and docs" [11/50 chars] ✓
• body_copy_03: "scripts/fetch_ibm_bob_docs.py
Refreshes KB .txt files from live Bob search AP..." [217/600 chars] ✓ ⚠️ IBM-BRAND

Slide 46: python_deploy (TABLE-01)
------------------------------------------------------------
• title: "Deployment command reference" [28/80 chars] ✓
• table: 3 columns × 8 rows
  Headers: Command | Purpose | Use case
  Row 1: ./scripts/start.sh | Full 9-step deploy | First-time setup
  Row 2: ./scripts/start.sh --skip-kb-check | Skip KB poll | KB already Ready
  Row 3: ./scripts/start.sh --force-reimport | Force clean slate | After YAML changes
  ... and 5 more rows

Slide 20: section_unsec (SECTION-03)
------------------------------------------------------------
• title: "Unsecured embed chat" [20/60 chars] ✓
• number: "03" [2/4 chars] ✓
• subtitle: "Step-by-step integration, code patterns, and runtime" [52/80 chars] ✓
• body_copy: "Zero-backend integration
Static HTML + generated config
Authentication toggle..." [93/800 chars] ✓

Slide 11: unsec_stats (STATS-3UP)
------------------------------------------------------------
• title: "Unsecured embed — at a glance" [29/80 chars] ✓
• statistic_01: "0" [1 chars]
• statistic_claim_01: "Backend services required — serves entirely from static files" [61 chars]
• statistic_02: "3" [1 chars]
• statistic_claim_02: "Config fields needed — orchestrationID, hostURL, agentId" [56 chars]
• statistic_03: "1" [1 chars]
• statistic_claim_03: "Admin toggle to flip — Embed Security OFF in wxO tenant UI" [58 chars] ⚠️ IBM-BRAND
• statistic_sources: "Source: IBM watsonx Orchestrate embed documentation, project web/demo-unsecur..." [84 chars]

Slide 17: unsec_steps (CONTENT-3COL-DIVIDERS)
------------------------------------------------------------
• title: "Unsecured embed — setup in three steps" [38/80 chars] ✓
• body_copy_title_01: "Step 1 — disable security" [25/50 chars] ✓
• body_copy_01: "Open your wxO tenant:
eu-de.watson-orchestrate.cloud.ibm.com

Navigate to:
Ad..." [232/600 chars] ✓ ⚠️ IBM-BRAND
• body_copy_title_02: "Step 2 — generate config" [24/50 chars] ✓
• body_copy_02: "Run the config generator:
bash scripts/get_webchat_embed.sh

This calls the w..." [282/600 chars] ✓
• body_copy_title_03: "Step 3 — serve and test" [23/50 chars] ✓
• body_copy_03: "Start the static web server:
python3 -m http.server 8080 --directory web

Ope..." [274/600 chars] ✓ ⚠️ IBM-BRAND

Slide 22: unsec_code (CONTENT-2COL)
------------------------------------------------------------
• title: "Unsecured embed — configuration and identifiers" [47/80 chars] ✓
• body_copy_01: "Required configuration fields

orchestrationID — tenant + instance composite
..." [494/600 chars] ✓ ⚠️ IBM-BRAND
• body_copy_02: "Identifiers are not secrets

The orchestrationID, agentId, and agentEnvironme..." [460/600 chars] ✓ ⚠️ IBM-BRAND

Slide 17: unsec_issues (CONTENT-3COL-DIVIDERS)
------------------------------------------------------------
• title: "Unsecured embed — troubleshooting" [33/80 chars] ✓
• body_copy_title_01: "Auth error banner" [17/50 chars] ✓
• body_copy_01: "Symptom: Authentication Error, Agent fetching failed.
Cause: Embed Security t..." [173/600 chars] ✓ ⚠️ IBM-BRAND
• body_copy_title_02: "Widget not loading" [18/50 chars] ✓
• body_copy_02: "Symptom: No chat bubble appears.
Causes: webchat-config.js is stale; CSP bloc..." [192/600 chars] ✓ ⚠️ IBM-BRAND
• body_copy_title_03: "Empty agent answers" [19/50 chars] ✓
• body_copy_03: "Symptom: Chat loads but queries return no relevant answers.
Cause: KB not yet..." [165/600 chars] ✓ ⚠️ IBM-BRAND

Slide 20: section_sec (SECTION-03)
------------------------------------------------------------
• title: "Secured embed chat (JWT)" [24/60 chars] ✓
• number: "04" [2/4 chars] ✓
• subtitle: "RSA signing, token lifecycle, and enterprise security" [53/80 chars] ✓
• body_copy: "RS256 asymmetric signing
RSA-2048 key pair
Short-lived tokens (max 7100 s)" [74/800 chars] ✓

Slide 11: sec_stats (STATS-3UP)
------------------------------------------------------------
• title: "Secured embed — key facts" [25/80 chars] ✓
• statistic_01: "RS256" [5 chars]
• statistic_claim_01: "JWT signing algorithm — RSA-2048 asymmetric key pair; private key never leave..." [89 chars]
• statistic_02: "7100 s" [6 chars]
• statistic_claim_02: "Maximum token lifetime enforced by IBM watsonx Orchestrate — default is 3600 ..." [95 chars]
• statistic_03: "4" [1 chars]
• statistic_claim_03: "Setup steps — generate keys, upload public key, start JWT server, add identit..." [92 chars]
• statistic_sources: "Source: IBM watsonx Orchestrate secured embed documentation, scripts/jwt_serv..." [82 chars]

Slide 28: sec_comps (GRID-4UP-01)
------------------------------------------------------------
• header: "Secured embed components" [24/30 chars] ✓
• title: "JWT architecture — component roles" [34/80 chars] ✓
• body_copy_title_01: "generate_rsa_keys.sh" [20/20 chars] ✓
• body_copy_01: "Generates RSA-2048 key pair. Outputs keys/wxo_embed_private.pem (chmod 600) a..." [149/150 chars] ✓ ⚠️ IBM-BRAND
• body_copy_title_02: "jwt_server.py" [13/20 chars] ✓
• body_copy_02: "Python HTTP server on :3001. GET / (health), GET /api/token (anon JWT), POST ..." [130/150 chars] ✓
• body_copy_title_03: "identityToken" [13/20 chars] ✓
• body_copy_03: "Added to chatOptions. Widget calls getToken() on init and before token expiry..." [135/150 chars] ✓ ⚠️ IBM-BRAND
• body_copy_title_04: "wxO tenant config" [17/20 chars] ✓
• body_copy_04: "Upload keys/wxo_embed_public.pem at Administration, Settings, Embed Security,..." [127/150 chars] ✓ ⚠️ IBM-BRAND

Slide 17: sec_jwt (CONTENT-3COL-DIVIDERS)
------------------------------------------------------------
• title: "JWT token lifecycle" [19/80 chars] ✓
• body_copy_title_01: "Token claims (RS256 payload)" [28/50 chars] ✓
• body_copy_01: "iss — ibm_bob_assistant_demo
sub — user ID or anonymous-<uuid8>
aud — watsonx..." [282/600 chars] ✓ ⚠️ IBM-BRAND
• body_copy_title_02: "Token flow — browser to wxO" [27/50 chars] ✓
• body_copy_02: "1. Browser loads page with wxO widget script
2. wxoLoader.init() is called
3...." [380/600 chars] ✓ ⚠️ IBM-BRAND
• body_copy_title_03: "Environment variables" [21/50 chars] ✓
• body_copy_03: "EMBED_PRIVATE_KEY_FILE — path to PEM private key
JWT_SERVER_PORT — default 30..." [255/600 chars] ✓

Slide 22: sec_issues (CONTENT-2COL)
------------------------------------------------------------
• title: "Secured embed — troubleshooting" [31/80 chars] ✓
• body_copy_01: "Error: WXO-PROXY-10080E (kid not found)
Cause: Public key not uploaded, or Se..." [528/600 chars] ✓ ⚠️ IBM-BRAND
• body_copy_02: "Error: CORS blocked on /api/token
Cause: Web page origin not in ALLOWED_ORIGI..." [479/600 chars] ✓ ⚠️ IBM-BRAND

Slide 8: closing_stmt (STATEMENT-01)
------------------------------------------------------------
• title: "From sample agent to production security" [40/80 chars] ✓
• quote: "“The authentication error is not a code bug — it is a tenant configuration re..." [264/150 chars] ✗ ⚠️ IBM-BRAND (must use curly quotes: )
• quote_name: "IBM watsonx Orchestrate — ibm_bob_assistant implementation guide" [64/60 chars] ⚠ ℹ️ IBM-BRAND (must use curly quotes: )

============================================================
VALIDATION SUMMARY
============================================================

Character Limits:
  ✓ = Within character limit
  ⚠ = At or near limit (90-110%)
  ✗ = Exceeds limit (requires truncation)

IBM Brand Guidelines:
  ⚠️ IBM-BRAND = High priority issue (capitalization)
  ℹ️ IBM-BRAND = Medium priority issue (quotation marks)


============================================================
IBM BRAND GUIDELINE ISSUES
============================================================

HIGH PRIORITY (Capitalization):
------------------------------------------------------------
• agenda - table_of_contents_01
  Issue: Uses title case instead of sentence-case capitalization
  Suggested: 01 sample agent foundation
Architecture, components, baseline setup

02 Python built agent
Production implementation with tools and knowledge base

03 unsecured embed chat
Integration, code patterns, and runtime behavior

• agenda - table_of_contents_02
  Issue: Uses title case instead of sentence-case capitalization
  Suggested: 04 secured embed chat (JWT)
Rsa key pair, token signing, and enterprise security

05 troubleshooting
Common errors, diagnostic commands, remediation

• section_sample - body_copy
  Issue: Uses title case instead of sentence-case capitalization
  Suggested: IBM watsonx orchestrate native agent
Knowledge base (milvus vector store)
Adk-based deployment pipeline

• sample_arch - body_copy_01
  Issue: Uses title case instead of sentence-case capitalization
  Suggested: Agent layer
The ibm_bob_assistant native agent is defined as a react_core agent in YAML and deployed via the orchestrate CLI. it references a milvus-backed knowledge base containing 11 IBM Bob documentation files.

Knowledge base
Ibm_bob_docs KB indexes 11 .txt files covering IBM Bob features, modes, skills, MCP, security, and telemetry. content is chunked and vectorized on import.

• sample_arch - body_copy_02
  Issue: Uses title case instead of sentence-case capitalization
  Suggested: Tool layer
Two @tool-decorated Python functions — search_bob_documentation and get_bob_doc_section — provide grounded retrieval against the KB. they enforce an allowlist of hostnames for SSRF protection.

Deploy pipeline
scripts/start.sh runs a 9-step idempotent pipeline: authenticate, import KB, poll readiness, import tools, import agent, deploy to live, regenerate embed config.

• sample_comps - body_copy_02
  Issue: Uses title case instead of sentence-case capitalization
  Suggested: knowledge-bases/ibm_bob_docs.kb.yaml — references 11 .txt files. milvus indexes on import; poll until ready = true.

• python_arch - body_copy_02
  Issue: Uses title case instead of sentence-case capitalization
  Suggested: requirements.txt pins orchestrate CLI, pyjwt >= 2.8.0, and cryptography >= 41.0.0. managed via uv venv + uv pip install.

Key env vars: orchestrate_url, ibm_cloud_api_key, orchestrate_env_name. never hard-coded — read from .env at startup.

Logs written to logs/ (gitignored content, tracked directory).

• python_tools - body_copy_01
  Issue: Uses title case instead of sentence-case capitalization
  Suggested: scripts/start.sh
Full 9-step idempotent deploy. flags: --force-reimport, --skip-kb-check, --start-jwt-server

scripts/stop.sh
Undeploy agent + KB + stop JWT server. flags: --keep-kb, --keep-agent

• python_tools - body_copy_03
  Issue: Uses title case instead of sentence-case capitalization
  Suggested: scripts/fetch_ibm_bob_docs.py
Refreshes KB .txt files from live Bob search API. requires bob_search_api_url and bob_search_api_token env vars.

Re-import KB after refresh: orchestrate knowledge-bases import -f kb.yaml

• unsec_stats - statistic_claim_03
  Issue: Uses title case instead of sentence-case capitalization
  Suggested: Admin toggle to flip — embed security OFF in wxo tenant UI

• unsec_steps - body_copy_01
  Issue: Uses title case instead of sentence-case capitalization
  Suggested: Open your wxo tenant:
eu-de.watson-orchestrate.cloud.ibm.com

Navigate to:
Administration, settings, embed security

Toggle security: OFF and click save.

Without this step, all widget auth requests return HTTP 401 wxo-proxy-10080e.

• unsec_steps - body_copy_03
  Issue: Uses title case instead of sentence-case capitalization
  Suggested: Start the static web server:
Python3 -m http.server 8080 --directory web

Open in browser:
http://localhost:8080

The wxo loader (wxoLoader.js) is fetched from the IBM CDN. the chat bubble appears bottom-right. click and type a test query to confirm end-to-end connectivity.

• unsec_code - body_copy_01
  Issue: Uses title case instead of sentence-case capitalization
  Suggested: Required configuration fields

Orchestrationid — tenant + instance composite
Hosturl — regional API base URL
Crn — IBM Cloud resource name
Deploymentplatform — ibmcloud
chatOptions.agentId — agent UUID
chatOptions.agentEnvironmentId — live env UUID

The loader script (wxoLoader.js) is appended dynamically after the config is set. call wxoLoader.init() in the script.onload handler.

webchat-config.js is generated by scripts/get_webchat_embed.sh on every start.sh run. never edit it manually.

• unsec_code - body_copy_02
  Issue: Uses title case instead of sentence-case capitalization
  Suggested: Identifiers are not secrets

The orchestrationid, agentid, and agentenvironmentid are client-visible identifiers. per IBM documentation, anyone with these ids can send messages and receive replies, but cannot log in to your account, modify the agent, or retrieve logs.

What IS secret — keep in .env only:
Orchestrate_api_key
Orchestrate_token (short expiry)
Bob_search_api_token

The RSA private key (secured embed only) must never appear in client-side code.

• unsec_issues - body_copy_01
  Issue: Uses title case instead of sentence-case capitalization
  Suggested: Symptom: authentication error, agent fetching failed.
Cause: embed security toggle is ON (default state).
Fix: administration, settings, embed security, security: OFF, save.

• unsec_issues - body_copy_02
  Issue: Uses title case instead of sentence-case capitalization
  Suggested: Symptom: no chat bubble appears.
Causes: webchat-config.js is stale; CSP blocks the wxo CDN; wrong hosturl region.
Fix: rerun get_webchat_embed.sh. check browser console for CSP or 404 errors.

• unsec_issues - body_copy_03
  Issue: Uses title case instead of sentence-case capitalization
  Suggested: Symptom: chat loads but queries return no relevant answers.
Cause: KB not yet ready.
Fix: orchestrate knowledge-bases status -n ibm_bob_docs — wait for ready = true.

• sec_comps - body_copy_01
  Issue: Uses title case instead of sentence-case capitalization
  Suggested: Generates rsa-2048 key pair. outputs keys/wxo_embed_private.pem (chmod 600) and keys/wxo_embed_public.pem. non-interactive when called from start.sh.

• sec_comps - body_copy_03
  Issue: Uses title case instead of sentence-case capitalization
  Suggested: Added to chatoptions. widget calls gettoken() on init and before token expiry. returns a raw rs256-signed JWT string to the wxo widget.

• sec_comps - body_copy_04
  Issue: Uses title case instead of sentence-case capitalization
  Suggested: Upload keys/wxo_embed_public.pem at administration, settings, embed security, security: ON. wxo verifies jwts against this key.

• sec_jwt - body_copy_01
  Issue: Uses title case instead of sentence-case capitalization
  Suggested: Iss — ibm_bob_assistant_demo
Sub — user ID or anonymous-<uuid8>
Aud — watsonx-orchestrate
Iat — issued-at unix timestamp
Exp — iat + jwt_expiry_seconds
Jti — UUID v4 (replay prevention)
Name — display name (optional)

All fields follow the IBM watsonx orchestrate JWT specification.

• sec_jwt - body_copy_02
  Issue: Uses title case instead of sentence-case capitalization
  Suggested: 1. browser loads page with wxo widget script
2. wxoLoader.init() is called
3. widget calls identityToken.getToken()
4. browser fetches GET localhost:3001/api/token
5. jwt_server.py signs token with private key
6. widget sends JWT to wxo auth endpoint
7. wxo verifies JWT with uploaded public key
8. session established — chat is active
9. widget auto-refreshes token before expiry

• sec_issues - body_copy_01
  Issue: Uses title case instead of sentence-case capitalization
  Suggested: Error: wxo-proxy-10080e (kid not found)
Cause: public key not uploaded, or security toggle is OFF.
Fix: upload keys/wxo_embed_public.pem at administration, settings, embed security, security: ON.

Error: JWT server not reachable
Cause: jwt_server.py not running, or wrong port.
Fix: source venv/bin/activate && Python scripts/jwt_server.py
Check: GET http://localhost:3001/ returns {status: ok}.

Error: token expired immediately
Cause: jwt_expiry_seconds exceeds 7100 (IBM hard limit).
Fix: set JWT_EXPIRY_SECONDS=3600 in .env.

• sec_issues - body_copy_02
  Issue: Uses title case instead of sentence-case capitalization
  Suggested: Error: CORS blocked on /api/token
Cause: web page origin not in allowed_origins.
Fix: add page origin to allowed_origins in .env.
Example: ALLOWED_ORIGINS=http://localhost:8080,https://myapp.example.com

Error: private key not found at startup
Cause: embed_private_key_file path is wrong or keys/ not generated.
Fix: run bash scripts/generate_rsa_keys.sh.

Stop the JWT server
scripts/stop.sh uses lsof -ti tcp:3001 to find and kill the process. manual: kill $(lsof -ti tcp:3001)

• closing_stmt - quote
  Issue: Uses title case instead of sentence-case capitalization
  Suggested: “The authentication error is not a code bug — it is a tenant configuration requirement. IBM watsonx orchestrate embed security is ON by default. toggle it OFF for quick integration, or sign jwts with an rsa-2048 key pair for enterprise-grade identity propagation.”

MEDIUM PRIORITY (Quotation Marks):
------------------------------------------------------------
• closing_stmt - quote
  Issue: Quote text should be wrapped in quotation marks
  Suggested: "“The authentication error is not a code bug — it is a tenant configuration requirement. IBM watsonx Orchestrate embed security is ON by default. Toggle it OFF for quick integration, or sign JWTs with an RSA-2048 key pair for enterprise-grade identity propagation.”"

• closing_stmt - quote_name
  Issue: Quote text should be wrapped in quotation marks
  Suggested: "IBM watsonx Orchestrate — ibm_bob_assistant implementation guide"

============================================================
Total Issues: 27

IBM Brand Guidelines:
• Use sentence-case capitalization (capitalize only first word and proper nouns)
• Wrap quote text in curly quotation marks ()
• Proper nouns: IBM, Watson, watsonx, Bob


============================================================
Next Steps:
1. Review the outline above
2. Verify all content is accurate
3. Check character counts for any ✗ or ⚠ indicators
4. Fix any IBM brand guideline issues (⚠️ or ℹ️ indicators)
5. Approve to proceed with generation

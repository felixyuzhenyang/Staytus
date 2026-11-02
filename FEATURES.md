# Feature status

| Capability | Implemented | Live dependency / limit |
| --- | --- | --- |
| Accounts/onboarding | Registration/login, hashes, rotating sessions, owned profile | No verified email/reset or production SSO |
| Frontend | Independent dashboard/chat/policies/approvals/profile/connections/updates/audit | Browser and production-build checks passed |
| Planning | YAML school adapter, deterministic internal targets and traces | No invented filing windows; Penn only; other schools public-only |
| Public capture | Scheduler, manual refresh, real snapshots/chunks/history/citations | Three federal sources captured; three Penn sources HTTP403 |
| Policy status | Pending capture separate from legal effect | Review needed before a legal rule can activate |
| Retrieval | Shared chat/API/tool entry, scoped hybrid retrieval; real multilingual embeddings and Chinese query verified | Five current public-source chunks indexed; larger topic coverage/evaluation and Penn 403 resolution remain |
| Assistant | One Orchestrate route, private threads, safe errors; local BFF and actual visual browser chat verified | Private local configuration enabled; temporary tool gateway must remain running |
| Orchestrate tools | 13 imported/bound tools; four bounded Live cases exercised all13 with17invocations, account isolation, audits and cleanup | Real mailbox access and final provider writes still need consent/configuration; previews never imply execution |
| Approvals | Content hash, TTL, current profile version, bound connected account, atomic one-use execution, audit | Relinking requires a fresh preview; uncertain provider results require manual reconciliation |
| Calendar | Approved `.ics` with alarms; Google/Outlook write adapters, separate scopes and destination preview | OAuth app registration and user consent required; no real provider calendar write tested |
| Email connection | Google/Microsoft OAuth+PKCE, encrypted tokens/refresh | OAuth app credentials and user consent required |
| Email read/draft | Shared account-scoped reads; separate Agent-preview toggle and draft scope; provider draft | OAuth application registration and user consent still needed; no automatic send |
| Updates/reminders | Durable inbox, visible-page popups, timezone-aware daily/weekly/monthly scheduling; opt-in SMTP digest outbox | Backend must run; SMTP sender and verified linked recipient required for real email; no device background push |
| Penn private portal | Unsupported state and official links | No portal authorization, private status reads or submissions |
| Test scenarios | Synthetic profiles/replays under tests only | No product demo login/chat/replay |
| Deployment | Bootstrap, containers, pgvector models and instructions | Cloud/PostgreSQL/retention/production identity validation pending |

Provider code and mocked HTTP tests are distinct from a verified external connection.

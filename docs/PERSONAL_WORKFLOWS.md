# Personal facts, application stages and future guided chat

## Implemented in this iteration

The existing owned profile now has an optional, typed `planning_details` JSON object in Supabase PostgreSQL. Alembic revision `20261103_0002` adds it with an empty-object default, preserving existing accounts and records. Unknown facts remain unknown; no live user's immigration details are filled in by the operator. The same conditional form is used in onboarding and Profile settings.

- F-1 activity (studying, post-completion OPT, STEM OPT, other/unknown) is separate from the application being tracked. A current OPT user can be preparing a STEM extension without overwriting their current EAD facts.
- OPT stages: unknown, not planning, considering, preparing, submitted, approved, active, completed, denied or withdrawn. The tracked type is pre-completion, initial post-completion or STEM extension. Optional facts include school-confirmed academic completion, DSO recommendation, application submission, requested start and current EAD start/end. Adviser-review answers are user-reported facts, not a grant of eligibility.
- Shared planning facts: next plan, extension stage/requested end, travel destination/return, passport/entry-visa expiry, whether a visa application is planned, I-94 D/S versus a dated admission and its date. No passport, visa, I-94, SEVIS or USCIS receipt identifying numbers are collected.
- J-1 student Academic Training stages and proposed/authorized dates remain separate from OPT. J-1 scholar category, sponsor and host department are recorded separately; scholar profiles cannot save student training fields.

Inputs are validated on create and after merging a partial update with saved data. Invalid EAD/training ranges, return before departure, unsupported fields and incompatible categories are rejected before persistence. Explicit null clears a fact. Category changes clear incompatible planning facts; the form explains this. Profile version increments invalidate prior action approvals, and the next authenticated chat/tool call receives the current structured profile.

`business_planning.py` provides deterministic stage selection and record checks, shared by the existing workflow guidance/dashboard/agent action-plan path. Submitted applications get receipt/progress and adviser-follow-up steps instead of an initial application checklist. Approved/active applications prompt EAD/date/reporting review. Not-planning/completed extension stages suppress the old extension-preparation target. Missing facts remain visible questions. Travel checks compare saved expiry dates with **return**, flag travel while an OPT application is pending and keep visa expiration distinct from authorized stay.

Additional internal planning targets feed the existing reminder inbox and opted-in digest pipeline: considering/preparing OPT produces a 60-day preparation buffer when the relevant date is known (academic completion for initial post-completion OPT, requested start for pre-completion OPT, current EAD end for STEM extension). Current/approved OPT with a saved EAD end produces a 30-day EAD-review buffer; authorized/active Academic Training with a saved end produces a 30-day sponsor-review buffer. These are configurable school-adapter product preferences, not legal windows. Submitting an application removes its preparation target; removed targets supersede existing unsent planning notices on the next reminder synchronization. Existing account-scoped scheduling, consent and Brevo delivery remain unchanged. This iteration does not claim a real personal reminder email or a real provider calendar write was performed.

## Legal-rule boundary and sources checked

No new legal deadline, grace-period countdown, eligibility approval or travel clearance is activated. Sources retain the existing capture/review/freshness gates; a fetched page or an LLM response cannot change active rules. The rule trace includes `business-planning-2026-11-03-v1`. Legal calculations need an explicitly reviewed, version-bound rule and all applicable facts; a general school page or an old numerical constant is not sufficient.

Primary pages inspected on 2026-11-03: [Penn OPT guide](https://global.upenn.edu/isss/opt/), [Penn STEM OPT](https://global.upenn.edu/isss/opt-stem/), [Penn travel](https://global.upenn.edu/isss/home/immigration/travel/) and [Penn final-rule resource center](https://global.upenn.edu/isss/dhs-final-rule-resource-center/). The USCIS OPT/STEM pages returned HTTP403 through the research tool. Conflicting/evolving guidance must be reviewed rather than silently converted into a filing rule. Signature validity depends on activity, document and re-entry circumstances; saving a signature date does not automatically establish permission to travel. This iteration intentionally does not turn a signature anniversary into an automatic legal conclusion.

## Feasible next increment: guided requests in chat (not implemented yet)

The existing chat already has starter prompts, but they currently send text. The proposed change is to make selected prompts launch an intent-specific form, for example **Plan an international trip**:

1. Show saved departure, return, destination, document dates, current activity and application stage; request only missing facts. Let the user review what will be saved.
2. Validate and save through the owned profile API, then send a structured intent referencing the new profile version to the existing authenticated chat route. Never let model-supplied account IDs select a principal.
3. Have Orchestrate request the personalized action plan and current official evidence. Deterministic checks supply dates/conditions; the model explains the plan and unresolved questions. A pending source is labelled pending.
4. Offer actual actions, such as preparing a calendar preview or opening the official request link. Existing final approval remains outside the model. Filing a school/government application is not implied.

The present profile changes provide most of the necessary data plumbing. A dedicated travel modal, intent state, review-before-save and a return-to-chat result are still needed. Do not label ordinary travel as an I-20 visa application: the workflow distinguishes a school document/travel endorsement from an entry-visa application.

## Feasible next increment: proactive assistant messages (not implemented yet)

A web page does not need to be open for the server to create a message. Use the existing cloud schedule and durable reminders as event producers, then add a separate message-generation outbox:

- A source-change or personal-planning event is matched to an owned profile. A content change is first labelled a detected change, not an effective legal policy or a confirmed personal impact.
- A unique key binds account, event, profile version and policy version. A bounded, retryable generation job gets only permitted profile facts and official evidence; mailbox previews remain excluded without their separate consent.
- The model writes a structured summary (what changed, why it may matter, unknown facts, next action, source links). Store it as a clearly labelled proactive assistant message with provenance. Do not insert a fabricated user question or trust generated HTML.
- The conversation API returns these persisted messages on the next visit. Email can link to the message, subject to the existing subscription; no browser-open requirement is introduced.
- On profile/source changes, invalidate stale generation work. Apply idempotency, token budgets and batching so each website edit does not trigger every user's LLM call. Never execute a calendar/email/application action because a background summary requested it.

No new multi-agent deployment is required for either increment. The server owns events, authorization and persistence; Orchestrate/model calls generate explanations and propose permitted actions. These features are assessed here as follow-up work, not claimed as delivered in the current profile/rule release.

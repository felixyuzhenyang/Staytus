# Staytus verification

This document describes how to validate the current checkout. Detailed dated test records are preserved in [the archived verification history](archive/verification-history/VERIFICATION_HISTORY.md).

## Automated checks

Run the repository checks from the project root:

```sh
make test
make build
```

`make test` runs the backend test suite, frontend TypeScript checks and the reviewed OpenAPI 3.0 tool-contract check. `make build` produces the Next.js production bundle.

The GitHub Actions workflow adds PostgreSQL-backed tests and builds both Docker images. These checks validate code, migrations, contracts and packaging. Provider availability and external account permissions require separate integration checks.

## Integration checks

The repository includes explicit scripts for the integrations that cannot be established by unit tests alone:

- `scripts/check_watsonx_connection.py` checks watsonx.ai configuration and can run bounded model probes.
- `scripts/orchestrate_preflight.py` inspects Orchestrate deployment prerequisites without changing the tenant.
- `scripts/verify_orchestrate_context.py` verifies signed user context and account isolation with synthetic records.
- `scripts/verify_orchestrate_tools.py` validates the published business-tool surface with synthetic records.
- `scripts/verify_public_deployment.py` checks the public web-to-backend flow with disposable accounts.
- `scripts/verify_google_calendar_connection.py` performs a read-only connection check after user consent.
- `scripts/verify_shared_database.py` checks shared PostgreSQL behavior with synthetic records.

Each script is offline or read-only by default where supported. Read its command help before selecting a live mode. Live checks may require configured provider credentials, an authorized test account and the script's explicit confirmation flag.

## Verification boundaries

- Successful automated tests do not prove that IBM, Google, Microsoft or Brevo is currently available.
- Source capture records the contents and capture time of a page. It does not by itself establish that the text is current law or an approved planning rule.
- Planning dates may include internal preparation targets. The interface identifies these separately from official filing dates.
- Mailbox, calendar and profile actions remain subject to the signed-in user's connection, consent and approval state.
- Use synthetic accounts for shared-environment checks and remove the exact test records afterward.

## Supporting documentation

- [Current architecture](ARCHITECTURE.md)
- [Database and containers](DATABASE_AND_CONTAINERS.md)
- [Orchestrate setup](ORCHESTRATE_SETUP.md)
- [Policy pipeline](POLICY_PIPELINE.md)
- [Email connections](EMAIL_CONNECTIONS.md)
- [Reminders and calendars](REMINDERS_AND_CALENDARS.md)

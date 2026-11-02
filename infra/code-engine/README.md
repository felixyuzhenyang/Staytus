# IBM Cloud deployment handoff

These files support deployment; provisioning in the course account is still unverified.

1. Run backend tests and the OpenAPI contract check.
2. Build the backend image with `docker build -t staytus-backend ./backend`.
3. Push the image to a registry you are authorized to use.
4. Create a Code Engine application pointing to that image, port 8000.
5. Bind a PostgreSQL URL with `sslmode=verify-full` and the provider CA where supported. Enable pgvector using an authorized database migration.
6. Configure secrets as environment references, not Docker build arguments. Copy the complete backend environment schema, not frontend public variables.
7. For a public course demonstration use synthetic data and an explicitly isolated demo deployment. Production identity integration remains a separate required step before real users.
8. Export/import the Orchestrate tools, set the backend HTTPS server URL and configure service credentials. Validate user-context forwarding before enabling personalized tools.
9. Deploy the frontend separately; set server-only BACKEND_URL to the backend URL.
10. Test from a clean browser, including cross-user isolation and approval expiry.

Do not create resources, API keys or billable services automatically. No deployment has been performed by this scaffold.

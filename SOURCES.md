# Source registry and provenance

The initial corpus is authored demonstration material, not copied official policy. Fixtures have `fixture=true`, `verified_at=null`, and visible demo labels. Official reference links are directory references for human verification.

| Source | Reference | Current use |
| --- | --- | --- |
| Penn ISSS | https://global.upenn.edu/isss/ | School/adviser directory reference |
| iPenn | https://ipenn.upenn.edu/ | Human handoff link; no automated login or submission |
| USCIS | https://www.uscis.gov/working-in-the-united-states/students-and-exchange-visitors | Federal reference |
| DHS Study in the States | https://studyinthestates.dhs.gov/ | Federal reference |
| Department of State | https://j1visa.state.gov/ | J-1 reference in configuration |

Before enabling source capture: verify the exact path/owner, permitted use and robots/terms, choose a fetch strategy, set an appropriate freshness threshold and retry schedule, and document the reviewer. Source hosts are stored in the backend registry. They cannot be supplied by the LLM. Automatic fetching defaults off.

Captured text stays `detected_pending_review`. Extraction/classification does not activate a rule. Do not use a URL hash alone as evidence that a legal requirement changed. Review authority, effective date, court orders and applicability separately. Keep snapshot history and retrieval provenance. Institutional student-record integration needs institution-approved access and privacy review.

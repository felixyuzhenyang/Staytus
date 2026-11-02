"""Explicit model discovery/probing helpers, separate from ordinary app requests."""
from app.integrations.watsonx import ProviderError, WatsonxClient, WatsonxConfig


def configuration_report(settings):
    return {"url_configured": bool(settings.watsonx_url),
        "credential_configured": bool(settings.watsonx_api_key),
        "project_configured": bool(settings.watsonx_project_id),
        "embedding_model": settings.watsonx_embedding_model or None,
        "generation_model": settings.watsonx_generation_model or None,
        "network_called": False, "live_embedding_verified": False, "live_generation_verified": False,
        "multilingual_probe_passed": False, "quality_probe_passed": False, "quality_probe_status": "not_run",
        "notice": "Students use project-managed models; credentials stay on the server. Model catalog presence is not an inference-permission check."}


def config_from_settings(settings):
    return WatsonxConfig(settings.watsonx_url, settings.watsonx_api_key, settings.watsonx_project_id,
        settings.watsonx_embedding_model, settings.watsonx_generation_model, settings.watsonx_api_version)


def discover_selection(client: WatsonxClient):
    result = {}
    for task, configured in (("embedding", client.config.embedding_model), ("text_generation", client.config.generation_model)):
        rows = client.discover_models(task)
        selected = next((row for row in rows if row["model_id"] == configured), None)
        # Returned multilingual metadata determines the embedding recommendation.
        # Generation stays a separate selection; discovery never changes .env.
        recommendation = selected or (rows[0] if rows else None)
        def brief(row):
            return {key: row[key] for key in ("model_id", "label", "task", "languages", "multilingual", "lifecycle")} if row else None
        result[task] = {"catalog_count": len(rows), "configured_model": configured or None,
            "configured_model_listed": selected is not None,
            "suggested_model": brief(recommendation),
            "candidates": [brief(row) for row in rows[:12]], "inference_verified": False,
            "notice": "Bounded regional catalog, up to 200 entries; confirm project permission with an explicit inference probe."}
    return result


def probe_selected_models(client: WatsonxClient, *, embedding=True, generation=True):
    """Use fixed public synthetic text only. Called exclusively by explicit CLI flag.

    No student profile, mail, session capability or captured personal record enters
    these requests. Model IDs must already be selected in server configuration.
    """
    result = {"live_embedding_verified": False, "live_generation_verified": False,
        "multilingual_probe_passed": False, "quality_probe_passed": False, "quality_probe_status": "not_run"}
    if embedding and client.config.embedding_model:
        try:
            from app.retrieval import cosine
            vectors = client.embeddings([
                "International students should check their travel documents before departure.",
                "出境前，国际学生应检查自己的旅行文件。",
                "A coffee grinder prepares beans for an espresso machine.",
            ])
            related, unrelated = cosine(vectors[0], vectors[1]), cosine(vectors[0], vectors[2])
            # A strict tiny margin rejects ties/rounding noise. It is a sanity
            # gate on this fixed pair, not a calibrated production threshold.
            multilingual_passed = related - unrelated > 0.000001
            result.update(live_embedding_verified=True, embedding_dimension=len(vectors[0]),
                multilingual_probe_passed=multilingual_passed,
                multilingual_probe={"related_similarity": round(related, 5), "unrelated_similarity": round(unrelated, 5),
                    "related_ranked_above_unrelated": related > unrelated,
                    "ranking_margin": round(related - unrelated, 8), "minimum_margin": 0.000001,
                    "notice": "One small cross-language relevance check, not a general retrieval-quality benchmark."})
        except ProviderError:
            result["embedding_error"] = "Embedding probe failed; check the selected model and project permission"
    elif embedding:
        result["embedding_error"] = "Select an embedding model from the regional catalog first"
    if generation and client.config.generation_model:
        try:
            suggestion = client.classify_candidate("The public office opens on Monday.", "The public office opens on Wednesday.")
            result.update(live_generation_verified=True, generation_response_valid=True,
                review_required=suggestion["review_required"])
        except ProviderError:
            result["generation_error"] = "Generation probe failed; check the selected model and project permission"
    elif generation:
        result["generation_error"] = "Select a generation model from the regional catalog first"
    if embedding:
        result["quality_probe_passed"] = bool(result["multilingual_probe_passed"]
            and (not generation or result["live_generation_verified"]))
        result["quality_probe_status"] = ("passed" if result["quality_probe_passed"] else
            ("failed" if result["live_embedding_verified"] else "unavailable"))
        result["quality_probe_scope"] = "One cross-language relevance ordering plus generation JSON format when requested; not a general model benchmark"
        if result["live_embedding_verified"] and not result["multilingual_probe_passed"]:
            result["quality_error"] = "Embedding requests succeeded, but the related English/Chinese pair did not rank above the unrelated sentence with the sanity margin"
    return result

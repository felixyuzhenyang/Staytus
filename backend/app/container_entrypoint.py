"""One image, explicit API/gateway/migration roles; never migrate on web startup."""
import os
import sys


def main():
    role = sys.argv[1] if len(sys.argv) > 1 else "api"
    if role in {"migrate", "check"}:
        from app.database_cli import main as database_main
        return database_main(["upgrade" if role == "migrate" else "check"])
    if role not in {"api", "gateway"}:
        raise SystemExit("Choose api, gateway, migrate or check")
    import uvicorn
    port = int(os.environ.get("PORT", "8001" if role == "gateway" else "8000"))
    if not 1 <= port <= 65535:
        raise SystemExit("PORT must be between 1 and 65535")
    uvicorn.run("app.tool_gateway:app" if role == "gateway" else "app.main:app",
                host="0.0.0.0", port=port, access_log=False, proxy_headers=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

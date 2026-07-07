import os


def is_cloud_run() -> bool:
    return bool(os.getenv("K_SERVICE"))


def is_local_dev() -> bool:
    return not is_cloud_run()


def get_cors_origins() -> list[str]:
    configured = os.getenv("CORS_ALLOWED_ORIGINS", "")
    if configured.strip():
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

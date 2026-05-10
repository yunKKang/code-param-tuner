"""FastAPI backend for Code Param Tuner."""

import logging
import os
import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    from .ai_analyzer import analyze_params
    from .parser import parse_code
except ImportError:
    from ai_analyzer import analyze_params
    from parser import parse_code

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("code-param-tuner")

app = FastAPI(title="Code Param Tuner")

APP_HOST = os.getenv("CPT_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("CPT_PORT", "8000"))
DEFAULT_ALLOWED_ORIGINS = f"http://localhost:{APP_PORT},http://127.0.0.1:{APP_PORT}"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CPT_ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["POST", "GET", "HEAD"],
    allow_headers=["Content-Type"],
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
CONFIG_DIR = Path(os.getenv("CPT_CONFIG_DIR", Path.home() / ".code-param-tuner"))
CONFIG_FILE = CONFIG_DIR / "settings.json"

# C4: Max code size 500KB
MAX_CODE_SIZE = 500_000


class AnalyzeRequest(BaseModel):
    code: str
    filename: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_format: str | None = None


class AnalyzeResponse(BaseModel):
    params: list[dict]
    code: str
    sections: list[dict] = Field(default_factory=list)
    fallback: bool = False
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)


class SettingsRequest(BaseModel):
    api_key: str | None = None
    clear_api_key: bool = False
    base_url: str | None = None
    model: str | None = None
    api_format: str | None = None


class SettingsResponse(BaseModel):
    has_api_key: bool = False
    base_url: str = ""
    model: str = ""
    api_format: str = "auto"


def _request_origin_allowed(request: Request) -> bool:
    origin = request.headers.get("origin", "")
    referer = request.headers.get("referer", "")
    if origin and origin not in ALLOWED_ORIGINS:
        return False
    if not origin and referer:
        from urllib.parse import urlparse as _urlparse
        ref_origin = f"{_urlparse(referer).scheme}://{_urlparse(referer).netloc}"
        return ref_origin in ALLOWED_ORIGINS
    return True


def _read_saved_settings() -> dict:
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        "api_key": str(data.get("api_key") or ""),
        "base_url": str(data.get("base_url") or ""),
        "model": str(data.get("model") or ""),
        "api_format": str(data.get("api_format") or "auto"),
    }


def _write_saved_settings(settings: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(CONFIG_DIR, 0o700)
    except OSError:
        pass

    safe_settings = {
        "api_key": str(settings.get("api_key") or ""),
        "base_url": str(settings.get("base_url") or ""),
        "model": str(settings.get("model") or ""),
        "api_format": str(settings.get("api_format") or "auto"),
    }
    tmp_file = CONFIG_FILE.with_suffix(".tmp")
    with tmp_file.open("w", encoding="utf-8") as f:
        json.dump(safe_settings, f, ensure_ascii=False, indent=2)
    os.replace(tmp_file, CONFIG_FILE)
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except OSError:
        pass


def _settings_response(settings: dict) -> SettingsResponse:
    return SettingsResponse(
        has_api_key=bool(settings.get("api_key")),
        base_url=str(settings.get("base_url") or ""),
        model=str(settings.get("model") or ""),
        api_format=str(settings.get("api_format") or "auto"),
    )


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net 'unsafe-eval'; "
        "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self' https://cdn.jsdelivr.net data:; "
        "connect-src 'self'; "
        "worker-src 'self' blob:; "
        "base-uri 'self'; "
        "form-action 'self'",
    )
    return response


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest, request: Request):
    """Analyze Python code and extract tunable parameters."""
    if not _request_origin_allowed(request):
        return JSONResponse(status_code=403, content={"error": "不允许的请求来源"})

    # C4: Input size limit (byte-based for accuracy with multi-byte chars)
    if len(req.code.encode("utf-8")) > MAX_CODE_SIZE:
        return JSONResponse(
            status_code=413,
            content={"error": f"代码长度超过限制（最大 {MAX_CODE_SIZE // 1000}KB）"},
        )

    logger.info("Analyzing code (%d chars, %d bytes)", len(req.code), len(req.code.encode("utf-8")))

    # Step 1: AST parsing
    ast_result = parse_code(req.code)

    if ast_result["errors"]:
        logger.warning("AST parse errors: %s", ast_result["errors"])
        return AnalyzeResponse(
            params=[],
            code=req.code,
            fallback=True,
            error="; ".join(ast_result["errors"]),
        )

    saved_settings = _read_saved_settings()
    api_key = req.api_key or saved_settings.get("api_key") or None
    base_url = req.base_url if req.base_url is not None else saved_settings.get("base_url") or None
    model = req.model if req.model is not None else saved_settings.get("model") or None
    api_format = req.api_format if req.api_format is not None else saved_settings.get("api_format") or None

    # Step 2: AI semantic analysis (with fallback, now async)
    ai_result = await analyze_params(
        code=req.code,
        params=ast_result["params"],
        api_key=api_key,
        base_url=base_url,
        model=model,
        api_format=api_format,
    )

    final_params = ai_result["params"]

    logger.info("Analysis complete: %d params (fallback=%s)", len(final_params), ai_result.get("fallback"))

    return AnalyzeResponse(
        params=final_params,
        code=req.code,
        sections=ai_result.get("sections", []),
        fallback=ai_result.get("fallback", False),
        error=ai_result.get("error"),
        warnings=ai_result.get("warnings", []) + (
            ["未在代码中发现可识别的参数；仍可查看代码分段解释。"] if not ast_result["params"] else []
        ),
    )


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "code-param-tuner"}


@app.get("/api/settings", response_model=SettingsResponse)
async def get_settings(request: Request):
    if not _request_origin_allowed(request):
        return JSONResponse(status_code=403, content={"error": "不允许的请求来源"})
    return _settings_response(_read_saved_settings())


@app.post("/api/settings", response_model=SettingsResponse)
async def save_settings(req: SettingsRequest, request: Request):
    if not _request_origin_allowed(request):
        return JSONResponse(status_code=403, content={"error": "不允许的请求来源"})

    settings = _read_saved_settings()
    if req.clear_api_key:
        settings["api_key"] = ""
    elif req.api_key is not None and req.api_key.strip():
        settings["api_key"] = req.api_key.strip()

    if req.base_url is not None:
        settings["base_url"] = req.base_url.strip()
    if req.model is not None:
        settings["model"] = req.model.strip()
    if req.api_format is not None:
        settings["api_format"] = req.api_format.strip() or "auto"

    _write_saved_settings(settings)
    return _settings_response(settings)


# Serve frontend
@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
async def serve_index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.api_route("/favicon.ico", methods=["GET", "HEAD"], include_in_schema=False)
async def serve_favicon():
    return FileResponse(FRONTEND_DIR / "favicon.svg", media_type="image/svg+xml")


app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=APP_HOST, port=APP_PORT)

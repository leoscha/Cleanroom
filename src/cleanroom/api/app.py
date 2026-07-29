from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse, Response

from cleanroom.api.review import build_review_router
from cleanroom.api.routes import build_router
from cleanroom.files.workspace_lock import WorkspaceBusyError
from cleanroom.runtime import Runtime, build_runtime


def create_app(runtime: Runtime | None = None) -> FastAPI:
    current = runtime or build_runtime()
    api = FastAPI(title="Cleanroom", docs_url=None, redoc_url=None)

    @api.exception_handler(WorkspaceBusyError)
    async def workspace_busy(_: Request, error: WorkspaceBusyError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"error_code": "WORKSPACE_BUSY",
                            "message": str(error)})

    @api.exception_handler(ValueError)
    async def safe_value_error(_: Request, error: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error_code": type(error).__name__,
                            "message": "The request could not be processed safely"})

    @api.middleware("http")
    async def request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path.startswith("/review") and request.url.hostname not in {
            "127.0.0.1", "localhost", "::1",
        }:
            return JSONResponse(status_code=403, content={"error_code": "LOOPBACK_REQUIRED"})
        identifier = request.headers.get("X-Request-ID", str(uuid4()))[:128]
        response = await call_next(request)
        response.headers["X-Request-ID"] = identifier
        if request.url.path.startswith("/review"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; "
                "frame-ancestors 'none'; form-action 'none'"
            )
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    api.include_router(build_router(current))
    api.include_router(build_review_router(current))
    return api


app = create_app()

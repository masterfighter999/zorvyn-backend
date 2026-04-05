import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import users, records, dashboard, auth, admin
from app.core.config import get_settings
from app.middleware.logging import AccessLogMiddleware
from app.redis.client import close_redis
from app.redis.idempotency import IdempotencyMiddleware
from app.workers.outbox_publisher import run_outbox_worker
from app.kafka.dlq_consumer import run_dlq_consumer

_worker_task: asyncio.Task | None = None
_dlq_task: asyncio.Task | None = None
_stop_event: asyncio.Event | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    global _worker_task, _dlq_task, _stop_event

    # Start background workers
    _stop_event = asyncio.Event()
    _worker_task = asyncio.create_task(run_outbox_worker(_stop_event))
    _dlq_task = asyncio.create_task(run_dlq_consumer())

    # Seed default admin user
    from app.core.database import get_db
    from app.models.user import User, UserRole, UserStatus
    from sqlalchemy import select

    async for db in get_db():
        result = await db.execute(select(User).where(User.email == "admin@zorvyn.com"))
        if not result.scalar_one_or_none():
            admin_user = User(
                name="Default Admin",
                email="admin@zorvyn.com",
                role=UserRole.admin,
                status=UserStatus.active
            )
            db.add(admin_user)
            await db.commit()
        break

    yield  # ← app is running

    # Graceful shutdown
    if _stop_event:
        _stop_event.set()
    if _worker_task:
        await asyncio.wait_for(_worker_task, timeout=15)
    if _dlq_task:
        _dlq_task.cancel()
        try:
            await _dlq_task
        except asyncio.CancelledError:
            pass
    await close_redis()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Zorvyn Finance API",
        version="0.1.0",
        description="Finance data processing & access-control backend",
        lifespan=lifespan,
    )

    # ── CORS ──
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Idempotency middleware ──
    app.add_middleware(IdempotencyMiddleware)

    # ── Access logging middleware ──
    app.add_middleware(AccessLogMiddleware)

    # ── Routers ──
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(records.router)
    app.include_router(dashboard.router)
    app.include_router(admin.router)

    @app.get("/health", tags=["Health"])
    async def health():
        return {"status": "ok"}

    return app


app = create_app()

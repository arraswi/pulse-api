from __future__ import annotations

import os
import sqlite3
import time
from collections.abc import Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import FastAPI, HTTPException, Path as PathParam, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, HttpUrl, field_validator

DATABASE_PATH = Path(os.getenv("PULSE_DB_PATH", "data/pulse.db"))


class MonitorCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    url: HttpUrl

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("O nome precisa ter pelo menos 2 caracteres.")
        return cleaned


class Monitor(BaseModel):
    id: int
    name: str
    url: str
    status: str
    last_status_code: int | None = None
    response_time_ms: float | None = None
    checked_at: str | None = None


@contextmanager
def connect_db() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DATABASE_PATH, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect_db() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS monitors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'unknown',
                last_status_code INTEGER,
                response_time_ms REAL,
                checked_at TEXT,
                created_at TEXT NOT NULL
            )
            """
        )


def row_to_monitor(row: sqlite3.Row) -> Monitor:
    return Monitor(
        id=row["id"],
        name=row["name"],
        url=row["url"],
        status=row["status"],
        last_status_code=row["last_status_code"],
        response_time_ms=row["response_time_ms"],
        checked_at=row["checked_at"],
    )


def get_monitor_or_404(monitor_id: int) -> Monitor:
    with connect_db() as connection:
        row = connection.execute(
            "SELECT * FROM monitors WHERE id = ?", (monitor_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Monitor não encontrado.")
    return row_to_monitor(row)


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(5.0), follow_redirects=True
    ) as client:
        app.state.http = client
        yield


app = FastAPI(
    title="Pulse API",
    description="API local para cadastrar serviços e acompanhar verificações HTTP.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/monitors", response_model=list[Monitor], tags=["monitors"])
def list_monitors() -> list[Monitor]:
    with connect_db() as connection:
        rows = connection.execute(
            "SELECT * FROM monitors ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [row_to_monitor(row) for row in rows]


@app.post(
    "/api/v1/monitors",
    response_model=Monitor,
    status_code=status.HTTP_201_CREATED,
    tags=["monitors"],
)
def create_monitor(payload: MonitorCreate) -> Monitor:
    created_at = datetime.now(UTC).isoformat()
    try:
        with connect_db() as connection:
            cursor = connection.execute(
                """
                INSERT INTO monitors (name, url, status, created_at)
                VALUES (?, ?, 'unknown', ?)
                """,
                (payload.name.strip(), str(payload.url), created_at),
            )
            monitor_id = cursor.lastrowid
    except sqlite3.IntegrityError as error:
        raise HTTPException(
            status_code=409, detail="Este endereço já está cadastrado."
        ) from error
    return get_monitor_or_404(int(monitor_id))


@app.get(
    "/api/v1/monitors/{monitor_id}",
    response_model=Monitor,
    tags=["monitors"],
)
def get_monitor(
    monitor_id: Annotated[int, PathParam(ge=1)],
) -> Monitor:
    return get_monitor_or_404(monitor_id)


@app.delete(
    "/api/v1/monitors/{monitor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["monitors"],
)
def delete_monitor(
    monitor_id: Annotated[int, PathParam(ge=1)],
) -> None:
    with connect_db() as connection:
        cursor = connection.execute(
            "DELETE FROM monitors WHERE id = ?", (monitor_id,)
        )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Monitor não encontrado.")


@app.post(
    "/api/v1/monitors/{monitor_id}/check",
    response_model=Monitor,
    tags=["monitors"],
)
async def check_monitor(
    monitor_id: Annotated[int, PathParam(ge=1)],
) -> Monitor:
    monitor = get_monitor_or_404(monitor_id)
    started_at = time.perf_counter()
    status_code: int | None = None
    new_status = "down"

    try:
        response = await app.state.http.get(monitor.url)
        status_code = response.status_code
        new_status = "up" if response.is_success else "down"
    except httpx.HTTPError:
        new_status = "down"

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    checked_at = datetime.now(UTC).isoformat()
    with connect_db() as connection:
        connection.execute(
            """
            UPDATE monitors
            SET status = ?, last_status_code = ?, response_time_ms = ?, checked_at = ?
            WHERE id = ?
            """,
            (new_status, status_code, elapsed_ms, checked_at, monitor_id),
        )
    return get_monitor_or_404(monitor_id)

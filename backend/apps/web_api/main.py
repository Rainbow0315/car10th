from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.web_api.routers import auth
from common.config import settings

app = FastAPI(
    title="园区智能巡检机器人 API",
    description="REST 业务网关：鉴权 / 告警 / 任务 / LLM",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "web_api"}


app.include_router(auth.router, prefix="/api/auth", tags=["鉴权"])

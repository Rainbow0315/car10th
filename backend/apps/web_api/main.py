import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.web_api.routers import auth, car_finding, fleet, inspection, llm, patrol, robot, slam, teleop
from apps.web_api.services.inspection_monitor_service import inspection_monitor_service
from apps.web_api.services.mqtt_service import mqtt_service
from apps.web_api.services.patrol_service import patrol_service
from common.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    mqtt_started = False
    try:
        mqtt_service.start()
        await mqtt_service.start_heartbeat()
        mqtt_started = True
    except Exception:
        logger.exception("MQTT service failed during startup; continuing with HTTP APIs")
    try:
        patrol_service.start_scheduler()
    except Exception:
        logger.exception("Patrol scheduler failed during startup; continuing with HTTP APIs")
    yield
    patrol_service.shutdown_scheduler()
    await inspection_monitor_service.shutdown()
    if mqtt_started:
        await mqtt_service.stop()


app = FastAPI(
    title="园区智能巡检机器人 API",
    description="REST 业务网关：鉴权 / 告警 / 任务 / LLM / 遥控 / MQTT / AI 检测",
    version="0.1.0",
    lifespan=lifespan,
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
    mqtt_health = mqtt_service.health()
    return {
        "status": "ok",
        "service": "web_api",
        "mqtt_connected": mqtt_health.connected,
    }


app.include_router(auth.router, prefix="/api/auth", tags=["鉴权"])
app.include_router(teleop.router, prefix="/api/teleop", tags=["遥控"])
app.include_router(robot.router, prefix="/api", tags=["小车与MQTT"])
app.include_router(inspection.router, prefix="/api/inspection", tags=["道路检测"])
app.include_router(fleet.router, prefix="/api/fleet", tags=["车队"])
app.include_router(llm.router, prefix="/api/llm", tags=["LLM任务助手"])
app.include_router(slam.router, prefix="/api/slam", tags=["建图导航"])
app.include_router(patrol.router, prefix="/api/patrol", tags=["巡航任务"])
app.include_router(car_finding.router, prefix="/api/car-finding", tags=["Car Finding"])

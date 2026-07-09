from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "parking_inspection_robot"

    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    mqtt_broker_host: str = "127.0.0.1"
    mqtt_broker_port: int = 1883
    mqtt_username: str = "parking_backend"
    mqtt_password: str = "parking_backend_dev"
    mqtt_client_id: str = "parking_backend"
    mqtt_keepalive: int = 60
    mqtt_status_interval_sec: int = 2
    mqtt_app_username: str = "parking_app"
    mqtt_app_password: str = "parking_app_dev"

    rosbridge_ws_url: str = "ws://127.0.0.1:9090"
    ros_bridge_http_url: str = "http://127.0.0.1:8001"

    llm_api_base: str = ""
    llm_api_key: str = ""
    llm_model: str = "qwen-plus"

    capture_img_dir: str = "./capture_img"
    cors_origins: list[str] = ["*"]

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset=utf8mb4"
        )


settings = Settings()

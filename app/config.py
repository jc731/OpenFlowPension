from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://openflow:changeme@postgres:5432/openflow_pension"
    redis_url: str = "redis://redis:6379/0"
    encryption_key: str = ""
    environment: str = "development"

    # Keycloak JWT — leave blank to use the dev bypass
    keycloak_url: str = ""        # e.g. http://keycloak:8080
    keycloak_realm: str = "openflow"
    keycloak_audience: str = "openflow-admin"  # must match the Keycloak client ID

    @property
    def database_sync_url(self) -> str:
        return self.database_url.replace("+asyncpg", "")


settings = Settings()

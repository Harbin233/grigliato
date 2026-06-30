from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str

    DB_HOST: str
    DB_PORT: int
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str

    MODE: str = "production"
    TIMEZONE: str = "Europe/Moscow"
    LOG_LEVEL: str = "INFO"

    ADMIN_IDS: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @property
    def admin_ids(self) -> set[int]:
        if not self.ADMIN_IDS.strip():
            return set()

        return {
            int(x.strip())
            for x in self.ADMIN_IDS.split(",")
            if x.strip()
        }


settings = Settings()

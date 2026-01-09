from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    This class handles all our
    """
    FINGRID_API_KEY: str | None = None
    FINGRID_PRIMARY_API_KEY: str | None = None
    FINGRID_SECONDARY_API_KEY: str | None = None
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


Config = Settings()  # type: ignore

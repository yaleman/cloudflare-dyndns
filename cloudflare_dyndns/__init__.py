from typing import Dict
from pydantic import Field, BaseModel


class ConfigFile(BaseModel):
    """config file"""

    token: str
    zone: str
    hostname: str
    dry_run: bool = Field(False)

    def auth_headers(self) -> Dict[str, str]:
        """return an auth header"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

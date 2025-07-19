"""Cloudflare Dynamic DNS magic"""

from typing import Dict
from pydantic import Field, BaseModel


class ConfigFile(BaseModel):
    """config file"""

    token: str = Field(..., description="Cloudflare API token")
    zone: str = Field(..., description="DNS zone")
    hostname: str = Field(..., description="DNS hostname")
    dry_run: bool = Field(False, description="If true, do not make any changes")

    def auth_headers(self) -> Dict[str, str]:
        """return an auth header"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

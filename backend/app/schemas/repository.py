from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
import uuid


class RepositoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    github_id: int
    full_name: str
    owner: str
    name: str
    default_branch: str
    language: Optional[str] = None
    private: bool
    enabled: bool
    created_at: datetime

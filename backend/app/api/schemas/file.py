from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class IndexDirectoryRequest(BaseModel):
    directory_path: str
    user_id: Optional[str] = None
    private: bool = False
    recursive: bool = True

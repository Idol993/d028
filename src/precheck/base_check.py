from abc import ABC, abstractmethod
from typing import Any, Dict, List

from src.common.config_loader import ConfigLoader
from src.common.audit_logger import AuditLogger
from src.common.models import SingleCheckResult


class BasePreCheck(ABC):
    def __init__(self):
        self.config = ConfigLoader()
        self.logger = AuditLogger()
        self.category = None
        self.check_name = ""

    @abstractmethod
    def execute(self, release_id: str, context: Dict[str, Any]) -> List[SingleCheckResult]:
        pass

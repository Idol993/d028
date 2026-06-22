import logging
import json
import os
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from typing import Any, Dict, Optional


class AuditLogger:
    _instance = None
    _audit_logger: logging.Logger = None
    _app_logger: logging.Logger = None

    def __new__(cls, log_dir: str = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_loggers(log_dir)
        return cls._instance

    def _init_loggers(self, log_dir: str = None):
        if log_dir is None:
            base_dir = Path(__file__).parent.parent.parent
            log_dir = base_dir / "logs"
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        audit_dir = log_dir / "audit"
        audit_dir.mkdir(exist_ok=True)

        self._app_logger = self._create_logger(
            "pharmacy_release_app",
            log_dir / "app.log",
            level=logging.INFO
        )

        self._audit_logger = self._create_logger(
            "pharmacy_release_audit",
            audit_dir / "audit.log",
            level=logging.INFO,
            json_format=True
        )

    def _create_logger(self, name: str, log_file: Path, level: int = logging.INFO,
                       json_format: bool = False) -> logging.Logger:
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.propagate = False

        if logger.handlers:
            return logger

        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        file_handler = TimedRotatingFileHandler(
            log_file, when="midnight", interval=1, backupCount=30, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        return logger

    def info(self, message: str, **kwargs):
        self._app_logger.info(message)

    def warning(self, message: str, **kwargs):
        self._app_logger.warning(message)

    def error(self, message: str, exc_info: bool = False, **kwargs):
        self._app_logger.error(message, exc_info=exc_info)

    def audit(self, operation: str, operator: str, resource: str,
              result: str, details: Optional[Dict[str, Any]] = None):
        audit_record = {
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "operator": operator,
            "resource": resource,
            "result": result,
            "details": details or {}
        }
        self._audit_logger.info(json.dumps(audit_record, ensure_ascii=False))

    @property
    def app_logger(self) -> logging.Logger:
        return self._app_logger

    @property
    def audit_logger(self) -> logging.Logger:
        return self._audit_logger

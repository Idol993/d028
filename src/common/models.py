from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CheckStatus(str, Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


class CheckCategory(str, Enum):
    AI_VISION = "ai_vision_test"
    HIS_INTERFACE = "his_interface_check"
    BARCODE_VALIDATION = "barcode_validation"
    DEVICE_HEALTH = "device_health_check"


class SingleCheckResult(BaseModel):
    check_id: str
    check_name: str
    category: CheckCategory
    status: CheckStatus
    actual_value: Optional[Any] = None
    threshold_value: Optional[Any] = None
    message: str = ""
    repair_suggestion: str = ""
    duration_ms: int = 0
    checked_at: datetime = Field(default_factory=datetime.now)


class PreCheckReport(BaseModel):
    release_id: str
    version: str
    overall_status: CheckStatus = CheckStatus.PENDING
    blocking: bool = True
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    warning_checks: int = 0
    skipped_checks: int = 0
    results: List[SingleCheckResult] = []
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    repair_summary: List[str] = []

    class Config:
        use_enum_values = True


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ApprovalChannel(str, Enum):
    REGULAR = "regular"
    HOTFIX = "hotfix"


class ApprovalNode(BaseModel):
    node_id: str
    node_name: str
    department: str
    approvers: List[str]
    status: ApprovalStatus = ApprovalStatus.PENDING
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    comments: str = ""
    timeout_hours: int = 48


class ApprovalFlow(BaseModel):
    release_id: str
    channel: ApprovalChannel
    version: str
    nodes: List[ApprovalNode] = []
    current_node_index: int = 0
    overall_status: ApprovalStatus = ApprovalStatus.PENDING
    hotfix_reason: str = ""
    deviation_report: str = ""
    allow_parallel: bool = False
    allow_post_sign: bool = False
    created_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None


class CanaryPhase(str, Enum):
    NOT_STARTED = "not_started"
    TIER1 = "tier1"
    TIER2 = "tier2"
    TIER3 = "tier3"
    COMPLETED = "completed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"


class MonitoringIndicator(BaseModel):
    name: str
    description: str
    current_value: float
    threshold: float
    status: CheckStatus
    unit: str = ""


class CanaryReleaseRecord(BaseModel):
    release_id: str
    version: str
    phase: CanaryPhase = CanaryPhase.NOT_STARTED
    target_pharmacies: List[str] = []
    current_pharmacies: List[str] = []
    indicators: List[MonitoringIndicator] = []
    phase_started_at: Optional[datetime] = None
    phase_observe_minutes: int = 30
    circuit_break_triggered: bool = False
    circuit_break_reason: str = ""
    rollback_triggered: bool = False
    rollback_completed_at: Optional[datetime] = None
    safety_impact_report: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=datetime.now)


class DrillRecord(BaseModel):
    drill_id: str
    drill_name: str
    trigger_type: str
    status: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: int = 0
    affected_pharmacies: List[str] = []
    rollback_success: bool = False
    details: Dict[str, Any] = {}
    archived: bool = False


class WeeklyReportData(BaseModel):
    week_start: str
    week_end: str
    total_releases: int = 0
    successful_releases: int = 0
    rollback_count: int = 0
    avg_approval_hours: float = 0.0
    release_success_rate: float = 0.0
    by_pharmacy: Dict[str, Dict[str, int]] = {}
    by_channel: Dict[str, Dict[str, int]] = {}

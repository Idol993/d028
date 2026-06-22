import uuid
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.common.config_loader import ConfigLoader
from src.common.audit_logger import AuditLogger
from src.common.models import (
    PreCheckReport,
    ApprovalFlow,
    CanaryReleaseRecord,
    ApprovalStatus,
    CheckStatus
)
from src.common.data_store import DataStore
from src.common.notification_manager import NotificationManager

from src.precheck.orchestrator import PreCheckOrchestrator
from src.approval.engine import ApprovalEngine
from src.canary.orchestrator import CanaryReleaseOrchestrator
from src.audit.rollback_drill import RollbackDrillManager
from src.audit.report_generator import ReportGenerator


class ReleasePipeline:
    def __init__(self):
        self.config = ConfigLoader()
        self.logger = AuditLogger()
        self.datastore = DataStore()
        self.notification = NotificationManager()

        self.precheck = PreCheckOrchestrator()
        self.approval = ApprovalEngine()
        self.canary = CanaryReleaseOrchestrator()
        self.drill = RollbackDrillManager()
        self.report = ReportGenerator()

    def submit_release(self, version: str, channel: str = "regular",
                        hotfix_reason: str = "", operator: str = "system",
                        auto_advance: bool = True) -> Dict[str, Any]:
        release_id = f"REL-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"

        self.logger.info(f"Submitting new release: {version} (ID: {release_id}, channel: {channel})")

        self.logger.audit(
            "release_submitted",
            operator,
            f"release:{release_id}",
            "submitted",
            {"version": version, "channel": channel, "hotfix_reason": hotfix_reason}
        )

        precheck_report = self.precheck.run_precheck(version, release_id, {"operator": operator})

        if precheck_report.blocking:
            self.logger.warning(
                f"Precheck blocked release {release_id}: "
                f"{precheck_report.failed_checks} checks failed"
            )
            self._notify_precheck_blocked(release_id, version, precheck_report)

            return self._assemble_result(
                release_id=release_id,
                version=version,
                precheck=precheck_report,
                approval=None,
                canary=None,
                pipeline_status="blocked_by_precheck",
                message=f"发布被前置校验阻断: {precheck_report.failed_checks} 项检查未通过"
            )

        self.logger.info(f"Precheck passed for {release_id}, proceeding to approval")

        approval_flow = self.approval.create_approval_flow(
            release_id=release_id,
            version=version,
            channel=channel,
            hotfix_reason=hotfix_reason,
            operator=operator
        )

        if auto_advance and channel == "hotfix":
            pass

        return self._assemble_result(
            release_id=release_id,
            version=version,
            precheck=precheck_report,
            approval=approval_flow,
            canary=None,
            pipeline_status="awaiting_approval",
            message="前置校验通过，等待审批完成"
        )

    def approve_release(self, release_id: str, node_id: str, approver: str,
                         comments: str = "") -> Dict[str, Any]:
        existing = self._load_release_state(release_id)
        if not existing:
            return {"error": f"Release {release_id} not found"}

        approval_dict = existing.get("approval")
        if not approval_dict:
            return {"error": f"Approval flow not found for {release_id}"}

        approval_flow = ApprovalFlow(**approval_dict)

        try:
            approval_flow = self.approval.approve(
                release_id=release_id,
                node_id=node_id,
                approver=approver,
                comments=comments,
                flow=approval_flow
            )
        except PermissionError as e:
            self.logger.warning(f"Approval sequence violation: {e}")
            return {
                "release_id": release_id,
                "pipeline_status": "approval_sequence_violation",
                "error": str(e),
                "approval": self.approval.get_flow_summary(approval_flow)
            }

        existing["approval"] = json.loads(approval_flow.model_dump_json())
        self.datastore.save_release_record(release_id, existing)

        if approval_flow.overall_status == ApprovalStatus.APPROVED:
            self.logger.info(f"All approvals obtained for {release_id}, starting canary release")
            return self._start_canary(release_id, existing, approver)

        return self._assemble_result(
            release_id=release_id,
            version=existing.get("version", ""),
            precheck=existing.get("precheck"),
            approval=approval_flow,
            canary=existing.get("canary"),
            pipeline_status="approval_in_progress",
            message=f"审批节点已通过，当前进度 {self.approval.get_flow_summary(approval_flow)['progress']}"
        )

    def reject_release(self, release_id: str, node_id: str, approver: str,
                        reject_reason: str) -> Dict[str, Any]:
        existing = self._load_release_state(release_id)
        if not existing:
            return {"error": f"Release {release_id} not found"}

        approval_dict = existing.get("approval")
        if not approval_dict:
            return {"error": f"Approval flow not found for {release_id}"}

        approval_flow = ApprovalFlow(**approval_dict)

        try:
            approval_flow = self.approval.reject(
                release_id=release_id,
                node_id=node_id,
                approver=approver,
                reject_reason=reject_reason,
                flow=approval_flow
            )
        except PermissionError as e:
            self.logger.warning(f"Approval sequence violation (reject): {e}")
            return {
                "release_id": release_id,
                "pipeline_status": "approval_sequence_violation",
                "error": str(e),
                "approval": self.approval.get_flow_summary(approval_flow)
            }

        existing["approval"] = json.loads(approval_flow.model_dump_json())
        self.datastore.save_release_record(release_id, existing)

        return self._assemble_result(
            release_id=release_id,
            version=existing.get("version", ""),
            precheck=existing.get("precheck"),
            approval=approval_flow,
            canary=existing.get("canary"),
            pipeline_status="rejected",
            message=f"发布被驳回: {reject_reason}"
        )

    def _start_canary(self, release_id: str, state: Dict[str, Any],
                       operator: str) -> Dict[str, Any]:
        version = state.get("version", "")
        canary_record = self.canary.run_full_canary(release_id, version, operator)

        state["canary"] = json.loads(canary_record.model_dump_json())
        state["created_at"] = state.get("created_at", datetime.now().isoformat())
        self.datastore.save_release_record(release_id, state)

        if canary_record.rollback_triggered:
            final_status = "rolled_back"
            message = f"灰度发布触发熔断，已自动回滚。原因: {canary_record.circuit_break_reason}"
        else:
            final_status = "completed"
            message = "灰度发布全部完成，所有药房已成功升级"

        return self._assemble_result(
            release_id=release_id,
            version=version,
            precheck=state.get("precheck"),
            approval=state.get("approval"),
            canary=canary_record,
            pipeline_status=final_status,
            message=message
        )

    def manual_rollback(self, release_id: str, reason: str,
                         operator: str = "system") -> Dict[str, Any]:
        existing = self._load_release_state(release_id)
        if not existing:
            return {"error": f"Release {release_id} not found"}

        canary_dict = existing.get("canary")
        if not canary_dict:
            return {"error": f"No canary record for release {release_id}"}

        canary_record = CanaryReleaseRecord(**canary_dict)
        canary_record = self.canary.manual_rollback(canary_record, reason, operator)

        existing["canary"] = json.loads(canary_record.model_dump_json())
        self.datastore.save_release_record(release_id, existing)

        return self._assemble_result(
            release_id=release_id,
            version=existing.get("version", ""),
            precheck=existing.get("precheck"),
            approval=existing.get("approval"),
            canary=canary_record,
            pipeline_status="manually_rolled_back",
            message=f"人工回滚完成: {reason}"
        )

    def execute_rollback_drill(self, drill_name: Optional[str] = None,
                                operator: str = "system") -> Dict[str, Any]:
        record = self.drill.execute_drill(drill_name=drill_name, operator=operator)
        return {
            "drill_id": record.drill_id,
            "drill_name": record.drill_name,
            "status": record.status,
            "rollback_success": record.rollback_success,
            "duration_seconds": record.duration_seconds,
            "affected_pharmacies": record.affected_pharmacies,
            "details": record.details
        }

    def generate_weekly_report(self) -> Dict[str, Any]:
        return self.report.generate_weekly_report()

    def get_release_status(self, release_id: str) -> Optional[Dict[str, Any]]:
        state = self._load_release_state(release_id)
        if not state:
            return None

        precheck = state.get("precheck")
        approval = state.get("approval")
        canary = state.get("canary")

        precheck_summary = None
        if precheck:
            report = PreCheckReport(**precheck)
            precheck_summary = self.precheck.get_checker_status_summary(report)

        approval_summary = None
        if approval:
            flow = ApprovalFlow(**approval)
            approval_summary = self.approval.get_flow_summary(flow)

        canary_summary = None
        if canary:
            record = CanaryReleaseRecord(**canary)
            canary_summary = self.canary.get_phases_status(record)

        return {
            "release_id": release_id,
            "version": state.get("version", ""),
            "created_at": state.get("created_at", state.get("saved_at", "")),
            "pipeline_status": self._determine_pipeline_status(state),
            "precheck": precheck_summary,
            "approval": approval_summary,
            "canary": canary_summary
        }

    def list_releases(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        records = self.datastore.list_release_records(filters)
        summary_list = []
        for record in records:
            summary_list.append({
                "release_id": record.get("release_id"),
                "version": record.get("version"),
                "saved_at": record.get("saved_at"),
                "precheck_status": record.get("precheck", {}).get("overall_status", ""),
                "approval_status": record.get("approval", {}).get("overall_status", ""),
                "canary_phase": record.get("canary", {}).get("phase", ""),
                "rollback_triggered": record.get("canary", {}).get("rollback_triggered", False)
            })
        return summary_list

    def _load_release_state(self, release_id: str) -> Optional[Dict[str, Any]]:
        return self.datastore.get_release_record(release_id)

    def _determine_pipeline_status(self, state: Dict[str, Any]) -> str:
        canary = state.get("canary")
        if canary:
            phase = canary.get("phase")
            if phase == "rolled_back":
                return "rolled_back"
            if phase == "completed":
                return "completed"
            if phase in ["tier1", "tier2", "tier3"]:
                return f"canary_{phase}"

        approval = state.get("approval")
        if approval:
            status = approval.get("overall_status")
            if status == "rejected":
                return "rejected"
            if status == "approved":
                return "awaiting_canary"
            if status == "pending":
                return "awaiting_approval"

        precheck = state.get("precheck")
        if precheck:
            status = precheck.get("overall_status")
            if status in ["failed"]:
                return "blocked_by_precheck"
            if status in ["passed", "warning"]:
                return "awaiting_approval"

        return "unknown"

    def _assemble_result(self, release_id: str, version: str,
                          precheck: Any, approval: Any, canary: Any,
                          pipeline_status: str, message: str) -> Dict[str, Any]:
        state = {
            "release_id": release_id,
            "version": version,
            "created_at": datetime.now().isoformat()
        }

        if precheck:
            if isinstance(precheck, PreCheckReport):
                state["precheck"] = json.loads(precheck.model_dump_json())
            else:
                state["precheck"] = precheck

        if approval:
            if isinstance(approval, ApprovalFlow):
                state["approval"] = json.loads(approval.model_dump_json())
            else:
                state["approval"] = approval

        if canary:
            if isinstance(canary, CanaryReleaseRecord):
                state["canary"] = json.loads(canary.model_dump_json())
            else:
                state["canary"] = canary

        self.datastore.save_release_record(release_id, state)

        precheck_summary = None
        if isinstance(precheck, PreCheckReport):
            precheck_summary = self.precheck.get_checker_status_summary(precheck)
        elif isinstance(precheck, dict):
            precheck_summary = precheck

        approval_summary = None
        if isinstance(approval, ApprovalFlow):
            approval_summary = self.approval.get_flow_summary(approval)
        elif isinstance(approval, dict):
            approval_summary = approval

        canary_summary = None
        if isinstance(canary, CanaryReleaseRecord):
            canary_summary = self.canary.get_phases_status(canary)
        elif isinstance(canary, dict):
            canary_summary = canary

        return {
            "release_id": release_id,
            "version": version,
            "pipeline_status": pipeline_status,
            "message": message,
            "precheck": precheck_summary,
            "approval": approval_summary,
            "canary": canary_summary
        }

    def _notify_precheck_blocked(self, release_id: str, version: str,
                                  report: PreCheckReport):
        title = f"【发布阻断】前置校验未通过 - {version}"
        content = (
            f"**发布版本**: {version}\n"
            f"**发布ID**: {release_id}\n"
            f"**阻断原因**: 共 {report.failed_checks} 项校验未通过\n\n"
            f"### 未通过检查项与修复建议\n"
        )
        for i, suggestion in enumerate(report.repair_summary, 1):
            content += f"{i}. {suggestion}\n\n"

        content += (
            f"\n请开发团队根据修复建议处理后重新提交发布申请。"
        )
        self.notification.send_notification(title, content)

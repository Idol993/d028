import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.common.config_loader import ConfigLoader
from src.common.audit_logger import AuditLogger
from src.common.models import (
    ApprovalFlow,
    ApprovalNode,
    ApprovalStatus,
    ApprovalChannel
)
from src.common.notification_manager import NotificationManager


class ApprovalEngine:
    def __init__(self):
        self.config = ConfigLoader()
        self.logger = AuditLogger()
        self.notification = NotificationManager()

    def create_approval_flow(self, release_id: str, version: str,
                             channel: str = "regular",
                             hotfix_reason: str = "",
                             operator: str = "system",
                             context: Optional[Dict[str, Any]] = None) -> ApprovalFlow:
        channel_config = self.config.get(f"approval.channels.{channel}")
        if not channel_config:
            raise ValueError(f"Unknown approval channel: {channel}")

        flow = ApprovalFlow(
            release_id=release_id,
            channel=ApprovalChannel(channel),
            version=version,
            hotfix_reason=hotfix_reason,
            allow_parallel=channel_config.get("parallel", False),
            allow_post_sign=channel_config.get("allow_post_sign", False)
        )

        timeout_hours = self.config.get("approval.timeout_hours", 48)
        flow_config = channel_config.get("flow", [])
        approvers_config = self.config.get("approval.approvers", {})

        for idx, dept in enumerate(flow_config):
            dept_approvers = approvers_config.get(dept, [])
            dept_name_map = {
                "pharmacy": "药房(处方流转与发药时效评估)",
                "it_department": "信息科(HIS接口、数据安全与追溯码上传评估)",
                "equipment_department": "设备科(机械臂运动规划、硬件兼容性与维保评估)"
            }
            node = ApprovalNode(
                node_id=f"NODE-{release_id}-{idx}",
                node_name=dept_name_map.get(dept, dept),
                department=dept,
                approvers=dept_approvers,
                timeout_hours=timeout_hours
            )
            flow.nodes.append(node)

        self.logger.audit(
            "approval_flow_created",
            operator,
            f"release:{release_id}",
            "success",
            {
                "channel": channel,
                "version": version,
                "hotfix_reason": hotfix_reason,
                "nodes_count": len(flow.nodes)
            }
        )

        self._notify_current_approvals(flow, operator)

        return flow

    def approve(self, release_id: str, node_id: str, approver: str,
                comments: str = "", flow: Optional[ApprovalFlow] = None) -> ApprovalFlow:
        if flow is None:
            raise ValueError("Approval flow must be provided or loaded")

        node = self._find_node(flow, node_id)
        if node is None:
            raise ValueError(f"Node {node_id} not found in flow")

        if node.status == ApprovalStatus.APPROVED:
            self.logger.warning(f"Node {node_id} already approved")
            return flow

        if approver not in node.approvers:
            raise ValueError(f"Approver {approver} not authorized for node {node_id}")

        if not flow.allow_parallel:
            current_node = flow.nodes[flow.current_node_index] if flow.current_node_index < len(flow.nodes) else None
            if current_node is None or current_node.node_id != node_id:
                expected_node = f"{current_node.node_name} (ID: {current_node.node_id})" if current_node else "无(流程已结束)"
                raise PermissionError(
                    f"审批顺序违规: 当前待审批节点为 {expected_node}, "
                    f"不允许跳过顺序审批 {node.node_name} (ID: {node_id})。"
                    f"请先完成当前待审批节点后再操作。"
                )

        node.status = ApprovalStatus.APPROVED
        node.approved_by = approver
        node.approved_at = datetime.now()
        node.comments = comments

        self.logger.audit(
            "approval_node_approved",
            approver,
            f"release:{release_id}/node:{node_id}",
            "approved",
            {"comments": comments, "department": node.department}
        )

        if flow.allow_parallel:
            if all(n.status == ApprovalStatus.APPROVED for n in flow.nodes):
                flow.overall_status = ApprovalStatus.APPROVED
                flow.completed_at = datetime.now()
        else:
            flow.current_node_index += 1
            if flow.current_node_index >= len(flow.nodes):
                flow.overall_status = ApprovalStatus.APPROVED
                flow.completed_at = datetime.now()

        if flow.overall_status == ApprovalStatus.APPROVED:
            self.logger.audit(
                "approval_flow_completed",
                approver,
                f"release:{release_id}",
                "approved",
                {"version": flow.version}
            )
            self._notify_flow_complete(flow)
        else:
            self._notify_current_approvals(flow, approver)

        return flow

    def reject(self, release_id: str, node_id: str, approver: str,
               reject_reason: str, flow: Optional[ApprovalFlow] = None) -> ApprovalFlow:
        if flow is None:
            raise ValueError("Approval flow must be provided or loaded")

        node = self._find_node(flow, node_id)
        if node is None:
            raise ValueError(f"Node {node_id} not found in flow")

        if approver not in node.approvers:
            raise ValueError(f"Approver {approver} not authorized for node {node_id}")

        if not flow.allow_parallel:
            current_node = flow.nodes[flow.current_node_index] if flow.current_node_index < len(flow.nodes) else None
            if current_node is None or current_node.node_id != node_id:
                expected_node = f"{current_node.node_name} (ID: {current_node.node_id})" if current_node else "无(流程已结束)"
                raise PermissionError(
                    f"审批顺序违规: 当前待审批节点为 {expected_node}, "
                    f"不允许跳过顺序驳回 {node.node_name} (ID: {node_id})。"
                    f"请先完成当前待审批节点后再操作。"
                )

        node.status = ApprovalStatus.REJECTED
        node.approved_by = approver
        node.approved_at = datetime.now()
        node.comments = reject_reason

        flow.overall_status = ApprovalStatus.REJECTED
        flow.completed_at = datetime.now()

        self.logger.audit(
            "approval_flow_rejected",
            approver,
            f"release:{release_id}/node:{node_id}",
            "rejected",
            {"reject_reason": reject_reason, "department": node.department}
        )

        self._notify_flow_rejected(flow, approver, reject_reason)

        return flow

    def post_sign(self, release_id: str, node_id: str, approver: str,
                  comments: str = "", deviation_report: str = "",
                  flow: Optional[ApprovalFlow] = None) -> ApprovalFlow:
        if flow is None:
            raise ValueError("Approval flow must be provided or loaded")

        if not flow.allow_post_sign:
            raise ValueError("Post-sign is not allowed for this approval channel")

        if flow.channel != ApprovalChannel.HOTFIX:
            raise ValueError("Post-sign is only allowed for Hotfix channel")

        node = self._find_node(flow, node_id)
        if node is None:
            raise ValueError(f"Node {node_id} not found in flow")

        node.status = ApprovalStatus.APPROVED
        node.approved_by = approver
        node.approved_at = datetime.now()
        node.comments = comments

        flow.deviation_report = deviation_report

        self.logger.audit(
            "approval_node_post_signed",
            approver,
            f"release:{release_id}/node:{node_id}",
            "post_signed",
            {
                "comments": comments,
                "deviation_report": deviation_report,
                "department": node.department
            }
        )

        if all(n.status == ApprovalStatus.APPROVED for n in flow.nodes):
            flow.overall_status = ApprovalStatus.APPROVED
            flow.completed_at = datetime.now()
            self._notify_flow_complete(flow)

        return flow

    def check_timeouts(self, flow: ApprovalFlow) -> List[str]:
        timeout_nodes = []
        timeout_hours = self.config.get("approval.timeout_hours", 48)
        reminder_interval = self.config.get("approval.reminder_interval_minutes", 30)

        for idx, node in enumerate(flow.nodes):
            if node.status == ApprovalStatus.PENDING:
                created_at = flow.created_at
                if not flow.allow_parallel and idx != flow.current_node_index:
                    continue

                elapsed = datetime.now() - created_at
                if elapsed > timedelta(hours=timeout_hours):
                    timeout_nodes.append(node.node_id)
                    self.logger.warning(
                        f"Approval timeout: node={node.node_id}, "
                        f"department={node.department}, elapsed={elapsed}"
                    )

        return timeout_nodes

    def _find_node(self, flow: ApprovalFlow, node_id: str) -> Optional[ApprovalNode]:
        for node in flow.nodes:
            if node.node_id == node_id:
                return node
        return None

    def get_current_nodes(self, flow: ApprovalFlow) -> List[ApprovalNode]:
        if flow.allow_parallel:
            return [n for n in flow.nodes if n.status == ApprovalStatus.PENDING]
        else:
            if flow.current_node_index < len(flow.nodes):
                return [flow.nodes[flow.current_node_index]]
            return []

    def _notify_current_approvals(self, flow: ApprovalFlow, operator: str):
        current_nodes = self.get_current_nodes(flow)
        if not current_nodes:
            return

        for node in current_nodes:
            channel_name = "紧急热修复" if flow.channel == ApprovalChannel.HOTFIX else "常规迭代"
            title = f"【待审批】药房发药系统{channel_name}发布 - {flow.version}"
            content = (
                f"**发布版本**: {flow.version}\n"
                f"**发布ID**: {flow.release_id}\n"
                f"**审批节点**: {node.node_name}\n"
                f"**审批人**: {', '.join(node.approvers)}\n"
                f"**发起时间**: {flow.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"**超时时间**: {(flow.created_at + timedelta(hours=node.timeout_hours)).strftime('%Y-%m-%d %H:%M:%S')}\n"
            )
            if flow.hotfix_reason:
                content += f"**紧急原因**: {flow.hotfix_reason}\n"

            self.notification.send_notification(title, content)

    def _notify_flow_complete(self, flow: ApprovalFlow):
        channel_name = "紧急热修复" if flow.channel == ApprovalChannel.HOTFIX else "常规迭代"
        title = f"【审批通过】药房发药系统{channel_name}发布已获全部批准 - {flow.version}"
        content = (
            f"**发布版本**: {flow.version}\n"
            f"**发布ID**: {flow.release_id}\n"
            f"**审批状态**: 全部通过\n"
            f"**完成时间**: {flow.completed_at.strftime('%Y-%m-%d %H:%M:%S') if flow.completed_at else 'N/A'}\n\n"
            f"审批详情:\n"
        )
        for node in flow.nodes:
            status_icon = "✅" if node.status == ApprovalStatus.APPROVED else "⏳"
            approver_info = f" (审批人: {node.approved_by})" if node.approved_by else ""
            content += f"- {status_icon} {node.node_name}{approver_info}\n"

        self.notification.send_notification(title, content)

    def _notify_flow_rejected(self, flow: ApprovalFlow, rejector: str, reason: str):
        channel_name = "紧急热修复" if flow.channel == ApprovalChannel.HOTFIX else "常规迭代"
        title = f"【审批驳回】药房发药系统{channel_name}发布被拒绝 - {flow.version}"
        content = (
            f"**发布版本**: {flow.version}\n"
            f"**发布ID**: {flow.release_id}\n"
            f"**驳回人**: {rejector}\n"
            f"**驳回原因**: {reason}\n"
            f"**驳回时间**: {flow.completed_at.strftime('%Y-%m-%d %H:%M:%S') if flow.completed_at else 'N/A'}\n"
        )
        self.notification.send_notification(title, content)

    def get_flow_summary(self, flow: ApprovalFlow) -> Dict[str, Any]:
        approved_count = sum(1 for n in flow.nodes if n.status == ApprovalStatus.APPROVED)
        pending_count = sum(1 for n in flow.nodes if n.status == ApprovalStatus.PENDING)
        rejected_count = sum(1 for n in flow.nodes if n.status == ApprovalStatus.REJECTED)

        current_nodes = self.get_current_nodes(flow)

        return {
            "release_id": flow.release_id,
            "version": flow.version,
            "channel": flow.channel,
            "overall_status": flow.overall_status,
            "progress": f"{approved_count}/{len(flow.nodes)}",
            "approved_count": approved_count,
            "pending_count": pending_count,
            "rejected_count": rejected_count,
            "current_approvers": [n.node_name for n in current_nodes],
            "hotfix_reason": flow.hotfix_reason,
            "has_deviation_report": bool(flow.deviation_report),
            "nodes": [
                {
                    "node_id": n.node_id,
                    "department": n.department,
                    "name": n.node_name,
                    "approvers": n.approvers,
                    "status": n.status.value if hasattr(n.status, 'value') else str(n.status),
                    "approved_by": n.approved_by,
                    "approved_at": n.approved_at.isoformat() if n.approved_at else None,
                    "comments": n.comments
                }
                for n in flow.nodes
            ]
        }

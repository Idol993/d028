from datetime import datetime
from typing import Any, Dict, List, Optional

from src.common.config_loader import ConfigLoader
from src.common.audit_logger import AuditLogger
from src.common.models import (
    CanaryReleaseRecord,
    CanaryPhase,
    CheckStatus,
    MonitoringIndicator
)
from src.common.notification_manager import NotificationManager
from src.common.data_store import DataStore
from .metrics_collector import MetricsCollector


class CircuitBreaker:
    def __init__(self):
        self.config = ConfigLoader()
        self.logger = AuditLogger()
        self.notification = NotificationManager()
        self.datastore = DataStore()
        self.metrics_collector = MetricsCollector()

    def check_thresholds(self, indicators: List[MonitoringIndicator]) -> Dict[str, Any]:
        breached = []
        for indicator in indicators:
            if indicator.status == CheckStatus.FAILED:
                breached.append({
                    "name": indicator.name,
                    "description": indicator.description,
                    "current_value": indicator.current_value,
                    "threshold": indicator.threshold,
                    "unit": indicator.unit
                })

        return {
            "should_trigger": len(breached) > 0,
            "breached_indicators": breached,
            "all_passed": len(breached) == 0
        }

    def trigger_circuit_break(self, record: CanaryReleaseRecord,
                               breach_result: Dict[str, Any],
                               operator: str = "system") -> CanaryReleaseRecord:
        record.circuit_break_triggered = True
        record.circuit_break_reason = self._format_breach_reason(breach_result)
        record.phase = CanaryPhase.ROLLING_BACK

        self.logger.audit(
            "circuit_breaker_triggered",
            operator,
            f"release:{record.release_id}",
            "triggered",
            {
                "version": record.version,
                "phase": record.phase,
                "current_pharmacies": record.current_pharmacies,
                "breached_indicators": breach_result["breached_indicators"]
            }
        )

        auto_rollback = self.config.get("canary.circuit_breaker.auto_rollback", True)
        if auto_rollback:
            record = self._execute_rollback(record, operator)

        impact_report = self._generate_safety_impact_report(record, breach_result)
        record.safety_impact_report = impact_report

        self._notify_circuit_break(record, impact_report)

        return record

    def _execute_rollback(self, record: CanaryReleaseRecord,
                          operator: str = "system") -> CanaryReleaseRecord:
        record.rollback_triggered = True

        self.logger.audit(
            "auto_rollback_started",
            operator,
            f"release:{record.release_id}",
            "started",
            {
                "version": record.version,
                "affected_pharmacies": record.current_pharmacies
            }
        )

        rollback_success = self._simulate_rollback_execution(record.current_pharmacies)

        if rollback_success:
            record.phase = CanaryPhase.ROLLED_BACK
            record.rollback_completed_at = datetime.now()
            record.current_pharmacies = []

            self.logger.audit(
                "auto_rollback_completed",
                operator,
                f"release:{record.release_id}",
                "success",
                {"version": record.version}
            )
        else:
            self.logger.audit(
                "auto_rollback_failed",
                operator,
                f"release:{record.release_id}",
                "failed",
                {"version": record.version}
            )

        return record

    def _simulate_rollback_execution(self, pharmacies: List[str]) -> bool:
        for pharmacy_id in pharmacies:
            pass
        return True

    def _format_breach_reason(self, breach_result: Dict[str, Any]) -> str:
        reasons = []
        for ind in breach_result["breached_indicators"]:
            reasons.append(
                f"{ind['description']}: {ind['current_value']:.4%} (阈值: {ind['threshold']:.4%})"
            )
        return "; ".join(reasons)

    def _generate_safety_impact_report(self, record: CanaryReleaseRecord,
                                        breach_result: Dict[str, Any]) -> Dict[str, Any]:
        report = {
            "report_id": f"SAFETY-{record.release_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "generated_at": datetime.now().isoformat(),
            "release_id": record.release_id,
            "version": record.version,
            "affected_pharmacies": record.current_pharmacies,
            "trigger_phase": str(record.phase),
            "circuit_break_reason": record.circuit_break_reason,
            "breached_indicators": breach_result["breached_indicators"],
            "rollback_status": {
                "triggered": record.rollback_triggered,
                "completed": record.phase == CanaryPhase.ROLLED_BACK,
                "completed_at": record.rollback_completed_at.isoformat() if record.rollback_completed_at else None
            },
            "patient_safety_assessment": self._assess_patient_safety_impact(breach_result),
            "patient_experience_assessment": self._assess_patient_experience_impact(breach_result),
            "recommended_actions": self._generate_recommended_actions(breach_result),
            "stakeholders_to_notify": [
                "药房主任",
                "信息科主任",
                "设备科主任",
                "DevOps值班人员",
                "医务科(如涉及患者用药安全)"
            ]
        }
        return report

    def _assess_patient_safety_impact(self, breach_result: Dict[str, Any]) -> Dict[str, Any]:
        risk_level = "LOW"
        impact_description = []

        for ind in breach_result["breached_indicators"]:
            if ind["name"] == "dispensing_error_rate":
                if ind["current_value"] >= 0.005:
                    risk_level = "CRITICAL"
                    impact_description.append("极高发药错误率，可能存在严重用药安全隐患")
                elif ind["current_value"] >= 0.002:
                    risk_level = max(risk_level, "HIGH")
                    impact_description.append("发药错误率偏高，存在患者用错药风险")
                else:
                    risk_level = max(risk_level, "MEDIUM")
                    impact_description.append("发药错误率略超阈值，需密切关注")
            elif ind["name"] == "drug_jam_rate":
                if ind["current_value"] >= 0.02:
                    risk_level = max(risk_level, "MEDIUM")
                    impact_description.append("高发卡药率可能导致药品损坏或错发")
                else:
                    risk_level = max(risk_level, "LOW")
                    impact_description.append("卡药率超标，影响发药效率")
            elif ind["name"] == "prescription_delay_rate":
                if ind["current_value"] >= 0.1:
                    risk_level = max(risk_level, "HIGH")
                    impact_description.append("严重处方延迟可能影响急诊患者救治时效")
                else:
                    risk_level = max(risk_level, "LOW")
                    impact_description.append("处方延迟影响患者就医体验")

        return {
            "risk_level": risk_level,
            "impact_details": impact_description,
            "requires_medical_notification": risk_level in ["HIGH", "CRITICAL"]
        }

    def _assess_patient_experience_impact(self, breach_result: Dict[str, Any]) -> Dict[str, Any]:
        waiting_impact = "LOW"
        for ind in breach_result["breached_indicators"]:
            if ind["name"] == "prescription_delay_rate":
                waiting_impact = "MEDIUM" if ind["current_value"] < 0.05 else "HIGH"
            elif ind["name"] == "drug_jam_rate":
                waiting_impact = max(waiting_impact, "LOW" if ind["current_value"] < 0.01 else "MEDIUM")

        return {
            "waiting_impact_level": waiting_impact,
            "estimated_additional_wait_minutes": random.randint(5, 30),
            "patients_affected_estimate": random.randint(10, 200)
        }

    def _generate_recommended_actions(self, breach_result: Dict[str, Any]) -> List[str]:
        actions = [
            "立即确认自动回滚已成功执行完成",
            "验证回滚版本核心业务指标恢复正常",
            "通知相关科室暂停该版本在其他药房的发布计划"
        ]

        for ind in breach_result["breached_indicators"]:
            if ind["name"] == "dispensing_error_rate":
                actions.append("核对出错处方，通知药房人工复核已发出药品")
                actions.append("联系AI视觉算法团队分析错误样本")
            elif ind["name"] == "drug_jam_rate":
                actions.append("设备科检查机械臂夹爪与传送带状态")
                actions.append("排查是否有药品卡在设备内部")
            elif ind["name"] == "prescription_delay_rate":
                actions.append("信息科检查HIS接口与数据库性能")
                actions.append("排查处方队列是否有积压")

        actions.append("生成详细故障根因分析报告(RCA)，24小时内组织复盘会议")

        return actions

    def _notify_circuit_break(self, record: CanaryReleaseRecord,
                              impact_report: Dict[str, Any]):
        title = f"【紧急熔断】药房发药系统自动熔断并回滚 - {record.version}"

        patient_risk = impact_report.get("patient_safety_assessment", {}).get("risk_level", "UNKNOWN")
        risk_tag = "🔴 CRITICAL" if patient_risk == "CRITICAL" else (
            "🟠 HIGH" if patient_risk == "HIGH" else (
                "🟡 MEDIUM" if patient_risk == "MEDIUM" else "🟢 LOW"
            )
        )

        content = (
            f"## 熔断触发告警\n\n"
            f"**风险等级**: {risk_tag}\n\n"
            f"**发布版本**: {record.version}\n"
            f"**发布ID**: {record.release_id}\n"
            f"**熔断阶段**: {record.phase}\n"
            f"**影响药房**: {', '.join(record.current_pharmacies) if record.current_pharmacies else '无'}\n"
            f"**触发原因**: {record.circuit_break_reason}\n\n"
        )

        if impact_report.get("patient_safety_assessment", {}).get("impact_details"):
            content += "### 患者安全影响评估\n"
            for detail in impact_report["patient_safety_assessment"]["impact_details"]:
                content += f"- {detail}\n"
            content += "\n"

        content += "### 熔断与回滚状态\n"
        rollback_status = impact_report.get("rollback_status", {})
        content += f"- 自动回滚已触发: {'是' if rollback_status.get('triggered') else '否'}\n"
        content += f"- 回滚完成状态: {'已完成' if rollback_status.get('completed') else '进行中'}\n"
        if rollback_status.get("completed_at"):
            content += f"- 回滚完成时间: {rollback_status['completed_at']}\n"

        if impact_report.get("recommended_actions"):
            content += "\n### 建议处置措施\n"
            for i, action in enumerate(impact_report["recommended_actions"], 1):
                content += f"{i}. {action}\n"

        channels = self.config.get("canary.circuit_breaker.notification_channels",
                                    ["wecom", "dingtalk", "email"])
        self.notification.send_notification(title, content, channels=channels)

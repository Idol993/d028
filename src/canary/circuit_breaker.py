import random
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
        affected_pharmacies_snapshot = list(record.current_pharmacies)

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

        impact_report = self._generate_safety_impact_report(
            record, breach_result, affected_pharmacies_snapshot
        )
        record.safety_impact_report = impact_report

        self._notify_circuit_break(record, impact_report, affected_pharmacies_snapshot)

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
                                        breach_result: Dict[str, Any],
                                        affected_pharmacies: List[str]) -> Dict[str, Any]:
        report = {
            "report_id": f"SAFETY-{record.release_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "generated_at": datetime.now().isoformat(),
            "release_id": record.release_id,
            "version": record.version,
            "affected_pharmacies": affected_pharmacies,
            "affected_pharmacy_count": len(affected_pharmacies),
            "trigger_phase": str(record.phase),
            "circuit_break_reason": record.circuit_break_reason,
            "breached_indicators": breach_result["breached_indicators"],
            "rollback_status": {
                "triggered": record.rollback_triggered,
                "completed": record.phase == CanaryPhase.ROLLED_BACK,
                "completed_at": record.rollback_completed_at.isoformat() if record.rollback_completed_at else None
            },
            "patient_safety_assessment": self._assess_patient_safety_impact(breach_result, affected_pharmacies),
            "patient_experience_assessment": self._assess_patient_experience_impact(breach_result),
            "recommended_actions": self._generate_recommended_actions(breach_result, affected_pharmacies),
            "stakeholders_to_notify": [
                "药房主任",
                "信息科主任",
                "设备科主任",
                "DevOps值班人员",
                "医务科(如涉及患者用药安全)"
            ]
        }
        return report

    @staticmethod
    def _risk_level_order(level: str) -> int:
        return {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}.get(level, -1)

    def _escalate_risk(self, current: str, new_level: str) -> str:
        if self._risk_level_order(new_level) > self._risk_level_order(current):
            return new_level
        return current

    def _assess_patient_safety_impact(self, breach_result: Dict[str, Any],
                                       affected_pharmacies: List[str]) -> Dict[str, Any]:
        risk_level = "LOW"
        impact_description = []

        emergency_flag = any("emergency" in p.lower() or "急诊" in p
                             for p in affected_pharmacies)

        for ind in breach_result["breached_indicators"]:
            val = ind["current_value"]

            if ind["name"] == "dispensing_error_rate":
                if val >= 0.005:
                    risk_level = self._escalate_risk(risk_level, "CRITICAL")
                    impact_description.append(
                        f"极高发药错误率({val:.2%} ≥ 0.5%)，可能存在严重用药安全隐患，"
                        f"需立即排查错发药品并启动用药差错应急预案"
                    )
                elif val >= 0.002:
                    risk_level = self._escalate_risk(risk_level, "HIGH")
                    impact_description.append(
                        f"发药错误率偏高({val:.2%} ≥ 0.2%)，存在患者用错药风险，"
                        f"建议药房人工复核已发出的高风险药品"
                    )
                else:
                    risk_level = self._escalate_risk(risk_level, "MEDIUM")
                    impact_description.append(
                        f"发药错误率略超阈值({val:.2%} > 0.1%)，需密切关注趋势并排查AI视觉模型偏差"
                    )

            elif ind["name"] == "drug_jam_rate":
                if val >= 0.03:
                    risk_level = self._escalate_risk(risk_level, "HIGH")
                    impact_description.append(
                        f"高卡药率({val:.2%} ≥ 3%)，可能导致药品损坏、药盒错放引发二次发药错误"
                    )
                elif val >= 0.01:
                    risk_level = self._escalate_risk(risk_level, "MEDIUM")
                    impact_description.append(
                        f"卡药率偏高({val:.2%} ≥ 1%)，设备科应尽快检查机械臂夹爪与传送带"
                    )
                else:
                    risk_level = self._escalate_risk(risk_level, "MEDIUM")
                    impact_description.append(
                        f"卡药率超标({val:.2%} > 0.5%)，提醒设备运维关注，暂不直接影响用药安全"
                    )

            elif ind["name"] == "prescription_delay_rate":
                if val >= 0.15:
                    risk_level = self._escalate_risk(risk_level, "CRITICAL")
                    impact_description.append(
                        f"极严重处方延迟({val:.2%} ≥ 15%)，"
                        f"{'急诊场景下可能危及患者生命安全' if emergency_flag else '严重影响患者救治时效'}"
                        f"，需立即启动人工发药应急预案"
                    )
                elif val >= 0.10:
                    risk_level = self._escalate_risk(risk_level, "HIGH")
                    impact_description.append(
                        f"严重处方延迟({val:.2%} ≥ 10%)，"
                        f"{'可能影响急诊患者抢救时效' if emergency_flag else '影响核心门诊就医体验'}"
                        f"，信息科需紧急排查HIS接口与数据库性能"
                    )
                elif val >= 0.05:
                    risk_level = self._escalate_risk(risk_level, "MEDIUM")
                    impact_description.append(
                        f"较严重处方延迟({val:.2%} ≥ 5%)，高流量药房可能出现排队积压"
                    )
                else:
                    risk_level = self._escalate_risk(risk_level, "MEDIUM")
                    impact_description.append(
                        f"处方延迟率超标({val:.2%} > 2%)，需关注后续趋势，暂按中等风险处置"
                    )

        if emergency_flag and risk_level in ["LOW", "MEDIUM"]:
            risk_level = self._escalate_risk(risk_level, "MEDIUM")
            impact_description.append(
                "⚠️ 熔断涉及急诊药房，风险等级已按涉急诊场景自动上调关注级别"
            )

        return {
            "risk_level": risk_level,
            "impact_details": impact_description,
            "emergency_pharmacy_involved": emergency_flag,
            "requires_medical_notification": risk_level in ["HIGH", "CRITICAL"]
        }

    def _assess_patient_experience_impact(self, breach_result: Dict[str, Any]) -> Dict[str, Any]:
        waiting_impact = "LOW"
        for ind in breach_result["breached_indicators"]:
            if ind["name"] == "prescription_delay_rate":
                new_level = "MEDIUM" if ind["current_value"] < 0.05 else "HIGH"
                waiting_impact = self._escalate_risk(waiting_impact, new_level)
            elif ind["name"] == "drug_jam_rate":
                new_level = "LOW" if ind["current_value"] < 0.01 else "MEDIUM"
                waiting_impact = self._escalate_risk(waiting_impact, new_level)

        return {
            "waiting_impact_level": waiting_impact,
            "estimated_additional_wait_minutes": random.randint(5, 30),
            "patients_affected_estimate": random.randint(10, 200)
        }

    def _generate_recommended_actions(self, breach_result: Dict[str, Any],
                                        affected_pharmacies: List[str]) -> List[str]:
        actions = [
            f"立即确认自动回滚已在以下药房成功执行: {', '.join(affected_pharmacies)}",
            "验证回滚版本核心业务指标恢复正常",
            "通知相关科室暂停该版本在其他药房的发布计划"
        ]

        for ind in breach_result["breached_indicators"]:
            if ind["name"] == "dispensing_error_rate":
                actions.append(
                    f"针对受影响药房({', '.join(affected_pharmacies)})，"
                    f"核对出错处方，通知药房人工复核熔断时段内已发出的药品"
                )
                actions.append("联系AI视觉算法团队分析错误样本并重新训练模型")
            elif ind["name"] == "drug_jam_rate":
                actions.append("设备科检查受影响药房的机械臂夹爪与传送带状态")
                actions.append("现场排查是否有药品卡在设备内部并清理")
            elif ind["name"] == "prescription_delay_rate":
                actions.append("信息科紧急检查HIS接口与数据库查询性能")
                actions.append("排查处方队列是否有积压并启动处方重推机制")

        actions.append("生成详细故障根因分析报告(RCA)，24小时内组织跨科室复盘会议")

        return actions

    def _notify_circuit_break(self, record: CanaryReleaseRecord,
                              impact_report: Dict[str, Any],
                              affected_pharmacies: List[str]):
        title = f"【紧急熔断】药房发药系统自动熔断并回滚 - {record.version}"

        patient_risk = impact_report.get("patient_safety_assessment", {}).get("risk_level", "UNKNOWN")
        risk_tag = "🔴 CRITICAL" if patient_risk == "CRITICAL" else (
            "🟠 HIGH" if patient_risk == "HIGH" else (
                "🟡 MEDIUM" if patient_risk == "MEDIUM" else "🟢 LOW"
            )
        )

        emergency_involved = impact_report.get("patient_safety_assessment", {}).get(
            "emergency_pharmacy_involved", False
        )

        content = (
            f"## 熔断触发告警\n\n"
            f"**风险等级**: {risk_tag}\n"
            f"**涉及急诊药房**: {'⚠️ 是' if emergency_involved else '否'}\n\n"
            f"**发布版本**: {record.version}\n"
            f"**发布ID**: {record.release_id}\n"
            f"**熔断阶段**: {record.phase}\n"
            f"**受影响药房 ({len(affected_pharmacies)}家)**: {', '.join(affected_pharmacies) if affected_pharmacies else '无'}\n"
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

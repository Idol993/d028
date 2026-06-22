import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

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
from .circuit_breaker import CircuitBreaker


class CanaryReleaseOrchestrator:
    def __init__(self, demo_force_result: Optional[str] = None):
        self.config = ConfigLoader()
        self.logger = AuditLogger()
        self.notification = NotificationManager()
        self.datastore = DataStore()
        self.metrics_collector = MetricsCollector()
        self.circuit_breaker = CircuitBreaker()
        self.demo_force_result = demo_force_result

    def create_canary_release(self, release_id: str, version: str,
                               operator: str = "system") -> CanaryReleaseRecord:
        record = CanaryReleaseRecord(
            release_id=release_id,
            version=version,
            phase=CanaryPhase.NOT_STARTED
        )

        all_pharmacies = []
        tiers_config = self.config.get("canary.pharmacies", {})
        for tier_name, tier_config in tiers_config.items():
            members = tier_config.get("members", [])
            all_pharmacies.extend(members)

        record.target_pharmacies = all_pharmacies

        self.logger.audit(
            "canary_release_created",
            operator,
            f"release:{release_id}",
            "created",
            {"version": version, "target_pharmacies": all_pharmacies}
        )

        return record

    def advance_phase(self, record: CanaryReleaseRecord,
                      operator: str = "system",
                      simulate_wait: bool = True) -> CanaryReleaseRecord:
        phase_order = [CanaryPhase.TIER1, CanaryPhase.TIER2, CanaryPhase.TIER3, CanaryPhase.COMPLETED]
        current_phase_index = phase_order.index(record.phase) if record.phase in phase_order else -1

        if record.phase == CanaryPhase.NOT_STARTED:
            next_phase = CanaryPhase.TIER1
        elif current_phase_index >= 0 and current_phase_index < len(phase_order) - 1:
            next_phase = phase_order[current_phase_index + 1]
        else:
            next_phase = CanaryPhase.COMPLETED

        tiers_config = self.config.get("canary.pharmacies", {})
        phase_tier_map = {
            CanaryPhase.TIER1: "tier1",
            CanaryPhase.TIER2: "tier2",
            CanaryPhase.TIER3: "tier3"
        }

        if next_phase in phase_tier_map:
            tier_key = phase_tier_map[next_phase]
            tier_config = tiers_config.get(tier_key, {})
            record.current_pharmacies = tier_config.get("members", [])
            record.phase_observe_minutes = tier_config.get("observe_minutes", 30)
            record.phase_started_at = datetime.now()
            record.phase = next_phase

            tier_name = tier_config.get("name", next_phase)
            self.logger.audit(
                "canary_phase_advanced",
                operator,
                f"release:{record.release_id}",
                "success",
                {
                    "version": record.version,
                    "to_phase": next_phase,
                    "tier_name": tier_name,
                    "pharmacies": record.current_pharmacies,
                    "observe_minutes": record.phase_observe_minutes
                }
            )

            self._notify_phase_start(record, tier_name)

            if simulate_wait:
                self.logger.info(
                    f"Simulating observation period for phase {next_phase}: "
                    f"{record.phase_observe_minutes} minutes (accelerated)"
                )
                record = self._monitor_during_phase(record, operator)
        else:
            record.phase = CanaryPhase.COMPLETED
            record.current_pharmacies = list(record.target_pharmacies)
            self.logger.audit(
                "canary_release_completed",
                operator,
                f"release:{record.release_id}",
                "completed",
                {"version": record.version}
            )
            self._notify_release_complete(record)

        return record

    def _monitor_during_phase(self, record: CanaryReleaseRecord,
                              operator: str = "system") -> CanaryReleaseRecord:
        interval_seconds = self.config.get("canary.monitoring.interval_seconds", 300)
        observe_minutes = record.phase_observe_minutes
        total_checks = max(1, int((observe_minutes * 60) / interval_seconds))

        simulated_checks = min(total_checks, 3)

        for check_idx in range(simulated_checks):
            self.logger.info(
                f"Monitoring check {check_idx + 1}/{simulated_checks} for phase {record.phase}"
            )

            if self.demo_force_result == "circuit_break":
                if record.phase == CanaryPhase.TIER1 and check_idx == 0:
                    demo_metrics = [
                        MonitoringIndicator(
                            name="prescription_delay_rate",
                            description="处方延迟率（从结算到发药完成超时）",
                            current_value=0.12,
                            threshold=0.02,
                            status=CheckStatus.FAILED,
                            unit="%"
                        ),
                        MonitoringIndicator(
                            name="dispensing_error_rate",
                            description="发药错误率（错发/漏发）",
                            current_value=0.0015,
                            threshold=0.001,
                            status=CheckStatus.FAILED,
                            unit="%"
                        )
                    ]
                    record.indicators = demo_metrics
                    breach_result = self.circuit_breaker.check_thresholds(demo_metrics)
                    self.logger.warning(
                        f"[DEMO] 强制熔断触发 during phase {record.phase} at check {check_idx + 1}"
                    )
                    record = self.circuit_breaker.trigger_circuit_break(record, breach_result, operator)
                    break
                else:
                    demo_metrics = [
                        MonitoringIndicator(
                            name="prescription_delay_rate",
                            description="处方延迟率",
                            current_value=0.005,
                            threshold=0.02,
                            status=CheckStatus.PASSED,
                            unit="%"
                        ),
                        MonitoringIndicator(
                            name="dispensing_error_rate",
                            description="发药错误率",
                            current_value=0.0001,
                            threshold=0.001,
                            status=CheckStatus.PASSED,
                            unit="%"
                        ),
                        MonitoringIndicator(
                            name="drug_jam_rate",
                            description="卡药率",
                            current_value=0.001,
                            threshold=0.005,
                            status=CheckStatus.PASSED,
                            unit="%"
                        )
                    ]
                    record.indicators = demo_metrics
                    breach_result = {"should_trigger": False, "all_passed": True, "breached_indicators": []}
            elif self.demo_force_result == "success":
                demo_metrics = [
                    MonitoringIndicator(
                        name="prescription_delay_rate",
                        description="处方延迟率",
                        current_value=0.005,
                        threshold=0.02,
                        status=CheckStatus.PASSED,
                        unit="%"
                    ),
                    MonitoringIndicator(
                        name="dispensing_error_rate",
                        description="发药错误率",
                        current_value=0.0001,
                        threshold=0.001,
                        status=CheckStatus.PASSED,
                        unit="%"
                    ),
                    MonitoringIndicator(
                        name="drug_jam_rate",
                        description="卡药率",
                        current_value=0.001,
                        threshold=0.005,
                        status=CheckStatus.PASSED,
                        unit="%"
                    )
                ]
                record.indicators = demo_metrics
                breach_result = {"should_trigger": False, "all_passed": True, "breached_indicators": []}
            else:
                metrics_by_pharmacy = self.metrics_collector.collect_pharmacy_metrics(
                    record.current_pharmacies,
                    duration_minutes=int(interval_seconds / 60)
                )
                aggregate_metrics = self.metrics_collector.compute_aggregate_metrics(metrics_by_pharmacy)
                record.indicators = aggregate_metrics
                breach_result = self.circuit_breaker.check_thresholds(aggregate_metrics)

            if breach_result["should_trigger"]:
                self.logger.warning(
                    f"Circuit breaker triggered during phase {record.phase} at check {check_idx + 1}"
                )
                record = self.circuit_breaker.trigger_circuit_break(record, breach_result, operator)
                break
            else:
                self.logger.info(
                    f"All indicators within thresholds for check {check_idx + 1}"
                )

        return record

    def run_full_canary(self, release_id: str, version: str,
                        operator: str = "system",
                        on_phase_complete: Optional[Callable] = None) -> CanaryReleaseRecord:
        record = self.create_canary_release(release_id, version, operator)

        while record.phase not in [CanaryPhase.COMPLETED, CanaryPhase.ROLLED_BACK, CanaryPhase.ROLLING_BACK]:
            record = self.advance_phase(record, operator, simulate_wait=True)

            if record.circuit_break_triggered:
                break

            if on_phase_complete:
                on_phase_complete(record)

        return record

    def manual_rollback(self, record: CanaryReleaseRecord,
                         reason: str,
                         operator: str = "system") -> CanaryReleaseRecord:
        self.logger.audit(
            "manual_rollback_triggered",
            operator,
            f"release:{record.release_id}",
            "triggered",
            {
                "version": record.version,
                "reason": reason,
                "current_pharmacies": record.current_pharmacies
            }
        )

        breach_result = {
            "should_trigger": True,
            "breached_indicators": [{
                "name": "manual_trigger",
                "description": f"人工触发回滚: {reason}",
                "current_value": 0,
                "threshold": 0,
                "unit": ""
            }],
            "all_passed": False
        }
        record.circuit_break_reason = f"人工触发: {reason}"

        return self.circuit_breaker.trigger_circuit_break(record, breach_result, operator)

    def get_phases_status(self, record: CanaryReleaseRecord) -> Dict[str, Any]:
        tiers_config = self.config.get("canary.pharmacies", {})

        phases_info = []
        for phase_enum, tier_key in [
            (CanaryPhase.TIER1, "tier1"),
            (CanaryPhase.TIER2, "tier2"),
            (CanaryPhase.TIER3, "tier3")
        ]:
            tier_config = tiers_config.get(tier_key, {})
            phases_info.append({
                "phase": phase_enum,
                "name": tier_config.get("name", tier_key),
                "pharmacies": tier_config.get("members", []),
                "observe_minutes": tier_config.get("observe_minutes", 30),
                "status": self._get_phase_status(record, phase_enum)
            })

        return {
            "release_id": record.release_id,
            "version": record.version,
            "current_phase": record.phase,
            "current_pharmacies": record.current_pharmacies,
            "circuit_break_triggered": record.circuit_break_triggered,
            "circuit_break_reason": record.circuit_break_reason,
            "rollback_triggered": record.rollback_triggered,
            "rollback_completed": record.phase == CanaryPhase.ROLLED_BACK,
            "indicators": [
                {
                    "name": ind.name,
                    "description": ind.description,
                    "current_value": ind.current_value,
                    "threshold": ind.threshold,
                    "status": ind.status,
                    "unit": ind.unit
                }
                for ind in record.indicators
            ],
            "phases": phases_info,
            "safety_impact_report": record.safety_impact_report
        }

    def _get_phase_status(self, record: CanaryReleaseRecord, phase: CanaryPhase) -> str:
        phase_order = [CanaryPhase.TIER1, CanaryPhase.TIER2, CanaryPhase.TIER3]

        if record.phase == CanaryPhase.NOT_STARTED:
            return "pending"
        if record.phase in [CanaryPhase.ROLLED_BACK, CanaryPhase.ROLLING_BACK]:
            return "rolled_back"
        if record.phase == CanaryPhase.COMPLETED:
            return "completed"

        current_idx = phase_order.index(record.phase) if record.phase in phase_order else -1
        target_idx = phase_order.index(phase) if phase in phase_order else -1

        if target_idx < current_idx:
            return "completed"
        elif target_idx == current_idx:
            return "in_progress"
        else:
            return "pending"

    def _notify_phase_start(self, record: CanaryReleaseRecord, tier_name: str):
        title = f"【灰度发布】药房发药系统进入{tier_name}发布阶段 - {record.version}"
        content = (
            f"**发布版本**: {record.version}\n"
            f"**发布ID**: {record.release_id}\n"
            f"**发布阶段**: {tier_name}\n"
            f"**涉及药房**: {', '.join(record.current_pharmacies)}\n"
            f"**观察时长**: {record.phase_observe_minutes} 分钟\n"
            f"**监控频率**: 每 {self.config.get('canary.monitoring.interval_seconds', 300)} 秒\n"
            f"**开始时间**: {record.phase_started_at.strftime('%Y-%m-%d %H:%M:%S') if record.phase_started_at else 'N/A'}\n\n"
            f"监控指标阈值:\n"
        )
        indicators_config = self.config.get("canary.monitoring.indicators", {})
        for ind_name, ind_config in indicators_config.items():
            content += f"- {ind_config.get('description', ind_name)}: 阈值 {ind_config.get('threshold', 'N/A')}\n"

        self.notification.send_notification(title, content)

    def _notify_release_complete(self, record: CanaryReleaseRecord):
        title = f"【发布完成】药房发药系统灰度发布全部完成 - {record.version}"
        content = (
            f"**发布版本**: {record.version}\n"
            f"**发布ID**: {record.release_id}\n"
            f"**完成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"**全部药房**: {', '.join(record.target_pharmacies)}\n\n"
            f"✅ 所有灰度阶段监控指标均在安全阈值内，发布圆满完成。"
        )
        self.notification.send_notification(title, content)

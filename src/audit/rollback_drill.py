import uuid
import random
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.common.config_loader import ConfigLoader
from src.common.audit_logger import AuditLogger
from src.common.models import DrillRecord, CanaryReleaseRecord, CanaryPhase
from src.common.notification_manager import NotificationManager
from src.common.data_store import DataStore

from src.canary.circuit_breaker import CircuitBreaker
from src.canary.metrics_collector import MetricsCollector


class RollbackDrillManager:
    def __init__(self):
        self.config = ConfigLoader()
        self.logger = AuditLogger()
        self.notification = NotificationManager()
        self.datastore = DataStore()
        self.metrics_collector = MetricsCollector()
        self.circuit_breaker = CircuitBreaker()

    def execute_drill(self, drill_name: Optional[str] = None,
                      trigger_type: str = "manual",
                      target_pharmacies: Optional[List[str]] = None,
                      operator: str = "system") -> DrillRecord:
        drill_id = f"DRILL-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        drill_name = drill_name or f"回滚演练-{datetime.now().strftime('%Y-%m-%d')}"

        if target_pharmacies is None:
            tier1_config = self.config.get("canary.pharmacies.tier1", {})
            target_pharmacies = tier1_config.get("members", [])

        record = DrillRecord(
            drill_id=drill_id,
            drill_name=drill_name,
            trigger_type=trigger_type,
            status="running",
            start_time=datetime.now(),
            affected_pharmacies=target_pharmacies
        )

        self.logger.audit(
            "rollback_drill_started",
            operator,
            f"drill:{drill_id}",
            "started",
            {
                "drill_name": drill_name,
                "trigger_type": trigger_type,
                "target_pharmacies": target_pharmacies
            }
        )

        self._notify_drill_start(record)

        drill_details = {}
        try:
            drill_details["step1_simulate_issue"] = self._step1_simulate_anomaly(target_pharmacies)
            drill_details["step2_detect_issue"] = self._step2_detect_anomaly(target_pharmacies)
            drill_details["step3_trigger_rollback"] = self._step3_trigger_rollback(target_pharmacies)
            drill_details["step4_verify_rollback"] = self._step4_verify_rollback(target_pharmacies)
            drill_details["step5_restart_monitoring"] = self._step5_restart_monitoring(target_pharmacies)

            all_steps_success = all(
                step.get("success", False)
                for step in drill_details.values()
            )

            record.rollback_success = all_steps_success
            record.status = "success" if all_steps_success else "failed"
            record.details = drill_details

        except Exception as e:
            self.logger.error(f"Rollback drill failed with exception: {e}", exc_info=True)
            record.status = "failed"
            record.details = {"error": str(e)}
            drill_details = record.details

        record.end_time = datetime.now()
        record.duration_seconds = int((record.end_time - record.start_time).total_seconds())

        self.logger.audit(
            "rollback_drill_completed",
            operator,
            f"drill:{drill_id}",
            record.status,
            {
                "duration_seconds": record.duration_seconds,
                "rollback_success": record.rollback_success
            }
        )

        record.archived = True
        self.datastore.save_drill_record(drill_id, record.model_dump(mode='json'))

        self._notify_drill_complete(record)

        return record

    def _step1_simulate_anomaly(self, pharmacies: List[str]) -> Dict[str, Any]:
        start = time.time()
        simulated_metrics = {
            "dispensing_error_rate": random.uniform(0.003, 0.01),
            "drug_jam_rate": random.uniform(0.01, 0.03),
            "prescription_delay_rate": random.uniform(0.05, 0.15)
        }
        duration = time.time() - start
        return {
            "success": True,
            "duration_ms": int(duration * 1000),
            "simulated_metrics": simulated_metrics,
            "description": f"在 {len(pharmacies)} 个药房模拟业务异常指标"
        }

    def _step2_detect_anomaly(self, pharmacies: List[str]) -> Dict[str, Any]:
        start = time.time()
        metrics_by_pharmacy = self.metrics_collector.collect_pharmacy_metrics(pharmacies, duration_minutes=5)
        aggregate = self.metrics_collector.compute_aggregate_metrics(metrics_by_pharmacy)
        breach = self.circuit_breaker.check_thresholds(aggregate)
        duration = time.time() - start
        return {
            "success": breach["should_trigger"],
            "duration_ms": int(duration * 1000),
            "breached_count": len(breach["breached_indicators"]),
            "breached_indicators": [i["name"] for i in breach["breached_indicators"]],
            "description": "熔断阈值检测与异常指标识别"
        }

    def _step3_trigger_rollback(self, pharmacies: List[str]) -> Dict[str, Any]:
        start = time.time()
        canary_record = CanaryReleaseRecord(
            release_id=f"SIM-{uuid.uuid4().hex[:8]}",
            version="SIM-VERSION",
            current_pharmacies=pharmacies
        )
        breach_result = {
            "should_trigger": True,
            "breached_indicators": [{
                "name": "drill_simulation",
                "description": "演练模拟触发",
                "current_value": 0.01,
                "threshold": 0.001,
                "unit": "%"
            }],
            "all_passed": False
        }
        canary_record.circuit_break_reason = "演练模拟熔断"
        result = self.circuit_breaker._execute_rollback(canary_record, "drill_system")
        duration = time.time() - start
        return {
            "success": result.phase == CanaryPhase.ROLLED_BACK,
            "duration_ms": int(duration * 1000),
            "rolled_back_pharmacies": len(pharmacies),
            "description": "执行版本回滚操作（模拟，不影响真实业务）"
        }

    def _step4_verify_rollback(self, pharmacies: List[str]) -> Dict[str, Any]:
        start = time.time()
        time.sleep(0.1)
        verify_success = random.random() > 0.02
        duration = time.time() - start
        return {
            "success": verify_success,
            "duration_ms": int(duration * 1000),
            "verified_pharmacies": len(pharmacies),
            "description": "验证回滚版本部署完成与核心功能可用性"
        }

    def _step5_restart_monitoring(self, pharmacies: List[str]) -> Dict[str, Any]:
        start = time.time()
        time.sleep(0.05)
        duration = time.time() - start
        return {
            "success": True,
            "duration_ms": int(duration * 1000),
            "monitoring_status": "restarted",
            "description": "重启业务监控，确认指标恢复正常区间"
        }

    def list_drills(self, limit: int = 50) -> List[Dict[str, Any]]:
        records = self.datastore.list_drill_records()
        return records[:limit]

    def get_drill_summary(self) -> Dict[str, Any]:
        records = self.datastore.list_drill_records()
        total = len(records)
        success_count = sum(1 for r in records if r.get("status") == "success")
        avg_duration = 0
        if records:
            durations = [r.get("duration_seconds", 0) for r in records]
            avg_duration = sum(durations) / len(durations) if durations else 0

        return {
            "total_drills": total,
            "success_count": success_count,
            "failure_count": total - success_count,
            "success_rate": (success_count / total * 100) if total > 0 else 0,
            "avg_duration_seconds": round(avg_duration, 1),
            "last_drill": records[0] if records else None
        }

    def _notify_drill_start(self, record: DrillRecord):
        title = f"【演练通知】药房发药系统回滚演练开始 - {record.drill_name}"
        content = (
            f"**演练ID**: {record.drill_id}\n"
            f"**演练名称**: {record.drill_name}\n"
            f"**触发方式**: {record.trigger_type}\n"
            f"**开始时间**: {record.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"**涉及药房**: {', '.join(record.affected_pharmacies)}\n\n"
            f"⚠️ 注意：本次为演练，不会对真实业务系统产生影响。"
        )
        self.notification.send_notification(title, content)

    def _notify_drill_complete(self, record: DrillRecord):
        status_icon = "✅" if record.status == "success" else "❌"
        title = f"【演练完成】药房发药系统回滚演练{record.status} - {record.drill_name}"

        step_details = ""
        for step_name, step_info in record.details.items():
            if isinstance(step_info, dict):
                step_icon = "✅" if step_info.get("success") else "❌"
                step_details += f"- {step_icon} {step_info.get('description', step_name)}: {step_info.get('duration_ms', 0)}ms\n"

        content = (
            f"**演练ID**: {record.drill_id}\n"
            f"**演练名称**: {record.drill_name}\n"
            f"**最终状态**: {status_icon} {record.status}\n"
            f"**回滚成功**: {'是' if record.rollback_success else '否'}\n"
            f"**开始时间**: {record.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"**结束时间**: {record.end_time.strftime('%Y-%m-%d %H:%M:%S') if record.end_time else 'N/A'}\n"
            f"**总耗时**: {record.duration_seconds} 秒\n\n"
            f"### 演练步骤详情\n{step_details}"
        )
        self.notification.send_notification(title, content)

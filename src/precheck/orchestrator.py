import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.common.config_loader import ConfigLoader
from src.common.audit_logger import AuditLogger
from src.common.models import (
    PreCheckReport,
    CheckStatus,
    SingleCheckResult
)

from .base_check import BasePreCheck
from .ai_vision_checker import AIVisionChecker
from .his_interface_checker import HISInterfaceChecker
from .barcode_checker import BarcodeValidationChecker
from .device_health_checker import DeviceHealthChecker


class PreCheckOrchestrator:
    def __init__(self, demo_force_result: Optional[str] = None):
        self.config = ConfigLoader()
        self.logger = AuditLogger()
        self._checkers: Dict[str, BasePreCheck] = {
            "ai_vision_test": AIVisionChecker(),
            "his_interface_check": HISInterfaceChecker(),
            "barcode_validation": BarcodeValidationChecker(),
            "device_health_check": DeviceHealthChecker()
        }
        self.demo_force_result = demo_force_result

    def run_precheck(self, version: str, release_id: Optional[str] = None,
                     context: Optional[Dict[str, Any]] = None) -> PreCheckReport:
        release_id = release_id or f"REL-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
        context = context or {}

        self.logger.audit(
            "precheck_start",
            context.get("operator", "system"),
            f"release:{release_id}",
            "started",
            {"version": version}
        )

        report = PreCheckReport(
            release_id=release_id,
            version=version
        )

        enabled_modules = self.config.get("precheck.modules", list(self._checkers.keys()))
        blocking_strategy = self.config.get("precheck.blocking_strategy", "any_fail_blocks")

        all_results: List[SingleCheckResult] = []

        if self.demo_force_result == "pass":
            for module_name in enabled_modules:
                if module_name in self._checkers:
                    checker = self._checkers[module_name]
                    all_results.append(SingleCheckResult(
                        check_id=f"demo_{module_name}",
                        check_name=checker.__class__.__name__.replace("Checker", ""),
                        category=checker.category if hasattr(checker, 'category') else "system",
                        status=CheckStatus.PASSED,
                        message="演示模式：强制通过",
                        repair_suggestion=""
                    ))
        elif self.demo_force_result == "fail":
            fail_reasons = [
                ("ai_vision_test", "AI视觉识别准确率未达99.95%基线", "请重新校准机械臂摄像头并执行AI模型准确率回归测试"),
                ("his_interface_check", "HIS接口处方流转超时>3000ms", "请排查HIS中间件日志，检查处方队列积压情况"),
                ("barcode_validation", "药盒追溯码采集成功率低于99.9%", "请检查条码扫描枪对焦和光源，清洁药盒标签"),
                ("device_health_check", "机械臂运动控制器健康度<90分", "请执行机械臂零点校准，检查同步带张力和关节润滑")
            ]
            for module_name, msg, repair in fail_reasons:
                if module_name in self._checkers:
                    checker = self._checkers[module_name]
                    all_results.append(SingleCheckResult(
                        check_id=f"demo_fail_{module_name}",
                        check_name=checker.__class__.__name__.replace("Checker", ""),
                        category=checker.category if hasattr(checker, 'category') else "system",
                        status=CheckStatus.FAILED,
                        message=msg,
                        repair_suggestion=repair
                    ))
        else:
            for module_name in enabled_modules:
                if module_name in self._checkers:
                    self.logger.info(f"Running precheck module: {module_name}")
                    checker = self._checkers[module_name]
                    try:
                        results = checker.execute(release_id, context)
                        all_results.extend(results)
                    except Exception as e:
                        self.logger.error(f"Precheck module {module_name} failed: {e}", exc_info=True)
                        all_results.append(SingleCheckResult(
                            check_id=f"sys_error_{module_name}",
                            check_name=f"模块执行异常-{module_name}",
                            category=checker.category if hasattr(checker, 'category') else "system",
                            status=CheckStatus.FAILED,
                            message=f"模块执行异常: {str(e)}",
                            repair_suggestion=f"请检查{module_name}模块配置与依赖, 查看详细日志定位问题"
                        ))

        report.results = all_results
        report.total_checks = len(all_results)
        report.passed_checks = sum(1 for r in all_results if r.status == CheckStatus.PASSED)
        report.failed_checks = sum(1 for r in all_results if r.status == CheckStatus.FAILED)
        report.warning_checks = sum(1 for r in all_results if r.status == CheckStatus.WARNING)
        report.skipped_checks = sum(1 for r in all_results if r.status == CheckStatus.SKIPPED)
        report.completed_at = datetime.now()

        failed_repairs = [r.repair_suggestion for r in all_results
                          if r.status == CheckStatus.FAILED and r.repair_suggestion]
        report.repair_summary = failed_repairs

        if blocking_strategy == "any_fail_blocks" and report.failed_checks > 0:
            report.overall_status = CheckStatus.FAILED
            report.blocking = True
        elif report.failed_checks == 0 and report.warning_checks == 0:
            report.overall_status = CheckStatus.PASSED
            report.blocking = False
        elif report.failed_checks == 0 and report.warning_checks > 0:
            report.overall_status = CheckStatus.WARNING
            report.blocking = False
        else:
            report.overall_status = CheckStatus.FAILED
            report.blocking = True

        self.logger.audit(
            "precheck_complete",
            context.get("operator", "system"),
            f"release:{release_id}",
            report.overall_status,
            {
                "version": version,
                "total": report.total_checks,
                "passed": report.passed_checks,
                "failed": report.failed_checks,
                "blocking": report.blocking
            }
        )

        return report

    def get_checker_status_summary(self, report: PreCheckReport) -> Dict[str, Any]:
        overall_status_val = report.overall_status.value if hasattr(report.overall_status, 'value') else str(report.overall_status)
        summary = {
            "release_id": report.release_id,
            "version": report.version,
            "overall_status": overall_status_val,
            "blocking": report.blocking,
            "by_category": {},
            "failed_checks": [],
            "repair_actions": []
        }

        for result in report.results:
            category = result.category.value if hasattr(result.category, 'value') else str(result.category)
            status_val = result.status.value if hasattr(result.status, 'value') else str(result.status)
            if category not in summary["by_category"]:
                summary["by_category"][category] = {"passed": 0, "failed": 0, "warning": 0, "skipped": 0, "pending": 0}
            summary["by_category"][category][status_val] += 1

            status_enum = result.status.value if hasattr(result.status, 'value') else result.status
            if status_enum == CheckStatus.FAILED or status_enum == "failed":
                summary["failed_checks"].append({
                    "check_id": result.check_id,
                    "check_name": result.check_name,
                    "message": result.message,
                    "repair_suggestion": result.repair_suggestion
                })
                if result.repair_suggestion:
                    summary["repair_actions"].append(result.repair_suggestion)

        return summary

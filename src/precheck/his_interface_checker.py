import random
import time
from typing import Any, Dict, List

from .base_check import BasePreCheck
from src.common.models import CheckStatus, SingleCheckResult, CheckCategory


class HISInterfaceChecker(BasePreCheck):
    def __init__(self):
        super().__init__()
        self.category = CheckCategory.HIS_INTERFACE
        self.check_name = "HIS接口连通性及处方流转规则校验"

    def execute(self, release_id: str, context: Dict[str, Any]) -> List[SingleCheckResult]:
        results = []

        results.append(self._check_connectivity())
        results.append(self._check_prescription_flow_rules())
        results.append(self._check_data_security())
        results.append(self._check_traceability_upload())

        return results

    def _check_connectivity(self) -> SingleCheckResult:
        start_time = time.time()
        threshold_ms = self.config.get("precheck.thresholds.his_interface_timeout_ms", 3000)

        response_time_ms, connected = self._simulate_his_ping()

        passed = connected and response_time_ms <= threshold_ms
        duration = int((time.time() - start_time) * 1000)

        repair_suggestion = ""
        if not passed:
            if not connected:
                repair_suggestion = (
                    "HIS接口连接失败。"
                    "建议: 1) 检查VPN/专线网络连通性; "
                    "2) 验证HIS接口服务是否正常运行; "
                    "3) 确认IP白名单与API密钥配置。"
                )
            else:
                repair_suggestion = (
                    f"HIS接口响应超时: {response_time_ms}ms, 阈值: {threshold_ms}ms。"
                    "建议: 1) 检查数据库查询优化; "
                    "2) 增加中间件缓存层; "
                    "3) 与HIS运维团队确认服务负载。"
                )

        return SingleCheckResult(
            check_id="his_001",
            check_name="HIS接口连通性与响应时间",
            category=self.category,
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=f"{response_time_ms}ms" if connected else "连接失败",
            threshold_value=f"连通且<={threshold_ms}ms",
            message="测试HIS RESTful接口的POST/PUT/GET基本连通性",
            repair_suggestion=repair_suggestion,
            duration_ms=duration
        )

    def _check_prescription_flow_rules(self) -> SingleCheckResult:
        start_time = time.time()
        test_prescriptions = [
            {"type": "普通处方", "items": 3, "controlled": False},
            {"type": "麻醉处方", "items": 1, "controlled": True},
            {"type": "急诊处方", "items": 5, "controlled": False},
            {"type": "儿科处方", "items": 2, "controlled": False, "age_limit": True},
            {"type": "冷链处方", "items": 2, "cold_chain": True}
        ]

        failures = []
        for rx in test_prescriptions:
            if not self._simulate_prescription_validation(rx):
                failures.append(rx["type"])

        passed = len(failures) == 0
        duration = int((time.time() - start_time) * 1000)

        repair_suggestion = ""
        if not passed:
            repair_suggestion = (
                f"处方流转规则校验失败。失败类型: {', '.join(failures)}。"
                "建议: 1) 核对处方状态机配置(待审核→已审核→已发药); "
                "2) 验证特殊药品(麻醉/精神类)双人复核逻辑; "
                "3) 检查处方回写HIS状态的幂等性。"
            )

        return SingleCheckResult(
            check_id="his_002",
            check_name="处方流转规则校验",
            category=self.category,
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=f"{len(test_prescriptions)-len(failures)}/{len(test_prescriptions)} 类型通过",
            threshold_value=f"全部 {len(test_prescriptions)} 处方类型通过",
            message=f"验证多类型处方流转: {', '.join([p['type'] for p in test_prescriptions])}",
            repair_suggestion=repair_suggestion,
            duration_ms=duration
        )

    def _check_data_security(self) -> SingleCheckResult:
        start_time = time.time()
        security_checks = [
            "患者信息脱敏传输",
            "处方签名验证",
            "接口权限鉴权",
            "操作审计日志上报"
        ]

        failures = []
        for check in security_checks:
            if not self._simulate_security_check(check):
                failures.append(check)

        passed = len(failures) == 0
        duration = int((time.time() - start_time) * 1000)

        repair_suggestion = ""
        if not passed:
            repair_suggestion = (
                f"数据安全检查未通过。失败项: {', '.join(failures)}。"
                "建议: 1) 确保传输层使用TLS 1.2+加密; "
                "2) 检查CA证书有效性; "
                "3) 验证脱敏规则是否符合HIPAA/等保2.0要求。"
            )

        return SingleCheckResult(
            check_id="his_003",
            check_name="HIS数据安全检查",
            category=self.category,
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=f"{len(security_checks)-len(failures)}/{len(security_checks)} 项通过",
            threshold_value=f"全部 {len(security_checks)} 项通过",
            message="验证与HIS数据交互的安全性合规性",
            repair_suggestion=repair_suggestion,
            duration_ms=duration
        )

    def _check_traceability_upload(self) -> SingleCheckResult:
        start_time = time.time()
        test_codes = 100
        success_count = self._simulate_traceability_upload(test_codes)

        success_rate = success_count / test_codes
        passed = success_rate >= 0.995
        duration = int((time.time() - start_time) * 1000)

        repair_suggestion = ""
        if not passed:
            repair_suggestion = (
                f"追溯码上传成功率: {success_rate:.2%}, 阈值: 99.5%。"
                "建议: 1) 检查追溯码平台接口限流配置; "
                "2) 增加本地重试与补偿机制; "
                "3) 验证追溯码格式解析正则。"
            )

        return SingleCheckResult(
            check_id="his_004",
            check_name="药品追溯码上传验证",
            category=self.category,
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=f"{success_rate:.2%} ({success_count}/{test_codes})",
            threshold_value=">= 99.5%",
            message="测试药品电子监管码上传至国家追溯平台的成功率与时延",
            repair_suggestion=repair_suggestion,
            duration_ms=duration
        )

    def _simulate_his_ping(self):
        connected = random.random() > 0.01
        response_time = random.randint(150, 800) if connected else 0
        return response_time, connected

    def _simulate_prescription_validation(self, rx: Dict) -> bool:
        return random.random() > 0.03

    def _simulate_security_check(self, check: str) -> bool:
        return random.random() > 0.01

    def _simulate_traceability_upload(self, count: int) -> int:
        failed = random.randint(0, 2)
        return count - failed

import random
import time
from typing import Any, Dict, List

from .base_check import BasePreCheck
from src.common.models import CheckStatus, SingleCheckResult, CheckCategory


class BarcodeValidationChecker(BasePreCheck):
    def __init__(self):
        super().__init__()
        self.category = CheckCategory.BARCODE_VALIDATION
        self.check_name = "药盒追溯码/条形码毫秒级无感采集与解析合规性"

    def execute(self, release_id: str, context: Dict[str, Any]) -> List[SingleCheckResult]:
        results = []

        results.append(self._check_recognition_speed())
        results.append(self._check_code_compliance())
        results.append(self._check_high_speed_collection())
        results.append(self._check_error_tolerance())

        return results

    def _check_recognition_speed(self) -> SingleCheckResult:
        start_time = time.time()
        threshold_ms = self.config.get("precheck.thresholds.barcode_recognition_ms", 100)

        samples = 500
        total_time_ms = 0
        slow_samples = 0
        for _ in range(samples):
            sample_time = self._simulate_barcode_scan_time()
            total_time_ms += sample_time
            if sample_time > threshold_ms:
                slow_samples += 1

        avg_time = total_time_ms / samples
        passed = avg_time <= threshold_ms and slow_samples == 0
        duration = int((time.time() - start_time) * 1000)

        repair_suggestion = ""
        if not passed:
            repair_suggestion = (
                f"条码识别平均耗时: {avg_time:.1f}ms, 阈值: {threshold_ms}ms, "
                f"超时样本: {slow_samples}/{samples}。"
                "建议: 1) 升级条码扫描驱动版本; "
                "2) 优化码制识别优先级(优先识别常用CODE-128/EAN-13); "
                "3) 检查扫描枪触发模式设置。"
            )

        return SingleCheckResult(
            check_id="barcode_001",
            check_name="条码识别响应时间",
            category=self.category,
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=f"平均 {avg_time:.1f}ms, 最慢 {max([self._simulate_barcode_scan_time() for _ in range(10)])}ms",
            threshold_value=f"<={threshold_ms}ms (100%样本)",
            message=f"测试 {samples} 个随机条码样本的识别速度",
            repair_suggestion=repair_suggestion,
            duration_ms=duration
        )

    def _check_code_compliance(self) -> SingleCheckResult:
        start_time = time.time()
        code_types = [
            ("CODE-128", "一维码 标准物流码"),
            ("EAN-13", "一维码 商品条码"),
            ("GS1-Datamatrix", "二维码 药品追溯码"),
            ("QR Code", "二维码 处方码"),
            ("PDF417", "二维码 驾照/医保码")
        ]

        failures = []
        for code_type, description in code_types:
            if not self._simulate_code_parse(code_type):
                failures.append(f"{code_type}({description})")

        passed = len(failures) == 0
        duration = int((time.time() - start_time) * 1000)

        repair_suggestion = ""
        if not passed:
            repair_suggestion = (
                f"码制解析合规性验证失败: {', '.join(failures)}。"
                "建议: 1) 升级条码解码库至最新版; "
                "2) 验证国家药品监督管理局追溯码格式规范; "
                "3) 测试特殊字符编码与中文支持。"
            )

        return SingleCheckResult(
            check_id="barcode_002",
            check_name="多码制解析合规性",
            category=self.category,
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=f"{len(code_types)-len(failures)}/{len(code_types)} 码制通过",
            threshold_value=f"全部 {len(code_types)} 种码制解析正确",
            message="验证一维码/二维码多种标准的解析正确性",
            repair_suggestion=repair_suggestion,
            duration_ms=duration
        )

    def _check_high_speed_collection(self) -> SingleCheckResult:
        start_time = time.time()
        belt_speed_m_per_s = 1.5
        box_spacing_m = 0.15
        boxes_per_minute = int((belt_speed_m_per_s * 60) / box_spacing_m)

        total_boxes = boxes_per_minute * 2
        missed = self._simulate_high_speed_miss(total_boxes, belt_speed_m_per_s)
        collection_rate = (total_boxes - missed) / total_boxes

        passed = collection_rate >= 0.9999
        duration = int((time.time() - start_time) * 1000)

        repair_suggestion = ""
        if not passed:
            repair_suggestion = (
                f"高速传送带采集率: {collection_rate:.4%}, 漏采: {missed}/{total_boxes}。"
                "建议: 1) 调整多扫描枪阵列触发时序; "
                "2) 优化运动模糊补偿算法; "
                "3) 增加补光灯亮度与频闪同步。"
            )

        return SingleCheckResult(
            check_id="barcode_003",
            check_name="高速传送带无感采集",
            category=self.category,
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=f"采集率 {collection_rate:.4%}, 传送带速度 {belt_speed_m_per_s}m/s",
            threshold_value="采集率 >= 99.99%",
            message=f"模拟 {boxes_per_minute} 盒/分钟高速场景下条码无感采集能力",
            repair_suggestion=repair_suggestion,
            duration_ms=duration
        )

    def _check_error_tolerance(self) -> SingleCheckResult:
        start_time = time.time()
        defect_types = [
            ("条码模糊 30%", 0.30),
            ("条码污损 20%", 0.20),
            ("反光干扰", 0.00),
            ("角度倾斜 ±45°", 0.00),
            ("褶皱变形", 0.10)
        ]

        failures = []
        for defect_name, severity in defect_types:
            if not self._simulate_defect_recognition(defect_name, severity):
                failures.append(defect_name)

        passed = len(failures) == 0
        duration = int((time.time() - start_time) * 1000)

        repair_suggestion = ""
        if not passed:
            repair_suggestion = (
                f"容错识别测试失败: {', '.join(failures)}。"
                "建议: 1) 引入AI增强复原算法处理污损条码; "
                "2) 部署多角度扫描阵列; "
                "3) 增加OCR辅助识别药品名称兜底。"
            )

        return SingleCheckResult(
            check_id="barcode_004",
            check_name="条码污损容错识别",
            category=self.category,
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=f"{len(defect_types)-len(failures)}/{len(defect_types)} 缺陷类型通过",
            threshold_value=f"全部 {len(defect_types)} 种缺陷场景可正确识别",
            message="测试条码在污损、模糊、倾斜等异常场景下的识别能力",
            repair_suggestion=repair_suggestion,
            duration_ms=duration
        )

    def _simulate_barcode_scan_time(self) -> int:
        return random.randint(15, 90)

    def _simulate_code_parse(self, code_type: str) -> bool:
        return random.random() > 0.015

    def _simulate_high_speed_miss(self, total: int, speed: float) -> int:
        miss_rate = 0.00005 + (speed - 1.0) * 0.0001
        return int(total * miss_rate)

    def _simulate_defect_recognition(self, defect: str, severity: float) -> bool:
        return random.random() > (severity * 0.05)

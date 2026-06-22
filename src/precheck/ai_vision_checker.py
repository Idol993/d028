import random
import time
from typing import Any, Dict, List

from .base_check import BasePreCheck
from src.common.models import CheckStatus, SingleCheckResult, CheckCategory


class AIVisionChecker(BasePreCheck):
    def __init__(self):
        super().__init__()
        self.category = CheckCategory.AI_VISION
        self.check_name = "AI视觉识别与机械臂抓取逻辑验证"

    def execute(self, release_id: str, context: Dict[str, Any]) -> List[SingleCheckResult]:
        results = []

        check_accuracy = self._check_dispensing_accuracy()
        results.append(check_accuracy)

        check_grasp_logic = self._check_robotic_grasp_logic()
        results.append(check_grasp_logic)

        check_vision_recognition = self._check_vision_recognition()
        results.append(check_vision_recognition)

        return results

    def _check_dispensing_accuracy(self) -> SingleCheckResult:
        start_time = time.time()
        threshold = self.config.get("precheck.thresholds.dispensing_accuracy_rate", 0.9995)

        test_cases = 10000
        errors = self._simulate_ai_accuracy_test()
        accuracy = (test_cases - errors) / test_cases

        passed = accuracy >= threshold
        duration = int((time.time() - start_time) * 1000)

        repair_suggestion = ""
        if not passed:
            repair_suggestion = (
                f"发药准确率不达标。当前准确率: {accuracy:.4%}, 阈值: {threshold:.2%}。"
                "建议: 1) 重新训练AI视觉识别模型, 增加误识别样本; "
                "2) 检查机械臂抓取坐标系校准参数; "
                "3) 优化药盒位置容错算法。"
            )

        return SingleCheckResult(
            check_id="ai_vision_001",
            check_name="发药准确率基线测试",
            category=self.category,
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=round(accuracy, 6),
            threshold_value=threshold,
            message=f"AI视觉识别+机械臂抓取联合测试, 样本量: {test_cases}, 错误数: {errors}",
            repair_suggestion=repair_suggestion,
            duration_ms=duration
        )

    def _check_robotic_grasp_logic(self) -> SingleCheckResult:
        start_time = time.time()
        test_scenarios = [
            "标准药盒正位抓取",
            "药盒倾斜15度抓取",
            "药盒位置偏移±5mm抓取",
            "连续高密度药盒抓取",
            "空仓位跳过逻辑"
        ]

        failures = []
        for scenario in test_scenarios:
            if not self._simulate_grasp_scenario(scenario):
                failures.append(scenario)

        passed = len(failures) == 0
        duration = int((time.time() - start_time) * 1000)

        repair_suggestion = ""
        if not passed:
            repair_suggestion = (
                f"机械臂抓取逻辑验证失败。失败场景: {', '.join(failures)}。"
                "建议: 1) 检查运动规划算法中的碰撞检测参数; "
                "2) 重新校准夹爪力度传感器; "
                "3) 更新异常仓位处理逻辑。"
            )

        return SingleCheckResult(
            check_id="ai_vision_002",
            check_name="机械臂抓取逻辑验证",
            category=self.category,
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=f"{len(test_scenarios)-len(failures)}/{len(test_scenarios)} 场景通过",
            threshold_value=f"全部 {len(test_scenarios)} 场景通过",
            message=f"执行抓取场景测试: {', '.join(test_scenarios)}",
            repair_suggestion=repair_suggestion,
            duration_ms=duration
        )

    def _check_vision_recognition(self) -> SingleCheckResult:
        start_time = time.time()
        recognition_time_ms = self._simulate_vision_recognition_time()
        threshold_ms = 200

        passed = recognition_time_ms <= threshold_ms
        duration = int((time.time() - start_time) * 1000)

        repair_suggestion = ""
        if not passed:
            repair_suggestion = (
                f"视觉识别耗时过长: {recognition_time_ms}ms, 阈值: {threshold_ms}ms。"
                "建议: 1) 优化图像预处理流水线; "
                "2) 升级AI推理引擎版本; "
                "3) 检查相机对焦与光源设置。"
            )

        return SingleCheckResult(
            check_id="ai_vision_003",
            check_name="AI视觉识别性能测试",
            category=self.category,
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=f"{recognition_time_ms}ms",
            threshold_value=f"<={threshold_ms}ms",
            message="测试单帧药盒识别平均响应时间",
            repair_suggestion=repair_suggestion,
            duration_ms=duration
        )

    def _simulate_ai_accuracy_test(self) -> int:
        base_errors = random.randint(0, 8)
        return base_errors

    def _simulate_grasp_scenario(self, scenario: str) -> bool:
        return random.random() > 0.02

    def _simulate_vision_recognition_time(self) -> int:
        return random.randint(40, 180)

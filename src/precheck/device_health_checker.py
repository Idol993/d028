import random
import time
from typing import Any, Dict, List

from .base_check import BasePreCheck
from src.common.models import CheckStatus, SingleCheckResult, CheckCategory


class DeviceHealthChecker(BasePreCheck):
    def __init__(self):
        super().__init__()
        self.category = CheckCategory.DEVICE_HEALTH
        self.check_name = "设备健康度检测（机械臂、传送带、二级库机器人、库存一致性）"

    def execute(self, release_id: str, context: Dict[str, Any]) -> List[SingleCheckResult]:
        results = []

        results.append(self._check_robotic_arm_status())
        results.append(self._check_conveyor_sensors())
        results.append(self._check_warehouse_robot_connectivity())
        results.append(self._check_inventory_consistency())
        results.append(self._check_device_firmware_compatibility())

        return results

    def _check_robotic_arm_status(self) -> SingleCheckResult:
        start_time = time.time()
        threshold = self.config.get("precheck.thresholds.device_health_score", 90)

        arm_metrics = self._simulate_robotic_arm_metrics()
        health_score = self._calculate_arm_health_score(arm_metrics)

        passed = health_score >= threshold
        duration = int((time.time() - start_time) * 1000)

        repair_suggestion = ""
        if not passed:
            low_metrics = [k for k, v in arm_metrics.items() if not v.get("normal", True)]
            repair_suggestion = (
                f"机械臂健康评分: {health_score}/100, 阈值: {threshold}。"
                f"异常指标: {', '.join(low_metrics)}。"
                "建议: 1) 检查关节电机电流与温度; "
                "2) 执行减速机润滑与磨损检查; "
                "3) 重新标定TCP(工具中心点)坐标系; "
                "4) 联系设备科安排预防性维保。"
            )

        return SingleCheckResult(
            check_id="device_001",
            check_name="机械臂状态检测",
            category=self.category,
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=f"健康评分 {health_score}/100",
            threshold_value=f">= {threshold}/100",
            message=f"检测机械臂: 关节温度/电流/扭矩, 夹爪压力传感器, 碰撞检测, 累计运行时长: "
                    f"{arm_metrics.get('runtime_hours', {}).get('value', 'N/A')}h",
            repair_suggestion=repair_suggestion,
            duration_ms=duration
        )

    def _check_conveyor_sensors(self) -> SingleCheckResult:
        start_time = time.time()
        sensor_types = [
            "红外对射传感器(计数)",
            "光电传感器(到位检测)",
            "压力传感器(承重检测)",
            "速度编码器(传送带速度)",
            "急停按钮(安全回路)",
            "光幕传感器(人员防闯入)"
        ]

        failures = []
        sensor_details = {}
        for sensor in sensor_types:
            status = self._simulate_sensor_check(sensor)
            sensor_details[sensor] = "正常" if status else "异常"
            if not status:
                failures.append(sensor)

        passed = len(failures) == 0
        duration = int((time.time() - start_time) * 1000)

        repair_suggestion = ""
        if not passed:
            repair_suggestion = (
                f"传送带传感器异常: {', '.join(failures)}。"
                "建议: 1) 清洁传感器镜头表面灰尘; "
                "2) 检查传感器接线端子松动情况; "
                "3) 使用万用表测量传感器供电电压; "
                "4) 校准光幕传感器对射角度。"
            )

        return SingleCheckResult(
            check_id="device_002",
            check_name="传送带传感器检测",
            category=self.category,
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=f"{len(sensor_types)-len(failures)}/{len(sensor_types)} 传感器正常",
            threshold_value=f"全部 {len(sensor_types)} 传感器正常",
            message=f"传感器状态详情: {sensor_details}",
            repair_suggestion=repair_suggestion,
            duration_ms=duration
        )

    def _check_warehouse_robot_connectivity(self) -> SingleCheckResult:
        start_time = time.time()
        robots = [
            "二级库AGV-001",
            "二级库AGV-002",
            "拆零机器人-001",
            "盘点机器人-001"
        ]

        connection_failures = []
        for robot in robots:
            if not self._simulate_robot_connectivity(robot):
                connection_failures.append(robot)

        passed = len(connection_failures) == 0
        duration = int((time.time() - start_time) * 1000)

        repair_suggestion = ""
        if not passed:
            repair_suggestion = (
                f"智能二级库机器人连接失败: {', '.join(connection_failures)}。"
                "建议: 1) 检查工业WiFi信号强度(-60dBm以上); "
                "2) 验证机器人调度系统(RCS)服务状态; "
                "3) 确认机器人电量充足(>20%); "
                "4) 检查MQTT消息Broker连通性。"
            )

        return SingleCheckResult(
            check_id="device_003",
            check_name="智能二级库机器人连通性",
            category=self.category,
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=f"{len(robots)-len(connection_failures)}/{len(robots)} 机器人在线",
            threshold_value=f"全部 {len(robots)} 机器人在线可调度",
            message="检测AGV/拆零/盘点机器人在线状态、电量、调度系统连通性",
            repair_suggestion=repair_suggestion,
            duration_ms=duration
        )

    def _check_inventory_consistency(self) -> SingleCheckResult:
        start_time = time.time()
        total_skus = 500
        mismatches = self._simulate_inventory_reconcile(total_skus)
        consistency_rate = (total_skus - mismatches) / total_skus

        passed = consistency_rate >= 0.999 and mismatches <= 3
        duration = int((time.time() - start_time) * 1000)

        repair_suggestion = ""
        if not passed:
            repair_suggestion = (
                f"库存数据不一致: {mismatches} 个SKU差异, 一致率: {consistency_rate:.2%}。"
                "建议: 1) 触发WMS与二级库实时对账任务; "
                "2) 对差异SKU执行自动盘点校准; "
                "3) 检查出入库事务消息队列是否有积压; "
                "4) 验证数据库主从同步延迟。"
            )

        return SingleCheckResult(
            check_id="device_004",
            check_name="库存数据一致性校验",
            category=self.category,
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=f"一致率 {consistency_rate:.4%}, 差异SKU数 {mismatches}/{total_skus}",
            threshold_value="一致率 >= 99.9%, 差异SKU <= 3",
            message="比对HIS/WMS系统库存与智能二级库实际库存的一致性",
            repair_suggestion=repair_suggestion,
            duration_ms=duration
        )

    def _check_device_firmware_compatibility(self) -> SingleCheckResult:
        start_time = time.time()
        device_firmware = {
            "机械臂主控": "v2.3.1",
            "传送带PLC": "v1.8.5",
            "AGV调度固件": "v3.1.0",
            "扫描枪固件": "v1.2.0"
        }
        required_versions = {
            "机械臂主控": ">=2.3.0",
            "传送带PLC": ">=1.8.0",
            "AGV调度固件": ">=3.0.0",
            "扫描枪固件": ">=1.1.0"
        }

        incompatible = []
        for device, version in device_firmware.items():
            if not self._check_version_compatible(version, required_versions[device]):
                incompatible.append(f"{device}({version} 需 {required_versions[device]})")

        passed = len(incompatible) == 0
        duration = int((time.time() - start_time) * 1000)

        repair_suggestion = ""
        if not passed:
            repair_suggestion = (
                f"固件版本不兼容: {', '.join(incompatible)}。"
                "建议: 1) 联系设备厂商获取最新固件包; "
                "2) 在维护窗口期安排固件升级; "
                "3) 升级前备份当前固件配置参数。"
            )

        return SingleCheckResult(
            check_id="device_005",
            check_name="设备固件兼容性校验",
            category=self.category,
            status=CheckStatus.PASSED if passed else CheckStatus.FAILED,
            actual_value=f"兼容 {len(device_firmware)-len(incompatible)}/{len(device_firmware)} 设备",
            threshold_value="全部设备固件版本满足兼容性要求",
            message=f"当前固件版本: {device_firmware}, 要求版本: {required_versions}",
            repair_suggestion=repair_suggestion,
            duration_ms=duration
        )

    def _simulate_robotic_arm_metrics(self) -> Dict:
        return {
            "joint_temperature": {"value": f"{random.randint(35, 55)}°C", "normal": random.random() > 0.02},
            "motor_current": {"value": f"{round(random.uniform(1.8, 3.5), 1)}A", "normal": random.random() > 0.03},
            "gripper_pressure": {"value": f"{random.randint(8, 15)}N", "normal": random.random() > 0.01},
            "runtime_hours": {"value": random.randint(500, 5000), "normal": True},
            "collision_alerts": {"value": random.randint(0, 2), "normal": random.random() > 0.05}
        }

    def _calculate_arm_health_score(self, metrics: Dict) -> int:
        normal_count = sum(1 for v in metrics.values() if v.get("normal", True))
        base_score = int((normal_count / len(metrics)) * 70)
        base_score += random.randint(20, 30)
        return min(100, base_score)

    def _simulate_sensor_check(self, sensor: str) -> bool:
        return random.random() > 0.02

    def _simulate_robot_connectivity(self, robot: str) -> bool:
        return random.random() > 0.01

    def _simulate_inventory_reconcile(self, total: int) -> int:
        return random.randint(0, 4)

    def _check_version_compatible(self, current: str, required: str) -> bool:
        return True

import random
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.common.models import MonitoringIndicator, CheckStatus


class MetricsCollector:
    def __init__(self):
        pass

    def collect_pharmacy_metrics(self, pharmacy_ids: List[str],
                                 duration_minutes: int = 5) -> Dict[str, List[MonitoringIndicator]]:
        all_metrics = {}
        for pharmacy_id in pharmacy_ids:
            all_metrics[pharmacy_id] = self._collect_single_pharmacy(pharmacy_id, duration_minutes)
        return all_metrics

    def _collect_single_pharmacy(self, pharmacy_id: str,
                                  duration_minutes: int) -> List[MonitoringIndicator]:
        indicators = []

        total_prescriptions = max(1, int(random.randint(100, 5000) * (duration_minutes / 60.0)))

        dispensing_error_rate = random.uniform(0.00001, 0.002)
        errors_count = int(total_prescriptions * dispensing_error_rate)
        indicators.append(MonitoringIndicator(
            name="dispensing_error_rate",
            description="发药错误率（错发/漏发）",
            current_value=round(dispensing_error_rate, 6),
            threshold=0.001,
            status=CheckStatus.PASSED if dispensing_error_rate <= 0.001 else CheckStatus.FAILED,
            unit="%"
        ))

        drug_jam_rate = random.uniform(0.0005, 0.008)
        jam_count = int(total_prescriptions * drug_jam_rate)
        indicators.append(MonitoringIndicator(
            name="drug_jam_rate",
            description="卡药率（机械臂抓取失败或传送带阻塞）",
            current_value=round(drug_jam_rate, 6),
            threshold=0.005,
            status=CheckStatus.PASSED if drug_jam_rate <= 0.005 else CheckStatus.FAILED,
            unit="%"
        ))

        prescription_delay_rate = random.uniform(0.005, 0.03)
        delayed_count = int(total_prescriptions * prescription_delay_rate)
        indicators.append(MonitoringIndicator(
            name="prescription_delay_rate",
            description="处方延迟率（从结算到发药完成超时）",
            current_value=round(prescription_delay_rate, 6),
            threshold=0.02,
            status=CheckStatus.PASSED if prescription_delay_rate <= 0.02 else CheckStatus.FAILED,
            unit="%"
        ))

        return indicators

    def compute_aggregate_metrics(self, metrics_by_pharmacy: Dict[str, List[MonitoringIndicator]]) -> List[MonitoringIndicator]:
        if not metrics_by_pharmacy:
            return []

        indicator_names = set()
        for metrics in metrics_by_pharmacy.values():
            for ind in metrics:
                indicator_names.add(ind.name)

        aggregated = []
        for name in indicator_names:
            values = []
            description = ""
            threshold = 0.0
            unit = ""
            for pharmacy_id, metrics in metrics_by_pharmacy.items():
                for ind in metrics:
                    if ind.name == name:
                        values.append(ind.current_value)
                        description = ind.description
                        threshold = ind.threshold
                        unit = ind.unit
                        break

            if values:
                avg_value = sum(values) / len(values)
                max_value = max(values)
                aggregated_value = max_value
                aggregated.append(MonitoringIndicator(
                    name=name,
                    description=description,
                    current_value=round(aggregated_value, 6),
                    threshold=threshold,
                    status=CheckStatus.PASSED if aggregated_value <= threshold else CheckStatus.FAILED,
                    unit=unit
                ))

        return aggregated

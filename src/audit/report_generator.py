import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from src.common.config_loader import ConfigLoader
from src.common.audit_logger import AuditLogger
from src.common.data_store import DataStore
from src.common.notification_manager import NotificationManager


class ReportGenerator:
    def __init__(self):
        self.config = ConfigLoader()
        self.logger = AuditLogger()
        self.datastore = DataStore()
        self.notification = NotificationManager()

        report_path = self.config.get("storage.report_path", "./data/reports")
        self.report_dir = Path(report_path)
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def generate_weekly_report(self, week_offset: int = 0,
                                formats: Optional[List[str]] = None) -> Dict[str, Any]:
        today = datetime.now()
        current_weekday = today.weekday()

        week_end = today - timedelta(days=current_weekday + 1 + (week_offset * 7))
        week_start = week_end - timedelta(days=6)

        week_start_str = week_start.strftime("%Y-%m-%d")
        week_end_str = week_end.strftime("%Y-%m-%d")

        self.logger.info(f"Generating weekly report for {week_start_str} to {week_end_str}")

        report_data = self._collect_weekly_data(week_start, week_end)
        report_data["week_start"] = week_start_str
        report_data["week_end"] = week_end_str

        if formats is None:
            formats = self.config.get("audit.report.formats", ["pdf", "excel"])

        output_files = {}

        if "excel" in formats:
            excel_path = self._generate_excel_report(report_data)
            output_files["excel"] = excel_path

        if "pdf" in formats:
            charts = self._generate_charts(report_data)
            pdf_path = self._generate_pdf_report(report_data, charts)
            output_files["pdf"] = pdf_path

        self.logger.audit(
            "weekly_report_generated",
            "system",
            f"report:weekly_{week_start_str}_{week_end_str}",
            "success",
            {"formats": formats, "files": output_files}
        )

        self._notify_weekly_report_ready(report_data, output_files)

        return {
            "report_data": report_data,
            "files": output_files
        }

    def _collect_weekly_data(self, week_start: datetime, week_end: datetime) -> Dict[str, Any]:
        release_records = self.datastore.list_release_records()

        weekly_releases = []
        for record in release_records:
            created_str = record.get("created_at") or record.get("saved_at", "")
            try:
                created_at = datetime.fromisoformat(created_str.replace('Z', ''))
                if week_start <= created_at <= week_end:
                    weekly_releases.append(record)
            except (ValueError, TypeError):
                continue

        total_releases = len(weekly_releases)
        successful_releases = sum(
            1 for r in weekly_releases
            if r.get("canary", {}).get("phase") == "completed"
        )
        rollback_count = sum(
            1 for r in weekly_releases
            if r.get("canary", {}).get("rollback_triggered", False)
        )

        avg_approval_hours = 0.0
        approval_durations = []
        for r in weekly_releases:
            approval = r.get("approval", {})
            created_at = approval.get("created_at")
            completed_at = approval.get("completed_at")
            if created_at and completed_at:
                try:
                    start = datetime.fromisoformat(created_at.replace('Z', ''))
                    end = datetime.fromisoformat(completed_at.replace('Z', ''))
                    duration_hours = (end - start).total_seconds() / 3600
                    if duration_hours > 0:
                        approval_durations.append(duration_hours)
                except (ValueError, TypeError):
                    continue
        if approval_durations:
            avg_approval_hours = round(sum(approval_durations) / len(approval_durations), 2)

        by_channel = {"regular": {"total": 0, "success": 0, "rollback": 0},
                      "hotfix": {"total": 0, "success": 0, "rollback": 0}}
        by_pharmacy = {}

        for r in weekly_releases:
            channel = r.get("approval", {}).get("channel", "regular")
            if channel not in by_channel:
                by_channel[channel] = {"total": 0, "success": 0, "rollback": 0}
            by_channel[channel]["total"] += 1

            canary = r.get("canary", {})
            if canary.get("phase") == "completed":
                by_channel[channel]["success"] += 1
            if canary.get("rollback_triggered"):
                by_channel[channel]["rollback"] += 1

            for pharmacy in canary.get("target_pharmacies", []):
                if pharmacy not in by_pharmacy:
                    by_pharmacy[pharmacy] = {"total": 0, "success": 0, "rollback": 0}
                by_pharmacy[pharmacy]["total"] += 1
                if canary.get("phase") == "completed":
                    by_pharmacy[pharmacy]["success"] += 1
                if canary.get("rollback_triggered"):
                    by_pharmacy[pharmacy]["rollback"] += 1

        success_rate = (successful_releases / total_releases * 100) if total_releases > 0 else 0.0

        return {
            "total_releases": total_releases,
            "successful_releases": successful_releases,
            "rollback_count": rollback_count,
            "avg_approval_hours": avg_approval_hours,
            "release_success_rate": round(success_rate, 2),
            "by_channel": by_channel,
            "by_pharmacy": by_pharmacy,
            "releases_detail": weekly_releases
        }

    def _generate_excel_report(self, report_data: Dict[str, Any]) -> str:
        filename = f"weekly_report_{report_data['week_start']}_{report_data['week_end']}.xlsx"
        filepath = self.report_dir / filename

        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            summary_df = pd.DataFrame([{
                "统计周期": f"{report_data['week_start']} 至 {report_data['week_end']}",
                "发布总次数": report_data["total_releases"],
                "发布成功次数": report_data["successful_releases"],
                "回滚次数": report_data["rollback_count"],
                "发布成功率(%)": report_data["release_success_rate"],
                "平均审批时长(小时)": report_data["avg_approval_hours"]
            }])
            summary_df.to_excel(writer, sheet_name="总览", index=False)

            channel_data = []
            for channel, stats in report_data["by_channel"].items():
                channel_data.append({
                    "发布通道": "常规迭代" if channel == "regular" else ("紧急热修复" if channel == "hotfix" else channel),
                    "发布次数": stats["total"],
                    "成功次数": stats["success"],
                    "回滚次数": stats["rollback"],
                    "成功率(%)": round(stats["success"] / stats["total"] * 100, 2) if stats["total"] > 0 else 0
                })
            if channel_data:
                pd.DataFrame(channel_data).to_excel(writer, sheet_name="按通道统计", index=False)

            pharmacy_data = []
            for pharmacy, stats in report_data["by_pharmacy"].items():
                pharmacy_data.append({
                    "药房ID": pharmacy,
                    "发布次数": stats["total"],
                    "成功次数": stats["success"],
                    "回滚次数": stats["rollback"],
                    "成功率(%)": round(stats["success"] / stats["total"] * 100, 2) if stats["total"] > 0 else 0
                })
            if pharmacy_data:
                pd.DataFrame(pharmacy_data).to_excel(writer, sheet_name="按药房统计", index=False)

            detail_data = []
            for release in report_data.get("releases_detail", []):
                approval = release.get("approval", {})
                canary = release.get("canary", {})
                detail_data.append({
                    "发布ID": release.get("release_id", ""),
                    "版本号": release.get("version", ""),
                    "发布通道": approval.get("channel", ""),
                    "审批状态": approval.get("overall_status", ""),
                    "发布状态": canary.get("phase", ""),
                    "是否回滚": "是" if canary.get("rollback_triggered") else "否",
                    "触发熔断原因": canary.get("circuit_break_reason", "")
                })
            if detail_data:
                pd.DataFrame(detail_data).to_excel(writer, sheet_name="发布明细", index=False)

        return str(filepath)

    def _generate_charts(self, report_data: Dict[str, Any]) -> Dict[str, str]:
        charts = {}
        plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False

        fig, ax = plt.subplots(figsize=(8, 5))
        categories = ['发布成功', '发布回滚']
        values = [report_data['successful_releases'], report_data['rollback_count']]
        colors = ['#22c55e', '#ef4444']
        bars = ax.bar(categories, values, color=colors)
        ax.set_title(f'发布结果统计 ({report_data["week_start"]} ~ {report_data["week_end"]})')
        ax.set_ylabel('次数')
        for bar, value in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2., bar.get_height(),
                    str(value), ha='center', va='bottom')
        chart_path = self.report_dir / f"chart_summary_{report_data['week_start']}_{report_data['week_end']}.png"
        plt.tight_layout()
        plt.savefig(chart_path, dpi=150)
        plt.close()
        charts["summary"] = str(chart_path)

        return charts

    def _generate_pdf_report(self, report_data: Dict[str, Any], charts: Dict[str, str]) -> str:
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
            from reportlab.lib import colors

            filename = f"weekly_report_{report_data['week_start']}_{report_data['week_end']}.pdf"
            filepath = self.report_dir / filename

            doc = SimpleDocTemplate(str(filepath), pagesize=A4)
            styles = getSampleStyleSheet()
            story = []

            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Title'],
                fontSize=20,
                spaceAfter=20
            )
            story.append(Paragraph("智慧药房自动化发药系统", title_style))
            story.append(Paragraph("版本发布与智能回滚周报", title_style))
            story.append(Paragraph(
                f"统计周期: {report_data['week_start']} 至 {report_data['week_end']}",
                styles['Normal']
            ))
            story.append(Spacer(1, 0.3 * inch))

            h2_style = ParagraphStyle('H2', parent=styles['Heading2'], fontSize=14)
            story.append(Paragraph("一、总体概况", h2_style))

            summary_data = [
                ['指标', '数值'],
                ['发布总次数', str(report_data['total_releases'])],
                ['发布成功次数', str(report_data['successful_releases'])],
                ['回滚次数', str(report_data['rollback_count'])],
                ['发布成功率', f"{report_data['release_success_rate']}%"],
                ['平均审批时长', f"{report_data['avg_approval_hours']} 小时"]
            ]
            summary_table = Table(summary_data, colWidths=[2.5 * inch, 2 * inch])
            summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4f46e5')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f5f3ff')),
                ('GRID', (0, 0), (-1, -1), 1, colors.gray)
            ]))
            story.append(summary_table)
            story.append(Spacer(1, 0.3 * inch))

            if "summary" in charts and os.path.exists(charts["summary"]):
                story.append(Paragraph("二、发布结果可视化", h2_style))
                img = Image(charts["summary"], width=5 * inch, height=3 * inch)
                story.append(img)
                story.append(Spacer(1, 0.3 * inch))

            story.append(Paragraph("三、按发布通道统计", h2_style))
            channel_data = [['通道', '总次数', '成功', '回滚', '成功率']]
            for channel, stats in report_data["by_channel"].items():
                channel_name = "常规迭代" if channel == "regular" else ("紧急热修复" if channel == "hotfix" else channel)
                rate = round(stats["success"] / stats["total"] * 100, 2) if stats["total"] > 0 else 0
                channel_data.append([channel_name, str(stats["total"]), str(stats["success"]),
                                     str(stats["rollback"]), f"{rate}%"])
            if len(channel_data) > 1:
                channel_table = Table(channel_data, colWidths=[1.5 * inch, 0.8 * inch, 0.8 * inch, 0.8 * inch, 1 * inch])
                channel_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#059669')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('GRID', (0, 0), (-1, -1), 1, colors.gray)
                ]))
                story.append(channel_table)

            doc.build(story)
            return str(filepath)

        except ImportError:
            self.logger.warning("reportlab not available, skipping PDF generation")
            return ""

    def query_release_history(self, start_time: Optional[str] = None,
                               end_time: Optional[str] = None,
                               pharmacy: Optional[str] = None,
                               version: Optional[str] = None,
                               status: Optional[str] = None) -> List[Dict[str, Any]]:
        filters = {}
        if version:
            filters["version"] = version

        records = self.datastore.list_release_records(filters if filters else None)

        filtered = []
        for record in records:
            if start_time:
                saved_at = record.get("saved_at", "")
                if saved_at and saved_at < start_time:
                    continue
            if end_time:
                saved_at = record.get("saved_at", "")
                if saved_at and saved_at > end_time:
                    continue
            if pharmacy:
                target_pharmacies = record.get("canary", {}).get("target_pharmacies", [])
                if pharmacy not in target_pharmacies:
                    continue
            if status:
                canary_phase = record.get("canary", {}).get("phase", "")
                approval_status = record.get("approval", {}).get("overall_status", "")
                if status not in [canary_phase, approval_status]:
                    continue
            filtered.append(record)

        return filtered

    def export_release_records(self, records: List[Dict[str, Any]],
                                format: str = "excel") -> str:
        filename = f"release_export_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        filepath = self.report_dir / filename

        export_data = []
        for record in records:
            precheck = record.get("precheck", {})
            approval = record.get("approval", {})
            canary = record.get("canary", {})
            export_data.append({
                "发布ID": record.get("release_id", ""),
                "版本号": record.get("version", ""),
                "创建时间": record.get("saved_at", ""),
                "前置校验状态": precheck.get("overall_status", ""),
                "前置校验通过率": f"{precheck.get('passed_checks', 0)}/{precheck.get('total_checks', 0)}",
                "审批通道": approval.get("channel", ""),
                "审批状态": approval.get("overall_status", ""),
                "审批节点数": len(approval.get("nodes", [])),
                "灰度发布阶段": canary.get("phase", ""),
                "是否触发熔断": "是" if canary.get("circuit_break_triggered") else "否",
                "熔断原因": canary.get("circuit_break_reason", ""),
                "是否回滚": "是" if canary.get("rollback_triggered") else "否",
                "涉及药房": ", ".join(canary.get("target_pharmacies", []))
            })

        if format == "excel":
            filepath = filepath.with_suffix(".xlsx")
            pd.DataFrame(export_data).to_excel(filepath, index=False, engine='openpyxl')
        else:
            filepath = filepath.with_suffix(".csv")
            pd.DataFrame(export_data).to_csv(filepath, index=False, encoding="utf-8-sig")

        return str(filepath)

    def _notify_weekly_report_ready(self, report_data: Dict[str, Any], files: Dict[str, str]):
        title = f"【周报】药房发药系统发布周报 {report_data['week_start']} ~ {report_data['week_end']}"
        content = (
            f"## 本周发布概况\n\n"
            f"| 指标 | 数值 |\n"
            f"|------|------|\n"
            f"| 发布总次数 | {report_data['total_releases']} |\n"
            f"| 发布成功次数 | {report_data['successful_releases']} |\n"
            f"| 回滚次数 | {report_data['rollback_count']} |\n"
            f"| 发布成功率 | {report_data['release_success_rate']}% |\n"
            f"| 平均审批时长 | {report_data['avg_approval_hours']} 小时 |\n\n"
            f"详细报表已生成，请查看附件或指定目录。"
        )

        attachments = [f for f in files.values() if f]
        self.notification.send_notification(title, content, attachments=attachments)

#!/usr/bin/env python3
import argparse
import json
import sys
import os
from datetime import datetime
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"

sys.path.insert(0, str(Path(__file__).parent))

from src.pipeline import ReleasePipeline


def cmd_submit(args):
    pipeline = ReleasePipeline()
    result = pipeline.submit_release(
        version=args.version,
        channel=args.channel,
        hotfix_reason=args.hotfix_reason or "",
        operator=args.operator
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def cmd_approve(args):
    pipeline = ReleasePipeline()
    result = pipeline.approve_release(
        release_id=args.release_id,
        node_id=args.node_id,
        approver=args.approver,
        comments=args.comments or ""
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def cmd_reject(args):
    pipeline = ReleasePipeline()
    result = pipeline.reject_release(
        release_id=args.release_id,
        node_id=args.node_id,
        approver=args.approver,
        reject_reason=args.reason
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def cmd_rollback(args):
    pipeline = ReleasePipeline()
    result = pipeline.manual_rollback(
        release_id=args.release_id,
        reason=args.reason,
        operator=args.operator
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def cmd_status(args):
    pipeline = ReleasePipeline()
    result = pipeline.get_release_status(args.release_id)
    if result is None:
        print(f"Error: Release {args.release_id} not found")
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def cmd_list(args):
    pipeline = ReleasePipeline()
    filters = {}
    if args.status:
        filters["status"] = args.status
    records = pipeline.list_releases(filters if filters else None)
    print(json.dumps(records, ensure_ascii=False, indent=2, default=str))


def cmd_drill(args):
    pipeline = ReleasePipeline()
    result = pipeline.execute_rollback_drill(
        drill_name=args.name,
        operator=args.operator
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def cmd_report(args):
    pipeline = ReleasePipeline()
    result = pipeline.generate_weekly_report()
    print(json.dumps({
        "week_start": result["report_data"]["week_start"],
        "week_end": result["report_data"]["week_end"],
        "total_releases": result["report_data"]["total_releases"],
        "successful_releases": result["report_data"]["successful_releases"],
        "rollback_count": result["report_data"]["rollback_count"],
        "success_rate": result["report_data"]["release_success_rate"],
        "generated_files": result["files"]
    }, ensure_ascii=False, indent=2))


def cmd_query(args):
    from src.audit.report_generator import ReportGenerator
    report = ReportGenerator()
    records = report.query_release_history(
        start_time=args.start,
        end_time=args.end,
        pharmacy=args.pharmacy,
        version=args.version,
        status=args.status
    )
    if args.export:
        filepath = report.export_release_records(records, format=args.export_format)
        print(f"Exported {len(records)} records to: {filepath}")
    else:
        print(json.dumps(records, ensure_ascii=False, indent=2, default=str))


def cmd_run_all(args):
    demo_mode = getattr(args, "demo_mode", None)
    pipeline = ReleasePipeline(demo_mode=demo_mode)

    print("=" * 60)
    print("智慧药房自动化发药系统 - 版本发布与智能回滚演示")
    if demo_mode:
        mode_desc = {
            "precheck-fail": "模式: 前置校验阻断 (确定性)",
            "precheck-pass": "模式: 前置校验通过 (后续灰度结果随机)",
            "canary-break": "模式: 灰度熔断回滚 (确定性)",
            "canary-success": "模式: 灰度完成发布 (确定性)"
        }[demo_mode]
        print(f"[{mode_desc}]")
    print("=" * 60)
    print()

    version = args.version or f"v{datetime.now().strftime('%Y.%m.%d')}.1"
    channel = args.channel or "regular"
    operator = "demo_user"

    phase_precheck_executed = False
    phase_precheck_passed = False
    phase_approval_executed = False
    phase_approval_completed = False
    phase_approval_interrupted = False
    phase_canary_executed = False
    phase_canary_rolled_back = False
    phase_canary_completed = False

    final_outcome = None
    release_id = None
    last_result = None
    canary_report_data = {}

    print("[1/4] 提交发布申请 + 前置校验 (16项质量门禁)")
    submit_result = pipeline.submit_release(
        version=version,
        channel=channel,
        operator=operator
    )
    release_id = submit_result["release_id"]
    phase_precheck_executed = True
    last_result = submit_result

    print(f"  发布ID: {release_id}")
    print(f"  管线状态: {submit_result['pipeline_status']}")
    precheck_summary = submit_result.get("precheck", {})
    if precheck_summary:
        passed = precheck_summary.get("passed_checks", 0)
        total = precheck_summary.get("total_checks", 0)
        failed = precheck_summary.get("failed_checks", 0)
        print(f"  前置校验: {precheck_summary.get('overall_status', 'N/A')} ({passed}/{total}通过, {failed}失败)")
    print()

    if submit_result["pipeline_status"] == "blocked_by_precheck":
        print("  [BLOCK] 发布被前置校验阻断，检测到以下需修复项:")
        repairs = precheck_summary.get("repair_actions", [])
        if repairs:
            for i, action in enumerate(repairs, 1):
                print(f"    [{i}] {action[:80]}..." if len(action) > 80 else f"    [{i}] {action}")
        print()
        print("  复查命令:")
        print(f"    python main.py status --release-id {release_id}")
        print("    python main.py submit --version v2.x.x-fixed --channel regular")
        print()

        print("=" * 60)
        print("【演示结果汇总】")
        print(f"  发布ID: {release_id}")
        print("  结局: 前置校验阻断")
        print("  阻断原因: 核心质量指标未通过门禁")
        print("  系统行为: 正确阻断不合格版本进入生产环境")
        print("=" * 60)
        return

    phase_precheck_passed = True
    approval = submit_result.get("approval", {})

    print("[2/4] 三级审批流程 (严格串行: 药房 -> 信息科 -> 设备科)")
    phase_approval_executed = True
    approve_result = submit_result
    nodes = approval.get("nodes", []) if isinstance(approval, dict) else []
    approval_broke = False
    for idx, node in enumerate(nodes):
        approver = node.get("approvers", ["demo_approver"])[0]
        node_id = node.get("node_id")
        dept = node.get("department", "")
        dept_name = {
            "pharmacy": "药房",
            "it_department": "信息科",
            "equipment_department": "设备科"
        }.get(dept, dept)

        print(f"  [{idx + 1}/3] {dept_name} 审批中... (审批人: {approver})")
        approve_result = pipeline.approve_release(
            release_id=release_id,
            node_id=node_id,
            approver=approver,
            comments=f"{dept_name}评估通过"
        )
        status = approve_result.get("pipeline_status")
        if status == "approval_sequence_violation":
            print(f"    [VIOLATION] 审批顺序违规，拦截成功: {approve_result.get('error')}")
            approval_broke = True
            break
        print(f"    [PASS] 通过，管线状态: {status}")
        last_result = approve_result

    if approval_broke:
        phase_approval_interrupted = True
        final_outcome = "approval_interrupted"
        print()
        print("=" * 60)
        print("【演示结果汇总】")
        print(f"  发布ID: {release_id}")
        print("  结局: 审批中断 (审批顺序违规被系统拦截)")
        print("  系统行为: 正确执行串行审批保护机制")
        print()
        print("  实际执行的环节:")
        print("   [PRECHECK] 发布前置校验 (已通过)")
        print("   [APPROVAL] 三级串行审批 (被顺序校验拦截)")
        print("=" * 60)
        return

    phase_approval_completed = True
    print()

    print("[3/4] 灰度发布与自动熔断监控 (三阶段放量 + 阈值监控)")
    phase_canary_executed = True
    final_status = approve_result.get("pipeline_status", "unknown")
    canary = approve_result.get("canary")
    if canary:
        print(f"  灰度最终状态: {final_status}")
        print(f"  熔断触发: {canary.get('circuit_break_triggered', False)}")
        if canary.get("circuit_break_reason"):
            print(f"  熔断原因: {canary['circuit_break_reason']}")
        print(f"  自动回滚: {canary.get('rollback_triggered', False)}")
        print(f"  目标药房(全部5家): {', '.join(canary.get('target_pharmacies', []))}")

        report = canary.get("safety_impact_report") or {}
        affected = report.get("affected_pharmacies", [])
        risk = report.get("patient_safety_assessment", {}).get("risk_level", "UNKNOWN")
        print(f"  受影响药房(保留快照): {', '.join(affected) if affected else '无'}")
        print(f"  风险等级: {risk}")
        canary_report_data = {
            "affected": affected,
            "risk_level": risk,
            "report": report
        }

        if final_status in ["rolled_back", "manually_rolled_back"]:
            phase_canary_rolled_back = True
            final_outcome = "canary_rollback"
            print()
            print("  [CIRCUIT_BREAK] 熔断机制正常工作：检测指标超限 -> 自动暂停 -> 版本回滚 -> 生成安全报告 -> 通知干系人")
        elif final_status == "completed":
            phase_canary_completed = True
            final_outcome = "canary_completed"
            print()
            print("  [SUCCESS] 三阶段灰度发布全部成功，无熔断触发")
    else:
        print(f"  灰度未启动，当前状态: {final_status}")
    print()

    print("=" * 60)
    print("【演示结果汇总】")
    print(f"  发布ID: {release_id}")

    if final_outcome == "canary_rollback":
        print("  结局: 灰度熔断回滚 (全流程走通，熔断保护生效)")
        print("  熔断保护: 正确触发并自动回滚")
        print("  安全报告: 已保留受影响药房与风险等级")
        print(f"  受影响药房: {', '.join(canary_report_data.get('affected', []))}")
        print(f"  风险等级: {canary_report_data.get('risk_level', 'UNKNOWN')}")
    elif final_outcome == "canary_completed":
        print("  结局: 灰度完成发布 (全流程全部成功)")
        print("  系统行为: 三阶段放量完成，正式发布到所有目标药房")
    print()
    print("  实际执行的环节:")
    if phase_precheck_executed and phase_precheck_passed:
        print("   [PRECHECK] 发布前置校验 (已通过)")
    if phase_approval_executed and phase_approval_completed:
        print("   [APPROVAL] 三级串行审批 (已全部通过)")
    if phase_canary_executed:
        if phase_canary_rolled_back:
            print("   [CANARY] 三阶段药房灰度发布 + 指标监控 + 自动熔断回滚")
            print("   [SAFETY_REPORT] 患者用药安全影响报告（含受影响药房、风险等级）")
        elif phase_canary_completed:
            print("   [CANARY] 三阶段药房灰度发布 + 指标监控（全量发布成功）")
    print()
    print("  复查命令:")
    print(f"    python main.py status --release-id {release_id}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="智慧药房自动化发药系统 - 版本发布与智能回滚自动化平台",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 提交新发布申请
  python main.py submit --version v2.5.0 --channel regular

  # 审批发布
  python main.py approve --release-id REL-xxx --node-id NODE-xxx --approver pharmacy_director

  # 驳回发布
  python main.py reject --release-id REL-xxx --node-id NODE-xxx --approver pharmacy_director --reason "接口测试不通过"

  # 查看发布状态
  python main.py status --release-id REL-xxx

  # 列出所有发布
  python main.py list

  # 手动触发回滚
  python main.py rollback --release-id REL-xxx --reason "发现严重bug"

  # 执行回滚演练
  python main.py drill --name "每月例行演练"

  # 生成周报
  python main.py report

  # 一键运行完整演示
  python main.py run-all
  python main.py run-all --demo-mode precheck-fail
  python main.py run-all --demo-mode precheck-pass
  python main.py run-all --demo-mode canary-break
  python main.py run-all --demo-mode canary-success
        """
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    submit_parser = subparsers.add_parser("submit", help="提交新发布申请")
    submit_parser.add_argument("--version", required=True, help="发布版本号")
    submit_parser.add_argument("--channel", choices=["regular", "hotfix"], default="regular", help="发布通道")
    submit_parser.add_argument("--hotfix-reason", help="紧急热修复原因 (hotfix通道必填)")
    submit_parser.add_argument("--operator", default="system", help="操作人")

    approve_parser = subparsers.add_parser("approve", help="审批发布")
    approve_parser.add_argument("--release-id", required=True, help="发布ID")
    approve_parser.add_argument("--node-id", required=True, help="审批节点ID")
    approve_parser.add_argument("--approver", required=True, help="审批人")
    approve_parser.add_argument("--comments", help="审批意见")

    reject_parser = subparsers.add_parser("reject", help="驳回发布")
    reject_parser.add_argument("--release-id", required=True, help="发布ID")
    reject_parser.add_argument("--node-id", required=True, help="审批节点ID")
    reject_parser.add_argument("--approver", required=True, help="审批人")
    reject_parser.add_argument("--reason", required=True, help="驳回原因")

    rollback_parser = subparsers.add_parser("rollback", help="手动触发回滚")
    rollback_parser.add_argument("--release-id", required=True, help="发布ID")
    rollback_parser.add_argument("--reason", required=True, help="回滚原因")
    rollback_parser.add_argument("--operator", default="system", help="操作人")

    status_parser = subparsers.add_parser("status", help="查看发布状态")
    status_parser.add_argument("--release-id", required=True, help="发布ID")

    list_parser = subparsers.add_parser("list", help="列出所有发布记录")
    list_parser.add_argument("--status", help="按状态过滤")

    drill_parser = subparsers.add_parser("drill", help="执行回滚演练")
    drill_parser.add_argument("--name", help="演练名称")
    drill_parser.add_argument("--operator", default="system", help="操作人")

    report_parser = subparsers.add_parser("report", help="生成运营周报")

    query_parser = subparsers.add_parser("query", help="查询历史发布与审计记录")
    query_parser.add_argument("--start", help="开始时间 (ISO格式)")
    query_parser.add_argument("--end", help="结束时间 (ISO格式)")
    query_parser.add_argument("--pharmacy", help="药房ID")
    query_parser.add_argument("--version", help="版本号")
    query_parser.add_argument("--status", help="发布状态")
    query_parser.add_argument("--export", action="store_true", help="导出为文件")
    query_parser.add_argument("--export-format", choices=["excel", "csv"], default="excel", help="导出格式")

    runall_parser = subparsers.add_parser("run-all", help="一键运行完整发布与回滚演示")
    runall_parser.add_argument("--version", help="版本号 (默认自动生成)")
    runall_parser.add_argument("--channel", choices=["regular", "hotfix"], help="发布通道")
    runall_parser.add_argument("--demo-mode", 
        choices=["precheck-fail", "precheck-pass", "canary-break", "canary-success"],
        help="指定演示模式，控制各环节的确定性结果：precheck-fail(前置校验必败) / precheck-pass(前置校验必过) / canary-break(灰度必熔断) / canary-success(灰度必成功)")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    cmd_map = {
        "submit": cmd_submit,
        "approve": cmd_approve,
        "reject": cmd_reject,
        "rollback": cmd_rollback,
        "status": cmd_status,
        "list": cmd_list,
        "drill": cmd_drill,
        "report": cmd_report,
        "query": cmd_query,
        "run-all": cmd_run_all
    }

    handler = cmd_map.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

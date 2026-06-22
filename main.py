#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

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
    pipeline = ReleasePipeline()

    print("=" * 60)
    print("智慧药房自动化发药系统 - 版本发布与智能回滚演示")
    print("=" * 60)
    print()

    version = args.version or f"v{datetime.now().strftime('%Y.%m.%d')}.1"
    channel = args.channel or "regular"
    operator = "demo_user"

    print(f"[1/5] 提交发布申请: 版本={version}, 通道={channel}")
    submit_result = pipeline.submit_release(
        version=version,
        channel=channel,
        operator=operator
    )
    release_id = submit_result["release_id"]
    print(f"  发布ID: {release_id}")
    print(f"  管线状态: {submit_result['pipeline_status']}")
    print(f"  前置校验: {submit_result['precheck']['overall_status'] if submit_result.get('precheck') else 'N/A'}")
    print()

    if submit_result["pipeline_status"] == "blocked_by_precheck":
        print("  发布被前置校验阻断，检测到以下需修复项:")
        if submit_result.get("precheck", {}).get("repair_actions"):
            for i, action in enumerate(submit_result["precheck"]["repair_actions"], 1):
                print(f"    [{i}] {action[:80]}..." if len(action) > 80 else f"    [{i}] {action}")
        print()
        print("  >>> 模拟: 开发团队修复问题后重新提交发布申请 <<<")
        print()
        submit_result = pipeline.submit_release(
            version=version + "-fixed",
            channel=channel,
            operator=operator
        )
        release_id = submit_result["release_id"]
        print(f"  新发布ID: {release_id}")
        print(f"  管线状态: {submit_result['pipeline_status']}")
        print(f"  前置校验: {submit_result['precheck']['overall_status'] if submit_result.get('precheck') else 'N/A'}")
        
        if submit_result["pipeline_status"] == "blocked_by_precheck":
            print("  仍未通过，跳过审批环节，直接演示后续功能...")
            approval = None
        else:
            print()
            approval = submit_result.get("approval", {})
    else:
        approval = submit_result.get("approval", {})

    print(f"[2/5] 三级审批流程 (模拟自动审批)")
    approve_result = submit_result
    if approval is not None:
        nodes = approval.get("nodes", []) if isinstance(approval, dict) else []
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
            print(f"    状态: {approve_result['pipeline_status']}")
    else:
        print("  (因前置校验未通过，跳过审批环节演示)")
    print()

    final_status = approve_result.get("pipeline_status", "unknown")
    print(f"[3/5] 灰度发布与自动熔断监控")
    print(f"  最终状态: {final_status}")
    if approve_result.get("canary"):
        canary = approve_result["canary"]
        print(f"  熔断触发: {canary.get('circuit_break_triggered', False)}")
        if canary.get("circuit_break_reason"):
            print(f"  熔断原因: {canary['circuit_break_reason']}")
        print(f"  回滚触发: {canary.get('rollback_triggered', False)}")
        print(f"  涉及药房: {', '.join(canary.get('target_pharmacies', []))}")
    print()

    print(f"[4/5] 执行回滚演练")
    drill_result = pipeline.execute_rollback_drill(
        drill_name=f"定期回滚演练-{datetime.now().strftime('%Y-%m-%d')}",
        operator=operator
    )
    print(f"  演练ID: {drill_result['drill_id']}")
    print(f"  演练状态: {drill_result['status']}")
    print(f"  回滚成功: {drill_result['rollback_success']}")
    print(f"  耗时: {drill_result['duration_seconds']}秒")
    print()

    print(f"[5/5] 生成运营周报")
    report_result = pipeline.generate_weekly_report()
    rd = report_result["report_data"]
    print(f"  统计周期: {rd['week_start']} ~ {rd['week_end']}")
    print(f"  发布总次数: {rd['total_releases']}")
    print(f"  发布成功次数: {rd['successful_releases']}")
    print(f"  回滚次数: {rd['rollback_count']}")
    print(f"  发布成功率: {rd['release_success_rate']}%")
    print(f"  生成文件: {list(report_result['files'].values())}")
    print()

    print("=" * 60)
    print("演示流程完成!")
    print(f"查看发布详情: python main.py status --release-id {release_id}")
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

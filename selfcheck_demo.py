import os
import sys
import subprocess

os.environ["PYTHONIOENCODING"] = "utf-8"

SCRIPT_DIR = r"e:\work\d028"


def run_demo(mode, forbidden_words, required_words, expected_outcome):
    print(f"{'=' * 60}")
    print(f"测试模式: {mode}")
    print(f"{'=' * 60}")

    txt_file = f"_selfcheck_{mode.replace('-', '_')}.txt"
    cmd = f'python main.py run-all --demo-mode {mode} > "{txt_file}" 2>&1'
    result = subprocess.run(cmd, shell=True, cwd=SCRIPT_DIR)

    filepath = os.path.join(SCRIPT_DIR, txt_file)
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    content = "".join(lines)

    all_pass = True

    print(f"  退出码: {result.returncode}")
    print()

    print(f"  【必含词汇检查】 ({len(required_words)}项)")
    for word in required_words:
        found = word in content
        status = "[PASS]" if found else "[FAIL]"
        if not found:
            all_pass = False
        print(f"    {status} 应包含: '{word}' -> {'存在' if found else '缺失'}")
    print()

    print(f"  【违禁词汇检查】 ({len(forbidden_words)}项)")
    for word in forbidden_words:
        found = word in content
        status = "[PASS]" if not found else "[FAIL]"
        if found:
            all_pass = False
            found_lines = [f"第{i+1}行: {l.strip()}" for i, l in enumerate(lines) if word in l]
            print(f"    {status} 不应包含: '{word}' -> 存在 ({len(found_lines)}处)")
            for fl in found_lines[:3]:
                print(f"           {fl[:60]}")
        else:
            print(f"    {status} 不应包含: '{word}' -> 未出现")
    print()

    print(f"  【结局一致性检查】")
    outcome_line = ""
    for line in lines:
        if "结局:" in line:
            outcome_line = line.strip()
            break

    found_expected = expected_outcome in outcome_line
    status = "[PASS]" if found_expected else "[FAIL]"
    if not found_expected:
        all_pass = False
    print(f"    {status} 结局应包含: '{expected_outcome}'")
    print(f"           实际: {outcome_line if outcome_line else '(未找到)'}")
    print()

    if not os.environ.get("KEEP_TMP"):
        try:
            os.remove(filepath)
        except OSError:
            pass

    return all_pass


def main():
    tests = [
        {
            "mode": "precheck-fail",
            "expected_outcome": "前置校验阻断",
            "required_words": [
                "[BLOCK]",
                "阻断原因与修复建议",
                "复查命令",
                "阶段一：发布前置校验",
                "python main.py status --release-id",
                "python main.py submit --version v2.x.x-fixed"
            ],
            "forbidden_words": [
                "阶段二",
                "阶段三",
                "三级审批",
                "灰度发布",
                "回滚演练",
                "运营周报",
                "[APPROVAL]",
                "[CANARY]",
                "[SKIPPED]",
                "[SAFETY_REPORT]",
                "[SUCCESS]",
                "[CIRCUIT_BREAK]",
                "实际执行的环节",
                "未执行的环节",
                "已执行环节"
            ]
        },
        {
            "mode": "canary-success",
            "expected_outcome": "灰度完成发布",
            "required_words": [
                "[SUCCESS]",
                "阶段一：发布前置校验",
                "阶段二：三级审批流程",
                "阶段三：灰度发布放量",
                "三阶段灰度发布全部成功",
                "发布流程:"
            ],
            "forbidden_words": [
                "回滚演练",
                "运营周报",
                "[CIRCUIT_BREAK]",
                "[SAFETY_REPORT]",
                "熔断触发",
                "熔断原因",
                "无熔断",
                "自动熔断",
                "受影响药房",
                "风险等级",
                "安全报告",
                "SKIPPED"
            ]
        },
        {
            "mode": "canary-break",
            "expected_outcome": "灰度熔断回滚",
            "required_words": [
                "[CIRCUIT_BREAK]",
                "阶段一：发布前置校验",
                "阶段二：三级审批流程",
                "阶段三：灰度发布放量",
                "熔断原因:",
                "受影响药房:",
                "风险等级:",
                "pharmacy_inpatient_a",
                "发布流程:",
                "患者用药安全影响报告"
            ],
            "forbidden_words": [
                "回滚演练",
                "运营周报",
                "SKIPPED",
                "[1/4]",
                "[2/4]",
                "[3/4]",
                "[4/4]"
            ]
        }
    ]

    print()
    print("=" * 60)
    print("run-all demo-mode 自检脚本")
    print("  覆盖模式: precheck-fail / canary-success / canary-break")
    print("  检查项: 必含词汇 + 违禁词汇 + 结局一致性")
    print("=" * 60)
    print()

    overall_pass = True
    results = []

    for test in tests:
        passed = run_demo(
            test["mode"],
            test["forbidden_words"],
            test["required_words"],
            test["expected_outcome"]
        )
        results.append((test["mode"], passed))
        if not passed:
            overall_pass = False

    print("=" * 60)
    print("【自检结果汇总】")
    print("=" * 60)
    for mode, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {mode}")
    print("=" * 60)

    if overall_pass:
        print()
        print("全部检查通过！")
        print()
        print("验收要点:")
        print()
        print("  [precheck-fail] 前置校验阻断模式")
        print("    - 只显示阶段一，不出现阶段二、阶段三")
        print("    - 只显示阻断原因、修复建议、复查命令")
        print("    - 不出现审批、灰度、演练、周报等后续流程词")
        print()
        print("  [canary-success] 灰度完成发布模式")
        print("    - 显示阶段一、阶段二、阶段三")
        print("    - 不出现任何熔断相关描述")
        print("    - 不出现受影响药房、风险等级、安全报告")
        print()
        print("  [canary-break] 灰度熔断回滚模式")
        print("    - 显示阶段一、阶段二、阶段三")
        print("    - 显示熔断原因、受影响药房、风险等级")
        print("    - 发布流程列出4项（含安全报告）")
        return 0
    else:
        print()
        print("存在未通过的检查，请修复后重试。")
        print("如需查看详细输出，请运行: $env:KEEP_TMP=1; python selfcheck_demo.py")
        return 1


if __name__ == "__main__":
    sys.exit(main())

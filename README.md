# 智慧药房自动化发药系统 - 版本发布与智能回滚自动化平台

## 一、系统概述

本系统是针对智慧药房自动化发药场景设计的版本发布与智能回滚自动化平台，覆盖**发布前置校验**、**多级审批流转**、**药房灰度发布与熔断**、**合规审计与复盘报表**四大核心业务维度，保障药房发药系统在版本迭代过程中的患者用药安全与系统稳定性。

### 核心设计目标

| 目标维度 | 具体指标 |
|---------|---------|
| 发布质量门禁 | 前置校验 16 项指标 100% 自动化覆盖 |
| 审批合规性 | 三级串行审批 + Hotfix 并行审批 + 事后补签审计 |
| 患者安全保障 | 3 类核心业务指标实时熔断，秒级自动回滚 |
| 审计可追溯 | 全流程不可篡改操作日志，365 天留存 |

---

## 二、系统架构

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      CLI / API 接入层                            │
│                   (main.py - ReleasePipeline)                   │
├──────────┬──────────┬──────────────┬────────────────────────────┤
│ 前置校验  │ 审批流转  │ 灰度发布熔断  │  演练·报表·审计            │
├──────────┼──────────┼──────────────┼────────────────────────────┤
│AI视觉    │审批引擎  │指标采集      │ 回滚演练管理器             │
│HIS接口   │动态路由  │灰度编排器    │ 周报生成器                 │
│条码识别  │通知提醒  │熔断保护器    │ 多维查询与导出             │
│设备健康  │超时监控  │安全影响评估  │ 合规审计日志               │
├──────────┴──────────┴──────────────┴────────────────────────────┤
│              公共基础服务层 (src/common)                        │
│  配置管理  │ 审计日志  │ 通知推送  │ 数据持久化  │ 数据模型    │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 目录结构

```
e:\work\d028\
├── main.py                          # 主入口 CLI
├── requirements.txt                 # 依赖清单
├── config/
│   └── system_config.yaml          # 系统全局配置
├── src/
│   ├── pipeline.py                  # 发布管线总编排
│   ├── common/                      # 公共基础模块
│   │   ├── config_loader.py        # YAML 配置加载（支持环境变量替换）
│   │   ├── audit_logger.py         # 应用日志 + 不可篡改审计日志
│   │   ├── notification_manager.py # 企微/钉钉/邮件多通道通知
│   │   ├── data_store.py           # JSON 持久化存储
│   │   └── models.py               # Pydantic 数据模型
│   ├── precheck/                    # 发布前置校验模块
│   │   ├── base_check.py           # 校验器抽象基类
│   │   ├── ai_vision_checker.py    # AI视觉+机械臂准确率校验
│   │   ├── his_interface_checker.py# HIS接口与处方流转校验
│   │   ├── barcode_checker.py      # 追溯码/条码采集校验
│   │   ├── device_health_checker.py# 设备健康度校验
│   │   └── orchestrator.py         # 校验编排+阻断决策
│   ├── approval/                    # 分级审批模块
│   │   └── engine.py               # 审批流引擎（串行/并行/补签）
│   ├── canary/                      # 灰度发布与熔断模块
│   │   ├── metrics_collector.py    # 业务指标采集聚合
│   │   ├── circuit_breaker.py      # 熔断保护器+安全影响报告
│   │   └── orchestrator.py         # 多阶段灰度编排
│   └── audit/                       # 演练、报表、审计模块
│       ├── rollback_drill.py       # 回滚演练管理
│       └── report_generator.py     # 周报+多维查询导出
├── data/                            # 运行时数据
│   ├── releases/                    # 每次发布全流程记录
│   ├── drills/                      # 回滚演练记录
│   ├── reports/                     # 生成的周报(PDF/Excel/图表)
│   └── audit_logs/                  # JSONL 格式审计日志
└── logs/                            # 运行时日志
    ├── app.log                      # 应用运行日志（按天滚动）
    └── audit/audit.log              # 结构化审计日志
```

---

## 三、四大核心模块设计

### 3.1 发布前置校验与多维质量门禁

**模块位置**: [src/precheck/](file:///e:/work/d028/src/precheck/)

#### 3.1.1 校验维度

| 校验大类 | 校验项数 | 核心指标 | 阈值 |
|---------|---------|---------|-----|
| AI视觉+机械臂 | 3 项 | 发药准确率 | ≥ 99.95% |
| | | 视觉识别耗时 | ≤ 200ms |
| HIS 接口 | 4 项 | 接口响应时间 | ≤ 3000ms |
| | | 追溯码上传成功率 | ≥ 99.5% |
| 条码识别 | 4 项 | 识别响应时间 | ≤ 100ms |
| | | 高速传送带采集率 | ≥ 99.99% |
| 设备健康 | 5 项 | 综合健康评分 | ≥ 90/100 |
| | | 库存数据一致性 | ≥ 99.9% |

#### 3.1.2 阻断与放行机制

```
任一校验失败 (any_fail_blocks 策略)
    │
    ├─→ 自动阻断发布流程
    ├─→ 为每项失败生成结构化修复建议
    ├─→ 通过企微/钉钉/邮件通知干系人
    └─→ 完整记录至审计日志

全部校验通过
    │
    └─→ 进入审批流转环节
```

**代码参考**: 
- 校验编排 [orchestrator.py](file:///e:/work/d028/src/precheck/orchestrator.py#L33-L110)
- AI视觉校验 [ai_vision_checker.py](file:///e:/work/d028/src/precheck/ai_vision_checker.py)
- HIS接口校验 [his_interface_checker.py](file:///e:/work/d028/src/precheck/his_interface_checker.py)

---

### 3.2 分级审批流转与动态路由

**模块位置**: [src/approval/engine.py](file:///e:/work/d028/src/approval/engine.py)

#### 3.2.1 双通道设计

| 发布通道 | 审批模式 | 适用场景 | 特殊机制 |
|---------|---------|---------|---------|
| **常规迭代 (regular)** | 三级串行审批 | 常规功能迭代 | 必须逐节点通过 |
| **紧急热修复 (hotfix)** | 并行审批 | 线上紧急 Bug 修复 | 支持事后补签、偏差报告 |

#### 3.2.2 审批矩阵

```
第一级: 药房审批
    ├─ 审批人: 药房主任 / 主任药师
    └─ 评估维度: 处方流转合理性、发药时效影响

第二级: 信息科审批
    ├─ 审批人: IT 经理 / 信息安全官
    └─ 评估维度: HIS 接口兼容性、数据安全、追溯码上传合规

第三级: 设备科审批
    ├─ 审批人: 设备科主任 / 维保工程师
    └─ 评估维度: 机械臂运动规划、硬件兼容性、维保计划
```

#### 3.2.3 关键特性

- **超时提醒**: 每 30 分钟自动催办，48 小时未处理标记超时
- **事后补签**: Hotfix 通道支持发布后补填审批意见，同时强制记录偏差报告
- **全程留痕**: 每步审批记录操作人、时间、意见至不可篡改审计日志

---

### 3.3 药房灰度发布、实时监控与自动熔断

**模块位置**:
- 灰度编排 [src/canary/orchestrator.py](file:///e:/work/d028/src/canary/orchestrator.py)
- 熔断保护 [src/canary/circuit_breaker.py](file:///e:/work/d028/src/canary/circuit_breaker.py)

#### 3.3.1 三阶段灰度放量策略

| 阶段 | 药房层级 | 示例药房 | 观察时长 | 风险等级 |
|-----|---------|---------|---------|---------|
| Tier 1 | 住院部/低流量药房 | pharmacy_inpatient_a/b | 30 分钟 | 低 |
| Tier 2 | 门诊普通药房 | pharmacy_outpatient_common | 60 分钟 | 中 |
| Tier 3 | 急诊/核心高流量药房 | pharmacy_emergency / outpatient_core | 120 分钟 | 高 |

#### 3.3.2 高频业务监控指标 (每 5 分钟采集)

| 指标名称 | 安全阈值 | 触发熔断含义 |
|---------|---------|------------|
| **发药错误率** | ≤ 0.1% | 错发/漏发超出安全线，患者用药风险 |
| **卡药率** | ≤ 0.5% | 机械臂或传送带异常频发 |
| **处方延迟率** | ≤ 2% | 从结算到发药完成超时过多 |

#### 3.3.3 熔断与自动回滚流程

```
指标超限被检测到
    │
    ▼
┌─────────────────────────┐
│  1. 立即触发熔断        │
│     - 暂停当前灰度发布   │
│     - 标记熔断药房列表   │
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│  2. 自动执行版本回滚    │
│     - 回滚至上一稳定版   │
│     - 清空灰度药房列表   │
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│  3. 生成结构化安全报告  │
│     - 患者用药安全评估   │
│     - 就医体验影响评估   │
│     - 建议处置措施       │
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│  4. 多通道同步通知      │
│     - 企微/钉钉/邮件     │
│     - 药房主任、信息科、  │
│       设备科、DevOps     │
└─────────────────────────┘
```

#### 3.3.4 患者用药安全影响评估

熔断触发后自动根据超限指标计算风险等级：

| 风险等级 | 判定条件 | 处置建议 |
|---------|---------|---------|
| 🟢 LOW | 仅轻微延迟/卡药 | 版本回滚，观察恢复 |
| 🟡 MEDIUM | 错误率略超或延迟较高 | 通知医务科关注 |
| 🟠 HIGH | 错误率 ≥ 0.2% 或严重延迟 | 药房人工复核已发药品 |
| 🔴 CRITICAL | 错误率 ≥ 0.5% | 立即启动用药差错应急预案 |

---

### 3.4 演练验证、复盘报表与合规审计

**模块位置**:
- 回滚演练 [src/audit/rollback_drill.py](file:///e:/work/d028/src/audit/rollback_drill.py)
- 报表审计 [src/audit/report_generator.py](file:///e:/work/d028/src/audit/report_generator.py)

#### 3.4.1 常态化回滚演练

- **演练频率**: 每月 15 日默认计划（可配置）
- **演练模式**: 手动触发 / 自动定时执行
- **演练步骤 (全程计时归档)**:
  1. 模拟业务异常指标注入
  2. 验证熔断阈值检测有效性
  3. 执行版本回滚操作（不影响真实业务）
  4. 验证回滚后核心功能可用性
  5. 重启监控并确认指标恢复
- **演练产出**: 结构化 JSON 记录，含每步耗时、成功率、详细日志

#### 3.4.2 自动化运营周报

**生成频率**: 每周一自动生成上周报表
**输出格式**: PDF + Excel + PNG 趋势图
**核心指标**:

| 指标 | 说明 |
|-----|-----|
| 发布总次数 | 统计周期内全部发布申请 |
| 发布成功率 | 成功完成全部灰度阶段的比例 |
| 回滚次数 | 自动或手动触发回滚的总次数 |
| 平均审批时长 | 从提交到审批完成的平均耗时(小时) |
| 按通道统计 | 常规迭代 vs 紧急热修复的分项统计 |
| 按药房统计 | 各药房的发布成功率与回滚分布 |

#### 3.4.3 多维度检索与合规审计

- **查询维度**: 发布时间范围、药房 ID、版本号、发布状态、审批状态
- **批量导出**: 支持 Excel / CSV 格式导出全部查询结果
- **审计日志**:
  - 全流程关键操作生成结构化 JSON 记录
  - 含操作时间、操作人、资源、结果、详情、哈希校验
  - 按天归档至 JSONL 文件
  - 保留期限 365 天（可配置）
  - 哈希链设计确保不可篡改

---

## 四、快速开始

### 4.1 环境准备

```bash
pip install -r requirements.txt
```

### 4.2 配置系统

编辑 [config/system_config.yaml](file:///e:/work/d028/config/system_config.yaml):

```yaml
# 通知渠道配置（可选，未配置时仅输出日志）
notification:
  wecom:
    webhook_url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY"
  email:
    smtp_host: "smtp.example.com"
    username: "devops@hospital.com"
    recipients: ["devops@hospital.com", "pharmacy@hospital.com"]
```

### 4.3 一键运行完整演示

```bash
python main.py run-all
```

此命令将依次演示：
1. ✅ 提交发布 → 前置校验阻断 → 修复后重新提交
2. ✅ 药房 → 信息科 → 设备科 三级审批
3. ✅ 三阶段灰度发布 + 实时监控 + 熔断回滚
4. ✅ 执行回滚演练
5. ✅ 生成运营周报 (PDF/Excel/图表)

### 4.4 常用命令

```bash
# 提交发布申请
python main.py submit --version v2.5.0 --channel regular

# 审批节点
python main.py approve \
  --release-id REL-20260622-XXXXXX \
  --node-id NODE-REL-20260622-XXXXXX-0 \
  --approver pharmacy_director \
  --comments "药房评估通过，发药时效无影响"

# 手动回滚
python main.py rollback \
  --release-id REL-20260622-XXXXXX \
  --reason "发现严重发药错误"

# 查询发布状态
python main.py status --release-id REL-20260622-XXXXXX

# 列出所有发布
python main.py list

# 执行回滚演练
python main.py drill --name "6月例行演练"

# 生成周报
python main.py report

# 查询并导出历史记录
python main.py query --start 2026-06-01 --export --export-format excel
```

---

## 五、关键技术实现要点

### 5.1 不可篡改审计日志

每条审计记录通过 SHA-256 哈希链保障完整性：

```python
def _compute_hash(self, data: Dict) -> str:
    sorted_data = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return sha256(sorted_data.encode("utf-8")).hexdigest()
```

位置: [src/common/data_store.py](file:///e:/work/d028/src/common/data_store.py#L23-L26)

### 5.2 熔断-安全评估联动

熔断触发后自动根据超限指标的类型与严重程度，生成包含风险等级、受影响患者预估、建议措施的结构化报告，确保一线人员快速响应。

位置: [src/canary/circuit_breaker.py](file:///e:/work/d028/src/canary/circuit_breaker.py#L95-L177)

### 5.3 发布状态全链路追踪

每次发布的状态流转:

```
submitted → precheck_running → precheck_passed/failed
    → awaiting_approval → approval_in_progress → approved/rejected
    → canary_tier1/2/3 → completed / rolling_back / rolled_back
```

---

## 六、运行验证

执行 `python main.py run-all` 后，检查以下产物确认系统正常：

| 产物路径 | 验证内容 |
|---------|---------|
| `data/releases/*.json` | 每次发布的完整状态记录 |
| `data/drills/*.json` | 回滚演练的步骤与耗时记录 |
| `data/reports/weekly_report_*.pdf` | PDF 格式周报 |
| `data/reports/weekly_report_*.xlsx` | Excel 格式多Sheet周报 |
| `data/reports/chart_summary_*.png` | 发布结果可视化图表 |
| `logs/app.log` | 应用运行日志（按天滚动） |
| `logs/audit/audit.log` | 结构化审计日志 |

---

## 七、扩展建议

1. **接入真实设备接口**: 替换各 Checker 中的 `_simulate_*` 方法为真实 HTTP/Modbus/OPC-UA 设备通信
2. **对接企业 SSO**: 将审批人校验接入医院 AD/LDAP 或企业微信组织架构
3. **数据库升级**: 将 JSON 文件存储升级为 PostgreSQL + 时序数据库 (InfluxDB) 支撑大规模指标存储
4. **Web 可视化**: 基于 FastAPI + Vue 构建发布管理控制台，实时展示灰度进度与监控大屏
5. **混沌工程集成**: 在演练模块引入混沌工程工具（如 Chaos Monkey），注入真实网络延迟、磁盘故障等异常

---

*系统版本: v1.0.0 | 设计日期: 2026-06-22*

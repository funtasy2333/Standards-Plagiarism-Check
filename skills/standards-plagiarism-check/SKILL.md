---
name: standards-plagiarism-check
description: 依据《团体标准化 第1部分：良好行为指南》附录 B（规范性），对团体标准（含草案）与国家/行业/地方/团体/国际标准进行技术内容重复率检测。支持接入 DeepSeek OCR 与百度 PaddleOCR 将 Word/PDF 转为 Markdown，按 GB/T 1.1 切分最小编号叶子条款，先核验标准化对象一致性，再动态圈定核心技术要素并逐条比对（规范性直接引用如“按 GB/T XXX 执行”判为不重复），最终按公式 R=(n2/n1)×100% 计算重复率并导出 Markdown/HTML/Word/Excel/JSON 五种报告。当用户需要检测标准重复率、查重团体标准技术内容、或使用 OCR 解析比对标准文档时使用本技能。
---

# 团体标准内容重复率检测（附录 B 规范性方法）

本 Skill 是一个**自包含的标准审查工具包**，用于执行团体标准（含草案）与国家标准、行业标准、地方标准、团体标准、国际国外标准（统称“比对标准”）的**技术内容重复率检测**。

> **核心原则**：本检测重点考察**核心技术要素与实质技术内容（指标、参数、试验方法、工艺流程、技术规定）的重复**，而非论文式字面查重。计算公式为：
> $$R = \frac{n_2}{n_1} \times 100\%$$

---

## Bundled Resources（技能包内附资源）

- `scripts/std_check.py`：自包含 CLI 执行脚本（带 PEP 723 依赖声明，支持 `uv run` 直接运行，内置完整的 `std_plagiarism_check` 模块）。
- `references/appendix_b_rules.md`：附录 B 细则、各类标准核心技术要素映射表与标准化对象一致性判定指南。
- `references/assessment_schema.json`：宿主 Agent 输出比对判定 JSON 必须遵循的 JSON Schema。
- `assets/env.example`：DeepSeek OCR 与百度 PaddleOCR 环境变量配置模板。

---

## 环境准备与运行方式

检查当前环境是否存在可用的 `std-check` 命令或 `.venv/bin/std-check`；若当前工作区未安装包，则直接通过本 Skill 自带的 `scripts/std_check.py` 运行（推荐使用 `uv run` 自动处理依赖）：

```bash
# 方式 A：使用技能自带的自包含脚本（任意工作区通用）
uv run <skill_dir>/scripts/std_check.py --help

# 方式 B：当前项目已安装虚拟环境时
.venv/bin/std-check --help
```

> **OCR 凭据配置**：使用前需确认环境变量或 `.env` 中已配置远程 OCR 凭据（参考 `assets/env.example`）：
> - **DeepSeek OCR**：设置 `DEEPSEEK_API_KEY`（原生支持 `.pdf`、`.doc`、`.docx`、图片）。
> - **百度 PaddleOCR**：设置 `PADDLEOCR_MODE=aistudio_api`、`PADDLEOCR_API_URL`、`PADDLEOCR_ACCESS_TOKEN`（或 `PADDLEOCR_MODE=mcp`）；若输入为 `.doc/.docx`，工具会自动调用 LibreOffice 先转为 PDF 再提交百度 OCR。

---

## 标准审查五步工作流（严格遵循附录 B）

### 第 1 步：远程 OCR 转换与叶子条款预切分

调用 `prepare` 子命令对 1 份团体标准与 1~N 份比对标准执行远程 OCR 转 Markdown 及 GB/T 1.1 叶子条款切分：

```bash
uv run <skill_dir>/scripts/std_check.py prepare \
  --target <团体标准文件路径(.docx/.pdf)> \
  --references <比对标准1> --references <比对标准2> \
  --engine deepseek \
  --workspace ./std_check_workspace
```

该步骤会在 `./std_check_workspace` 生成：
- `markdown/*.md`：远程 OCR 转换后的纯净 Markdown 文本；
- `parsed/target.json` 与 `parsed/ref_*.json`：已自动排除**前言、引言、1 范围、2 规范性引用文件、3 术语和定义、资料性附录及参考文献**后的标准元数据、章节概览与最小编号叶子条款；
- `assessment_template.json`：预填了所有候选叶子条款 ID 及规范性引用检测提示的评估模板。

*(若用户已自行通过外部挂载的 `paddleocr-mcp` 将 PDF 转为 `.md`，也可直接调用 `parse` 子命令切分条款。)*

---

### 第 2 步：步骤 a —— 标准化对象与适用范围一致性核验（前置必检）

读取 `parsed/target.json` 与所有 `parsed/ref_*.json` 的 `metadata`（`standard_code`、`standard_title`、`scope_chapter_text`），**逐一明确提取并对比团标与每份比对标准的“标准化对象”与“适用范围”**：

1. 明确写出 `target_object`（待测团标的标准化对象）与 `reference_object`（比对标准的标准化对象）。
2. 判定 `object_consistency`：
   - `IDENTICAL`：标准化对象与适用范围完全一致；
   - `SIMILAR`：标准化对象相同/相近，或存在细分规格、上下游覆盖关系（满足附录 B“相同或相似”前提）；
   - `INCONSISTENT`：标准化对象不一致或领域跨度过远，**不满足附录 B 步骤 a 前提**。
3. 当判定为 `INCONSISTENT` 时，必须设置 `"is_eligible_for_comparison": false`。计算引擎会在报告首部显著标注“标准化对象不一致”，并将其从有效重复率计算中剔除。

---

### 第 3 步：步骤 b —— 识别标准类型并动态圈定核心技术要素（锁定 $n_1$）

解析器已自动排除前言、引言、1 范围、2 规范性引用文件、3 术语和定义、资料性附录及参考文献。请阅读 `parsed/target.json` 的 `chapters` 概览，**根据标准类型动态判定第 4 章及以后章节（含规范性附录）是否属于“核心技术要素”**（详见 `references/appendix_b_rules.md`）：

- **产品标准**：核心通常为“技术要求/性能指标”、“试验方法”、“检验规则”及规范性附录；纯背景综述章节可排除；
- **方法/检测标准**：核心通常为“原理”、“试剂与材料”、“仪器设备”、“样品制备”、“分析/试验步骤”、“结果计算与精密度”；
- **管理/服务/评价标准**：核心通常为“基本原则与要求”、“过程/服务规范”、“评价指标与方法”、“监督与改进”。

在 `chapter_scope_decisions` 中为每个候选章节填写 `in_comparison_scope` (`true` / `false`) 与 `reason`。所有纳入章节内的最小编号叶子条款总数即为 $n_1$。

---

### 第 4 步：步骤 c & d —— 逐条技术内容语义比对（锁定 $n_2$）

遍历纳入 $n_1$ 的每一个叶子条款（条款内的列项 a/b/c 与附表归入所属编号条款整体评估），在所有通过步骤 a 核验（`is_eligible_for_comparison == true`）的比对标准条款中进行**技术内容语义比对**，严格使用以下 **6 类判定枚举**：

| 判定枚举 (`verdict`) | 含义与判定标准 | 官方计入 $n_2$ | 折算权重 |
| :--- | :--- | :---: | :---: |
| `DUPLICATE_EXACT` | 将比对标准的技术要求、指标数值、试验步骤直接写入团标正文，内容完全一致 | **1** | `1.0` |
| `DUPLICATE_EQUIVALENT` | 调整句式、语序、排版或同义词替换（未采用规范性引用），但核心技术参数/方法原理实质等同 | **1** | `1.0` |
| `DUPLICATE_PARTIAL` | 条款内仅部分子项/表格指标重复，需给出 `overlap_ratio`（重复项数 / 总项数） | **占比 $\ge 0.5$ 计 1，否则计 0** | `overlap_ratio` |
| `NON_DUPLICATE_DIRECT_REF` | 条款直接写“**按 GB/T XXX 的规定执行**”“符合 GB/T XXX 第 X 章规定”等合规规范性引用（即使该国标在比对列表中） | **0（不重复）** | `0.0` |
| `NON_DUPLICATE_UPGRADED` | 考核维度相近，但团标**实质加严/提升了技术指标（严于比对标准）**或对试验方法有实质性技术改进 | **0（不重复）** | `0.0` |
| `NON_DUPLICATE_UNIQUE` | 比对标准中无对应或相似技术规定，属于团标独创内容 | **0（不重复）** | `0.0` |

> **关键规则提醒**：
> - 遇到 `detected_normative_refs` 提示时，只要团标正文是直接规范性引用（如“按 GB/T XXXX—2020 的规定执行”）而非抄录条文内容，一律判为 **`NON_DUPLICATE_DIRECT_REF`（不重复，计 0）**。
> - 团标指标实质严于国标/行标（如抗拉强度要求更高、有害物质限值更低、测试条件更严苛），判为 **`NON_DUPLICATE_UPGRADED`（不重复，计 0）**。

---

### 第 5 步：保存判定 JSON 并导出全套报告

将完整判定结果保存为 `std_check_workspace/assessment.json`（严格符合 `references/assessment_schema.json`），执行：

```bash
uv run <skill_dir>/scripts/std_check.py report \
  --workspace ./std_check_workspace \
  --assessment ./std_check_workspace/assessment.json \
  --output-dir ./reports
```

程序将在 `./reports` 一次性生成五份报告：
1. `plagiarism_report.md`（结构化审查报告）
2. `plagiarism_report.html`（可筛选、左右对照的交互式可视化报告）
3. `plagiarism_report.docx`（正式 Word 审查报告）
4. `plagiarism_report.xlsx`（4 工作表逐条明细 Excel）
5. `plagiarism_report.json`（完整可追溯 JSON 数据）

最后向用户汇总标准化对象核验结论、$n_1$、$n_2$、官方重复率 $R$、指标提升亮点及高重复条款清单，并附上报告文件链接。

---
name: standards-plagiarism-check
description: 依据《团体标准化 第1部分：良好行为指南》附录 B（规范性），通过远程 OCR（DeepSeek OCR / 百度 PaddleOCR）将团体标准及比对标准（Word/PDF）转为 Markdown，按最小编号叶子条款切分，由宿主 Agent 完成标准化对象一致性核验、核心技术要素动态圈定及逐条技术内容语义比对，最终自动计算内容重复率并导出 Markdown/HTML/Word/Excel/JSON 五种格式报告。
---

# 团体标准内容重复率检测工作流（附录 B 规范性方法）

本 Skill 用于执行团体标准（含草案）与国家标准、行业标准、地方标准、团体标准、国际国外标准（统称“比对标准”）的**技术内容重复率检测**。

> **核心原则**：本检测不是传统论文的文字查重，重点在于**核心技术要素与实质技术内容（指标、参数、试验方法、工艺流程、技术规定）的重复**，公式为：
> $$R = \frac{n_2}{n_1} \times 100\%$$

---

## 执行前提与工具调用

优先检查当前环境是否已挂载 `std-check-mcp` MCP Server 或已安装 `std-check` CLI：
- **CLI 方式**：`std-check prepare ...` / `std-check report ...`
- **MCP 方式**：`prepare_comparison_workspace` / `generate_plagiarism_reports`
- 若宿主已额外挂载官方 `paddleocr-mcp` 且需要直接使用该通道，也可先用 `paddleocr-mcp` 将 PDF 转为 `.md` 后再调用 `std-check parse`；若输入包含 `.doc/.docx` 且选择百度 PaddleOCR，`std-check` 会自动先将 Word 转为 PDF 再提交百度 OCR。

---

## 标准审查四步工作流（严格遵循附录 B）

### 第 1 步：远程 OCR 转换与叶子条款预切分

调用以下命令（或同名 MCP 工具 `prepare_comparison_workspace`）：

```bash
std-check prepare \
  --target <团体标准文件路径(.docx/.pdf)> \
  --references <比对标准1> --references <比对标准2> \
  --engine deepseek \
  --workspace ./std_check_workspace
```

该步骤会输出：
- `std_check_workspace/markdown/*.md`：远程 OCR 转换后的纯净 Markdown 文本；
- `std_check_workspace/parsed/target.json` 与 `parsed/ref_*.json`：已按 GB/T 1.1 自动排除**前言、引言、1 范围、2 规范性引用文件、3 术语和定义、资料性附录及参考文献**后的标准结构与最小编号叶子条款；
- `std_check_workspace/assessment_template.json`：预填了所有候选叶子条款 ID 及规范性引用检测提示的评估模板。

---

### 第 2 步：步骤 a —— 标准化对象与适用范围一致性核验（前置必检）

读取 `parsed/target.json` 与所有 `parsed/ref_*.json` 的 `metadata`（尤其是 `standard_code`、`standard_title`、`scope_chapter_text`），**逐一明确提取并对比团标与每份比对标准的“标准化对象”与“适用范围”**：

1. 明确写出 `target_object`（团标的标准化对象）与 `reference_object`（比对标准的标准化对象）。
2. 判定 `object_consistency`：
   - `IDENTICAL`：标准化对象与适用范围完全一致；
   - `SIMILAR`：标准化对象相同/相近，或存在细分规格、上下游产品/方法覆盖关系（符合附录 B“相同或相似”条件）；
   - `INCONSISTENT`：标准化对象完全不同或适用领域跨度过远，**不满足附录 B 步骤 a 前提**。
3. 当判定为 `INCONSISTENT` 时，必须设置 `"is_eligible_for_comparison": false`。后续计算引擎会在报告首部显著提示“标准化对象不一致”，并将其从有效重复率计算中剔除。

---

### 第 3 步：步骤 b —— 识别标准类型并动态圈定核心技术要素（锁定 $n_1$）

虽然解析器已自动排除了前言、引言、1 范围、2 规范性引用文件、3 术语和定义、资料性附录及参考文献，你仍需阅读 `parsed/target.json` 的 `chapters` 概览，**根据标准类型动态判定第 4 章及以后章节（含规范性附录）是否属于“核心技术要素”**（参考 [appendix_b_rules.md](references/appendix_b_rules.md)）：

- **产品标准**：核心通常为“分类与标记（若含技术规格参数）”、“技术要求/性能指标”、“试验方法”、“检验规则”及规范性附录；纯背景综述性非规范章节可排除；
- **方法/检测标准**：核心通常为“原理”、“试剂与材料”、“仪器设备”、“样品制备”、“分析/试验步骤”、“结果计算与精密度”；
- **管理/服务/评价标准**：核心通常为“基本原则与要求”、“过程/服务规范”、“评价指标与方法”、“监督与改进”。

在 `chapter_scope_decisions` 中为每个候选章节填写 `in_comparison_scope` (`true` / `false`) 与 `reason`。所有 `in_comparison_scope == true` 的章节内的最小编号叶子条款总数即为 $n_1$。

---

### 第 4 步：步骤 c & d —— 逐条技术内容语义比对（锁定 $n_2$）

遍历纳入 $n_1$ 的每一个叶子条款（条款内的列项 a/b/c 与附表整体评估），在所有通过步骤 a 核验（`is_eligible_for_comparison == true`）的比对标准条款中进行**技术内容语义比对**，严格使用以下 **6 类判定枚举**：

| 判定枚举 (`verdict`) | 含义与判定标准 | 官方计入 $n_2$ | 折算权重 |
| :--- | :--- | :---: | :---: |
| `DUPLICATE_EXACT` | 将比对标准的技术要求、指标数值、试验步骤直接写入团标正文，内容完全一致 | **1** | `1.0` |
| `DUPLICATE_EQUIVALENT` | 调整句式、语序、排版或同义词替换（未采用规范性引用），但核心技术参数/方法原理实质等同 | **1** | `1.0` |
| `DUPLICATE_PARTIAL` | 条款内仅部分子项/表格指标重复，需精确计算 `overlap_ratio`（重复项数 / 总项数） | **占比 $\ge 0.5$ 计 1，否则计 0** | `overlap_ratio` |
| `NON_DUPLICATE_DIRECT_REF` | 条款直接写“**按 GB/T XXX 的规定执行**”“符合 GB/T XXX 第 X 章规定”等合规规范性引用（即使该国标在比对列表中） | **0（不重复）** | `0.0` |
| `NON_DUPLICATE_UPGRADED` | 考核维度相近，但团标**实质加严/提升了技术指标（严于比对标准）**或对试验方法有实质性技术改进 | **0（不重复）** | `0.0` |
| `NON_DUPLICATE_UNIQUE` | 比对标准中无对应或相似技术规定，属于团标独创内容 | **0（不重复）** | `0.0` |

> **关键规则提醒**：
> - 若某叶子条款内有 `detected_normative_refs` 提示，请核实原文：只要该条款是直接采用“按 GB/T XXXX 规定执行”而未将国标具体条款文字/表格搬入正文，一律判为 **`NON_DUPLICATE_DIRECT_REF`（不重复，计 0）**！
> - 若某指标数值在团标中比国标更严格（如抗拉强度国标要求 `≥ 350 MPa`，团标要求 `≥ 420 MPa`；或有害物质限值更低），判为 **`NON_DUPLICATE_UPGRADED`（不重复，计 0）**！

---

### 第 5 步：保存判定 JSON 并生成全套审查报告

将完整的判定结果保存为 `std_check_workspace/assessment.json`（格式必须符合 [assessment_schema.json](references/assessment_schema.json)），然后调用：

```bash
std-check report \
  --workspace ./std_check_workspace \
  --assessment ./std_check_workspace/assessment.json \
  --output-dir ./reports
```
（或调用 MCP 工具 `generate_plagiarism_reports`）。

程序将自动校验标准化对象门禁、精确计算 $R_i$、1对N 并集总重复率 $R_{\text{total}}$ 及加权参考率，并在 `./reports` 生成：
1. `plagiarism_report.md`
2. `plagiarism_report.html`
3. `plagiarism_report.docx`
4. `plagiarism_report.xlsx`
5. `plagiarism_report.json`

向用户汇报核心结果（标准化对象核验结论、$n_1$、$n_2$、$R$、亮点提升条款与高重复风险条款清单）并附上报告文件路径。

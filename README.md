# Standards Plagiarism Check（团体标准内容重复率检测 Agent 插件）

依据《团体标准化 第1部分：良好行为指南》**附录 B（规范性）《团体标准内容重复率的计算方法》**开发的 AI Agent 插件（**Agent Skill + Python CLI + MCP Server**）。

不同于常规论文的字面查重，本工具专注于**标准核心技术要素与实质技术内容的重复率计算**（$R = \frac{n_2}{n_1} \times 100\%$）：

1. **统一远程 OCR 文档解析**：接入 **DeepSeek OCR API** 与 **百度飞桨 PaddleOCR（AI Studio HTTP API / `paddleocr-mcp`）**，将团体标准和比对标准（Word / PDF）统一转为纯净 Markdown 文档；针对仅支持 PDF/图片的百度 PaddleOCR，自动先将 Word（`.doc`/`.docx`）渲染转换为 PDF 再识别。
2. **GB/T 1.1 叶子条款智能切分**：自动识别章条层级并提取**最小编号叶子条款**（不重复计数父级标题，自动聚合条内列项与附表），自动初筛排除前言、引言、第 1 章 范围、第 2 章 规范性引用文件、第 3 章 术语和定义、资料性附录及参考文献。
3. **宿主 Agent 语义审查四步法（`SKILL.md`）**：
   - **步骤 a（前置必检）**：明确对比待测团体标准与各比对标准的**标准化对象与适用范围是否一致**；标准化对象不一致的标准不纳入有效重复率计算。
   - **步骤 b**：根据标准类型（产品/方法/管理/服务等）动态圈定核心技术要素章节，锁定分母 $n_1$。
   - **步骤 c & d**：逐条技术语义比对，识别完全重复、同义改写、部分重复（$\ge 50\%$ 计 1 并附折算参考值），并将**规范性直接引用（如“按 GB/T XXX 规定执行”）**及**指标提升/实质改进**明确判定为**不重复（计 0）**。
4. **多格式报告一键导出**：同时生成 **Markdown (`.md`)**、**交互式 HTML (`.html`)**、**正式 Word 审查报告 (`.docx`)**、**Excel 多表工作簿 (`.xlsx`)** 与 **可追溯 JSON (`.json`)**。

---

## 快速安装

推荐使用 `uv` 或 Python 3.10+ 虚拟环境安装：

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

若使用 **百度 PaddleOCR** 处理 `.doc`/`.docx` 文件，请确保本机已安装 LibreOffice（提供 `soffice` 命令用于 Word 转 PDF）。如果使用 **DeepSeek OCR**，则可直接上传 `.doc`/`.docx`/`.pdf` 无需本地 LibreOffice。

---

## 配置远程 OCR 密钥

复制环境变量模板并填写你的 API 凭据：

```bash
cp .env.example .env
```

### 方式 1：DeepSeek OCR API
- 文档：<https://api-docs.deepseek.com/zh-cn/guides/ocr>
- 在 `.env` 中设置：
  ```env
  STD_CHECK_DEFAULT_OCR_ENGINE=deepseek
  DEEPSEEK_API_KEY=sk-...
  DEEPSEEK_OCR_PURPOSE=text_recognition
  ```

### 方式 2：百度飞桨 PaddleOCR（AI Studio API 或 `paddleocr-mcp`）
- 官网：<https://aistudio.baidu.com/paddleocr>
- 使用 AI Studio 在线 API 时，在 `.env` 中设置：
  ```env
  STD_CHECK_DEFAULT_OCR_ENGINE=paddleocr
  PADDLEOCR_MODE=aistudio_api
  PADDLEOCR_API_URL=https://xxxxxx.aistudio-app.com/layout-parsing
  PADDLEOCR_ACCESS_TOKEN=your_aistudio_token
  ```
- 使用官方 `paddleocr-mcp` 时，设置 `PADDLEOCR_MODE=mcp` 及相应 `PADDLEOCR_MCP_*` 参数。

---

## 使用方式

### 1. 作为 Agent Skill + MCP Server 使用

将 `skills/standards-plagiarism-check/` 放入你的 Agent Skill 目录，并在 MCP 配置中添加本项目的 `std-check-mcp`：

```json
{
  "mcpServers": {
    "standards-plagiarism-check": {
      "command": "/path/to/.venv/bin/std-check-mcp",
      "args": []
    }
  }
}
```

宿主 Agent 将自动按 `SKILL.md` 调用 `prepare_comparison_workspace` $\rightarrow$ 完成步骤 a/b/c/d 语义评估 $\rightarrow$ 调用 `generate_plagiarism_reports` 输出全部五种格式报告。

### 2. 命令行 CLI (`std-check`)

```bash
# 1) 单文件远程 OCR 转 Markdown
std-check ocr ./samples/group_standard.docx --engine deepseek -o ./out/target.md

# 2) 标准 Markdown 切分叶子条款
std-check parse ./out/target.md --role target -o ./out/target.parsed.json

# 3) 一键准备比对工作区（1 份团标 + N 份比对标准）
std-check prepare \
  --target ./samples/group_std.docx \
  --references ./samples/gb_1.pdf \
  --references ./samples/gb_2.pdf \
  --engine deepseek \
  --workspace ./std_check_workspace

# 4) 根据 Agent 评估结果 JSON 计算重复率并生成 5 种报告
std-check report \
  --workspace ./std_check_workspace \
  --assessment ./std_check_workspace/assessment.json \
  --output-dir ./reports
```

---

## 运行单元测试

```bash
.venv/bin/pytest -v
```

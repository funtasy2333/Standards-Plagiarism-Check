"""Interactive HTML report generator for Appendix B standard duplication results."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Template

from ..models import ClauseVerdict, ObjectConsistency, PlagiarismReportResult
from .md_exporter import CONSISTENCY_LABELS, VERDICT_LABELS

_HTML_TEMPLATE = Template(
    r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>团体标准内容重复率检测报告 - {{ report.target_standard.standard_code or report.target_standard.standard_id }}</title>
  <style>
    :root {
      --bg: #f5f7fb;
      --card: #ffffff;
      --text: #1e293b;
      --muted: #64748b;
      --border: #e2e8f0;
      --primary: #2563eb;
      --danger: #dc2626;
      --danger-bg: #fef2f2;
      --warn: #d97706;
      --warn-bg: #fffbeb;
      --success: #059669;
      --success-bg: #ecfdf5;
      --info: #0284c7;
      --info-bg: #f0f9ff;
      --purple: #7c3aed;
      --purple-bg: #f5f3ff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
    }
    .container { max-width: 1280px; margin: 0 auto; padding: 28px 20px 60px; }
    header.hero {
      background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);
      color: #fff;
      padding: 28px 32px;
      border-radius: 16px;
      margin-bottom: 24px;
      box-shadow: 0 10px 30px rgba(15, 23, 42, 0.15);
    }
    header.hero h1 { margin: 0 0 8px; font-size: 24px; }
    header.hero .meta { font-size: 14px; color: #cbd5e1; display: flex; flex-wrap: wrap; gap: 18px; }
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }
    .kpi-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 18px 20px;
      box-shadow: 0 2px 6px rgba(15, 23, 42, 0.04);
    }
    .kpi-label { font-size: 13px; color: var(--muted); margin-bottom: 6px; }
    .kpi-value { font-size: 28px; font-weight: 700; color: var(--text); }
    .kpi-sub { font-size: 12px; color: var(--muted); margin-top: 4px; }
    .kpi-highlight .kpi-value { color: var(--primary); }
    .section {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 22px 24px;
      margin-bottom: 22px;
      box-shadow: 0 2px 6px rgba(15, 23, 42, 0.03);
    }
    .section h2 {
      margin: 0 0 14px;
      font-size: 18px;
      border-left: 4px solid var(--primary);
      padding-left: 10px;
    }
    .alert-warn {
      background: var(--warn-bg);
      border: 1px solid #fde68a;
      color: #92400e;
      border-radius: 8px;
      padding: 10px 14px;
      margin-bottom: 10px;
      font-size: 14px;
    }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    th, td {
      text-align: left;
      padding: 10px 12px;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }
    th { background: #f8fafc; font-weight: 600; color: #334155; }
    .badge {
      display: inline-block;
      padding: 2px 9px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 600;
      white-space: nowrap;
    }
    .badge-dup { background: var(--danger-bg); color: var(--danger); border: 1px solid #fecaca; }
    .badge-partial { background: var(--warn-bg); color: var(--warn); border: 1px solid #fde68a; }
    .badge-ref { background: var(--info-bg); color: var(--info); border: 1px solid #bae6fd; }
    .badge-up { background: var(--purple-bg); color: var(--purple); border: 1px solid #ddd6fe; }
    .badge-uniq { background: var(--success-bg); color: var(--success); border: 1px solid #a7f3d0; }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      margin-bottom: 16px;
    }
    .filter-btn {
      border: 1px solid var(--border);
      background: #fff;
      color: var(--text);
      border-radius: 8px;
      padding: 6px 12px;
      font-size: 13px;
      cursor: pointer;
    }
    .filter-btn.active {
      background: var(--primary);
      color: #fff;
      border-color: var(--primary);
    }
    .search-box {
      margin-left: auto;
      padding: 7px 12px;
      border: 1px solid var(--border);
      border-radius: 8px;
      font-size: 13px;
      min-width: 240px;
    }
    .clause-card {
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px;
      margin-bottom: 14px;
      background: #fff;
    }
    .clause-header {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      margin-bottom: 10px;
      padding-bottom: 8px;
      border-bottom: 1px dashed var(--border);
    }
    .clause-id { font-weight: 700; font-size: 15px; color: #0f172a; }
    .clause-path { font-size: 12px; color: var(--muted); }
    .compare-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
    }
    .pane {
      background: #f8fafc;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px;
      font-size: 13px;
      white-space: pre-wrap;
    }
    .pane-title { font-size: 12px; font-weight: 600; color: var(--muted); margin-bottom: 6px; }
    .reason-box {
      margin-top: 10px;
      padding: 10px 12px;
      background: #f1f5f9;
      border-radius: 8px;
      font-size: 13px;
    }
    @media (max-width: 820px) {
      .compare-grid { grid-template-columns: 1fr; }
      .search-box { margin-left: 0; width: 100%; }
    }
    @media print {
      body { background: #fff; }
      .toolbar { display: none; }
      .section { break-inside: avoid; box-shadow: none; }
    }
  </style>
</head>
<body>
  <div class="container">
    <header class="hero">
      <h1>团体标准技术内容重复率检测报告（附录 B）</h1>
      <div class="meta">
        <span>待测团标：<strong>{{ report.target_standard.standard_code or report.target_standard.standard_id }}</strong> {{ report.target_standard.standard_title }}</span>
        <span>标准类型：{{ report.standard_type }}</span>
        <span>生成时间：{{ report.generated_at }}</span>
      </div>
    </header>

    {% if report.warnings %}
    <div class="section">
      <h2>核验提醒</h2>
      {% for w in report.warnings %}
      <div class="alert-warn">{{ w }}</div>
      {% endfor %}
    </div>
    {% endif %}

    <div class="kpi-grid">
      <div class="kpi-card kpi-highlight">
        <div class="kpi-label">官方内容重复率 R = (n2 / n1) × 100%</div>
        <div class="kpi-value">{{ "%.2f"|format(report.duplicate_rate_percent) }}%</div>
        <div class="kpi-sub">公式 (B.1)：({{ report.n2 }} / {{ report.n1 }}) × 100%</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">纳入比对条款数 n1</div>
        <div class="kpi-value">{{ report.n1 }}</div>
        <div class="kpi-sub">已排除前置及非核心条款 {{ report.excluded_clauses_count }} 条</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">判定重复条款数 n2</div>
        <div class="kpi-value">{{ report.n2 }}</div>
        <div class="kpi-sub">规范性直接引用“按 GB/T XXX 执行”计 0</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">按比例折算参考重复率</div>
        <div class="kpi-value">{{ "%.2f"|format(report.weighted_duplicate_rate_percent) }}%</div>
        <div class="kpi-sub">折算分子 {{ "%.2f"|format(report.weighted_numerator) }} / {{ report.n1 }}</div>
      </div>
    </div>

    <div class="section">
      <h2>步骤 a：标准化对象与适用范围一致性核验</h2>
      <table>
        <thead>
          <tr>
            <th>比对标准</th>
            <th>团标标准化对象</th>
            <th>比对标准标准化对象</th>
            <th>一致性判定</th>
            <th>单标重复率</th>
            <th>说明</th>
          </tr>
        </thead>
        <tbody>
          {% for st in report.per_reference_stats %}
          <tr>
            <td><strong>{{ st.reference_code or st.reference_id }}</strong><br/>{{ st.reference_title }}</td>
            <td>{{ st.target_object }}</td>
            <td>{{ st.reference_object }}</td>
            <td>
              {% if st.object_consistency.value == "INCONSISTENT" %}
                <span class="badge badge-dup">{{ consistency_labels[st.object_consistency] }}</span>
              {% else %}
                <span class="badge badge-uniq">{{ consistency_labels[st.object_consistency] }}</span>
              {% endif %}
            </td>
            <td>{% if st.is_eligible_for_comparison %}{{ "%.2f"|format(st.duplicate_rate_percent) }}% ({{ st.n2 }}/{{ st.n1 }}){% else %}不纳入计算{% endif %}</td>
            <td>{{ st.consistency_reasoning }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>

    <div class="section">
      <h2>步骤 b：核心技术要素比对范围界定</h2>
      <table>
        <thead>
          <tr>
            <th>章节</th>
            <th>章节名称</th>
            <th>界定结果</th>
            <th>判定依据</th>
          </tr>
        </thead>
        <tbody>
          {% for ch in report.chapter_scope_decisions %}
          <tr>
            <td>{{ ch.chapter_no }}</td>
            <td>{{ ch.chapter_title }}</td>
            <td>
              {% if ch.in_comparison_scope %}
                <span class="badge badge-ref">纳入 (n1)</span>
              {% else %}
                <span class="badge badge-partial">排除</span>
              {% endif %}
            </td>
            <td>{{ ch.reason }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>

    <div class="section">
      <h2>步骤 c & d：逐条技术内容比对明细</h2>
      <div class="toolbar">
        <button class="filter-btn active" data-filter="all">全部 ({{ report.clause_details|length }})</button>
        <button class="filter-btn" data-filter="duplicate">计入重复 ({{ report.n2 }})</button>
        <button class="filter-btn" data-filter="DUPLICATE_PARTIAL">部分重复 ({{ report.verdict_counts.get("DUPLICATE_PARTIAL", 0) }})</button>
        <button class="filter-btn" data-filter="NON_DUPLICATE_DIRECT_REF">规范性直接引用 ({{ report.verdict_counts.get("NON_DUPLICATE_DIRECT_REF", 0) }})</button>
        <button class="filter-btn" data-filter="NON_DUPLICATE_UPGRADED">指标提升 ({{ report.verdict_counts.get("NON_DUPLICATE_UPGRADED", 0) }})</button>
        <button class="filter-btn" data-filter="NON_DUPLICATE_UNIQUE">独创条款 ({{ report.verdict_counts.get("NON_DUPLICATE_UNIQUE", 0) }})</button>
        <input id="searchInput" class="search-box" type="text" placeholder="搜索条款号、内容或分析理由..." />
      </div>

      <div id="clauseList">
        {% for item in report.clause_details %}
        <div class="clause-card" data-verdict="{{ item.verdict.value }}" data-score="{{ item.official_duplicate_score }}">
          <div class="clause-header">
            <div>
              <span class="clause-id">{{ item.clause_id }} {{ item.title }}</span>
              <div class="clause-path">{{ item.chapter_path }}</div>
            </div>
            <div>
              {% if item.verdict.value in ["DUPLICATE_EXACT", "DUPLICATE_EQUIVALENT"] %}
                <span class="badge badge-dup">{{ verdict_labels[item.verdict] }}</span>
              {% elif item.verdict.value == "DUPLICATE_PARTIAL" %}
                <span class="badge badge-partial">部分重复 ({{ "%.0f"|format(item.overlap_ratio * 100) }}%，计 {{ item.official_duplicate_score }})</span>
              {% elif item.verdict.value == "NON_DUPLICATE_DIRECT_REF" %}
                <span class="badge badge-ref">{{ verdict_labels[item.verdict] }}</span>
              {% elif item.verdict.value == "NON_DUPLICATE_UPGRADED" %}
                <span class="badge badge-up">{{ verdict_labels[item.verdict] }}</span>
              {% else %}
                <span class="badge badge-uniq">{{ verdict_labels[item.verdict] }}</span>
              {% endif %}
            </div>
          </div>
          <div class="compare-grid">
            <div class="pane">
              <div class="pane-title">待测团体标准条款原文</div>
              {{- item.target_text -}}
            </div>
            <div class="pane">
              <div class="pane-title">对应比对标准条款</div>
              {%- if item.matched_clauses -%}
                {%- for m in item.matched_clauses -%}
[{{ m.reference_code or m.reference_id }}] {{ m.reference_clause_id }} {{ m.reference_clause_title }}
{{ m.reference_excerpt }}
{% if m.match_note %}说明：{{ m.match_note }}{% endif %}
{% if not loop.last %}---
{% endif %}
                {%- endfor -%}
              {%- else -%}
无对应重复条款
              {%- endif -%}
            </div>
          </div>
          <div class="reason-box"><strong>技术对比判定理由：</strong>{{ item.technical_reasoning }}</div>
        </div>
        {% endfor %}
      </div>
    </div>

    {% if report.overall_expert_notes %}
    <div class="section">
      <h2>综合评审意见</h2>
      <p>{{ report.overall_expert_notes }}</p>
    </div>
    {% endif %}
  </div>

  <script>
    const buttons = document.querySelectorAll('.filter-btn');
    const cards = document.querySelectorAll('.clause-card');
    const searchInput = document.getElementById('searchInput');
    let currentFilter = 'all';

    function applyFilters() {
      const q = (searchInput.value || '').trim().toLowerCase();
      cards.forEach(card => {
        const verdict = card.dataset.verdict;
        const score = card.dataset.score;
        const text = card.innerText.toLowerCase();
        let matchFilter = true;
        if (currentFilter === 'duplicate') {
          matchFilter = score === '1';
        } else if (currentFilter !== 'all') {
          matchFilter = verdict === currentFilter;
        }
        const matchQuery = !q || text.includes(q);
        card.style.display = (matchFilter && matchQuery) ? '' : 'none';
      });
    }

    buttons.forEach(btn => {
      btn.addEventListener('click', () => {
        buttons.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentFilter = btn.dataset.filter;
        applyFilters();
      });
    });
    searchInput.addEventListener('input', applyFilters);
  </script>
</body>
</html>
"""
)


def render_html_report(report: PlagiarismReportResult) -> str:
    """Render an interactive standalone HTML report."""
    return _HTML_TEMPLATE.render(
        report=report,
        verdict_labels=VERDICT_LABELS,
        consistency_labels=CONSISTENCY_LABELS,
    )


def export_html_report(report: PlagiarismReportResult, output_path: Path) -> Path:
    """Write interactive HTML report to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html_report(report), encoding="utf-8")
    return output_path

"""Command-line interface (`std-check`) for Standards Plagiarism Check."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Optional

import typer
from rich.console import Console
from rich.table import Table

from .config import load_settings
from .ocr import OcrError, create_ocr_client
from .parser import parse_standard_markdown
from .workspace import generate_reports_from_workspace, prepare_workspace

app = typer.Typer(
    name="std-check",
    help="团体标准技术内容重复率检测 CLI（远程 OCR + GB/T 1.1 叶子条款解析 + 附录 B 计算与报告导出）",
    no_args_is_help=True,
)
console = Console()


@app.command()
def ocr(
    file_path: Path = typer.Argument(..., exists=True, help="待识别的 Word/PDF/图片标准文件"),
    engine: Optional[Literal["deepseek", "paddleocr"]] = typer.Option(
        None, "--engine", "-e", help="远程 OCR 引擎：deepseek 或 paddleocr"
    ),
    purpose: Optional[str] = typer.Option(
        None,
        "--purpose",
        help="DeepSeek OCR 模式：text_recognition 或 rich_layout_recognition",
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="输出的 Markdown 文件路径（默认写入缓存或同目录 .md）"
    ),
    no_cache: bool = typer.Option(False, "--no-cache", help="禁用本地 OCR 结果缓存"),
) -> None:
    """调用远程 OCR 模型将 Word/PDF 标准文件转换为干净的 Markdown 文档。"""
    settings = load_settings()
    try:
        client = create_ocr_client(engine, settings)
        output_dir = output.parent if output else file_path.parent
        result = client.convert_to_markdown(
            file_path, output_dir=output_dir, purpose=purpose, use_cache=not no_cache
        )
        if output and Path(result.markdown_path) != output.resolve():
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(result.markdown_text, encoding="utf-8")
            final_path = output.resolve()
        else:
            final_path = Path(result.markdown_path)

        console.print(
            f"[green]✓ OCR 完成[/green] 引擎: [bold]{result.engine}[/bold] | "
            f"页数: {result.page_count} | 缓存命中: {result.cached} | 输出: {final_path}"
        )
    except OcrError as exc:
        console.print(f"[red]✗ OCR 失败:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def parse(
    markdown_path: Path = typer.Argument(..., exists=True, help="标准 Markdown 文件路径"),
    role: Literal["target", "reference"] = typer.Option(
        "target", "--role", "-r", help="标准角色：target（待测团标）或 reference（比对标准）"
    ),
    standard_id: Optional[str] = typer.Option(
        None, "--id", help="标准唯一标识（默认取文件名）"
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="输出结构化 JSON 文件路径"
    ),
) -> None:
    """按 GB/T 1.1 解析标准 Markdown，执行前置/非核心章节初筛并切分叶子条款。"""
    md_text = markdown_path.read_text(encoding="utf-8")
    std_id = standard_id or markdown_path.stem
    parsed = parse_standard_markdown(
        md_text,
        standard_id=std_id,
        role=role,
        markdown_file=str(markdown_path.resolve()),
    )

    out_path = output or markdown_path.with_suffix(".parsed.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(parsed.model_dump_json(indent=2), encoding="utf-8")

    table = Table(title=f"标准解析概览: {parsed.metadata.standard_code or std_id}")
    table.add_column("章节", style="cyan")
    table.add_column("标题")
    table.add_column("自动排除", style="magenta")
    table.add_column("叶子条款数", justify="right")

    for ch in parsed.chapters:
        excl = ch.auto_exclude_reason or "否（候选技术章节）"
        table.add_row(ch.chapter_no, ch.chapter_title, excl, str(ch.leaf_clause_count))

    console.print(table)
    console.print(
        f"[green]✓ 解析完成[/green] 候选核心叶子条款: [bold]{len(parsed.candidate_leaf_clauses)}[/bold] 条 | "
        f"总叶子条款: {len(parsed.all_leaf_clauses)} 条 | 输出: {out_path.resolve()}"
    )


@app.command()
def prepare(
    target: Path = typer.Option(..., "--target", "-t", exists=True, help="待测团体标准 (Word/PDF)"),
    references: list[Path] = typer.Option(
        ..., "--references", "--ref", "-r", exists=True, help="比对标准文件列表（支持多个）"
    ),
    engine: Optional[Literal["deepseek", "paddleocr"]] = typer.Option(
        None, "--engine", "-e", help="远程 OCR 引擎：deepseek 或 paddleocr"
    ),
    purpose: Optional[str] = typer.Option(
        None, "--purpose", help="DeepSeek OCR 模式（text_recognition / rich_layout_recognition）"
    ),
    workspace: Path = typer.Option(
        Path("./std_check_workspace"), "--workspace", "-w", help="工作区输出目录"
    ),
    no_cache: bool = typer.Option(False, "--no-cache", help="禁用本地 OCR 缓存"),
) -> None:
    """一键完成团标与比对标准的远程 OCR 转 Markdown 与叶子条款预切分，生成待比对工作区。"""
    settings = load_settings()
    try:
        manifest = prepare_workspace(
            target_file=target,
            reference_files=references,
            workspace_dir=workspace,
            ocr_engine=engine,
            purpose=purpose,
            settings=settings,
            use_cache=not no_cache,
        )
    except OcrError as exc:
        console.print(f"[red]✗ 准备工作区失败:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print("[green]✓ 比对工作区准备完成[/green]")
    console.print(json.dumps(manifest, ensure_ascii=False, indent=2))


@app.command()
def report(
    workspace: Path = typer.Option(
        Path("./std_check_workspace"), "--workspace", "-w", exists=True, help="工作区目录"
    ),
    assessment: Path = typer.Option(
        ..., "--assessment", "-a", exists=True, help="宿主 Agent 生成的比对判定 JSON 文件"
    ),
    output_dir: Path = typer.Option(
        Path("./reports"), "--output-dir", "-o", help="报告输出目录"
    ),
    strict: bool = typer.Option(
        False, "--strict", help="若为 True，缺失任何纳入范围条款的判定结果将报错退出"
    ),
) -> None:
    """校验比对判定 JSON，按附录 B 公式计算重复率并导出 .md/.json/.html/.docx/.xlsx 报告。"""
    try:
        rep, files = generate_reports_from_workspace(
            workspace_dir=workspace,
            assessment_json_path=assessment,
            output_dir=output_dir,
            strict_clause_coverage=strict,
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]✗ 报告生成失败:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        f"[green]✓ 附录 B 计算与五格式报告导出完成[/green]\n"
        f"  • 纳入条款数 n1: [bold]{rep.n1}[/bold]\n"
        f"  • 重复条款数 n2: [bold]{rep.n2}[/bold]\n"
        f"  • 官方内容重复率 R: [bold cyan]{rep.duplicate_rate_percent:.2f}%[/bold cyan]\n"
        f"  • 加权折算参考重复率: {rep.weighted_duplicate_rate_percent:.2f}%"
    )
    for fmt, p in files.items():
        console.print(f"  - {fmt}: {p}")


if __name__ == "__main__":
    app()

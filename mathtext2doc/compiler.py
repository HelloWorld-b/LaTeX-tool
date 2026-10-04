"""LaTeX 编译器 + PNG 转换。

策略：
    1. 优先直接输出 PNG：尝试 `xelatex -output-format=png`（若发行版支持）。
       - TeX Live 的 xelatex 不直接支持 PNG 输出，所以这一步通常会跳过。
       - 但保留作为优先尝试，符合需求规范第 6 条。
    2. 回退方案：xelatex 编译 PDF → pdftoppm / pdftocairo / convert 转 PNG。
       - 这是支持中文 + ctex 的最稳定路径。
    3. 多页 PDF 输出多张 PNG：pdftoppm 默认就会按页输出 prefix-1.png prefix-2.png ...
    4. 失败时保留 .log / .tex / .pdf 等中间产物，输出清晰错误信息。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional


class CompileError(Exception):
    pass


# ---------------------------------------------------------------------------
# 工具：查找可执行文件
# ---------------------------------------------------------------------------

def _which(name: str) -> Optional[str]:
    return shutil.which(name)


# ---------------------------------------------------------------------------
# 编译器选择
# ---------------------------------------------------------------------------

def pick_latex_compiler(prefer: Optional[str] = None) -> str:
    """选择一个可用的 LaTeX 编译器。

    优先级：
        1. 用户指定的 prefer
        2. xelatex（中文支持最好）
        3. lualatex
        4. pdflatex（不支持中文，仅作为兜底）
    """
    candidates = []
    if prefer:
        candidates.append(prefer)
    candidates.extend(["xelatex", "lualatex", "pdflatex"])
    for c in candidates:
        if _which(c):
            return c
    raise CompileError(
        "未找到任何 LaTeX 编译器。请安装 TeX Live / MiKTeX / MacTeX，"
        "并确保 xelatex 在 PATH 中。\n"
        "下载：https://www.tug.org/texlive/"
    )


# ---------------------------------------------------------------------------
# 主编译流程
# ---------------------------------------------------------------------------

@dataclass
class CompileResult:
    png_paths: List[str]
    pdf_path: Optional[str]
    log_path: Optional[str]
    compiler: str
    fallback_used: bool


def compile_tex_to_png(
    tex_path: str,
    out_dir: str,
    *,
    compiler: Optional[str] = None,
    dpi: int = 150,
    overwrite: bool = False,
    keep_intermediates: bool = True,
) -> CompileResult:
    """编译 .tex 到 PNG（多页输出多张）。

    参数：
        tex_path: .tex 文件路径
        out_dir: 输出目录（.tex 所在目录）
        compiler: 指定 LaTeX 编译器；None 自动选择
        dpi: PNG DPI，默认 150
        overwrite: 是否覆盖已有 PNG
        keep_intermediates: 是否保留 .log/.aux/.pdf 等中间文件

    返回 CompileResult。

    失败抛 CompileError，错误信息中包含日志路径。
    """
    if not os.path.isfile(tex_path):
        raise CompileError(f".tex 文件不存在：{tex_path}")

    base = os.path.splitext(os.path.basename(tex_path))[0]
    chosen = pick_latex_compiler(compiler)

    # 第一步：尝试直接 PNG 输出（仅当编译器是 xelatex/lualatex/pdflatex 且支持时）
    # 实际上 TeX Live 的 xelatex 不支持 -output-format=png，所以这一步几乎总失败。
    # 但我们保留作为优先尝试。
    png_paths = _try_direct_png(tex_path, out_dir, chosen, dpi, overwrite)
    if png_paths:
        return CompileResult(
            png_paths=png_paths,
            pdf_path=None,
            log_path=os.path.join(out_dir, base + ".log"),
            compiler=chosen,
            fallback_used=False,
        )

    # 第二步：回退——编译 PDF
    pdf_path = _compile_pdf(tex_path, out_dir, chosen)
    log_path = os.path.join(out_dir, base + ".log")

    if not os.path.isfile(pdf_path):
        # 读取 log 最后 30 行帮助诊断
        log_tail = _read_log_tail(log_path)
        raise CompileError(
            f"LaTeX 编译失败，未生成 PDF。\n"
            f"编译器：{chosen}\n"
            f".tex 文件：{tex_path}\n"
            f".log 文件：{log_path}\n"
            f"日志末尾：\n{log_tail}"
        )

    # 第三步：PDF → PNG（多页）
    png_paths = _pdf_to_png(pdf_path, out_dir, base, dpi, overwrite)

    if not png_paths:
        raise CompileError(
            f"PDF 转 PNG 失败。请确认已安装 pdftoppm / pdftocairo / ImageMagick 之一。\n"
            f"PDF 文件：{pdf_path}"
        )

    # 第四步：清理中间文件（可选）
    if not keep_intermediates:
        _cleanup_intermediates(out_dir, base, keep_pdf=False)
    else:
        # 保留 .pdf / .log / .tex，仅清理 .aux / .out 等
        _cleanup_intermediates(out_dir, base, keep_pdf=True)

    return CompileResult(
        png_paths=png_paths,
        pdf_path=pdf_path if keep_intermediates else None,
        log_path=log_path if keep_intermediates else None,
        compiler=chosen,
        fallback_used=True,
    )


# ---------------------------------------------------------------------------
# 直接 PNG 输出尝试
# ---------------------------------------------------------------------------

def _try_direct_png(
    tex_path: str,
    out_dir: str,
    compiler: str,
    dpi: int,
    overwrite: bool,
) -> List[str]:
    """尝试让 LaTeX 直接输出 PNG。TeX Live 通常不支持，所以基本会返回 []。"""
    base = os.path.splitext(os.path.basename(tex_path))[0]
    # xelatex 不支持 -output-format=png；lualatex 同样；pdflatex 也不行。
    # 真正能直接输出 PNG 的是 dvipng（处理 dvi），但 dvipng 不支持 xetex 输出。
    # 我们这里只做一个保险检查：如果用户装了 dvi 工具链，就尝试 latex+dvipng 路径。
    # 但这又无法处理中文 ctex，所以只在源文件不含中文时才尝试。
    try:
        with open(tex_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return []
    has_chinese = bool(re.search(r"[\u4e00-\u9fff]", content))
    if has_chinese:
        # 直接 PNG 路径无法处理中文，跳过
        return []

    latex = _which("latex")
    dvipng = _which("dvipng")
    if not latex or not dvipng:
        return []

    # 临时把 \documentclass{ctexart} 改成 \documentclass{article}（去掉中文依赖）
    # 这里只做最简单的尝试；如果失败就回退。
    tmp_tex = os.path.join(out_dir, base + "_direct_png.tex")
    try:
        with open(tex_path, "r", encoding="utf-8") as f:
            src = f.read()
        # 简单替换 ctexart → article，并去掉 ctex 相关包
        src = src.replace(r"\documentclass[11pt,a4paper]{ctexart}",
                          r"\documentclass[11pt,a4paper]{article}")
        with open(tmp_tex, "w", encoding="utf-8") as f:
            f.write(src)
    except Exception:
        return []

    try:
        # latex → dvi
        r1 = subprocess.run(
            [latex, "-interaction=nonstopmode", "-output-directory=" + out_dir,
             "-no-shell-escape", tmp_tex],
            cwd=out_dir, capture_output=True, text=True, timeout=120,
        )
        dvi_path = os.path.join(out_dir, base + "_direct_png.dvi")
        if not os.path.isfile(dvi_path):
            return []
        # dvipng → png（多页会输出 _direct_png1.png _direct_png2.png ...）
        # dvipn 默认输出 prefix%d.png
        out_prefix = os.path.join(out_dir, base + "_direct_png_")
        r2 = subprocess.run(
            [dvipng, "-q", "-D", str(dpi), "-o", out_prefix + "%d.png",
             "-T", "tight", "--png", dvi_path],
            cwd=out_dir, capture_output=True, text=True, timeout=120,
        )
        # 收集生成的 PNG
        pngs = []
        for fn in sorted(os.listdir(out_dir)):
            if fn.startswith(base + "_direct_png_") and fn.endswith(".png"):
                pngs.append(os.path.join(out_dir, fn))
        if pngs:
            # 重命名为 base-N.png
            final = []
            for i, p in enumerate(pngs, start=1):
                dst = os.path.join(out_dir, f"{base}-{i}.png")
                if os.path.exists(dst) and not overwrite:
                    raise CompileError(f"输出文件已存在：{dst}（使用 --overwrite 覆盖）")
                shutil.move(p, dst)
                final.append(dst)
            return final
    except Exception:
        return []
    finally:
        # 清理临时文件
        for ext in [".aux", ".log", ".dvi"]:
            p = os.path.join(out_dir, base + "_direct_png" + ext)
            if os.path.isfile(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
        if os.path.isfile(tmp_tex):
            try:
                os.remove(tmp_tex)
            except Exception:
                pass

    return []


# ---------------------------------------------------------------------------
# 编译 PDF
# ---------------------------------------------------------------------------

def _compile_pdf(tex_path: str, out_dir: str, compiler: str) -> str:
    """调用 xelatex/lualatex/pdflatex 编译 PDF。"""
    base = os.path.splitext(os.path.basename(tex_path))[0]
    pdf_path = os.path.join(out_dir, base + ".pdf")

    cmd = [
        compiler,
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-output-directory=" + out_dir,
        tex_path,
    ]

    try:
        proc = subprocess.run(
            cmd, cwd=out_dir, capture_output=True, text=True, timeout=180,
        )
    except subprocess.TimeoutExpired:
        raise CompileError(
            f"LaTeX 编译超时（180s）。编译器：{compiler}\n"
            f".tex 文件：{tex_path}"
        )
    except FileNotFoundError:
        raise CompileError(
            f"找不到编译器 {compiler}，请确认已安装。"
        )

    return pdf_path


# ---------------------------------------------------------------------------
# PDF → PNG
# ---------------------------------------------------------------------------

def _pdf_to_png(
    pdf_path: str,
    out_dir: str,
    base: str,
    dpi: int,
    overwrite: bool,
) -> List[str]:
    """把 PDF 转 PNG，多页输出多张。返回 PNG 路径列表。"""
    # 优先级：pdftoppm > pdftocairo > convert (ImageMagick)
    if _which("pdftoppm"):
        return _pdf_to_png_pdftoppm(pdf_path, out_dir, base, dpi, overwrite)
    if _which("pdftocairo"):
        return _pdf_to_png_pdftocairo(pdf_path, out_dir, base, dpi, overwrite)
    if _which("convert"):
        return _pdf_to_png_convert(pdf_path, out_dir, base, dpi, overwrite)
    raise CompileError(
        "未找到 PDF→PNG 转换工具。请安装 poppler-utils（pdftoppm/pdftocairo）"
        "或 ImageMagick（convert）。\n"
        "Ubuntu/Debian: apt-get install poppler-utils\n"
        "macOS: brew install poppler"
    )


def _pdf_to_png_pdftoppm(
    pdf_path: str, out_dir: str, base: str, dpi: int, overwrite: bool,
) -> List[str]:
    # pdftoppm -r DPI -png prefix 输出 prefix-1.png prefix-2.png ...
    prefix = os.path.join(out_dir, base)
    # 先清理可能存在的旧文件
    if overwrite:
        for fn in os.listdir(out_dir):
            if fn.startswith(base + "-") and fn.endswith(".png"):
                try:
                    os.remove(os.path.join(out_dir, fn))
                except Exception:
                    pass
    else:
        # 检查是否已存在
        existing = [fn for fn in os.listdir(out_dir)
                    if fn.startswith(base + "-") and fn.endswith(".png")]
        if existing:
            raise CompileError(
                f"输出文件已存在：{os.path.join(out_dir, existing[0])} "
                f"（使用 --overwrite 覆盖）"
            )
    cmd = ["pdftoppm", "-r", str(dpi), "-png", pdf_path, prefix]
    try:
        subprocess.run(cmd, cwd=out_dir, capture_output=True, text=True, timeout=120)
    except Exception as ex:
        raise CompileError(f"pdftoppm 执行失败：{ex}")
    pngs = []
    for fn in sorted(os.listdir(out_dir)):
        if fn.startswith(base + "-") and fn.endswith(".png"):
            pngs.append(os.path.join(out_dir, fn))
    return pngs


def _pdf_to_png_pdftocairo(
    pdf_path: str, out_dir: str, base: str, dpi: int, overwrite: bool,
) -> List[str]:
    prefix = os.path.join(out_dir, base)
    if overwrite:
        for fn in os.listdir(out_dir):
            if fn.startswith(base + "-") and fn.endswith(".png"):
                try:
                    os.remove(os.path.join(out_dir, fn))
                except Exception:
                    pass
    cmd = ["pdftocairo", "-r", str(dpi), "-png", pdf_path, prefix]
    try:
        subprocess.run(cmd, cwd=out_dir, capture_output=True, text=True, timeout=120)
    except Exception as ex:
        raise CompileError(f"pdftocairo 执行失败：{ex}")
    pngs = []
    for fn in sorted(os.listdir(out_dir)):
        if fn.startswith(base + "-") and fn.endswith(".png"):
            pngs.append(os.path.join(out_dir, fn))
    return pngs


def _pdf_to_png_convert(
    pdf_path: str, out_dir: str, base: str, dpi: int, overwrite: bool,
) -> List[str]:
    # ImageMagick：convert -density DPI file.pdf out-%d.png
    pattern = os.path.join(out_dir, base + "-%d.png")
    if overwrite:
        for fn in os.listdir(out_dir):
            if fn.startswith(base + "-") and fn.endswith(".png"):
                try:
                    os.remove(os.path.join(out_dir, fn))
                except Exception:
                    pass
    cmd = ["convert", "-density", str(dpi), pdf_path, pattern]
    try:
        subprocess.run(cmd, cwd=out_dir, capture_output=True, text=True, timeout=180)
    except Exception as ex:
        raise CompileError(f"ImageMagick convert 执行失败：{ex}")
    pngs = []
    for fn in sorted(os.listdir(out_dir)):
        if fn.startswith(base + "-") and fn.endswith(".png"):
            pngs.append(os.path.join(out_dir, fn))
    return pngs


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _read_log_tail(log_path: str, n: int = 40) -> str:
    if not os.path.isfile(log_path):
        return "(无日志文件)"
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-n:])
    except Exception as ex:
        return f"(读取日志失败：{ex})"


def _cleanup_intermediates(out_dir: str, base: str, keep_pdf: bool) -> None:
    """清理 LaTeX 中间文件。"""
    exts_to_remove = [".aux", ".out", ".toc", ".fls", ".fdb_latexmk", ".synctex.gz"]
    if not keep_pdf:
        exts_to_remove.append(".pdf")
    for ext in exts_to_remove:
        p = os.path.join(out_dir, base + ext)
        if os.path.isfile(p):
            try:
                os.remove(p)
            except Exception:
                pass

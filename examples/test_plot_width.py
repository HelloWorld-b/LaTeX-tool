"""测试图片宽度调节功能。"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python"))
from mathtext2doc.parser import parse_document, Plot
from mathtext2doc.texgen import generate_tex

# 测试 1：默认无 width
text1 = """# 测试

@plot{
  y = sin(x), x in [-pi, pi], label="sin(x)"
}
"""
blocks1 = parse_document(text1)
plot1 = [b for b in blocks1 if isinstance(b, Plot)][0]
print(f"测试 1（无 width）: plot.width = {plot1.width}")
assert plot1.width is None, "无 width 时应为 None"
plot_paths1 = {id(plot1): "fake-plot1.png"}
tex1 = generate_tex(blocks1, plot_paths1, default_plot_width=0.7)
assert "0.7\\paperwidth" in tex1, f"tex 应含 0.7\\paperwidth，实际：{tex1}"
print("  ✅ 默认 0.7 paperwidth")

# 测试 2：单图 width=0.5
text2 = """# 测试

@plot(width=0.5){
  y = sin(x), x in [-pi, pi], label="sin(x)"
}
"""
blocks2 = parse_document(text2)
plot2 = [b for b in blocks2 if isinstance(b, Plot)][0]
print(f"\n测试 2（width=0.5）: plot.width = {plot2.width}")
assert plot2.width == 0.5, f"width 应为 0.5，实际 {plot2.width}"
plot_paths2 = {id(plot2): "fake-plot2.png"}
tex2 = generate_tex(blocks2, plot_paths2, default_plot_width=0.7)
assert "0.5\\paperwidth" in tex2, f"tex 应含 0.5\\paperwidth，实际：{tex2}"
print("  ✅ 单图 width=0.5 覆盖全局默认")

# 测试 3：全局默认改为 0.4
tex3 = generate_tex(blocks1, plot_paths1, default_plot_width=0.4)
assert "0.4\\paperwidth" in tex3, f"tex 应含 0.4\\paperwidth，实际：{tex3}"
print(f"\n测试 3（全局 0.4）: ✅ 全局默认 0.4 生效")

# 测试 4：混合 — 第一个图无 width，第二个图 width=0.3
text4 = """# 测试

@plot{
  y = sin(x), x in [-pi, pi], label="sin(x)"
}

@plot(width=0.3){
  y = cos(x), x in [-pi, pi], label="cos(x)"
}
"""
blocks4 = parse_document(text4)
plots4 = [b for b in blocks4 if isinstance(b, Plot)]
print(f"\n测试 4（混合）: plot1.width={plots4[0].width}, plot2.width={plots4[1].width}")
assert plots4[0].width is None
assert plots4[1].width == 0.3
plot_paths4 = {id(p): f"fake-{i}.png" for i, p in enumerate(plots4)}
tex4 = generate_tex(blocks4, plot_paths4, default_plot_width=0.7)
# 第一个图用全局 0.7
assert tex4.count("0.7\\paperwidth") == 1, f"应有一个 0.7，实际：{tex4}"
# 第二个图用单图 0.3
assert tex4.count("0.3\\paperwidth") == 1, f"应有一个 0.3，实际：{tex4}"
print("  ✅ 混合：plot1 用全局 0.7，plot2 用单图 0.3")

# 测试 5：width 越界报错
text5 = """@plot(width=1.5){
  y = sin(x), x in [-pi, pi]
}
"""
try:
    parse_document(text5)
    print("\n测试 5（width=1.5）: ❌ 应该报错但没有")
    sys.exit(1)
except Exception as ex:
    print(f"\n测试 5（width=1.5）: ✅ 正确报错：{ex}")

# 测试 6：CLI 参数校验
from mathtext2doc.cli import build_parser, run
import argparse
parser = build_parser()

# 写一个临时输入文件
with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
    f.write("# 测试\n")
    tmp_input = f.name

args_bad = parser.parse_args([tmp_input, "--plot-width", "1.5"])
rc = run(tmp_input, args_bad)
print(f"\n测试 6（CLI --plot-width 1.5）: 退出码 {rc}")
assert rc == 4, f"应退出码 4，实际 {rc}"
print("  ✅ CLI 参数校验生效")

args_ok = parser.parse_args([tmp_input, "--plot-width", "0.8", "--overwrite"])
# 不实际跑（没装 LaTeX），只验证参数被正确解析
print(f"\n测试 7（CLI --plot-width 0.8）: args.plot_width = {args_ok.plot_width}")
assert args_ok.plot_width == 0.8
print("  ✅ CLI 参数解析正确")

os.unlink(tmp_input)
print("\n" + "=" * 50)
print("全部测试通过 ✅")

"""验证 SYNTAX_FOR_AI.md 的可读性：
1. 用 LLM 读这份文档后生成一个输入文本
2. 用 parser 解析生成的文本，看是否有错误
"""
import sys, os, json, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python"))

from mathtext2doc.parser import parse_document, Plot, PlotParseError, ParseError

# 用 LLM 读 SYNTAX_FOR_AI.md 后生成一个测试输入
syntax_doc = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python", "SYNTAX_FOR_AI.md")).read()

prompt = f"""你是一个 AI 助手。请阅读以下 mathtext2doc 工具的语法规范文档，然后严格按照规范生成一个输入文本。

要求：
1. 主题：二次函数与抛物线
2. 必须包含：一级标题、二级标题、普通段落、列表、行内公式、块级公式、表格、至少 2 个 @plot（其中至少 1 个隐函数）
3. 严格遵守文档中的所有规则
4. 只输出输入文本本身，不要任何解释

=== 语法规范文档 ===
{syntax_doc}
=== 文档结束 ===

现在请生成输入文本："""

result = subprocess.run(
    ["z-ai", "chat", "-p", prompt, "-o", "/tmp/ai_gen.json"],
    capture_output=True, text=True, timeout=120
)
if result.returncode != 0:
    print("LLM 调用失败:", result.stderr)
    sys.exit(1)

ai_text = json.load(open("/tmp/ai_gen.json"))["choices"][0]["message"]["content"]

print("=" * 60)
print("AI 生成的输入文本：")
print("=" * 60)
print(ai_text)
print("=" * 60)

# 保存到文件
with open("/tmp/ai_input.txt", "w", encoding="utf-8") as f:
    f.write(ai_text)
print("\n已保存到 /tmp/ai_input.txt")

# 用 parser 解析
print("\n" + "=" * 60)
print("解析结果：")
print("=" * 60)
try:
    blocks = parse_document(ai_text)
    print(f"✅ 解析成功，共 {len(blocks)} 个 Block")
    # 统计
    from collections import Counter
    type_counts = Counter(type(b).__name__ for b in blocks)
    for t, c in sorted(type_counts.items()):
        print(f"  {t}: {c}")
    # 检查 plot 项
    plots = [b for b in blocks if isinstance(b, Plot)]
    print(f"\n  @plot 数量: {len(plots)}")
    for i, p in enumerate(plots, 1):
        kinds = [it.kind for it in p.items]
        print(f"    plot {i}: {len(p.items)} 项, 类型={kinds}")
        for it in p.items:
            print(f"      - expr={it.expr!r}, x_range={it.x_range}, y_range={it.y_range}, label={it.label!r}")
except (PlotParseError, ParseError) as ex:
    print(f"❌ 解析失败：{ex}")
    sys.exit(1)
except Exception as ex:
    print(f"❌ 未预期错误：{ex}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

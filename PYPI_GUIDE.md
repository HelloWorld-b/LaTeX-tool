# PyPI 打包发布指南

本文档说明如何把 `mathtext2doc` 打包成 PyPI 库并发布。

---

## 一、前置准备

### 1. 注册 PyPI 账号

- **PyPI**（正式发布）：https://pypi.org/account/register/
- **TestPyPI**（测试用）：https://test.pypi.org/account/register/

### 2. 创建 API Token

发布到 PyPI 需要 API Token（不能用密码）：

1. 登录 PyPI → Account settings → API tokens
2. 点 "Add API token"
3. Scope 选 "Entire account"（首次）或指定项目
4. 复制 token（形如 `pypi-xxxxxxxxxxxx`），**只显示一次**

### 3. 配置 `~/.pypirc`

```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-你的token

[testpypi]
username = __token__
password = pypi-你的testpypi-token
```

> ⚠️ `~/.pypirc` 含敏感信息，确保权限 `chmod 600 ~/.pypirc`，**不要提交到 git**。

---

## 二、项目配置（已完成）

### `pyproject.toml`（关键配置）

```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "mathtext2doc"                    # PyPI 包名（唯一）
version = "0.1.0"                        # 每次发布必须递增
description = "..."
requires-python = ">=3.10"
license = "MIT"                          # SPDX 表达式
authors = [{name = "...", email = "..."}]
keywords = ["latex", "math", ...]
classifiers = [...]                      # PyPI 分类
dependencies = ["matplotlib>=3.5", ...]

[project.urls]
Homepage = "https://github.com/..."
Repository = "https://github.com/..."

[project.scripts]
mathtext2doc = "mathtext2doc.cli:main"   # 安装后注册 CLI 命令

[tool.setuptools]
packages = ["mathtext2doc"]
```

### 必需文件

| 文件 | 用途 |
|---|---|
| `pyproject.toml` | 构建配置 + 项目元数据 |
| `LICENSE` | MIT 许可证全文 |
| `README.md` | 项目说明（PyPI 首页展示） |
| `MANIFEST.in` | 声明包含的非代码文件 |

---

## 三、构建打包

### 1. 安装构建工具

```bash
pip install build
```

### 2. 清理旧产物

```bash
rm -rf dist/ build/ *.egg-info
```

### 3. 构建

```bash
python -m build
```

生成两个文件在 `dist/`：

| 文件 | 用途 |
|---|---|
| `mathtext2doc-0.1.0-py3-none-any.whl` | wheel（推荐，二进制分发） |
| `mathtext2doc-0.1.0.tar.gz` | sdist（源码分发） |

### 4. 验证产物

```bash
# 检查 wheel 内容
python -m zipfile -l dist/mathtext2doc-0.1.0-py3-none-any.whl

# 检查 metadata
tar -tzf dist/mathtext2doc-0.1.0.tar.gz | head
```

### 5. 本地测试安装

```bash
# 创建虚拟环境测试
python -m venv /tmp/test_env
source /tmp/test_env/bin/activate

# 从 wheel 安装
pip install dist/mathtext2doc-0.1.0-py3-none-any.whl

# 验证命令可用
mathtext2doc --version
mathtext2doc --help

# 退出并清理
deactivate
rm -rf /tmp/test_env
```

---

## 四、发布到 TestPyPI（推荐先测）

```bash
# 安装发布工具
pip install twine

# 上传到 TestPyPI
twine upload --repository testpypi dist/*

# 从 TestPyPI 安装测试
pip install --index-url https://test.pypi.org/simple/ mathtext2doc
```

打开 https://test.pypi.org/project/mathtext2doc/ 查看页面。

---

## 五、发布到正式 PyPI

```bash
# 确认版本号已递增（编辑 pyproject.toml 的 version）
# 确认所有改动已 commit

# 上传
twine upload dist/*
```

打开 https://pypi.org/project/mathtext2doc/ 查看页面。

**用户安装命令**：

```bash
pip install mathtext2doc
```

安装后可直接用 `mathtext2doc input.txt` 命令。

---

## 六、版本发布流程（每次更新）

```bash
# 1. 更新版本号
# 编辑 pyproject.toml: version = "0.2.0"

# 2. 更新 CHANGELOG（可选但推荐）

# 3. 提交并打 tag
git add -A
git commit -m "release: v0.2.0"
git tag v0.2.0
git push origin main --tags

# 4. 清理并重新构建
rm -rf dist/ build/ *.egg-info
python -m build

# 5. 上传
twine upload dist/*
```

---

## 七、常见问题

### Q: `twine upload` 报 `403 Forbidden`

- API token 错误或过期
- token scope 不对（首次需 "Entire account"）
- `~/.pypirc` 的 `username` 必须是 `__token__`，`password` 是 token 本身

### Q: `version` 已存在

PyPI 不允许覆盖已发布的版本。每次发布必须递增版本号。

### Q: wheel 里少了文件

检查 `MANIFEST.in` 和 `[tool.setuptools] packages`。用 `python -m zipfile -l dist/*.whl` 验证。

### Q: `pip install` 后命令找不到

检查 `pyproject.toml` 的 `[project.scripts]` 段。确保 `mathtext2doc = "mathtext2doc.cli:main"` 正确。

### Q: 包名被占用

PyPI 包名先到先得。如果 `mathtext2doc` 被占用，换名如 `mathtext2doc-cli` 或 `mathtext2doc-tool`。

---

## 八、CI 自动发布（可选）

在 `.github/workflows/publish.yml` 配置：

```yaml
name: Publish to PyPI

on:
  release:
    types: [created]

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Build
        run: |
          pip install build
          python -m build
      - name: Publish
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
        run: |
          pip install twine
          twine upload dist/*
```

在 GitHub 仓库 Settings → Secrets 添加 `PYPI_API_TOKEN`。之后只要在 GitHub 创建 Release，就会自动发布到 PyPI。

---

## 九、当前项目状态

✅ 已完成：
- `pyproject.toml` 完整配置（含 classifiers、urls、scripts）
- `LICENSE` MIT 许可证
- `MANIFEST.in` 包含 README/LICENSE/examples
- 本地构建验证通过（wheel + sdist）
- entry_point `mathtext2doc` 命令注册正确

⏳ 待你完成：
1. 注册 PyPI 账号
2. 创建 API Token
3. 配置 `~/.pypirc`
4. 运行 `twine upload dist/*` 发布

发布后用户就能用 `pip install mathtext2doc` 安装了。

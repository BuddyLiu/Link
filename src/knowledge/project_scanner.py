"""
项目知识库 - 自动扫描和理解项目结构、技术栈、规范
"""

import os
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any


class ProjectScanner:
    """项目扫描器

    自动分析项目目录，提取关键信息存入知识库。
    """

    # 识别的配置文件
    CONFIG_FILES = {
        "pyproject.toml": ("python", "toml"),
        "package.json": ("node", "json"),
        "Cargo.toml": ("rust", "toml"),
        "go.mod": ("go", "text"),
        "Gemfile": ("ruby", "text"),
        "CMakeLists.txt": ("cpp", "text"),
        "Makefile": ("make", "text"),
        "Dockerfile": ("docker", "text"),
        "composer.json": ("php", "json"),
        "pubspec.yaml": ("dart", "yaml"),
        "Project.toml": ("julia", "toml"),
        "setup.py": ("python", "python"),
        "setup.cfg": ("python", "cfg"),
        "requirements.txt": ("python", "text"),
        "Pipfile": ("python", "toml"),
        ".editorconfig": ("config", "cfg"),
        ".pre-commit-config.yaml": ("lint", "yaml"),
        "tsconfig.json": ("typescript", "json"),
        "deno.json": ("typescript", "json"),
        "deno.jsonc": ("typescript", "jsonc"),
    }

    # 要忽略的目录
    IGNORE_DIRS = {
        ".git", "__pycache__", "node_modules", ".venv", "venv",
        ".env", ".tox", "build", "dist", ".egg-info", "target",
        ".next", ".nuxt", ".output", "coverage", ".idea", ".vscode",
        ".mypy_cache", ".pytest_cache", ".ruff_cache", ".DS_Store",
    }

    # 源码文件后缀（用于统计技术栈）
    SOURCE_EXTS = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".rs", ".go", ".java",
        ".rb", ".php", ".swift", ".kt", ".scala", ".c", ".cpp", ".h",
        ".hpp", ".cs", ".vue", ".svelte", ".r", ".m", ".mm",
    }

    def __init__(self, project_root: str = "."):
        self.root = Path(project_root).resolve()
        # knowledge: { category: [fact_string, ...] }
        self.knowledge: Dict[str, List[str]] = {}

    # ── 主入口 ──

    def scan(self, max_depth: int = 3) -> Dict[str, List[str]]:
        """执行完整项目扫描"""
        self.knowledge = {}
        self._read_readme()
        self._read_config_files()
        self._detect_tech_stack()
        self._scan_structure(max_depth)
        self._detect_architecture()
        self._analyze_entry_points()
        self._analyze_python_code()
        self._detect_conventions()
        self._detect_test_framework()
        self._detect_ci_cd()
        return self.knowledge

    def learn_from_file(self, filepath: str) -> List[tuple]:
        """从单个文件提取知识（供自动学习使用）"""
        fpath = Path(filepath).resolve()
        if self._is_ignored(fpath) or not fpath.is_file():
            return []
        facts = []
        ext = fpath.suffix.lower()
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return []

        rel = str(fpath.relative_to(self.root)) if fpath != self.root else fpath.name

        if ext == ".py":
            # 提取类和函数
            classes = re.findall(r'^class\s+(\w+)', content, re.MULTILINE)
            for c in classes:
                facts.append((f"文件 {rel} 定义了类: {c}", 0.55, ["project_knowledge", "code_structure"]))
            funcs = re.findall(r'^async?\s+def\s+(\w+)', content, re.MULTILINE)
            for f in funcs[:5]:
                facts.append((f"文件 {rel} 定义了函数: {f}", 0.5, ["project_knowledge", "code_structure"]))
            # 导入
            imports = re.findall(r'^(?:from\s+[\w.]+\s+)?import\s+[\w,\s]+', content, re.MULTILINE)
            if imports and len(imports) <= 8:
                facts.append((f"文件 {rel} 导入了: {len(imports)} 个模块",
                              0.45, ["project_knowledge", "deps"]))

        elif ext in (".js", ".ts"):
            classes = re.findall(r'(?:export\s+)?(?:default\s+)?class\s+(\w+)', content)
            for c in classes[:3]:
                facts.append((f"文件 {rel} 定义了类: {c}", 0.55, ["project_knowledge", "code_structure"]))
            funcs = re.findall(r'(?:export\s+)?(?:async\s+)?function\s+(\w+)', content)
            for f in funcs[:3]:
                facts.append((f"文件 {rel} 定义了函数: {f}", 0.5, ["project_knowledge", "code_structure"]))

        return facts

    def to_simple_facts(self) -> str:
        """生成小模型易读的平铺陈述列表（每行一个事实）"""
        if not self.knowledge:
            return ""
        lines = ["【项目知识】"]
        for cat, items in self.knowledge.items():
            if cat == "structure":
                # 跳过目录结构（容易变旧，以实际文件系统为准）
                continue
            for item in items:
                clean = item.replace("📁 ", "").replace("📄 ", "")
                lines.append(f"- {clean}")
        context = "\n".join(lines[:10])  # 最多 10 条
        return context

    def to_context_string(self) -> str:
        """格式化为 LLM 上下文"""
        if not self.knowledge:
            return ""
        parts = ["【项目知识】"]
        for cat, items in self.knowledge.items():
            cat_label = {
                "project_info": "项目信息",
                "tech_stack": "技术栈",
                "structure": "目录结构",
                "architecture": "架构",
                "conventions": "开发规范",
                "tools": "工具配置",
                "testing": "测试",
            }.get(cat, cat)
            if items:
                parts.append(f"  {cat_label}:")
                for item in items[:8]:  # 每类最多 8 条
                    parts.append(f"    - {item}")
        return "\n".join(parts)

    def to_memory_facts(self) -> List[tuple]:
        """转换为 (fact_text, importance, tags) 列表，用于存入记忆"""
        facts = []
        for cat, items in self.knowledge.items():
            for item in items:
                facts.append((item, 0.7, ["project_knowledge", cat]))
        return facts

    # ── README ──

    def _read_readme(self):
        """从 README 提取项目名和描述"""
        for name in ["README.md", "README.txt", "README", "Readme.md"]:
            fpath = self.root / name
            if fpath.exists():
                text = fpath.read_text(encoding="utf-8", errors="ignore")[:3000]
                lines = text.strip().split("\n")
                # 第一行通常是标题
                title = ""
                for line in lines:
                    line = line.strip().strip("#* ").strip()
                    if line and len(line) > 2:
                        title = line
                        break
                if title:
                    self.knowledge.setdefault("project_info", []).append(f"项目名称: {title}")
                # 提取描述（标题后的非空段落）
                desc_lines = []
                for line in lines[1:]:
                    stripped = line.strip().strip("#* ").strip()
                    if stripped and len(stripped) > 10 and not stripped.startswith("![") and not stripped.startswith("["):
                        desc_lines.append(stripped)
                    if len(desc_lines) >= 3:
                        break
                if desc_lines:
                    desc = " ".join(desc_lines)[:200]
                    self.knowledge.setdefault("project_info", []).append(f"项目描述: {desc}")
                return
        self.knowledge.setdefault("project_info", []).append(f"项目目录: {self.root.name}")

    # ── 配置文件 ──

    def _read_config_files(self):
        """读取关键配置文件"""
        for fname, (lang, fmt) in self.CONFIG_FILES.items():
            fpath = self.root / fname
            if fpath.exists():
                try:
                    content = fpath.read_text(encoding="utf-8", errors="ignore")[:2000]
                    self._parse_config(fname, lang, fmt, content)
                except Exception:
                    pass

    def _parse_config(self, fname: str, lang: str, fmt: str, content: str):
        """解析配置文件提取关键信息"""
        if fname == "pyproject.toml":
            m = re.search(r'name\s*=\s*"([^"]+)"', content)
            if m:
                self.knowledge.setdefault("project_info", []).append(f"包名: {m.group(1)}")
            m = re.search(r'version\s*=\s*"([^"]+)"', content)
            if m:
                self.knowledge.setdefault("project_info", []).append(f"版本: {m.group(1)}")
            # Python 版本要求
            m = re.search(r'requires-python\s*=\s*"([^"]+)"', content)
            if m:
                self.knowledge.setdefault("tech_stack", []).append(f"Python: {m.group(1)}")
            # 依赖
            deps = re.findall(r'^([a-zA-Z0-9_.-]+)\s*[=~><]', content, re.MULTILINE)
            if deps:
                self.knowledge.setdefault("tech_stack", []).append(f"依赖: {', '.join(deps[:8])}")

        elif fname == "package.json":
            try:
                data = json.loads(content)
                if "name" in data:
                    self.knowledge.setdefault("project_info", []).append(f"包名: {data['name']}")
                if "description" in data:
                    self.knowledge.setdefault("project_info", []).append(f"描述: {data['description']}")
                deps = list(data.get("dependencies", {}).keys()) + list(data.get("devDependencies", {}).keys())
                if deps:
                    self.knowledge.setdefault("tech_stack", []).append(f"依赖: {', '.join(deps[:10])}")
            except json.JSONDecodeError:
                pass

        elif fname == ".editorconfig":
            # 提取缩进等规范
            m = re.search(r'indent_style\s*=\s*(\w+)', content)
            if m:
                self.knowledge.setdefault("conventions", []).append(f"缩进风格: {m.group(1)}")
            m = re.search(r'indent_size\s*=\s*(\d+)', content)
            if m:
                self.knowledge.setdefault("conventions", []).append(f"缩进大小: {m.group(1)}")
            m = re.search(r'end_of_line\s*=\s*(\w+)', content)
            if m:
                self.knowledge.setdefault("conventions", []).append(f"换行符: {m.group(1)}")
            m = re.search(r'charset\s*=\s*(\w+)', content)
            if m:
                self.knowledge.setdefault("conventions", []).append(f"字符集: {m.group(1)}")

    # ── 技术栈检测 ──

    def _is_ignored(self, path: Path) -> bool:
        """检查路径是否在忽略列表中"""
        try:
            for p in path.relative_to(self.root).parts:
                if p in self.IGNORE_DIRS or p.startswith("."):
                    return True
        except ValueError:
            return True
        return False

    def _detect_tech_stack(self):
        """通过源码文件后缀检测技术栈（排除忽略目录和隐藏目录）"""
        lang_counts = {}
        src_files = []
        for fpath in self.root.rglob("*"):
            if not fpath.is_file():
                continue
            if self._is_ignored(fpath):
                continue
            if fpath.suffix.lower() in self.SOURCE_EXTS:
                rel = fpath.relative_to(self.root)
                lang_counts[fpath.suffix.lower()] = lang_counts.get(fpath.suffix.lower(), 0) + 1
                if len(src_files) < 50:
                    src_files.append(str(rel))

        lang_names = {
            ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
            ".jsx": "React(JSX)", ".tsx": "React(TSX)", ".rs": "Rust",
            ".go": "Go", ".java": "Java", ".rb": "Ruby",
            ".php": "PHP", ".swift": "Swift", ".kt": "Kotlin",
            ".c": "C", ".cpp": "C++", ".h": "C Header",
            ".cs": "C#", ".vue": "Vue", ".svelte": "Svelte",
        }

        detected = []
        for ext, count in sorted(lang_counts.items(), key=lambda x: x[1], reverse=True):
            name = lang_names.get(ext, ext)
            detected.append(f"{name}({count}个文件)")
        if detected:
            self.knowledge.setdefault("tech_stack", []).append(f"语言: {'; '.join(detected[:5])}")
            self.knowledge.setdefault("structure", []).append(f"源码文件数: {sum(lang_counts.values())}")

    # ── 目录结构 ──

    def _scan_structure(self, max_depth: int = 3):
        """扫描顶层目录结构"""
        entries = sorted(self.root.iterdir(), key=lambda x: (not x.is_dir(), x.name))
        lines = []
        for e in entries[:30]:
            if e.name in self.IGNORE_DIRS:
                continue
            if e.is_dir():
                sub_count = 0
                for _ in e.rglob("*"):
                    if _.is_file() and not self._is_ignored(_):
                        sub_count += 1
                lines.append(f"📁 {e.name}/ ({sub_count}个文件)")
            elif e.suffix.lower() in self.SOURCE_EXTS:
                size = e.stat().st_size
                size_str = f"{size}B" if size < 1024 else f"{size//1024}KB"
                lines.append(f"📄 {e.name} ({size_str})")
        if lines:
            self.knowledge.setdefault("structure", []).append(f"根目录: {'; '.join(lines[:12])}")

    # ── 测试框架 ──

    def _detect_test_framework(self):
        """检测测试配置"""
        test_indicators = {
            "pytest": [".pytest_cache", "pytest.ini", "pyproject.toml"],
            "jest": ["jest.config.js", "jest.config.ts", "jest.setup.js"],
            "go test": ["*_test.go"],
            "cargo test": ["Cargo.toml"],
            "vitest": ["vitest.config.ts", "vitest.config.js"],
        }
        for framework, indicators in test_indicators.items():
            for ind in indicators:
                if ind.startswith("*"):
                    if list(self.root.rglob(ind[1:])):
                        self.knowledge.setdefault("testing", []).append(f"测试框架: {framework}")
                        break
                elif (self.root / ind).exists():
                    self.knowledge.setdefault("testing", []).append(f"测试框架: {framework}")
                    break


    # ── 架构检测 ──

    def _detect_architecture(self):
        """检测项目架构模式和框架"""
        arch_facts = []
        py_files = list(self.root.rglob("*.py"))

        # 检测 Web 框架
        for f in py_files:
            if self._is_ignored(f):
                continue
            try:
                text = f.read_text("utf-8", errors="ignore")[:500]
            except Exception:
                continue
            if "from fastapi" in text or "import fastapi" in text:
                arch_facts.append("Web框架: FastAPI")
                break
            if "from flask" in text or "import flask" in text:
                arch_facts.append("Web框架: Flask")
                break
            if "from django" in text:
                arch_facts.append("Web框架: Django")
                break

        # 检测 ORM
        for f in py_files:
            if self._is_ignored(f):
                continue
            try:
                text = f.read_text("utf-8", errors="ignore")[:500]
            except Exception:
                continue
            if "from sqlalchemy" in text or "import sqlalchemy" in text:
                arch_facts.append("ORM: SQLAlchemy")
                break
            if "from tortoise" in text:
                arch_facts.append("ORM: Tortoise ORM")
                break
            if "from beanie" in text or "from mongoengine" in text:
                arch_facts.append("ORM: MongoDB ODM")
                break

        # 检测 CLI 框架
        for f in py_files:
            if self._is_ignored(f):
                continue
            try:
                text = f.read_text("utf-8", errors="ignore")[:500]
            except Exception:
                continue
            if "import typer" in text or "from typer" in text:
                arch_facts.append("CLI框架: Typer")
                break
            if "import click" in text or "from click" in text:
                arch_facts.append("CLI框架: Click")
                break
            if "import argparse" in text or "from argparse" in text:
                arch_facts.append("CLI方式: argparse")
                break

        # 检测异步框架
        for f in py_files:
            if self._is_ignored(f):
                continue
            try:
                text = f.read_text("utf-8", errors="ignore")[:500]
            except Exception:
                continue
            if "import asyncio" in text or "from asyncio" in text:
                arch_facts.append("异步: asyncio")
                break

        # 检测类型注解使用
        type_hints = 0
        for f in py_files:
            if self._is_ignored(f) or type_hints > 3:
                continue
            try:
                text = f.read_text("utf-8", errors="ignore")
                if ": " in text and "-> " in text:
                    type_hints += 1
            except Exception:
                continue
        if type_hints >= 2:
            arch_facts.append("编码风格: 使用类型注解")

        # 检测项目类型
        if any((self.root / n).exists() for n in ["setup.py", "pyproject.toml"]):
            arch_facts.append("项目类型: Python 包/库")
        if (self.root / "Dockerfile").exists():
            arch_facts.append("部署: Docker")
        if (self.root / "docker-compose.yml").exists() or (self.root / "docker-compose.yaml").exists():
            arch_facts.append("部署: Docker Compose")
        if (self.root / "Makefile").exists():
            arch_facts.append("构建工具: Make")

        if arch_facts:
            self.knowledge["architecture"] = arch_facts

    # ── 入口分析 ──

    def _analyze_entry_points(self):
        """分析项目入口点"""
        # Python 入口
        for entry in ["main.py", "app.py", "cli.py", "run.py", "__main__.py"]:
            fpath = self.root / entry
            if fpath.exists():
                size = fpath.stat().st_size
                self.knowledge.setdefault("structure", []).append(f"入口文件: {entry} ({size//1024}KB)")
                # 检测入口文件中的路由/命令
                try:
                    text = fpath.read_text("utf-8", errors="ignore")[:1000]
                    routes = re.findall(r'@\w+\.(?:get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)', text)
                    for r in routes[:5]:
                        self.knowledge.setdefault("structure", []).append(f"路由: {r}")
                    commands = re.findall(r'@\w+\.(?:command|callback)\s*\(\s*["\']([^"\']+)', text)
                    for c in commands[:3]:
                        self.knowledge.setdefault("structure", []).append(f"命令: {c}")
                except Exception:
                    pass
                break

    # ── 代码分析 ──

    def _analyze_python_code(self):
        """分析 Python 源码提取关键结构"""
        py_files = sorted(self.root.rglob("*.py"))
        total_classes = 0
        total_funcs = 0
        module_summary = []

        for f in py_files[:30]:  # 只看前 30 个文件
            if self._is_ignored(f):
                continue
            try:
                text = f.read_text("utf-8", errors="ignore")
            except Exception:
                continue
            classes = re.findall(r'^class\s+(\w+)', text, re.MULTILINE)
            funcs = re.findall(r'^\s+(?:async\s+)?def\s+(\w+)', text, re.MULTILINE)
            total_classes += len(classes)
            total_funcs += len(funcs)
            if classes or funcs:
                rel = f.relative_to(self.root)
                module_summary.append(f"{rel} ({len(classes)}类, {len(funcs)}函数)")

        if total_classes > 0 or total_funcs > 0:
            self.knowledge.setdefault("structure", []).append(
                f"代码统计: {total_classes} 个类, {total_funcs} 个方法（扫描 {min(len(list(self.root.rglob('*.py'))), 30)} 个文件）"
            )
        if module_summary[:6]:
            self.knowledge.setdefault("structure", []).append(
                f"关键模块: {'; '.join(module_summary[:6])}"
            )

    # ── 规范提取 ──

    def _detect_conventions(self):
        """从配置文件提取编码规范"""
        # ruff 配置 (pyproject.toml)
        ruff_path = self.root / "pyproject.toml"
        if ruff_path.exists():
            try:
                text = ruff_path.read_text("utf-8", errors="ignore")
                # ruff 规则
                ruff_rules = re.findall(r'select\s*=\s*\[([^\]]+)\]', text)
                if ruff_rules:
                    rules = [r.strip().strip('"\'') for r in ruff_rules[0].split(",")]
                    self.knowledge.setdefault("conventions", []).append(f"Lint规则: {', '.join(rules[:5])}")
                # line-length
                ll = re.search(r'line-length\s*=\s*(\d+)', text)
                if ll:
                    self.knowledge.setdefault("conventions", []).append(f"行宽限制: {ll.group(1)}")
            except Exception:
                pass

        # .prettierrc / .prettierrc.json / .prettierrc.js
        for pf in [".prettierrc", ".prettierrc.json", ".prettierrc.js", ".prettierrc.yaml"]:
            pf_path = self.root / pf
            if pf_path.exists():
                try:
                    text = pf_path.read_text("utf-8", errors="ignore")
                    # 缩进
                    m = re.search(r'tabWidth["\']?\s*[:=]\s*(\d+)', text)
                    if m:
                        self.knowledge.setdefault("conventions", []).append(f"缩进: {m.group(1)}")
                    m = re.search(r'useTabs["\']?\s*[:=]\s*(true|false)', text)
                    if m and m.group(1) == "true":
                        self.knowledge.setdefault("conventions", []).append("缩进风格: Tab")
                    m = re.search(r'semi["\']?\s*[:=]\s*(true|false)', text)
                    if m:
                        self.knowledge.setdefault("conventions", []).append(f"分号: {m.group(1)}")
                    m = re.search(r'quote["\']?\s*[:=]\s*["\'](single|double)["\']', text)
                    if m:
                        self.knowledge.setdefault("conventions", []).append(f"引号: {m.group(1)}")
                except Exception:
                    pass
                break

        # .gitignore 内容摘要
        gitignore = self.root / ".gitignore"
        if gitignore.exists():
            try:
                lines = gitignore.read_text("utf-8", errors="ignore").strip().split("\n")
                if lines:
                    self.knowledge.setdefault("conventions", []).append(f"忽略规则: {len(lines)} 条")
            except Exception:
                pass

    # ── CI/CD ──

    def _detect_ci_cd(self):
        """检测 CI/CD 配置"""
        gh_actions = self.root / ".github" / "workflows"
        if gh_actions.exists():
            wfs = list(gh_actions.glob("*.yml")) + list(gh_actions.glob("*.yaml"))
            if wfs:
                names = []
                for wf in wfs:
                    try:
                        text = wf.read_text("utf-8", errors="ignore")[:200]
                        m = re.search(r'name:\s*(.+)$', text, re.MULTILINE)
                        if m:
                            names.append(m.group(1).strip())
                    except Exception:
                        pass
                self.knowledge.setdefault("tools", []).append(
                    f"CI: GitHub Actions ({', '.join(names[:3])})" if names else "CI: GitHub Actions"
                )


def test_scanner():
    """测试项目扫描器"""
    scanner = ProjectScanner(".")
    scanner.scan()
    print("=== 项目扫描结果 ===")
    for cat, items in scanner.knowledge.items():
        print(f"\n[{cat}]")
        for item in items:
            print(f"  - {item}")
    print()
    print("=== 上下文格式 ===")
    print(scanner.to_context_string())


if __name__ == "__main__":
    test_scanner()

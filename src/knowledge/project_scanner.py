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
        self._detect_test_framework()
        return self.knowledge

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

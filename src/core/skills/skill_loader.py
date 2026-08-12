"""
Skill 加载器 — 按用户意图匹配并加载技能指令

借鉴主流 AI 代码智能体（Claude Code 等）的 skill 设计：
- 每个 skill 是一个带 frontmatter 的 Markdown 文件
- frontmatter 含 name / description / trigger（触发关键词）
- LINK 根据用户输入匹配 trigger，把匹配的 skill 指令注入 system prompt

目录约定：SKILLS_DIR 下的 *.skill.md 文件。
"""

import os
import re
from typing import Dict, List, Optional

# skills 目录（项目根）
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SKILLS_DIR = os.path.join(_PROJECT_ROOT, "skills")


class Skill:
    """一个技能的定义"""

    def __init__(self, name: str, description: str, triggers: List[str],
                 body: str, core: str = "", filepath: str = ""):
        self.name = name
        self.description = description
        self.triggers = triggers  # 触发关键词
        self.body = body          # 完整技能文档（供开发者参考）
        self.core = core or body  # 注入 system prompt 的精简指令（默认全文）
        self.filepath = filepath

    def matches(self, text: str) -> bool:
        """判断用户输入是否命中该技能的触发关键词"""
        t = text.lower()
        return any(tg.lower() in t for tg in self.triggers)

    def to_system_block(self, max_chars: int = 1200) -> str:
        """生成可注入 system prompt 的指令块（渐进披露：只注入精简指令）"""
        core = self.core.strip()
        if len(core) > max_chars:
            core = core[:max_chars] + "\n…（完整 skill 文档见 skills 目录）"
        return f"## Skill: {self.name}（{self.description}）\n{core}\n"


class SkillLoader:
    """加载并匹配 skills"""

    def __init__(self, skills_dir: str = SKILLS_DIR):
        self.skills_dir = skills_dir
        self._skills: List[Skill] = []
        self._loaded = False

    def _parse_frontmatter(self, content: str) -> Optional[Dict]:
        """解析 Markdown frontmatter（--- 包裹的 YAML 简化版，支持 key: | 多行块）"""
        m = re.match(r'^---\s*\n(.*?)\n---\s*\n?(.*)$', content, re.DOTALL)
        if not m:
            return None
        fm_text, body = m.group(1), m.group(2)
        fm = {}
        lines = fm_text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            if ":" in line:
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip()
                if val == "|":
                    # 多行块：收集后续缩进行
                    block = []
                    i += 1
                    while i < len(lines) and (lines[i].startswith("  ") or lines[i].startswith("\t")):
                        block.append(lines[i].strip())
                        i += 1
                    fm[key] = "\n".join(block)
                    continue
                fm[key] = val
            i += 1
        return {"meta": fm, "body": body}

    def load(self) -> List[Skill]:
        """加载所有 skill 文件"""
        if self._loaded:
            return self._skills
        self._skills = []
        if not os.path.isdir(self.skills_dir):
            return self._skills
        for fname in sorted(os.listdir(self.skills_dir)):
            if not fname.endswith(".skill.md"):
                continue
            fpath = os.path.join(self.skills_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
                parsed = self._parse_frontmatter(content)
                if not parsed:
                    continue
                meta = parsed["meta"]
                name = meta.get("name", fname.replace(".skill.md", ""))
                desc = meta.get("description", "")
                triggers = [t.strip() for t in meta.get("trigger", "").split(",") if t.strip()]
                core = meta.get("core", "")
                self._skills.append(Skill(name, desc, triggers, parsed["body"], core, fpath))
            except (IOError, OSError) as e:
                print(f"[skill_loader] 加载 {fname} 失败: {e}")
        self._loaded = True
        return self._skills

    def match(self, text: str, max_skills: int = 3) -> List[Skill]:
        """按用户输入匹配 skill（按触发命中数降序）"""
        skills = self.load()
        scored = [(s, sum(1 for tg in s.triggers if tg.lower() in text.lower()))
                  for s in skills]
        matched = [s for s, score in scored if score > 0]
        matched.sort(key=lambda s: -sum(1 for tg in s.triggers if tg.lower() in text.lower()))
        return matched[:max_skills]

    def build_system_context(self, text: str) -> str:
        """为给定用户输入构建 skill 上下文块（注入 system prompt）"""
        matched = self.match(text)
        if not matched:
            return ""
        blocks = "\n".join(s.to_system_block() for s in matched)
        return f"\n【技能指令（请按需遵循）】\n{blocks}\n"


# 全局单例
_loader: Optional[SkillLoader] = None


def get_skill_loader() -> SkillLoader:
    """获取全局 SkillLoader 单例"""
    global _loader
    if _loader is None:
        _loader = SkillLoader()
    return _loader

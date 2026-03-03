"""
知识更新器模块

将反思和学习结果转化为可复用的知识，更新系统知识库。
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import os
from dataclasses import dataclass, field


@dataclass
class KnowledgeEntry:
    """知识条目"""
    id: str
    knowledge_type: str  # 知识类型：pattern, strategy, constraint, resource, error
    content: Dict[str, Any]  # 知识内容
    source_reflection_id: str  # 来源反思ID
    source_learning_id: Optional[str] = None  # 来源学习ID
    confidence: float = 0.5  # 置信度
    applicability: float = 0.5  # 适用性
    created_at: datetime = field(default_factory=datetime.now)
    last_used_at: Optional[datetime] = None
    usage_count: int = 0  # 使用次数
    tags: List[str] = field(default_factory=list)  # 标签


class KnowledgeUpdater:
    """知识更新器主类"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化知识更新器
        
        Args:
            config: 配置参数
        """
        # 默认配置
        self.config = {
            "enable_knowledge_updates": True,
            "knowledge_storage_path": "./data/knowledge/",  # 知识存储路径
            "min_confidence_threshold": 0.6,  # 最小置信度阈值
            "min_applicability_threshold": 0.5,  # 最小适用性阈值
            "max_knowledge_entries": 1000,  # 最大知识条目数
            "knowledge_consolidation_enabled": True,  # 是否启用知识整合
            "auto_save_interval": 300,  # 自动保存间隔（秒）
            "knowledge_types": ["pattern", "strategy", "constraint", "resource", "error"],
        }
        
        # 更新配置
        if config:
            self.config.update(config)
        
        # 知识存储
        self.knowledge_base: Dict[str, List[KnowledgeEntry]] = {}  # 按类型组织的知识
        self.knowledge_index: Dict[str, KnowledgeEntry] = {}  # ID到知识条目的索引
        
        # 状态跟踪
        self.last_save_time = datetime.now()
        self.logger = None
        
        # 初始化知识库
        self._initialize_knowledge_base()
    
    def set_logger(self, logger):
        """设置日志记录器"""
        self.logger = logger
    
    def _log(self, level: str, message: str):
        """记录日志"""
        if self.logger:
            if level == "debug":
                self.logger.debug(message)
            elif level == "info":
                self.logger.info(message)
            elif level == "warning":
                self.logger.warning(message)
            elif level == "error":
                self.logger.error(message)
    
    def _initialize_knowledge_base(self):
        """初始化知识库"""
        # 为每种知识类型创建空列表
        for knowledge_type in self.config["knowledge_types"]:
            self.knowledge_base[knowledge_type] = []
        
        # 尝试从文件加载现有知识
        self._load_knowledge_from_file()
    
    def _load_knowledge_from_file(self):
        """从文件加载知识"""
        storage_path = self.config.get("knowledge_storage_path", "./data/knowledge/")
        knowledge_file = os.path.join(storage_path, "knowledge_base.json")
        
        if not os.path.exists(knowledge_file):
            self._log("info", "知识库文件不存在，将创建新的知识库")
            return
        
        try:
            with open(knowledge_file, 'r', encoding='utf-8') as f:
                knowledge_data = json.load(f)
            
            # 解析知识数据
            loaded_count = 0
            for knowledge_type, entries in knowledge_data.items():
                if knowledge_type in self.knowledge_base:
                    for entry_data in entries:
                        # 转换时间字符串为datetime对象
                        entry_data["created_at"] = datetime.fromisoformat(entry_data["created_at"])
                        if entry_data.get("last_used_at"):
                            entry_data["last_used_at"] = datetime.fromisoformat(entry_data["last_used_at"])
                        
                        # 创建知识条目
                        knowledge_entry = KnowledgeEntry(**entry_data)
                        self.knowledge_base[knowledge_type].append(knowledge_entry)
                        self.knowledge_index[knowledge_entry.id] = knowledge_entry
                        loaded_count += 1
            
            self._log("info", f"从文件加载了 {loaded_count} 条知识")
            
        except Exception as e:
            self._log("error", f"加载知识库失败: {str(e)}")
    
    def _save_knowledge_to_file(self):
        """保存知识到文件"""
        if not self.config["enable_knowledge_updates"]:
            return
        
        storage_path = self.config.get("knowledge_storage_path", "./data/knowledge/")
        os.makedirs(storage_path, exist_ok=True)
        
        knowledge_file = os.path.join(storage_path, "knowledge_base.json")
        
        try:
            # 准备要保存的数据
            save_data = {}
            for knowledge_type, entries in self.knowledge_base.items():
                type_entries = []
                for entry in entries:
                    # 转换为可序列化的字典
                    entry_dict = {
                        "id": entry.id,
                        "knowledge_type": entry.knowledge_type,
                        "content": entry.content,
                        "source_reflection_id": entry.source_reflection_id,
                        "source_learning_id": entry.source_learning_id,
                        "confidence": entry.confidence,
                        "applicability": entry.applicability,
                        "created_at": entry.created_at.isoformat(),
                        "last_used_at": entry.last_used_at.isoformat() if entry.last_used_at else None,
                        "usage_count": entry.usage_count,
                        "tags": entry.tags,
                    }
                    type_entries.append(entry_dict)
                
                save_data[knowledge_type] = type_entries
            
            # 写入文件
            with open(knowledge_file, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, indent=2, ensure_ascii=False)
            
            self._log("debug", f"知识库已保存到 {knowledge_file}")
            
        except Exception as e:
            self._log("error", f"保存知识库失败: {str(e)}")
    
    def update_knowledge(self, reflection_result: Any, learning_outcome: Any):
        """
        更新知识库
        
        Args:
            reflection_result: 反思结果
            learning_outcome: 学习结果
        """
        if not self.config["enable_knowledge_updates"]:
            self._log("debug", "知识更新功能已禁用")
            return
        
        # 检查置信度和适用性阈值
        if (learning_outcome.confidence < self.config["min_confidence_threshold"] or
            learning_outcome.applicability_score < self.config["min_applicability_threshold"]):
            self._log("debug", f"学习结果置信度或适用性过低，跳过知识更新: "
                            f"置信度={learning_outcome.confidence:.2f}, "
                            f"适用性={learning_outcome.applicability_score:.2f}")
            return
        
        self._log("info", f"更新知识库: 反思 {reflection_result.id}, 学习 {learning_outcome.id}")
        
        # 根据学习类型确定知识类型
        knowledge_type = self._map_learning_to_knowledge_type(learning_outcome.learning_type)
        
        # 创建知识条目
        knowledge_entry = self._create_knowledge_entry(
            reflection_result=reflection_result,
            learning_outcome=learning_outcome,
            knowledge_type=knowledge_type
        )
        
        # 添加到知识库
        if knowledge_type in self.knowledge_base:
            self.knowledge_base[knowledge_type].append(knowledge_entry)
            self.knowledge_index[knowledge_entry.id] = knowledge_entry
            
            # 限制每种类型的知识条目数量
            max_entries = self.config.get("max_knowledge_entries_per_type", 200)
            if len(self.knowledge_base[knowledge_type]) > max_entries:
                # 按置信度和适用性排序，保留高质量条目
                self.knowledge_base[knowledge_type].sort(
                    key=lambda x: (x.confidence + x.applicability) / 2, 
                    reverse=True
                )
                self.knowledge_base[knowledge_type] = self.knowledge_base[knowledge_type][:max_entries]
            
            self._log("debug", f"已添加知识条目 {knowledge_entry.id} 到类型 {knowledge_type}")
        
        # 检查是否需要保存
        self._check_auto_save()
        
        # 检查是否需要知识整合
        if self.config.get("knowledge_consolidation_enabled", True):
            self._check_knowledge_consolidation()
    
    def _map_learning_to_knowledge_type(self, learning_type: Any) -> str:
        """将学习类型映射到知识类型"""
        learning_type_str = learning_type.value if hasattr(learning_type, 'value') else str(learning_type)
        
        mapping = {
            "pattern_recognition": "pattern",
            "strategy_improvement": "strategy", 
            "constraint_adjustment": "constraint",
            "resource_optimization": "resource",
            "error_recovery": "error",
        }
        
        return mapping.get(learning_type_str, "general")
    
    def _create_knowledge_entry(self, 
                                reflection_result: Any, 
                                learning_outcome: Any, 
                                knowledge_type: str) -> KnowledgeEntry:
        """创建知识条目"""
        import uuid
        
        # 提取关键信息
        key_insights = learning_outcome.key_insights
        action_items = learning_outcome.action_items
        
        # 创建知识内容
        knowledge_content = {
            "summary": learning_outcome.summary,
            "key_insights": key_insights,
            "action_items": action_items,
            "reflection_analysis": reflection_result.analysis,
            "root_causes": reflection_result.root_causes,
            "suggestions": reflection_result.suggestions,
            "trigger": reflection_result.trigger.value if hasattr(reflection_result.trigger, 'value') else str(reflection_result.trigger),
        }
        
        # 生成知识ID
        knowledge_id = f"knowledge_{uuid.uuid4().hex[:8]}"
        
        # 生成标签
        tags = self._generate_tags(reflection_result, learning_outcome, knowledge_type)
        
        return KnowledgeEntry(
            id=knowledge_id,
            knowledge_type=knowledge_type,
            content=knowledge_content,
            source_reflection_id=reflection_result.id,
            source_learning_id=learning_outcome.id,
            confidence=learning_outcome.confidence,
            applicability=learning_outcome.applicability_score,
            tags=tags,
        )
    
    def _generate_tags(self, reflection_result: Any, learning_outcome: Any, knowledge_type: str) -> List[str]:
        """生成知识标签"""
        tags = [knowledge_type]
        
        # 添加触发器标签
        trigger = reflection_result.trigger.value if hasattr(reflection_result.trigger, 'value') else str(reflection_result.trigger)
        tags.append(f"trigger:{trigger}")
        
        # 添加学习类型标签
        learning_type = learning_outcome.learning_type.value if hasattr(learning_outcome.learning_type, 'value') else str(learning_outcome.learning_type)
        tags.append(f"learning:{learning_type}")
        
        # 从关键洞察中提取关键词作为标签
        for insight in learning_outcome.key_insights[:3]:  # 取前3个关键洞察
            # 简单提取中文关键词（实际实现中可能需要更复杂的分词）
            if "超时" in insight:
                tags.append("timeout")
            if "权限" in insight:
                tags.append("permission")
            if "资源" in insight:
                tags.append("resource")
            if "连接" in insight:
                tags.append("connection")
            if "验证" in insight:
                tags.append("validation")
            if "约束" in insight:
                tags.append("constraint")
        
        # 去重
        return list(set(tags))
    
    def _check_auto_save(self):
        """检查自动保存"""
        current_time = datetime.now()
        time_since_last = (current_time - self.last_save_time).total_seconds()
        
        if time_since_last >= self.config.get("auto_save_interval", 300):
            self._save_knowledge_to_file()
            self.last_save_time = current_time
    
    def _check_knowledge_consolidation(self):
        """检查知识整合"""
        # 检查每种类型的知识条目数量
        total_entries = sum(len(entries) for entries in self.knowledge_base.values())
        max_total_entries = self.config.get("max_knowledge_entries", 1000)
        
        if total_entries > max_total_entries * 0.8:  # 当达到80%容量时进行整合
            self._consolidate_knowledge()
    
    def _consolidate_knowledge(self):
        """整合知识库"""
        self._log("info", "开始知识整合")
        
        consolidated_count = 0
        
        for knowledge_type, entries in self.knowledge_base.items():
            if len(entries) <= 10:  # 条目太少不需要整合
                continue
            
            # 按置信度和适用性排序
            entries.sort(key=lambda x: (x.confidence + x.applicability) / 2, reverse=True)
            
            # 保留高质量条目（前70%）
            keep_count = int(len(entries) * 0.7)
            self.knowledge_base[knowledge_type] = entries[:keep_count]
            
            consolidated_count += (len(entries) - keep_count)
            
            # 重建索引
            for entry in self.knowledge_base[knowledge_type]:
                self.knowledge_index[entry.id] = entry
        
        self._log("info", f"知识整合完成，删除了 {consolidated_count} 条低质量知识")
        
        # 保存整合后的知识库
        self._save_knowledge_to_file()
    
    def mark_reflection_applied(self, reflection_id: str):
        """
        标记反思已应用
        
        Args:
            reflection_id: 反思ID
        """
        # 查找与该反思相关的知识条目
        applied_entries = []
        for knowledge_type, entries in self.knowledge_base.items():
            for entry in entries:
                if entry.source_reflection_id == reflection_id:
                    entry.last_used_at = datetime.now()
                    entry.usage_count += 1
                    applied_entries.append(entry.id)
        
        if applied_entries:
            self._log("debug", f"反思 {reflection_id} 的应用已记录，更新了 {len(applied_entries)} 条知识")
        
        # 检查是否需要保存
        self._check_auto_save()
    
    def query_knowledge(self, 
                        query: str, 
                        knowledge_types: Optional[List[str]] = None,
                        min_confidence: float = 0.0,
                        limit: int = 10) -> List[KnowledgeEntry]:
        """
        查询知识库
        
        Args:
            query: 查询字符串
            knowledge_types: 知识类型过滤（如果为None则查询所有类型）
            min_confidence: 最小置信度阈值
            limit: 返回数量限制
            
        Returns:
            List[KnowledgeEntry]: 匹配的知识条目
        """
        results = []
        
        # 确定要查询的知识类型
        search_types = knowledge_types if knowledge_types else self.config["knowledge_types"]
        
        # 简单关键字匹配查询（实际实现中可能需要更复杂的搜索算法）
        query_lower = query.lower()
        
        for knowledge_type in search_types:
            if knowledge_type not in self.knowledge_base:
                continue
            
            for entry in self.knowledge_base[knowledge_type]:
                # 检查置信度阈值
                if entry.confidence < min_confidence:
                    continue
                
                # 检查是否匹配
                if self._knowledge_matches_query(entry, query_lower):
                    results.append(entry)
        
        # 按置信度和适用性排序
        results.sort(key=lambda x: (x.confidence + x.applicability) / 2, reverse=True)
        
        return results[:limit]
    
    def _knowledge_matches_query(self, knowledge_entry: KnowledgeEntry, query_lower: str) -> bool:
        """检查知识条目是否匹配查询"""
        # 检查标签匹配
        for tag in knowledge_entry.tags:
            if query_lower in tag.lower():
                return True
        
        # 检查知识内容匹配
        content = knowledge_entry.content
        
        # 检查总结
        if "summary" in content and query_lower in content["summary"].lower():
            return True
        
        # 检查关键洞察
        if "key_insights" in content:
            for insight in content["key_insights"]:
                if query_lower in insight.lower():
                    return True
        
        # 检查行动项
        if "action_items" in content:
            for action in content["action_items"]:
                if query_lower in action.lower():
                    return True
        
        # 检查反思分析
        if "reflection_analysis" in content and query_lower in content["reflection_analysis"].lower():
            return True
        
        # 检查根本原因
        if "root_causes" in content:
            for cause in content["root_causes"]:
                if query_lower in cause.lower():
                    return True
        
        # 检查建议
        if "suggestions" in content:
            for suggestion in content["suggestions"]:
                if query_lower in suggestion.lower():
                    return True
        
        return False
    
    def get_knowledge_stats(self) -> Dict[str, Any]:
        """获取知识库统计信息"""
        stats = {
            "total_entries": 0,
            "by_type": {},
            "confidence_stats": {
                "min": 1.0,
                "max": 0.0,
                "avg": 0.0,
            },
            "applicability_stats": {
                "min": 1.0,
                "max": 0.0,
                "avg": 0.0,
            },
            "usage_stats": {
                "total_usage": 0,
                "avg_usage_per_entry": 0.0,
            }
        }
        
        total_confidence = 0.0
        total_applicability = 0.0
        total_usage = 0
        entry_count = 0
        
        for knowledge_type, entries in self.knowledge_base.items():
            type_count = len(entries)
            stats["by_type"][knowledge_type] = type_count
            stats["total_entries"] += type_count
            
            for entry in entries:
                # 更新置信度统计
                stats["confidence_stats"]["min"] = min(stats["confidence_stats"]["min"], entry.confidence)
                stats["confidence_stats"]["max"] = max(stats["confidence_stats"]["max"], entry.confidence)
                total_confidence += entry.confidence
                
                # 更新适用性统计
                stats["applicability_stats"]["min"] = min(stats["applicability_stats"]["min"], entry.applicability)
                stats["applicability_stats"]["max"] = max(stats["applicability_stats"]["max"], entry.applicability)
                total_applicability += entry.applicability
                
                # 更新使用统计
                total_usage += entry.usage_count
                
                entry_count += 1
        
        # 计算平均值
        if entry_count > 0:
            stats["confidence_stats"]["avg"] = total_confidence / entry_count
            stats["applicability_stats"]["avg"] = total_applicability / entry_count
            stats["usage_stats"]["total_usage"] = total_usage
            stats["usage_stats"]["avg_usage_per_entry"] = total_usage / entry_count
        
        return stats
    
    def save_knowledge_base(self):
        """手动保存知识库"""
        self._save_knowledge_to_file()
        self._log("info", "知识库已手动保存")
    
    def clear_knowledge_base(self, knowledge_type: Optional[str] = None):
        """
        清空知识库
        
        Args:
            knowledge_type: 知识类型（如果为None则清空所有）
        """
        if knowledge_type:
            if knowledge_type in self.knowledge_base:
                self._log("warning", f"清空知识类型: {knowledge_type}")
                self.knowledge_base[knowledge_type] = []
        else:
            self._log("warning", "清空所有知识")
            for kt in self.knowledge_base:
                self.knowledge_base[kt] = []
            self.knowledge_index.clear()
        
        # 保存空的知识库
        self._save_knowledge_to_file()


# 便捷函数
def create_knowledge_updater(config: Dict[str, Any] = None) -> KnowledgeUpdater:
    """
    创建知识更新器的便捷函数
    
    Args:
        config: 配置参数
        
    Returns:
        知识更新器实例
    """
    return KnowledgeUpdater(config)
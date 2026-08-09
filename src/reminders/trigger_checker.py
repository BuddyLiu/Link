"""
触发器检查器模块

检查各种类型的提醒触发器条件是否满足。
"""

from typing import Dict, Any, Optional
from datetime import datetime
from enum import Enum


class TriggerType(Enum):
    """触发器类型"""
    TIME = "time"          # 时间触发
    CONDITION = "condition"  # 条件触发
    LOCATION = "location"  # 位置触发
    EVENT = "event"        # 事件触发


class TriggerChecker:
    """触发器检查器主类"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化触发器检查器
        
        Args:
            config: 配置参数
        """
        # 默认配置
        self.config = {
            "check_interval": 60,  # 检查间隔（秒）
            "enable_condition_checks": True,
            "enable_location_checks": False,
            "enable_event_checks": False,
            "location_accuracy_meters": 100,  # 位置精度（米）
            "max_condition_evaluation_time": 5,  # 最大条件评估时间（秒）
        }
        
        # 更新配置
        if config:
            self.config.update(config)
        
        # 组件引用
        self.logger = None
        self.location_service = None
        self.event_system = None
        self.memory_store = None  # 记忆源（用于 memory: 前缀条件）
        
        # 状态跟踪
        self.last_check_time = {}
        self.condition_cache = {}
    
    def set_components(self, location_service=None, event_system=None, memory_store=None):
        """设置依赖组件"""
        self.location_service = location_service
        self.event_system = event_system
        self.memory_store = memory_store
    
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
    
    def check_condition(self, reminder: Any, current_time: datetime) -> bool:
        """
        检查提醒条件是否满足
        
        Args:
            reminder: 提醒对象
            current_time: 当前时间
            
        Returns:
            bool: 条件是否满足
        """
        if reminder.trigger_type.value == "time":
            return self._check_time_trigger(reminder, current_time)
        
        elif reminder.trigger_type.value == "condition":
            return self._check_condition_trigger(reminder, current_time)
        
        elif reminder.trigger_type.value == "location":
            return self._check_location_trigger(reminder, current_time)
        
        elif reminder.trigger_type.value == "event":
            return self._check_event_trigger(reminder, current_time)
        
        return False
    
    def _check_time_trigger(self, reminder: Any, current_time: datetime) -> bool:
        """检查时间触发器"""
        # 时间触发器由ReminderManager处理，这里只返回False
        # 避免重复处理
        return False
    
    def _check_condition_trigger(self, reminder: Any, current_time: datetime) -> bool:
        """检查条件触发器"""
        if not self.config["enable_condition_checks"]:
            return False
        
        # 获取条件配置
        trigger_config = reminder.trigger_config
        
        # 检查条件类型
        condition_type = trigger_config.get("condition_type", "simple")
        
        if condition_type == "simple":
            return self._check_simple_condition(trigger_config, current_time)
        
        elif condition_type == "compound":
            return self._check_compound_condition(trigger_config, current_time)
        
        elif condition_type == "script":
            return self._check_script_condition(trigger_config, current_time)
        
        return False
    
    def _check_simple_condition(self, condition_config: Dict[str, Any], current_time: datetime) -> bool:
        """检查简单条件"""
        condition_key = condition_config.get("key", "")
        condition_operator = condition_config.get("operator", "equals")
        expected_value = condition_config.get("value")
        
        # 获取当前值（简化实现，实际应从数据源获取）
        current_value = self._get_current_value(condition_key)
        
        # 应用比较操作
        return self._apply_operator(current_value, condition_operator, expected_value)
    
    def _get_current_value(self, key: str) -> Any:
        """获取当前值（简化实现）"""
        # 在实际实现中，这里应该从系统状态、传感器、API等获取值
        # 这里返回一些模拟值用于测试
        
        if key == "system_time":
            return datetime.now().strftime("%H:%M")
        
        elif key == "cpu_usage":
            try:
                import psutil
                # psutil 首次调用 cpu_percent() 返回 0（只采样不计算），先校准再取真实值
                psutil.cpu_percent(None)
                return psutil.cpu_percent(interval=0.1)
            except Exception:
                # 降级：基于系统 uptime 估算（某些受限环境 cpu_percent 恒为 0）
                import os, time as _t
                try:
                    return round(100.0 - os.getloadavg()[0] / max(os.cpu_count() or 1, 1) * 100.0, 1)
                except Exception:
                    return None
        
        elif key == "memory_usage":
            import psutil
            return psutil.virtual_memory().percent
        
        elif key == "disk_usage":
            import psutil
            return psutil.disk_usage("/").percent
        
        elif key == "network_status":
            # 真实检测网络连通性（8.8.8.8 + 223.5.5.5 双源）
            import socket
            for host in ("8.8.8.8", "223.5.5.5"):
                try:
                    s = socket.create_connection((host, 53), timeout=1.5)
                    s.close()
                    return "online"
                except OSError:
                    continue
            return "offline"

        elif key == "battery_level":
            import psutil
            try:
                battery = psutil.sensors_battery()
                if battery:
                    return battery.percent
            except:
                pass
            return 100  # 默认值

        elif key == "weather_temperature":
            # 需要天气API，这里返回模拟值
            return 25

        elif key == "is_working_hours":
            current_hour = datetime.now().hour
            return 9 <= current_hour <= 17

        # 记忆条件源：memory:xxx → 查询记忆库（用户偏好/事实）
        elif key.startswith("memory:"):
            return self._get_memory_value(key)

        # 默认值
        return None

    def _get_memory_value(self, key: str) -> Any:
        """从记忆库获取条件值。

        key 格式:
          - memory:user_preference:咖啡 → 是否有"咖啡"相关偏好记忆 → bool
          - memory:fact:xxx → 是否有 xxx 事实 → bool
        """
        if not self.memory_store:
            return None
        try:
            parts = key.split(":", 2)
            mem_type = parts[1] if len(parts) > 1 else "preference"
            query = parts[2] if len(parts) > 2 else mem_type
            # 从记忆库检索
            results = self.memory_store.search_memories(query, n_results=5)
            if not results:
                return False
            # 检查是否有匹配类型的记忆
            for entry, _sim in results:
                t = str(getattr(entry, "memory_type", "")).lower()
                if mem_type in t or mem_type == "any":
                    return True
            return False
        except Exception:
            return None
    
    def _apply_operator(self, current_value: Any, operator: str, expected_value: Any) -> bool:
        """应用比较操作符"""
        try:
            if operator == "equals":
                return current_value == expected_value
            
            elif operator == "not_equals":
                return current_value != expected_value
            
            elif operator == "greater_than":
                return float(current_value) > float(expected_value)
            
            elif operator == "greater_than_or_equal":
                return float(current_value) >= float(expected_value)
            
            elif operator == "less_than":
                return float(current_value) < float(expected_value)
            
            elif operator == "less_than_or_equal":
                return float(current_value) <= float(expected_value)
            
            elif operator == "contains":
                return str(expected_value) in str(current_value)
            
            elif operator == "starts_with":
                return str(current_value).startswith(str(expected_value))
            
            elif operator == "ends_with":
                return str(current_value).endswith(str(expected_value))
            
            elif operator == "matches_regex":
                import re
                pattern = re.compile(str(expected_value))
                return bool(pattern.search(str(current_value)))
            
            elif operator == "is_true":
                return bool(current_value)
            
            elif operator == "is_false":
                return not bool(current_value)
            
            elif operator == "in_range":
                if isinstance(expected_value, (list, tuple)) and len(expected_value) >= 2:
                    min_val, max_val = expected_value[0], expected_value[1]
                    return min_val <= float(current_value) <= max_val
            
        except (ValueError, TypeError) as e:
            self._log("error", f"应用操作符失败: {operator}, 值: {current_value}, 期望: {expected_value}, 错误: {str(e)}")
        
        return False
    
    def _check_compound_condition(self, condition_config: Dict[str, Any], current_time: datetime) -> bool:
        """检查复合条件"""
        logical_operator = condition_config.get("logical_operator", "and")
        sub_conditions = condition_config.get("conditions", [])
        
        if not sub_conditions:
            return False
        
        results = []
        for sub_condition in sub_conditions:
            if isinstance(sub_condition, dict):
                condition_type = sub_condition.get("condition_type", "simple")
                if condition_type == "simple":
                    result = self._check_simple_condition(sub_condition, current_time)
                    results.append(result)
                else:
                    # 递归检查嵌套条件
                    result = self._check_compound_condition(sub_condition, current_time)
                    results.append(result)
        
        if not results:
            return False
        
        if logical_operator == "and":
            return all(results)
        elif logical_operator == "or":
            return any(results)
        elif logical_operator == "not":
            return not results[0] if results else False
        elif logical_operator == "xor":
            return sum(results) == 1  # 只有一个为真
        
        return False
    
    def _check_script_condition(self, condition_config: Dict[str, Any], current_time: datetime) -> bool:
        """检查脚本条件（安全简化实现）"""
        # 注意：在实际生产环境中，执行用户脚本需要严格的安全措施
        # 这里提供简化的脚本评估
        
        script_type = condition_config.get("script_type", "python_expr")
        script_content = condition_config.get("script", "")
        
        if script_type == "python_expr":
            # 只允许简单的Python表达式
            try:
                # 限制可用的内置函数
                safe_builtins = {
                    'abs': abs, 'all': all, 'any': any, 'bool': bool,
                    'dict': dict, 'float': float, 'int': int, 'len': len,
                    'list': list, 'max': max, 'min': min, 'pow': pow,
                    'round': round, 'str': str, 'sum': sum, 'tuple': tuple,
                }
                
                # 创建安全的命名空间
                namespace = {
                    '__builtins__': safe_builtins,
                    'datetime': datetime,
                    'current_time': current_time,
                }
                
                # 评估表达式
                result = eval(script_content, namespace)
                return bool(result)
                
            except Exception as e:
                self._log("error", f"评估脚本条件失败: {str(e)}")
                return False
        
        return False
    
    def _check_location_trigger(self, reminder: Any, current_time: datetime) -> bool:
        """检查位置触发器"""
        if not self.config["enable_location_checks"] or not self.location_service:
            return False
        
        trigger_config = reminder.trigger_config
        
        # 获取目标位置
        target_latitude = trigger_config.get("latitude")
        target_longitude = trigger_config.get("longitude")
        target_radius = trigger_config.get("radius_meters", 100)
        
        if target_latitude is None or target_longitude is None:
            return False
        
        # 获取当前位置
        try:
            current_location = self.location_service.get_current_location()
            if not current_location:
                return False
            
            # 计算距离
            distance = self._calculate_distance(
                current_location["latitude"], current_location["longitude"],
                target_latitude, target_longitude
            )
            
            # 检查是否在范围内
            trigger_type = trigger_config.get("trigger_type", "enter")
            
            if trigger_type == "enter":
                # 进入区域触发
                return distance <= target_radius
            
            elif trigger_type == "exit":
                # 离开区域触发
                return distance > target_radius
            
            elif trigger_type == "within":
                # 在区域内触发
                return distance <= target_radius
            
            elif trigger_type == "nearby":
                # 在附近触发（比目标半径稍大）
                nearby_radius = target_radius * 1.5
                return distance <= nearby_radius
            
        except Exception as e:
            self._log("error", f"检查位置触发器失败: {str(e)}")
        
        return False
    
    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """计算两个坐标点之间的距离（米）- 使用Haversine公式简化实现"""
        from math import radians, sin, cos, sqrt, atan2
        
        # 将角度转换为弧度
        lat1_rad = radians(lat1)
        lon1_rad = radians(lon1)
        lat2_rad = radians(lat2)
        lon2_rad = radians(lon2)
        
        # Haversine公式
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        
        a = sin(dlat/2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        
        # 地球半径（米）
        earth_radius = 6371000
        
        return earth_radius * c
    
    def _check_event_trigger(self, reminder: Any, current_time: datetime) -> bool:
        """检查事件触发器"""
        if not self.config["enable_event_checks"] or not self.event_system:
            return False
        
        trigger_config = reminder.trigger_config
        
        event_type = trigger_config.get("event_type")
        event_source = trigger_config.get("event_source")
        event_filter = trigger_config.get("event_filter", {})
        
        if not event_type:
            return False
        
        # 检查事件系统是否有匹配的事件
        try:
            recent_events = self.event_system.get_recent_events(
                event_type=event_type,
                source=event_source,
                since=reminder.last_triggered_at or reminder.created_at,
                filter_criteria=event_filter
            )
            
            # 如果有匹配的事件，则触发
            return len(recent_events) > 0
            
        except Exception as e:
            self._log("error", f"检查事件触发器失败: {str(e)}")
        
        return False
    
    def evaluate_condition(self, condition_expression: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        评估条件表达式
        
        Args:
            condition_expression: 条件表达式
            context: 上下文变量
            
        Returns:
            Dict[str, Any]: 评估结果
        """
        result = {
            "success": False,
            "result": False,
            "error": None,
            "evaluation_time": datetime.now().isoformat(),
        }
        
        try:
            # 解析条件表达式（简化实现）
            # 在实际实现中，应该使用更复杂的解析器
            
            # 这里简单地将条件表达式视为Python布尔表达式
            safe_globals = {
                'True': True,
                'False': False,
                'None': None,
                'datetime': datetime,
            }
            
            # 添加上下文变量
            if context:
                safe_globals.update(context)
            
            # 评估表达式
            eval_result = eval(condition_expression, {"__builtins__": {}}, safe_globals)
            
            result["success"] = True
            result["result"] = bool(eval_result)
            
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    def validate_condition_config(self, condition_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证条件配置
        
        Args:
            condition_config: 条件配置
            
        Returns:
            Dict[str, Any]: 验证结果
        """
        validation_result = {
            "valid": False,
            "errors": [],
            "warnings": [],
            "parsed_config": None,
        }
        
        try:
            # 检查必填字段
            if "condition_type" not in condition_config:
                validation_result["errors"].append("缺少 condition_type 字段")
            
            condition_type = condition_config.get("condition_type")
            
            if condition_type == "simple":
                # 验证简单条件
                if "key" not in condition_config:
                    validation_result["errors"].append("简单条件缺少 key 字段")
                if "operator" not in condition_config:
                    validation_result["errors"].append("简单条件缺少 operator 字段")
                if "value" not in condition_config:
                    validation_result["warnings"].append("简单条件缺少 value 字段，某些操作符可能需要")
                
                # 验证操作符
                valid_operators = [
                    "equals", "not_equals", "greater_than", "greater_than_or_equal",
                    "less_than", "less_than_or_equal", "contains", "starts_with",
                    "ends_with", "matches_regex", "is_true", "is_false", "in_range"
                ]
                
                operator = condition_config.get("operator")
                if operator and operator not in valid_operators:
                    validation_result["errors"].append(f"无效的操作符: {operator}")
            
            elif condition_type == "compound":
                # 验证复合条件
                if "logical_operator" not in condition_config:
                    validation_result["errors"].append("复合条件缺少 logical_operator 字段")
                if "conditions" not in condition_config:
                    validation_result["errors"].append("复合条件缺少 conditions 字段")
                
                logical_operator = condition_config.get("logical_operator")
                valid_logical_operators = ["and", "or", "not", "xor"]
                if logical_operator and logical_operator not in valid_logical_operators:
                    validation_result["errors"].append(f"无效的逻辑操作符: {logical_operator}")
                
                # 递归验证子条件
                sub_conditions = condition_config.get("conditions", [])
                for i, sub_condition in enumerate(sub_conditions):
                    if isinstance(sub_condition, dict):
                        sub_validation = self.validate_condition_config(sub_condition)
                        if not sub_validation["valid"]:
                            validation_result["errors"].extend([
                                f"子条件 {i}: {error}" for error in sub_validation["errors"]
                            ])
                            validation_result["warnings"].extend([
                                f"子条件 {i}: {warning}" for warning in sub_validation["warnings"]
                            ])
            
            elif condition_type == "script":
                # 验证脚本条件
                if "script" not in condition_config:
                    validation_result["errors"].append("脚本条件缺少 script 字段")
                
                # 检查脚本类型
                script_type = condition_config.get("script_type", "python_expr")
                valid_script_types = ["python_expr"]
                if script_type not in valid_script_types:
                    validation_result["errors"].append(f"无效的脚本类型: {script_type}")
            
            else:
                validation_result["errors"].append(f"未知的条件类型: {condition_type}")
            
            # 如果没有错误，标记为有效
            if not validation_result["errors"]:
                validation_result["valid"] = True
                validation_result["parsed_config"] = condition_config.copy()
        
        except Exception as e:
            validation_result["errors"].append(f"验证过程中发生错误: {str(e)}")
        
        return validation_result


# 便捷函数
def create_trigger_checker(config: Dict[str, Any] = None) -> TriggerChecker:
    """
    创建触发器检查器的便捷函数
    
    Args:
        config: 配置参数
        
    Returns:
        触发器检查器实例
    """
    return TriggerChecker(config)
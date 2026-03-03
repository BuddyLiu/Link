"""
通知发送器模块

通过不同渠道发送提醒通知。
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum
import os
import json


class NotificationChannel(Enum):
    """通知渠道"""
    CLI = "cli"              # 命令行界面
    DESKTOP = "desktop"      # 桌面通知
    EMAIL = "email"          # 电子邮件
    SMS = "sms"              # 短信
    MOBILE_APP = "mobile_app"  # 移动应用推送
    WEBHOOK = "webhook"      # Webhook
    LOG_FILE = "log_file"    # 日志文件


class NotificationSender:
    """通知发送器主类"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化通知发送器
        
        Args:
            config: 配置参数
        """
        # 默认配置
        self.config = {
            "default_channels": ["cli"],
            "cli_enabled": True,
            "desktop_enabled": False,
            "email_enabled": False,
            "sms_enabled": False,
            "mobile_app_enabled": False,
            "webhook_enabled": False,
            "log_file_enabled": True,
            "log_file_path": "./data/reminders/notifications.log",
            "max_notification_length": 500,  # 最大通知长度
            "notification_timeout": 30,      # 通知超时时间（秒）
            "retry_count": 3,                # 重试次数
            "retry_delay": 5,                # 重试延迟（秒）
        }
        
        # 更新配置
        if config:
            self.config.update(config)
        
        # 状态跟踪
        self.logger = None
        self.sent_notifications_count = 0
        self.failed_notifications_count = 0
        
        # 初始化日志文件
        if self.config["log_file_enabled"]:
            log_dir = os.path.dirname(self.config["log_file_path"])
            os.makedirs(log_dir, exist_ok=True)
    
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
    
    def send(self, 
             reminder: Any, 
             channels: Optional[List[str]] = None) -> bool:
        """
        发送提醒通知
        
        Args:
            reminder: 提醒对象
            channels: 通知渠道列表（如果为None则使用默认渠道）
            
        Returns:
            bool: 是否至少有一个渠道发送成功
        """
        if channels is None:
            channels = self.config["default_channels"]
        
        if not channels:
            self._log("warning", "没有指定通知渠道")
            return False
        
        self._log("info", f"发送提醒通知: {reminder.id} - {reminder.title}")
        
        # 准备通知内容
        notification_content = self._prepare_notification_content(reminder)
        
        # 发送到所有指定的渠道
        success_count = 0
        failure_count = 0
        
        for channel in channels:
            channel_success = self._send_to_channel(
                channel=channel,
                reminder=reminder,
                content=notification_content
            )
            
            if channel_success:
                success_count += 1
            else:
                failure_count += 1
        
        # 更新统计
        if success_count > 0:
            self.sent_notifications_count += 1
        else:
            self.failed_notifications_count += 1
        
        # 记录到日志文件
        if self.config["log_file_enabled"]:
            self._log_to_file(reminder, notification_content, success_count > 0)
        
        return success_count > 0
    
    def _prepare_notification_content(self, reminder: Any) -> Dict[str, Any]:
        """准备通知内容"""
        # 基础内容
        content = {
            "id": reminder.id,
            "title": reminder.title,
            "content": reminder.content,
            "trigger_type": reminder.trigger_type.value,
            "triggered_at": datetime.now().isoformat(),
            "priority": reminder.metadata.get("priority", "normal"),
            "category": reminder.metadata.get("category", "reminder"),
        }
        
        # 添加上下文信息
        if reminder.metadata:
            context = reminder.metadata.get("context", {})
            if context:
                content["context"] = context
        
        # 添加操作链接（如果有）
        actions = reminder.metadata.get("actions", [])
        if actions:
            content["actions"] = actions
        
        # 限制内容长度
        max_length = self.config.get("max_notification_length", 500)
        if len(str(content)) > max_length:
            content["content"] = content["content"][:max_length] + "..."
        
        return content
    
    def _send_to_channel(self, 
                         channel: str, 
                         reminder: Any, 
                         content: Dict[str, Any]) -> bool:
        """发送通知到指定渠道"""
        channel_enum = NotificationChannel(channel)
        
        try:
            if channel_enum == NotificationChannel.CLI:
                return self._send_to_cli(reminder, content)
            
            elif channel_enum == NotificationChannel.DESKTOP:
                return self._send_to_desktop(reminder, content)
            
            elif channel_enum == NotificationChannel.EMAIL:
                return self._send_to_email(reminder, content)
            
            elif channel_enum == NotificationChannel.SMS:
                return self._send_to_sms(reminder, content)
            
            elif channel_enum == NotificationChannel.MOBILE_APP:
                return self._send_to_mobile_app(reminder, content)
            
            elif channel_enum == NotificationChannel.WEBHOOK:
                return self._send_to_webhook(reminder, content)
            
            elif channel_enum == NotificationChannel.LOG_FILE:
                # 日志文件渠道总是成功
                return True
            
            else:
                self._log("warning", f"未知的通知渠道: {channel}")
                return False
                
        except Exception as e:
            self._log("error", f"发送到渠道 {channel} 失败: {str(e)}")
            return False
    
    def _send_to_cli(self, reminder: Any, content: Dict[str, Any]) -> bool:
        """发送到命令行界面"""
        if not self.config["cli_enabled"]:
            return False
        
        try:
            # 格式化输出
            print("\n" + "=" * 60)
            print(f"📢 提醒通知")
            print("=" * 60)
            print(f"标题: {reminder.title}")
            print(f"内容: {reminder.content}")
            print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"触发类型: {reminder.trigger_type.value}")
            print("=" * 60 + "\n")
            
            self._log("debug", f"CLI通知已发送: {reminder.id}")
            return True
            
        except Exception as e:
            self._log("error", f"发送CLI通知失败: {str(e)}")
            return False
    
    def _send_to_desktop(self, reminder: Any, content: Dict[str, Any]) -> bool:
        """发送到桌面通知"""
        if not self.config["desktop_enabled"]:
            return False
        
        try:
            # 尝试使用系统通知
            import platform
            
            system = platform.system()
            
            if system == "Darwin":  # macOS
                import subprocess
                apple_script = f'''
                display notification "{reminder.content}" with title "{reminder.title}"
                '''
                subprocess.run(["osascript", "-e", apple_script], check=False)
                
            elif system == "Linux":
                try:
                    import notify2
                    notify2.init("JARVIS Reminder")
                    notification = notify2.Notification(
                        reminder.title,
                        reminder.content,
                        "dialog-information"
                    )
                    notification.show()
                except ImportError:
                    # 使用其他方法或记录警告
                    self._log("warning", "桌面通知需要notify2库，请安装: pip install notify2")
                    return False
                
            elif system == "Windows":
                from win10toast import ToastNotifier
                toaster = ToastNotifier()
                toaster.show_toast(
                    reminder.title,
                    reminder.content,
                    duration=10,
                    threaded=True
                )
            
            self._log("debug", f"桌面通知已发送: {reminder.id}")
            return True
            
        except Exception as e:
            self._log("error", f"发送桌面通知失败: {str(e)}")
            return False
    
    def _send_to_email(self, reminder: Any, content: Dict[str, Any]) -> bool:
        """发送到电子邮件"""
        if not self.config["email_enabled"]:
            return False
        
        # 需要配置电子邮件设置
        email_config = self.config.get("email_config", {})
        if not email_config:
            self._log("warning", "电子邮件配置未设置")
            return False
        
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            # 创建邮件
            msg = MIMEMultipart()
            msg["From"] = email_config.get("from_email", "jarvis@example.com")
            msg["To"] = reminder.metadata.get("email", email_config.get("default_to"))
            msg["Subject"] = f"提醒: {reminder.title}"
            
            # 邮件正文
            body = f"""
            <html>
            <body>
                <h2>📢 提醒通知</h2>
                <p><strong>标题:</strong> {reminder.title}</p>
                <p><strong>内容:</strong> {reminder.content}</p>
                <p><strong>时间:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p><strong>触发类型:</strong> {reminder.trigger_type.value}</p>
                <hr>
                <p><em>这是来自JARVIS智能体的自动提醒。</em></p>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(body, "html"))
            
            # 发送邮件
            smtp_server = email_config.get("smtp_server", "smtp.gmail.com")
            smtp_port = email_config.get("smtp_port", 587)
            username = email_config.get("username", "")
            password = email_config.get("password", "")
            
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(username, password)
                server.send_message(msg)
            
            self._log("debug", f"电子邮件通知已发送: {reminder.id}")
            return True
            
        except Exception as e:
            self._log("error", f"发送电子邮件通知失败: {str(e)}")
            return False
    
    def _send_to_sms(self, reminder: Any, content: Dict[str, Any]) -> bool:
        """发送到短信"""
        if not self.config["sms_enabled"]:
            return False
        
        # 需要短信API配置
        sms_config = self.config.get("sms_config", {})
        if not sms_config:
            self._log("warning", "短信配置未设置")
            return False
        
        try:
            # 这里使用Twilio API作为示例
            # 实际实现中应该根据使用的短信服务提供商调整
            from twilio.rest import Client
            
            account_sid = sms_config.get("account_sid")
            auth_token = sms_config.get("auth_token")
            from_number = sms_config.get("from_number")
            to_number = reminder.metadata.get("phone_number", sms_config.get("default_to"))
            
            if not all([account_sid, auth_token, from_number, to_number]):
                self._log("error", "短信配置不完整")
                return False
            
            client = Client(account_sid, auth_token)
            
            message = client.messages.create(
                body=f"提醒: {reminder.title}\n{reminder.content}",
                from_=from_number,
                to=to_number
            )
            
            self._log("debug", f"短信通知已发送: {reminder.id}, 消息SID: {message.sid}")
            return True
            
        except ImportError:
            self._log("warning", "发送短信需要twilio库，请安装: pip install twilio")
            return False
        except Exception as e:
            self._log("error", f"发送短信通知失败: {str(e)}")
            return False
    
    def _send_to_mobile_app(self, reminder: Any, content: Dict[str, Any]) -> bool:
        """发送到移动应用"""
        if not self.config["mobile_app_enabled"]:
            return False
        
        # 需要移动推送服务配置
        push_config = self.config.get("push_config", {})
        if not push_config:
            self._log("warning", "移动推送配置未设置")
            return False
        
        try:
            # 这里使用Firebase Cloud Messaging作为示例
            import firebase_admin
            from firebase_admin import credentials, messaging
            
            # 初始化Firebase（如果未初始化）
            if not firebase_admin._apps:
                cred_path = push_config.get("credential_path")
                if cred_path and os.path.exists(cred_path):
                    cred = credentials.Certificate(cred_path)
                    firebase_admin.initialize_app(cred)
                else:
                    self._log("error", "Firebase凭证文件不存在")
                    return False
            
            # 获取设备令牌
            device_tokens = reminder.metadata.get("device_tokens", [])
            if not device_tokens:
                device_tokens = push_config.get("default_tokens", [])
            
            if not device_tokens:
                self._log("warning", "没有可用的设备令牌")
                return False
            
            # 创建消息
            message = messaging.MulticastMessage(
                notification=messaging.Notification(
                    title=reminder.title,
                    body=reminder.content,
                ),
                data={
                    "reminder_id": reminder.id,
                    "trigger_type": reminder.trigger_type.value,
                    "timestamp": datetime.now().isoformat(),
                },
                tokens=device_tokens,
            )
            
            # 发送消息
            response = messaging.send_multicast(message)
            
            self._log("debug", f"移动应用通知已发送: {reminder.id}, 成功: {response.success_count}, 失败: {response.failure_count}")
            return response.success_count > 0
            
        except ImportError:
            self._log("warning", "移动推送需要firebase-admin库，请安装: pip install firebase-admin")
            return False
        except Exception as e:
            self._log("error", f"发送移动应用通知失败: {str(e)}")
            return False
    
    def _send_to_webhook(self, reminder: Any, content: Dict[str, Any]) -> bool:
        """发送到Webhook"""
        if not self.config["webhook_enabled"]:
            return False
        
        # 获取Webhook配置
        webhook_url = reminder.metadata.get("webhook_url")
        if not webhook_url:
            webhook_url = self.config.get("default_webhook_url")
        
        if not webhook_url:
            self._log("warning", "Webhook URL未设置")
            return False
        
        try:
            import requests
            
            # 准备请求数据
            payload = {
                "event": "reminder_triggered",
                "timestamp": datetime.now().isoformat(),
                "reminder": content,
                "source": "jarvis"
            }
            
            # 发送请求
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "JARVIS-Reminder/1.0"
            }
            
            timeout = self.config.get("notification_timeout", 30)
            response = requests.post(
                webhook_url,
                json=payload,
                headers=headers,
                timeout=timeout
            )
            
            success = response.status_code in [200, 201, 202]
            
            if success:
                self._log("debug", f"Webhook通知已发送: {reminder.id}, 状态码: {response.status_code}")
            else:
                self._log("warning", f"Webhook通知失败: {reminder.id}, 状态码: {response.status_code}, 响应: {response.text[:100]}")
            
            return success
            
        except ImportError:
            self._log("warning", "Webhook需要requests库，请安装: pip install requests")
            return False
        except Exception as e:
            self._log("error", f"发送Webhook通知失败: {str(e)}")
            return False
    
    def _log_to_file(self, reminder: Any, content: Dict[str, Any], success: bool):
        """记录到日志文件"""
        try:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "reminder_id": reminder.id,
                "title": reminder.title,
                "success": success,
                "content": content,
            }
            
            with open(self.config["log_file_path"], "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
                
        except Exception as e:
            self._log("error", f"记录通知到文件失败: {str(e)}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取通知统计信息"""
        return {
            "sent_notifications": self.sent_notifications_count,
            "failed_notifications": self.failed_notifications_count,
            "total_notifications": self.sent_notifications_count + self.failed_notifications_count,
            "success_rate": (
                self.sent_notifications_count / (self.sent_notifications_count + self.failed_notifications_count)
                if (self.sent_notifications_count + self.failed_notifications_count) > 0 else 0
            ),
            "channels_enabled": {
                "cli": self.config["cli_enabled"],
                "desktop": self.config["desktop_enabled"],
                "email": self.config["email_enabled"],
                "sms": self.config["sms_enabled"],
                "mobile_app": self.config["mobile_app_enabled"],
                "webhook": self.config["webhook_enabled"],
                "log_file": self.config["log_file_enabled"],
            },
        }
    
    def test_channel(self, channel: str, test_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        测试通知渠道
        
        Args:
            channel: 渠道名称
            test_data: 测试数据
            
        Returns:
            Dict[str, Any]: 测试结果
        """
        result = {
            "channel": channel,
            "success": False,
            "error": None,
            "timestamp": datetime.now().isoformat(),
        }
        
        if test_data is None:
            test_data = {
                "title": "测试提醒",
                "content": "这是一个测试提醒通知，用于验证渠道配置。",
                "metadata": {
                    "priority": "test",
                    "category": "test",
                }
            }
        
        # 创建测试提醒对象
        class TestReminder:
            def __init__(self, data):
                self.id = "test_reminder_001"
                self.title = data["title"]
                self.content = data["content"]
                self.trigger_type = type('obj', (object,), {'value': 'test'})()
                self.metadata = data.get("metadata", {})
        
        test_reminder = TestReminder(test_data)
        
        try:
            success = self._send_to_channel(channel, test_reminder, test_data)
            result["success"] = success
            
            if not success:
                result["error"] = "发送失败，但未捕获具体错误"
                
        except Exception as e:
            result["error"] = str(e)
        
        return result


# 便捷函数
def create_notification_sender(config: Dict[str, Any] = None) -> NotificationSender:
    """
    创建通知发送器的便捷函数
    
    Args:
        config: 配置参数
        
    Returns:
        通知发送器实例
    """
    return NotificationSender(config)
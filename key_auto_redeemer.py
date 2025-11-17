import aiohttp
import re
import json
import logging
from typing import Set
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

# 配置日志
logger = logging.getLogger(__name__)

@register("KeyAutoRedeemer", "AstrBot", "QQ群卡密自动兑换插件", "1.0.0")
class KeyAutoRedeemer(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.redeemed_keys: Set[str] = set()
        self.key_pattern = re.compile(r'KEY_[a-f0-9]{32}', re.IGNORECASE)
        
        # 配置信息
        self.target_group_id = "180505621"  # 知弈题库群号
        self.redeem_url = "https://api.anqingyou.top/api/user/use-key"
        self.bearer_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NjM0NDEyMTgsImlhdCI6MTc2MzM1NDgxOCwidXNlcl9pZCI6Mjg3LCJ1c2VybmFtZSI6IjMxNDEifQ.OMYML0EI1gD6kedcHLyYyfn1WZiEHRatHPRB_2gFzk4"
        
        # 加载已兑换记录
        self.load_redeemed_keys()
        
        logger.info("卡密自动兑换插件初始化完成")

    def load_redeemed_keys(self):
        """加载已兑换的卡密记录"""
        try:
            with open("redeemed_keys.txt", "r", encoding="utf-8") as f:
                for line in f:
                    if "KEY_" in line:
                        key = line.split(" - ")[0].strip()
                        self.redeemed_keys.add(key)
            logger.info(f"已加载 {len(self.redeemed_keys)} 个已兑换卡密")
        except FileNotFoundError:
            logger.info("未找到已兑换记录文件，从头开始")

    def save_redeemed_key(self, key: str):
        """保存已兑换的卡密"""
        import time
        with open("redeemed_keys.txt", "a", encoding="utf-8") as f:
            f.write(f"{key} - {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    async def redeem_key(self, key_code: str) -> bool:
        """执行卡密兑换"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.bearer_token}',
            'Origin': 'https://anqingyou.top',
            'Referer': 'https://anqingyou.top/'
        }
        
        payload = {"code": key_code}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.redeem_url, json=payload, headers=headers, timeout=10) as response:
                    
                    response_text = await response.text()
                    logger.info(f"兑换请求: {key_code}, HTTP状态: {response.status}, 响应: {response_text}")
                    
                    if response.status == 200:
                        try:
                            result = json.loads(response_text)
                        except:
                            result = {"raw_response": response_text}
                        
                        # 判断兑换是否成功
                        success = (
                            result.get('success') is True or 
                            result.get('status') == 'success' or 
                            any(keyword in str(result).lower() for keyword in ['成功', '增加', '剩余', '有效'])
                        )
                        
                        if success:
                            logger.info(f"卡密兑换成功: {key_code}")
                            return True
                        else:
                            logger.warning(f"卡密兑换失败: {result}")
                            return False
                    elif response.status == 400:
                        logger.warning(f"卡密无效或已被使用: {key_code}")
                        return False
                    elif response.status == 401:
                        logger.error("Token已失效，请重新获取")
                        return False
                    else:
                        logger.error(f"HTTP错误 {response.status}: {response_text}")
                        return False

        except Exception as e:
            logger.error(f"兑换过程中出错: {e}")
            return False

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        """监听群消息事件"""
        try:
            # 检查是否来自目标群
            if event.group_id != self.target_group_id:
                return
            
            message_text = event.message_str
            logger.info(f"收到群消息: {message_text}")
            
            # 提取卡密
            found_keys = self.key_pattern.findall(message_text)
            
            for key in found_keys:
                normalized_key = key.upper()
                
                # 检查是否已兑换
                if normalized_key in self.redeemed_keys:
                    logger.info(f"跳过已兑换的卡密: {normalized_key}")
                    continue
                
                logger.info(f"发现新卡密: {normalized_key}")
                
                # 执行兑换
                success = await self.redeem_key(normalized_key)
                
                if success:
                    self.redeemed_keys.add(normalized_key)
                    self.save_redeemed_key(normalized_key)
                    # 可以发送成功通知（可选）
                    # yield event.plain_result(f"卡密 {normalized_key} 兑换成功！")
                else:
                    logger.error(f"卡密兑换失败: {normalized_key}")
                    # 即使失败也记录，避免重复尝试
                    self.redeemed_keys.add(normalized_key)
                    self.save_redeemed_key(f"FAILED_{normalized_key}")
                    
        except Exception as e:
            logger.error(f"处理群消息时出错: {e}")

    # 可选：添加管理命令用于手动操作
    @filter.command("兑换状态", alias={'状态', 'status'})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def check_status(self, event: AstrMessageEvent):
        """检查兑换插件状态"""
        status_msg = f"卡密自动兑换插件运行中\n已记录卡密数量: {len(self.redeemed_keys)}\n监控群号: {self.target_group_id}"
        yield event.plain_result(status_msg)

    @filter.command("手动兑换", alias={'redeem'})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def manual_redeem(self, event: AstrMessageEvent, key: str):
        """手动兑换卡密"""
        if not self.key_pattern.match(key):
            yield event.plain_result("卡密格式错误，请使用 KEY_xxxxxxxx 格式")
            return
        
        normalized_key = key.upper()
        if normalized_key in self.redeemed_keys:
            yield event.plain_result("该卡密已兑换过")
            return
        
        yield event.plain_result(f"正在手动兑换卡密: {normalized_key}")
        success = await self.redeem_key(normalized_key)
        
        if success:
            self.redeemed_keys.add(normalized_key)
            self.save_redeemed_key(normalized_key)
            yield event.plain_result("手动兑换成功！")
        else:
            yield event.plain_result("手动兑换失败")

    # 插件生命周期钩子
    @filter.on_astrbot_loaded()
    async def on_loaded(self):
        """Bot初始化完成时调用"""
        logger.info("AstrBot卡密兑换插件已就绪")

    @filter.after_message_sent()
    async def after_sent(self, event: AstrMessageEvent):
        """消息发送后记录日志"""
        logger.debug(f"消息已发送: {event.message_str}")

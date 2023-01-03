from typing import List, Dict
from pathlib import Path

from pydantic import BaseModel, Field

from nonebot import get_driver, logger
from ruamel import yaml

CONFIG_PATH = Path() / 'data' / 'learning_chat' / 'learning_chat.yml'
CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

driver = get_driver()
try:
    SUPERUSERS: List[int] = [int(s) for s in driver.config.superusers]
except Exception:
    SUPERUSERS = []
    logger.warning('请在.env.prod文件中中配置超级用户SUPERUSERS')

try:
    NICKNAME: str = list(driver.config.nickname)[0]
except Exception:
    NICKNAME = 'bot'


class ChatGroupConfig(BaseModel):
    enable: bool = Field(True, alias='群聊学习开关')
    ban_words: List[str] = Field([], alias='屏蔽词')
    ban_users: List[int] = Field([], alias='屏蔽用户')
    answer_threshold: int = Field(4, alias='回复阈值')
    answer_threshold_weights: List[int] = Field([10, 30, 60], alias='回复阈值权重')
    repeat_threshold: int = Field(3, alias='复读阈值')
    break_probability: float = Field(0.25, alias='打断复读概率')
    speak_enable: bool = Field(True, alias='主动发言开关')
    speak_threshold: int = Field(5, alias='主动发言阈值')
    speak_min_interval: int = Field(300, alias='主动发言最小间隔')
    speak_continuously_probability: float = Field(0.5, alias='连续主动发言概率')
    speak_continuously_max_len: int = Field(3, alias='最大连续主动发言句数')
    speak_poke_probability: float = Field(0.5, alias='主动发言附带戳一戳概率')

    def update(self, **kwargs):
        for key, value in kwargs.items():
            if key in self.__fields__:
                self.__setattr__(key, value)


class ChatConfig(BaseModel):
    total_enable: bool = Field(True, alias='群聊学习总开关')
    enable_web: bool = Field(True, alias='启用后台管理')
    web_username: str = Field('chat', alias='后台管理用户名')
    web_password: str = Field('admin', alias='后台管理密码')
    web_secret_key: str = Field('49c294d32f69b732ef6447c18379451ce1738922a75cd1d4812ef150318a2ed0',
                                alias='后台管理token密钥')
    ban_words: List[str] = Field([], alias='全局屏蔽词')
    ban_users: List[int] = Field([], alias='全局屏蔽用户')
    KEYWORDS_SIZE: int = Field(3, alias='单句关键词分词数量')
    cross_group_threshold: int = Field(3, alias='跨群回复阈值')
    learn_max_count: int = Field(6, alias='最高学习次数')
    dictionary: List[str] = Field([], alias='自定义词典')
    group_config: Dict[int, ChatGroupConfig] = Field({}, alias='分群配置')

    def update(self, **kwargs):
        for key, value in kwargs.items():
            if key in self.__fields__:
                self.__setattr__(key, value)


class ChatConfigManager:

    def __init__(self):
        self.file_path = CONFIG_PATH
        if self.file_path.exists():
            self.config = ChatConfig.parse_obj(
                yaml.load(self.file_path.read_text(encoding='utf-8'), Loader=yaml.Loader))
        else:
            self.config = ChatConfig()
        self.save()

    def get_group_config(self, group_id: int) -> ChatGroupConfig:
        if group_id not in self.config.group_config:
            self.config.group_config[group_id] = ChatGroupConfig()
            self.save()
        return self.config.group_config[group_id]

    @property
    def config_list(self) -> List[str]:
        return list(self.config.dict(by_alias=True).keys())

    def save(self):
        with self.file_path.open('w', encoding='utf-8') as f:
            yaml.dump(
                self.config.dict(by_alias=True),
                f,
                indent=2,
                Dumper=yaml.RoundTripDumper,
                allow_unicode=True)


config_manager = ChatConfigManager()

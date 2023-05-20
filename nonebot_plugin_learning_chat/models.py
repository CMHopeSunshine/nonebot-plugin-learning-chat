import functools
from functools import cached_property
from pathlib import Path
from typing import List, Dict, Any

try:
    import ujson as json
except ImportError:
    import json
try:
    import jieba_fast as jieba
    import jieba_fast.analyse as jieba_analyse
except ImportError:
    import jieba
    import jieba.analyse as jieba_analyse
from tortoise import fields, Tortoise
from tortoise.models import Model
from tortoise.connection import ConnectionHandler

from .config import config_manager, driver, log_info

DBConfigType = Dict[str, Any]


async def _init(self, db_config: "DBConfigType", create_db: bool):
    if self._db_config is None:
        self._db_config = db_config
    else:
        self._db_config.update(db_config)
    self._create_db = create_db
    await self._init_connections()


ConnectionHandler._init = _init

config = config_manager.config

DATABASE_PATH = Path() / 'data' / 'learning_chat' / 'learning_chat.db'
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
JSON_DUMPS = functools.partial(json.dumps, ensure_ascii=False)
jieba.setLogLevel(jieba.logging.INFO)
jieba.load_userdict(str(Path(__file__).parent / 'genshin_word.txt'))  # 加载原神词典
jieba.load_userdict(config.dictionary)  # 加载用户自定义的词典


class ChatMessage(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    group_id = fields.IntField()
    user_id = fields.IntField()
    message_id = fields.IntField()
    message = fields.TextField()
    raw_message = fields.TextField()
    plain_text = fields.TextField()
    time = fields.IntField()

    class Meta:
        table = 'message'
        indexes = ('group_id', 'time')
        ordering = ['-time']

    @cached_property
    def is_plain_text(self):
        return '[CQ:' not in self.message

    @cached_property
    def keyword_list(self):
        if not self.is_plain_text and not len(self.plain_text):
            return []
        return jieba_analyse.extract_tags(self.plain_text, topK=config.KEYWORDS_SIZE)

    @cached_property
    def keywords(self):
        if not self.is_plain_text and not len(self.plain_text):
            return self.message
        return (
            self.message if len(self.keyword_list) < 2 else ' '.join(self.keyword_list)
        )


class ChatContext(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    keywords = fields.TextField()
    time = fields.IntField()
    count = fields.IntField(default=1)
    answers: fields.ReverseRelation['ChatAnswer']

    class Meta:
        table = 'context'
        indexes = ('keywords', 'time')
        ordering = ['-time']


class ChatAnswer(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    keywords = fields.TextField()
    group_id = fields.IntField()
    count = fields.IntField(default=1)
    time = fields.IntField()
    messages = fields.JSONField(encoder=JSON_DUMPS, default=list)
    context = fields.ForeignKeyNullableRelation[ChatContext]

    class Meta:
        table = 'answer'
        indexes = ('keywords', 'time')
        ordering = ['-time']


class ChatBlackList(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    keywords = fields.TextField()
    global_ban = fields.BooleanField(default=False)
    ban_group_id = fields.JSONField(default=list)

    class Meta:
        table = 'blacklist'
        indexes = ('keywords',)


@driver.on_startup
async def startup():
    try:
        await Tortoise.init(
            db_url=f'sqlite://{DATABASE_PATH}', modules={'models': [__name__]}
        )
        await Tortoise.generate_schemas()
        log_info('群聊学习', '数据库连接成功')
    except Exception as e:
        log_info('群聊学习', f'数据库连接失败，{e}')
        raise e


@driver.on_shutdown
async def shutdown():
    await Tortoise.close_connections()
    log_info('群聊学习', '数据库断开连接成功')

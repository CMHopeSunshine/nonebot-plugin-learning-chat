import asyncio
import datetime
import random
import re
import time
from functools import cmp_to_key
from typing import List, Union, Optional, Tuple
from enum import IntEnum, auto
from nonebot import get_bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment, ActionFailed
from tortoise.functions import Count
from .models import ChatBlackList, ChatContext, ChatAnswer, ChatMessage
from .config import (
    config_manager,
    SUPERUSERS,
    NICKNAME,
    COMMAND_START,
    log_info,
    log_debug,
)

chat_config = config_manager.config

NO_PERMISSION_WORDS = [f"{NICKNAME}就喜欢说这个，哼！", f"你管得着{NICKNAME}吗！"]
ENABLE_WORDS = [f"{NICKNAME}会尝试学你们说怪话！", f"好的呢，让{NICKNAME}学学你们的说话方式~"]
DISABLE_WORDS = [f"好好好，{NICKNAME}不学说话就是了！", f"果面呐噻，{NICKNAME}以后不学了..."]
SORRY_WORDS = [
    f"{NICKNAME}知道错了...达咩!",
    f"{NICKNAME}不会再这么说了...",
    f"果面呐噻,{NICKNAME}说错话了...",
]
DOUBT_WORDS = [f"{NICKNAME}有说什么奇怪的话吗？"]
BREAK_REPEAT_WORDS = ["打断复读", "打断！"]
ALL_WORDS = (
    NO_PERMISSION_WORDS
    + SORRY_WORDS
    + DOUBT_WORDS
    + ENABLE_WORDS
    + DISABLE_WORDS
    + BREAK_REPEAT_WORDS
)


class Result(IntEnum):
    Learn = auto()
    Pass = auto()
    Repeat = auto()
    Ban = auto()
    SetEnable = auto()
    SetDisable = auto()


class LearningChat:
    def __init__(self, event: GroupMessageEvent):
        self.data = ChatMessage(
            group_id=event.group_id,
            user_id=event.user_id,
            message_id=event.message_id,
            message=re.sub(
                r'(\[CQ:at,qq=.+])|(\[CQ:reply,id=.+])',
                '',
                re.sub(r'(,subType=\d+,url=.+])', r']', event.raw_message),
            ).strip(),
            raw_message=event.raw_message,
            plain_text=event.get_plaintext(),
            time=event.time,
        )
        self.bot_id = event.self_id
        self.to_me = event.to_me or NICKNAME in self.data.message
        self.role = 'superuser' if event.user_id in SUPERUSERS else event.sender.role
        self.config = config_manager.get_group_config(self.data.group_id)
        self.ban_users = set(chat_config.ban_users + self.config.ban_users)
        self.ban_words = set(chat_config.ban_words + self.config.ban_words)
        self.reply = event.reply or None

    async def _learn(self) -> Result:
        def skip(reason):
            log_debug('群聊学习', f'➤{reason}，跳过')
            return Result.Pass

        if self.to_me and any(w in self.data.message for w in {'学说话', '快学', '开启学习'}):
            return Result.SetEnable
        elif self.to_me and any(w in self.data.message for w in {'闭嘴', '别学', '关闭学习'}):
            return Result.SetDisable
        elif not chat_config.total_enable or not self.config.enable:
            return skip(f'该群<{self.data.group_id}>未开启群聊学习')
        elif COMMAND_START and self.data.message.startswith(tuple(COMMAND_START)):
            return skip('该消息以命令前缀开头')
        elif self.data.user_id in self.ban_users:
            return skip(f'发言人<{self.data.user_id}>在屏蔽列表中')
        elif self.to_me and any(w in self.data.message for w in {'不可以', '达咩', '不能说这'}):
            return Result.Ban
        elif not await self._check_allow(self.data):
            return skip('消息未通过校验')
        elif self.reply:
            message = await ChatMessage.filter(message_id=self.reply.message_id).first()
            if not message:
                return skip('回复的消息不在数据库中')
            if message.user_id in self.ban_users:
                return skip('回复的人在屏蔽列表中')
            if not await self._check_allow(message):
                return skip('回复的消息未通过校验')
            await self._set_answer(message)
            return Result.Learn
        else:
            messages = await ChatMessage.filter(
                group_id=self.data.group_id, time__gte=self.data.time - 3600
            ).limit(5)
            if not messages:
                return Result.Pass
            if messages[0].message == self.data.message:
                return skip('复读中')
            for message in messages:
                if (
                    message.user_id not in self.ban_users
                    and set(self.data.keyword_list) & set(message.keyword_list)
                    and self.data.keyword_list != message.keyword_list
                    and await self._check_allow(message)
                ):
                    await self._set_answer(message)
                    return Result.Learn
            if messages[0].user_id in self.ban_users or not await self._check_allow(
                messages[0]
            ):
                return skip('最后一条消息未通过校验')
            await self._set_answer(messages[0])
            return Result.Learn

    async def answer(self) -> Optional[List[Union[MessageSegment, str]]]:
        """获取这句话的回复"""
        result = await self._learn()
        await self.data.save()

        if result == Result.Ban:
            # 禁用某句话
            if self.role not in {'superuser', 'admin', 'owner'}:
                # 检查权限
                return [random.choice(NO_PERMISSION_WORDS)]

            if self.reply:
                ban_result = await self._ban(message_id=self.reply.message_id)
            else:
                ban_result = await self._ban()

            if ban_result:
                return [random.choice(SORRY_WORDS)]
            else:
                return [random.choice(DOUBT_WORDS)]

        elif result in [Result.SetEnable, Result.SetDisable]:
            # 检查权限
            if self.role not in {'superuser', 'admin', 'owner'}:
                return [random.choice(NO_PERMISSION_WORDS)]

            self.config.update(enable=(result == Result.SetEnable))
            config_manager.config.group_config[self.data.group_id] = self.config
            config_manager.save()
            log_info(
                '群聊学习',
                f'群<m>{self.data.group_id}</m>{"开启" if result == Result.SetEnable else "关闭"}学习功能',
            )
            return [
                random.choice(
                    ENABLE_WORDS if result == Result.SetEnable else DISABLE_WORDS
                )
            ]

        elif result == Result.Pass:
            # 跳过
            return None

        elif result == Result.Repeat:
            if (
                await ChatMessage.filter(
                    group_id=self.data.group_id, time__gte=self.data.time - 3600
                )
                .limit(self.config.repeat_threshold + 5)
                .filter(user_id=self.bot_id, message=self.data.message)
                .exists()
            ):
                # 如果在阈值+5条消息内，bot已经回复过这句话，则跳过
                log_debug('群聊学习', '➤➤已经复读过了，跳过')
                return None

            if not (
                messages := await ChatMessage.filter(
                    group_id=self.data.group_id, time__gte=self.data.time - 3600
                ).limit(self.config.repeat_threshold)
            ):
                return None

            # 如果达到阈值，且不是全都为同一个人在说，则进行复读
            if (
                len(messages) >= self.config.repeat_threshold
                and all(message.message == self.data.message for message in messages)
                and any(message.user_id != self.data.user_id for message in messages)
            ):
                if random.random() < self.config.break_probability:
                    log_debug('群聊学习', '➤➤达到复读阈值，打断复读！')
                    return [random.choice(BREAK_REPEAT_WORDS)]
                else:
                    log_debug('群聊学习', f'➤➤达到复读阈值，复读<m>{messages[0].message}</m>')
                    return [self.data.message]

            return None

        else:
            # 回复
            if self.data.is_plain_text and len(self.data.plain_text) <= 1:
                log_debug('群聊学习', '➤➤消息过短，不回复')
                return None

            if not (
                context := await ChatContext.filter(keywords=self.data.keywords).first()
            ):
                log_debug('群聊学习', '➤➤尚未有已学习的回复，不回复')
                return None

            # 获取回复阈值
            if not self.to_me:
                answer_choices = list(
                    range(
                        self.config.answer_threshold
                        - len(self.config.answer_threshold_weights)
                        + 1,
                        self.config.answer_threshold + 1,
                    )
                )

                answer_count_threshold = random.choices(
                    answer_choices, weights=self.config.answer_threshold_weights
                )[0]

                if len(self.data.keyword_list) == chat_config.KEYWORDS_SIZE:
                    answer_count_threshold -= 1

                cross_group_threshold = chat_config.cross_group_threshold
            else:
                answer_count_threshold = 1
                cross_group_threshold = 1

            log_debug(
                '群聊学习',
                f'➤➤本次回复阈值为<m>{answer_count_threshold}</m>，跨群阈值为<m>{cross_group_threshold}</m>',
            )

            # 获取满足跨群条件的回复
            answers_cross = await ChatAnswer.filter(
                context=context,
                count__gte=answer_count_threshold,
                keywords__in=await ChatAnswer.annotate(cross=Count('keywords'))
                .group_by('keywords')
                .filter(cross__gte=cross_group_threshold)
                .values_list('keywords', flat=True),
            )

            answer_same_group = await ChatAnswer.filter(
                context=context,
                count__gte=answer_count_threshold,
                group_id=self.data.group_id,
            )

            candidate_answers: List[Optional[ChatAnswer]] = []

            # 检查候选回复是否在屏蔽列表中
            for answer in set(answers_cross) | set(answer_same_group):
                if not await self._check_allow(answer):
                    continue
                candidate_answers.append(answer)

            if not candidate_answers:
                log_debug('群聊学习', '➤➤没有符合条件的候选回复')
                return None

            # 从候选回复中进行选择
            sum_count = sum(answer.count for answer in candidate_answers)
            per_list = [
                answer.count / sum_count * (1 - 1 / answer.count)
                for answer in candidate_answers
            ]

            per_list.append(1 - sum(per_list))
            answer_dict = tuple(zip(candidate_answers, per_list))
            log_debug(
                '群聊学习',
                f'➤➤候选回复有<m>{"|".join([f"""{a.keywords}({round(p, 3)})""" for a, p in answer_dict])}|不回复({round(per_list[-1], 3)})</m>',
            )

            if (
                result := random.choices(candidate_answers + [None], weights=per_list)[
                    0
                ]
            ) is None:
                log_debug('群聊学习', '➤➤但不进行回复')
                return None

            result_message = random.choice(result.messages)
            log_debug('群聊学习', f'➤➤将回复<m>{result_message}</m>')
            await asyncio.sleep(random.random() + 0.5)
            return [result_message]

    async def _ban(self, message_id: Optional[int] = None) -> bool:
        """屏蔽消息"""
        bot = get_bot()
        if message_id:
            message = await ChatMessage.filter(message_id=message_id).first()
            if not message or message.message in ALL_WORDS:
                return False
            keywords = message.keywords
            try:
                await bot.delete_msg(message_id=message_id)
            except ActionFailed:
                log_info('群聊学习', f'待禁用消息<m>{message_id}</m>尝试撤回<r>失败</r>')
        else:
            last_reply = await ChatMessage.filter(
                group_id=self.data.group_id, user_id=self.bot_id
            ).first()
            if not last_reply or last_reply.message in ALL_WORDS:
                return False
            keywords = last_reply.keywords
            try:
                await bot.delete_msg(message_id=last_reply.message_id)
            except ActionFailed:
                log_info('群聊学习', f'待禁用消息<m>{last_reply.message_id}</m>尝试撤回<r>失败</r>')

        ban_word = await ChatBlackList.filter(keywords=keywords).first()
        if ban_word:
            if self.data.group_id not in ban_word.ban_group_id:
                ban_word.ban_group_id.append(self.data.group_id)
            if len(ban_word.ban_group_id) >= 2:
                ban_word.global_ban = True
                log_info('群聊学习', f'学习词<m>{keywords}</m>将被全局禁用')
                await ChatAnswer.filter(keywords=keywords).delete()
            else:
                log_info('群聊学习', f'群<m>{self.data.group_id}</m>禁用了学习词<m>{keywords}</m>')
                await ChatAnswer.filter(
                    keywords=keywords, group_id=self.data.group_id
                ).delete()
        else:
            log_info('群聊学习', f'群<m>{self.data.group_id}</m>禁用了学习词<m>{keywords}</m>')
            ban_word = ChatBlackList(
                keywords=keywords, ban_group_id=[self.data.group_id]
            )
            await ChatAnswer.filter(
                keywords=keywords, group_id=self.data.group_id
            ).delete()

        await ChatContext.filter(keywords=keywords).delete()
        await ban_word.save()
        return True

    @staticmethod
    async def add_ban(data: Union[ChatMessage, ChatContext, ChatAnswer]):
        if isinstance(data, ChatMessage):
            ban_group_id = [data.group_id]
            log_info('群聊学习', f'群<m>{data.group_id}</m>禁用了学习词<m>{data.keywords}</m>')
            await ChatAnswer.filter(
                keywords=data.keywords, group_id=data.group_id
            ).delete()
        else:
            ban_group_id = []
            log_info('群聊学习', f'学习词<m>{data.keywords}</m>将被全局禁用')
            await ChatAnswer.filter(keywords=data.keywords).delete()

        ban_word = await ChatBlackList.filter(keywords=data.keywords).first()
        if ban_word:
            ban_word.global_ban = True
            ban_word.ban_group_id.extend(ban_group_id)
        else:
            ban_word = ChatBlackList(
                keywords=data.keywords,
                ban_group_id=ban_group_id,
                global_ban=bool(ban_group_id),
            )

        await ChatContext.filter(keywords=data.keywords).delete()
        await ban_word.save()

    @staticmethod
    async def speak(
        self_id: int,
    ) -> Optional[Tuple[int, List[Union[str, MessageSegment]]]]:
        cur_time = int(time.time())
        today_time = time.mktime(datetime.date.today().timetuple())
        groups = (
            await ChatMessage.filter(time__gte=today_time)
            .annotate(count=Count('id'))
            .group_by('group_id')
            .filter(count__gte=10)
            .values_list('group_id', flat=True)
        )
        if not groups:
            return None
        total_messages = {
            group_id: await ChatMessage.filter(group_id=group_id, time__gte=today_time)
            for group_id in groups
        }
        total_messages = {
            group_id: messages
            for group_id, messages in total_messages.items()
            if messages
        }
        if not total_messages:
            return None

        # 根据消息平均间隔来对群进行排序
        def group_popularity_cmp(
            left_group: Tuple[int, List[ChatMessage]],
            right_group: Tuple[int, List[ChatMessage]],
        ):
            left_group_id, left_messages = left_group
            right_group_id, right_messages = right_group
            left_duration = left_messages[0].time - left_messages[-1].time
            right_duration = right_messages[0].time - right_messages[-1].time
            return (len(left_messages) / left_duration) - (
                len(right_messages) / right_duration
            )

        popularity: List[Tuple[int, List[ChatMessage]]] = sorted(
            total_messages.items(), key=cmp_to_key(group_popularity_cmp), reverse=True
        )
        log_debug(
            '群聊学习', f'主动发言：群热度排行<m>{">>".join([str(g[0]) for g in popularity])}</m>'
        )

        for group_id, messages in popularity:
            if len(messages) < 30:
                log_debug('群聊学习', f'主动发言：群<m>{group_id}</m>消息小于30条，不发言')
                continue

            config = config_manager.get_group_config(group_id)
            ban_words = {
                '[CQ:xml',
                '[CQ:json',
                '[CQ:at',
                '[CQ:video',
                '[CQ:record',
                '[CQ:share',
            }

            # 是否开启了主动发言
            if not config.speak_enable or not config.enable:
                log_debug('群聊学习', f'主动发言：群<m>{group_id}</m>未开启，不发言')
                continue

            # 如果最后一条消息是自己发的，则不主动发言
            last_reply = await ChatMessage.filter(
                group_id=group_id, user_id=self_id
            ).first()
            if last_reply and last_reply.time >= messages[0].time:
                log_debug(
                    '群聊学习',
                    f'主动发言：群<m>{group_id}</m>最后一条消息是{NICKNAME}发的{last_reply.message}，不发言',
                )
                continue
            elif last_reply and cur_time - last_reply.time < config.speak_min_interval:
                log_debug('群聊学习', f'主动发言：群<m>{group_id}</m>上次主动发言时间小于主动发言最小间隔，不发言')
                continue

            # 该群每多少秒发一条消息
            avg_interval = (messages[0].time - messages[-1].time) / len(messages)
            # 如果该群已沉默的时间小于阈值，则不主动发言
            silent_time = cur_time - messages[0].time
            threshold = avg_interval * config.speak_threshold
            if silent_time < threshold:
                log_debug(
                    '群聊学习',
                    f'主动发言：群<m>{group_id}</m>已沉默时间({silent_time})小于阈值({int(threshold)})，不发言',
                )
                continue

            contexts = await ChatContext.filter(
                count__gte=config.answer_threshold
            ).all()
            if contexts:
                speak_list = []
                random.shuffle(contexts)
                for context in contexts:
                    if (
                        not speak_list
                        or random.random() < config.speak_continuously_probability
                    ) and len(speak_list) < config.speak_continuously_max_len:
                        answers = await ChatAnswer.filter(
                            context=context,
                            group_id=group_id,
                            count__gte=config.answer_threshold,
                        )
                        if answers:
                            answer = random.choices(
                                answers,
                                weights=[
                                    answer.count + 1
                                    if answer.time >= today_time
                                    else answer.count
                                    for answer in answers
                                ],
                            )[0]
                            message = random.choice(answer.messages)
                            if len(message) < 2:
                                continue
                            if message.startswith('&#91;') and message.endswith(
                                '&#93;'
                            ):
                                continue
                            if any(word in message for word in ban_words):
                                continue
                            speak_list.append(message)
                            follow_answer = answer
                            while (
                                random.random() < config.speak_continuously_probability
                                and len(speak_list) < config.speak_continuously_max_len
                            ):
                                follow_context = await ChatContext.filter(
                                    keywords=follow_answer.keywords
                                ).first()
                                if follow_context:
                                    follow_answers = await ChatAnswer.filter(
                                        group_id=group_id,
                                        context=follow_context,
                                        count__gte=config.answer_threshold,
                                    )
                                    if follow_answers:
                                        follow_answer = random.choices(
                                            follow_answers,
                                            weights=[
                                                a.count + 1
                                                if a.time >= today_time
                                                else a.count
                                                for a in follow_answers
                                            ],
                                        )[0]
                                        message = random.choice(follow_answer.messages)
                                        if len(message) < 2:
                                            continue
                                        if message.startswith(
                                            '&#91;'
                                        ) and message.endswith('&#93;'):
                                            continue
                                        if all(
                                            word not in message for word in ban_words
                                        ):
                                            speak_list.append(message)
                                    else:
                                        break
                                else:
                                    break
                        else:
                            log_debug('群聊学习', f'主动发言：群<m>{group_id}</m>没有找到符合条件的发言，不发言')
                            break

                if speak_list:
                    if random.random() < config.speak_poke_probability:
                        last_speak_users = {
                            message.user_id
                            for message in messages[:5]
                            if message.user_id != self_id
                        }
                        select_user = random.choice(list(last_speak_users))
                        speak_list.append(MessageSegment('poke', {'qq': select_user}))
                    return group_id, speak_list
            else:
                log_debug('群聊学习', '主动发言：没有符合条件的群，不主动发言')
                return None

    async def _set_answer(self, message: ChatMessage):
        if context := await ChatContext.filter(keywords=message.keywords).first():
            if context.count < chat_config.learn_max_count:
                context.count += 1
            context.time = self.data.time
            if answer := await ChatAnswer.filter(
                keywords=self.data.keywords,
                group_id=self.data.group_id,
                context=context,
            ).first():
                if answer.count < chat_config.learn_max_count:
                    answer.count += 1
                answer.time = self.data.time
                if self.data.message not in answer.messages:
                    answer.messages.append(self.data.message)
            else:
                answer = ChatAnswer(
                    keywords=self.data.keywords,
                    group_id=self.data.group_id,
                    time=self.data.time,
                    context=context,
                    messages=[self.data.message],
                )
            await answer.save()
            await context.save()
        else:
            context = await ChatContext.create(
                keywords=message.keywords, time=self.data.time
            )
            answer = await ChatAnswer.create(
                keywords=self.data.keywords,
                group_id=self.data.group_id,
                time=self.data.time,
                context=context,
                messages=[self.data.message],
            )
        log_debug(
            '群聊学习', f'➤将被学习为<m>{message.message}</m>的回答，已学次数为<m>{answer.count}</m>'
        )

    async def _check_allow(self, message: Union[ChatMessage, ChatAnswer]) -> bool:
        raw_message = (
            message.message if isinstance(message, ChatMessage) else message.messages[0]
        )
        if any(
            i in raw_message
            for i in {
                '[CQ:xml',
                '[CQ:json',
                '[CQ:at',
                '[CQ:video',
                '[CQ:record',
                '[CQ:share',
            }
        ):
            return False
        if any(i in raw_message for i in self.ban_words):
            return False
        if raw_message.startswith('&#91;') and raw_message.endswith('&#93;'):
            return False
        ban_word = await ChatBlackList.filter(keywords=message.keywords).first()
        return (
            not ban_word
            or not ban_word.global_ban
            and message.group_id not in ban_word.ban_group_id
        )

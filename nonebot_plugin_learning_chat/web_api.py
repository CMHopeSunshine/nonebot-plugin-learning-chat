import datetime
from typing import Optional, Union

from fastapi import FastAPI
from fastapi import Header, HTTPException, Depends
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from jose import jwt
from nonebot import get_bot, get_app
from pydantic import BaseModel

try:
    import jieba_fast as jieba
except ImportError:
    import jieba

from .handler import LearningChat
from .models import ChatMessage, ChatContext, ChatAnswer, ChatBlackList
from .config import config_manager, driver
from .web_page import login_page, admin_app

requestAdaptor = '''
requestAdaptor(api) {
    api.headers["token"] = localStorage.getItem("token");
    return api;
},
'''
responseAdaptor = '''
responseAdaptor(api, payload, query, request, response) {
    if (response.data.detail == '登录验证失败或已失效，请重新登录') {
        window.location.href = '/LittlePaimon/login'
        window.localStorage.clear()
        window.sessionStorage.clear()
        window.alert('登录验证失败或已失效，请重新登录')
    }
    return payload
},
'''


def authentication():
    def inner(token: Optional[str] = Header(...)):
        try:
            payload = jwt.decode(token, config_manager.config.web_secret_key, algorithms='HS256')
            if not (username := payload.get('username')) or username != config_manager.config.web_username:
                raise HTTPException(status_code=400, detail='登录验证失败或已失效，请重新登录')
        except (jwt.JWTError, jwt.ExpiredSignatureError, AttributeError):
            raise HTTPException(status_code=400, detail='登录验证失败或已失效，请重新登录')

    return Depends(inner)


class UserModel(BaseModel):
    username: str
    password: str


@driver.on_startup
async def init_web():
    if not config_manager.config.enable_web:
        return
    app: FastAPI = get_app()

    @app.post('/learning_chat/api/login', response_class=JSONResponse)
    async def login(user: UserModel):
        if user.username != config_manager.config.web_username or user.password != config_manager.config.web_password:
            return {
                'status': -100,
                'msg':    '登录失败，请确认用户ID和密码无误'
            }
        token = jwt.encode({'username': user.username,
                            'exp':      datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
                                minutes=30)}, config_manager.config.web_secret_key, algorithm='HS256')
        return {
            'status': 0,
            'msg':    '登录成功',
            'data':   {
                'token': token
            }
        }

    @app.get('/learning_chat/api/get_group_list', response_class=JSONResponse, dependencies=[authentication()])
    async def get_group_list_api():
        try:
            group_list = await get_bot().get_group_list()
            group_list = [{'label': f'{group["group_name"]}({group["group_id"]})', 'value': group['group_id']} for group
                          in group_list]
            return {
                'status': 0,
                'msg':    'ok',
                'data':   {
                    'group_list': group_list
                }
            }
        except ValueError:
            return {
                'status': -100,
                'msg':    '获取群和好友列表失败，请确认已连接GOCQ'
            }

    @app.get('/learning_chat/api/chat_global_config', response_class=JSONResponse, dependencies=[authentication()])
    async def get_chat_global_config():
        try:
            bot = get_bot()
            groups = await bot.get_group_list()
            member_list = []
            for group in groups:
                members = await bot.get_group_member_list(group_id=group['group_id'])
                member_list.extend(
                    [{'label': f'{member["nickname"] or member["card"]}({member["user_id"]})',
                      'value': member['user_id']}
                     for
                     member in members])
            config = config_manager.config.dict(exclude={'group_config'})
            config['member_list'] = member_list
            return config
        except ValueError:
            return {
                'status': -100,
                'msg':    '获取群和好友列表失败，请确认已连接GOCQ'
            }

    @app.post('/learning_chat/api/chat_global_config', response_class=JSONResponse, dependencies=[authentication()])
    async def post_chat_global_config(data: dict):
        config_manager.config.update(**data)
        config_manager.save()
        await ChatContext.filter(count__gt=config_manager.config.learn_max_count).update(
            count=config_manager.config.learn_max_count)
        await ChatAnswer.filter(count__gt=config_manager.config.learn_max_count).update(
            count=config_manager.config.learn_max_count)
        jieba.load_userdict(config_manager.config.dictionary)
        return {
            'status': 0,
            'msg':    '保存成功'
        }

    @app.get('/learning_chat/api/chat_group_config', response_class=JSONResponse, dependencies=[authentication()])
    async def get_chat_global_config(group_id: int):
        try:
            members = await get_bot().get_group_member_list(group_id=group_id)
            member_list = [
                {'label': f'{member["nickname"] or member["card"]}({member["user_id"]})', 'value': member['user_id']}
                for member in members]
            config = config_manager.get_group_config(group_id).dict()
            config['break_probability'] = config['break_probability'] * 100
            config['speak_continuously_probability'] = config['speak_continuously_probability'] * 100
            config['speak_poke_probability'] = config['speak_poke_probability'] * 100
            config['member_list'] = member_list
            return config
        except ValueError:
            return {
                'status': -100,
                'msg':    '获取群和好友列表失败，请确认已连接GOCQ'
            }

    @app.post('/learning_chat/api/chat_group_config', response_class=JSONResponse, dependencies=[authentication()])
    async def post_chat_global_config(group_id: Union[int, str], data: dict):
        if not data['answer_threshold_weights']:
            return {
                'status': 400,
                'msg':    '回复阈值权重不能为空，必须至少有一个数值'
            }
        data['break_probability'] = data['break_probability'] / 100
        data['speak_continuously_probability'] = data['speak_continuously_probability'] / 100
        data['speak_poke_probability'] = data['speak_poke_probability'] / 100
        groups = (
            [{'group_id': group_id}]
            if group_id != 'all'
            else await get_bot().get_group_list()
        )
        for group in groups:
            config = config_manager.get_group_config(group['group_id'])
            config.update(**data)
            config_manager.config.group_config[group['group_id']] = config
        config_manager.save()
        return {
            'status': 0,
            'msg':    '保存成功'
        }

    @app.get('/learning_chat/api/get_chat_messages', response_class=JSONResponse, dependencies=[authentication()])
    async def get_chat_messages(page: int = 1,
                                perPage: int = 10,
                                orderBy: str = 'time',
                                orderDir: str = 'desc',
                                group_id: Optional[str] = None,
                                user_id: Optional[str] = None,
                                message: Optional[str] = None):
        orderBy = (orderBy or 'time') if (orderDir or 'desc') == 'asc' else f'-{orderBy or "time"}'
        filter_args = {f'{k}__contains': v for k, v in
                       {'group_id': group_id, 'user_id': user_id, 'raw_message': message}.items() if v}
        return {
            'status': 0,
            'msg':    'ok',
            'data':   {
                'items': await ChatMessage.filter(**filter_args).order_by(orderBy).offset((page - 1) * perPage).limit(
                    perPage).values(),
                'total': await ChatMessage.filter(**filter_args).count()
            }
        }

    @app.get('/learning_chat/api/get_chat_contexts', response_class=JSONResponse, dependencies=[authentication()])
    async def get_chat_context(page: int = 1, perPage: int = 10, orderBy: str = 'time', orderDir: str = 'desc',
                               keywords: Optional[str] = None):
        orderBy = (orderBy or 'time') if (orderDir or 'desc') == 'asc' else f'-{orderBy or "time"}'
        filter_arg = {'keywords__contains': keywords} if keywords else {}
        return {
            'status': 0,
            'msg':    'ok',
            'data':   {
                'items': await ChatContext.filter(**filter_arg).order_by(orderBy).offset((page - 1) * perPage).limit(
                    perPage).values(),
                'total': await ChatContext.filter(**filter_arg).count()
            }
        }

    @app.get('/learning_chat/api/get_chat_answers', response_class=JSONResponse, dependencies=[authentication()])
    async def get_chat_answers(context_id: Optional[int] = None, page: int = 1, perPage: int = 10,
                               orderBy: str = 'count',
                               orderDir: str = 'desc', keywords: Optional[str] = None):
        filter_arg = {'context_id': context_id} if context_id else {}
        if keywords:
            filter_arg['keywords__contains'] = keywords  # type: ignore
        orderBy = (orderBy or 'count') if (orderDir or 'desc') == 'asc' else f'-{orderBy or "count"}'
        return {
            'status': 0,
            'msg':    'ok',
            'data':   {
                'items': list(
                    map(lambda x: x.update({'messages': [{'msg': m} for m in x['messages']]}) or x,
                        await ChatAnswer.filter(**filter_arg).order_by(orderBy).offset((page - 1) * perPage).limit(
                            perPage).values())),
                'total': await ChatAnswer.filter(**filter_arg).count()
            }
        }

    @app.get('/learning_chat/api/get_chat_blacklist', response_class=JSONResponse, dependencies=[authentication()])
    async def get_chat_blacklist(page: int = 1, perPage: int = 10, keywords: Optional[str] = None,
                                 bans: Optional[str] = None):
        filter_arg = {'keywords__contains': keywords} if keywords else {}
        items = await ChatBlackList.filter(**filter_arg).offset((page - 1) * perPage).limit(perPage).values()
        for item in items:
            item['bans'] = '全局禁用' if item['global_ban'] else str(item['ban_group_id'][0])
        if bans:
            items = list(filter(lambda x: bans in x['bans'], items))
        return {
            'status': 0,
            'msg':    'ok',
            'data':   {
                'items': items,
                'total': len(items)
            }
        }

    @app.delete('/learning_chat/api/delete_chat', response_class=JSONResponse, dependencies=[authentication()])
    async def delete_chat(id: int, type: str):
        try:
            if type == 'message':
                await ChatMessage.filter(id=id).delete()
            elif type == 'context':
                c = await ChatContext.get(id=id)
                await ChatAnswer.filter(context=c).delete()
                await c.delete()
            elif type == 'answer':
                await ChatAnswer.filter(id=id).delete()
            elif type == 'blacklist':
                await ChatBlackList.filter(id=id).delete()
            return {
                'status': 0,
                'msg':    '删除成功'
            }
        except Exception as e:
            return {
                'status': 500,
                'msg':    f'删除失败，{e}'
            }

    @app.put('/learning_chat/api/ban_chat', response_class=JSONResponse, dependencies=[authentication()])
    async def ban_chat(id: int, type: str):
        try:
            if type == 'message':
                data = await ChatMessage.get(id=id)
            elif type == 'context':
                data = await ChatContext.get(id=id)
            else:
                data = await ChatAnswer.get(id=id)
            await LearningChat.add_ban(data)
            return {
                'status': 0,
                'msg':    '禁用成功'
            }
        except Exception as e:
            return {
                'status': 500,
                'msg':    f'禁用失败: {e}'
            }

    @app.put('/learning_chat/api/delete_all', response_class=JSONResponse, dependencies=[authentication()])
    async def delete_all(type: str, id: Optional[int] = None):
        try:
            if type == 'answer':
                if id:
                    await ChatAnswer.filter(context_id=id).delete()
                else:
                    await ChatAnswer.all().delete()
            elif type == 'blacklist':
                await ChatBlackList.all().delete()
            elif type == 'context':
                await ChatContext.all().delete()
            elif type == 'message':
                await ChatMessage.all().delete()
            return {
                'status': 0,
                'msg':    '操作成功'
            }
        except Exception as e:
            return {
                'status': 500,
                'msg':    f'操作失败，{e}'
            }

    @app.get('/learning_chat', response_class=RedirectResponse)
    async def redirect_page():
        return RedirectResponse('/learning_chat/login')

    @app.get('/learning_chat/login', response_class=HTMLResponse)
    async def login_page_app():
        return login_page.render(site_title='登录 | Learning-Chat 后台管理',
                                 theme='ang')

    @app.get('/learning_chat/admin', response_class=HTMLResponse)
    async def admin_page_app():
        return admin_app.render(site_title='Learning-Chat 后台管理',
                                theme='ang',
                                requestAdaptor=requestAdaptor,
                                responseAdaptor=responseAdaptor)

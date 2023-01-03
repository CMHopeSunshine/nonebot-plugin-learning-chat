<div align="center">
  <a href="https://v2.nonebot.dev/store"><img src="https://github.com/A-kirami/nonebot-plugin-template/blob/resources/nbp_logo.png" width="180" height="180" alt="NoneBotPluginLogo"></a>
  <br>
  <p><img src="https://github.com/A-kirami/nonebot-plugin-template/blob/resources/NoneBotPlugin.svg" width="240" alt="NoneBotPluginText"></p>
</div>

<div align="center">

# nonebot-plugin-learning-chat

_✨ 让Bot学习群友的发言和表情包! ✨_

<a href="./LICENSE">
    <img src="https://img.shields.io/github/license/CMHopeSunshine/nonebot-plugin-learning-chat.svg" alt="license">
</a>
<a href="https://pypi.python.org/pypi/nonebot-plugin-learning-chat">
    <img src="https://img.shields.io/pypi/v/nonebot-plugin-learning-chat.svg" alt="pypi">
</a>
<img src="https://img.shields.io/badge/python-3.8+-blue.svg" alt="python">

</div>

## 📖 介绍

一个能够让Bot根据群友的规律性发言，自动选择历史语录或者表情包进行回复的学习插件。

安装完本插件后并不会马上有效果，需要给Bot一段时间积累群聊记录。

学到一定程度后，插件就会变成话唠王，~~把群友们的奇怪发言和表情包通通抢过来~~。

本插件还配备了一个`Web UI`后台管理供Bot主人修改配置，支持**分群**配置。

本插件仅适用于`OneBot V11`适配器和**群聊**。

## 💿 安装

<details>
<summary>使用 nb-cli 安装</summary>
在 nonebot2 项目的根目录下打开命令行, 输入以下指令即可安装

    nb plugin install nonebot-plugin-learning-chat

</details>

<details>
<summary>使用包管理器安装</summary>
在 nonebot2 项目的插件目录下, 打开命令行, 根据你使用的包管理器, 输入相应的安装命令

<details>
<summary>pip</summary>

    pip install nonebot-plugin-learning-chat
</details>
<details>
<summary>pdm</summary>

    pdm add nonebot-plugin-learning-chat
</details>
<details>
<summary>poetry</summary>

    poetry add nonebot-plugin-learning-chat
</details>
<details>
<summary>conda</summary>

    conda install nonebot-plugin-learning-chat
</details>

打开 nonebot2 项目的 `bot.py` 文件, 在其中写入

    nonebot.load_plugin('nonebot_plugin_learning_chat')

</details>

## ☀️ 指令
不同于其它的命令式插件，本插件只有2个命令用于在群聊里管理Bot。

|   指令    |             示例              |                         作用                          |
|:-------:|:---------------------------:|:---------------------------------------------------:|
| 开启\关闭学习 | @bot 开启学习\学说话\快学\关闭学习\别学\闭嘴 |                开启或关闭该群的学习能力(需艾特机器人)                 |
|  禁用回复   |      @bot 不可以\达咩\不能说这       | 将某句已学会的回复给禁用掉，以后不会再说这句话，需要有管理员权限者艾特机器人并**回复**机器人的发言 |


## ✏️ 工作原理
该插件会将群友们的发言都记录在数据库中，根据群友的规律性发言进行回复。

每当群友有一条新发言时，插件会将本条发言记录为上一条发言的可选回复之一，然后在数据库中查找符合条件的本发言的历史回复，从中选择一条进行回复。

以下为一个简单的例子:
```
群友1:诶嘿
群友2:诶嘿是什么意思啊
群友1:诶嘿
群友2:诶嘿是什么意思啊
群友1:诶嘿
群友2:诶嘿是什么意思啊
群友1:诶嘿
群友2:诶嘿是什么意思啊
```
每次有人说`诶嘿`时，就有人说`诶嘿是什么意思啊`，这组对话就可以看作**规律性发言(表情包同理)**。

`诶嘿是什么意思啊`会被学习为`诶嘿`的回复4次，而`诶嘿`会被学习为`诶嘿是什么意思啊`的回复3次。

在默认配置中，某个回复需要学习次数达到**4**次后才会将其列为可选答案之一。

因此以后当有群友说`诶嘿`时，插件就会从数据中查找所以学习次数大于4的回复，发现目前有`诶嘿是什么意思啊`一种，就会有概率回复`诶嘿是什么意思啊`。

简而言之，本插件就是一个高级一点的复读姬和QA问答人，如果你的群友没有明显的规律性发言，本插件的效果可能会比较差。

## ✨ 其他功能

插件还具备复读和主动发言的功能。

### 复读
顾名思义，就是复读。当群友复读达到一定次数时(默认为3)，插件就会跟着复读。

以下情况即使达到次数也不会跟随复读:
- 复读的信息是被ban了的或者过短的
- 复读的人是被ban了的或者全都为同一个人在复读
- 达到次数所花费的时间太长(超过一个小时)

### 主动发言
每隔一段时间，插件就会对群聊热度进行一次排行，从中选取一个群，随机发送一条或多条该群的历史发言。

## 🔧 配置项
本插件使用`yml`文件作为配置文件，因为需要做动态修改和分群配置，因此**没有**采用Nonebot的`.env`形式的配置。

`yml`配置文件位于`Bot目录/data/learing_chat/learning_chat.yml`中，不过个人更推荐你使用`Web UI`后台管理来修改配置。

**每个配置项的作用都在后台管理页面中有较为详细的介绍**，这里只列举几个:


|  配置项   | 默认值  |          说明           |
|:------:|:----:|:---------------------:|
 | 群聊学习开关 | true |         顾名思义          |
|  屏蔽词   | [ ]  |   含有这些词的聊天记录不会进行学习    |
|  屏蔽用户  | [ ]  |  与这些用户相关的聊天记录不会进行学习   |
| 跨群回复阈值 |  3   |  N个群均有相同的回复时，则作为全局回复  |
| 最高学习次数 |  6   |    学习的回复最高能累计到的次数     |
| 自定义词典  | [ ]  | 添加自定义词语，让分词能够识别未收录的词汇 |
|  回复阈值  |  4   |   需要学多少次才会作为可选回复之一    |
|  复读阈值  |  3   |     群友复读多少次后才跟着复读     |
| 主动发言阈值 |  5   |        主动发言的概率        |

部分配置为全局配置，部分可设置**分群配置**，具体请在后台管理中查看。

## 🔑 后台管理
本插件提供了一个简易的`Web UI`后台管理，你可以在后台管理中进行:
- 分群修改配置项
- 查看群聊聊天记录
- 查看本插件已学习的内容
- 对学习的内容进行禁用

`Web UI`默认启用，访问`http://127.0.0.1:nb端口/learning_chat/login`进行登录。

- 默认用户名: chat
- 默认密码: admin
- 
登录成功后会跳转至后台管理页面`http://127.0.0.1:nb端口/learning_chat/admin`。

**请在登入之后，修改默认的用户名、密码以及加密所用的token密钥。**

## 👌 其他
- 可以尝试安装以下包提高插件性能。
  + `pip install ujson`
  + `pip install jieba_fast`
- 打开`DEBUG`级别日志可以查看到插件的学习和回复过程。
- [小派蒙](https://github.com/CMHopeSunshine/LittlePaimon)中已内置该插件，就不要重复装啦！

## 💝 鸣谢
- [Pallas-Bot](https://github.com/MistEO/Pallas-Bot): 本项目的核心算法源自于牛牛的复读功能，~~基本上就是抄它的~~。
- [Nonebot](https://github.com/nonebot/nonebot2): 本项目的基础。
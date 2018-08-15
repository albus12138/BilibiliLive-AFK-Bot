# Bilibili 直播挂机脚本

Python 版B站挂机脚本, 欢迎各位大佬对项目有意见或改进建议在issues提出来 0w0

## Features

- `[x] 登录`

- `[x] 自动参与抽奖`

- `[x] 自动处理即将过期礼物`

- `[x] 每日任务`

    - `[x] 每日签到`

    - `[x] 双端观看直播` 
    
    - `[x] 自动领取银瓜子`

- `[x] 应援团每日签到`

- `[x] 银瓜子兑换硬币`

- `[x] 弹幕姬`


## Install

- 安装 git

    `sudo apt-get install git`
    
- 安装 pip, virtualenv
    
    - Python 3 测试通过, Python 2 未经测试, 建议使用 Python 3 (Python 3 的安装过程请自行百度)
    
    `sudo apt-get install python-pip`
    
    `pip install virtualenv`
    
- 获取程序代码

    `git clone git@github.com:albus12138/BilibiliLive-AFK-Bot.git`
    
- 建立虚拟环境并安装程序所需运行库

    `cd BilibiliLive-AFK-Bot`

    `virtualenv venv`

    `pip install -r requirements.txt`
    
- 启动虚拟环境并运行程序

    `source venv/bin/activate`
    
    `python main.py`
    
- 通过 Supervisor 维持程序运行

    - 配置文件样例 `bili.conf`, 将其中的 `/path/to/program` 替换为程序根目录
    
    `supervisorctl reload` 重载配置文件后会自动启动
    
## Config

- username: B站登录用户名 (邮箱或手机)

- password: B站登录密码

- roomID: 程序清空过期礼物的目标直播间, 弹幕姬监听的直播间, 可以是短号, 程序会自动解析

- silver2coin: 银瓜子兑换硬币开关, 每天限量一枚, 700银瓜子兑换1硬币, 0为关闭, 1为移动端API, 2为网页端API, 1和2效果相同

- enable_raffle: 自动抽奖开关, 1为开启, 0为关闭

- drop_rate: 自动抽奖时放弃抽奖的概率, 用于降低封禁概率, 范围0~100

- SCKEY: 用于在抽奖抽到特殊物品时通知用户, 请自行到 [Server酱](http://sc.ftqq.com/) 申请 SCKEY

- schedule: 弹幕姬监听弹幕(自动抽奖)的时间段, 例: 0700-0900_1800-2100 为 早7点-早9点和晚6点到晚9点, 为降低封禁概率, 请不要过长时间开启自动抽奖

- raffle_keyword: 自动抽奖监听的关键词, 可根据抓包信息自行添加活动关键词

- 其他参数请不要自行修改

## Reference

- [bilibili_geetest](https://github.com/OSinoooO/bilibili_geetest) B站极验验证码破解

- [bilibili_api](https://github.com/ysc3839/bilibili-api) B站移动端api签名示例

- [biliHelper](https://github.com/lkeme/BiliHelper) PHP版B站挂机助手

## License

本项目基于 MIT 许可证发布, 具体条款见 LICENSE 文件
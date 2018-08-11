import re
import base64
import requests
import numpy as np
import time
import logging
import coloredlogs
import websocket
import struct
import json
try:
    import thread
except ImportError:
    import _thread as thread

from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA
from hashlib import md5
from urllib.parse import urlencode
from configparser import ConfigParser
from PIL import Image
from skimage import morphology, filters
from tf_train import ocr_cnn
from geetest_crack import login


class Bilibili:
    def __init__(self, config_file):
        self.logger = logging.getLogger("BilibiliLive_AFK_Bot")
        coloredlogs.install(level='DEBUG', logger=self.logger, fmt="%(asctime)s [%(levelname)8s] %(message)s")
        self.logger.info("Bilibili Live AFK Bot 启动~")

        self.logger.info("载入配置文件...")
        config = ConfigParser()
        config.read(config_file)
        self.config_file = config_file
        self.urls = config["URLS"]
        self.username = config["USER"]["username"]
        self.password = config["USER"]["password"]
        self.login_mode = int(config["GENERAL"]["login_mode"])
        self.shared_payload = config["PAYLOAD"]
        self.appsecret = self.shared_payload.pop("appsecret")
        self.refresh_key = self.shared_payload.pop("refresh_key")
        self.access_key = config["PAYLOAD"]["access_key"]
        self.appkey = self.shared_payload["appkey"]
        self.room_id = config["USER"]["roomID"]
        self.sliver2coin = int(config["USER"]["sliver2coin"])
        self.logger.info("配置文件载入完成")

        self.uid = 0
        self.room_uid = 0
        self._session = requests.Session()

    def _get_captcha(self, filename=".captcha."):
        try:
            data = self._session.get(self.urls["Captcha"]).json()
        except:
            return 0
        if "msg" not in data.keys():
            raise RuntimeError("获取验证码失败, 错误原因: 返回值错误, 请检查网络连接")
        if data["msg"] != "ok":
            raise RuntimeError("获取验证码失败, 错误原因: {}".format(data["msg"]))
        regex = re.compile(r"^data:image/(jpeg);base64,(.*)$")
        img_type, img_data = regex.findall(data["data"]["img"])[0]
        wfile = open("{}{}".format(filename, img_type), "wb")
        wfile.write(base64.b64decode(img_data))
        wfile.close()
        return 1

    def _ocr(self):
        if not self._get_captcha():
            return 0
        rfile = Image.open(".captcha.jpeg", "r")
        img = rfile.convert("L")
        x, y = img.size
        for i in range(0, x):
            for j in range(0, y):
                pixel = img.getpixel((i, j))
                pixel_up = img.getpixel((i, j-1)) if j > 0 else 254
                pixel_down = img.getpixel((i, j+1)) if j < y-1 else 254
                if pixel != 37:
                    continue
                if pixel_up > 250 and pixel_down != 37:
                    img.putpixel((i, j), 254)
                    continue
                if pixel_up != 37 and pixel_down > 250:
                    img.putpixel((i, j), 254)
        for i in range(0, x):
            for j in range(0, y):
                pixel = img.getpixel((i, j))
                pixel_up = img.getpixel((i-1, j)) if i > 0 else 254
                pixel_down = img.getpixel((i+1, j)) if i < x-1 else 254
                if pixel != 37:
                    continue
                if pixel_up > 250 and pixel_down != 37:
                    img.putpixel((i, j), 254)
                    continue
                if pixel_up != 37 and pixel_down > 250:
                    img.putpixel((i, j), 254)
        img = np.asarray(img)
        thresh = filters.threshold_otsu(img)
        bw = morphology.closing(img > thresh, morphology.square(3))
        dst = morphology.remove_small_objects(bw, min_size=20, connectivity=1)
        img = Image.fromarray(np.uint8(dst)*255, "L")
        img.save(".tmp.bmp")
        return ocr_cnn()

    def sign(self):
        self.logger.info("每日签到模块启动")
        res = self._session.get(self.urls["Sign"])
        data = res.json()
        if data["msg"] == "OK":
            self.logger.info("    签到成功, 获得 {}".format(data["data"]["text"]))
            self.logger.info("退出每日签到模块")
            return 1
        self.logger.warning("    签到失败, 原因: {}".format(data.get("message")))
        self.logger.info("退出每日签到模块")
        return 0

    def check_session_status(self):
        res = self._session.get(self.urls["userInfo"])
        data = res.json()
        if data.get("code") != 0:
            return False
        self.logger.info("    当前会话用户: {}".format(data.get("data")["uname"]))
        return True

    def login(self):
        self.logger.info("登录模块启动")
        if self.login_mode == 1:
            self.logger.info("    登录模式: OAuth")
            if self.access_key == "":
                self.logger.info("    未检测到 ACCESS_KEY, 尝试 OAuth 登录")
                self.login_oauth()
            else:
                self.logger.info("    检测到 ACCESS_KEY, 尝试载入令牌")
                if not self.check_access_token():
                    if not self.refresh_access_token():
                        self.login_oauth()
            self.oauth_sso()

        if self.login_mode == 2:
            self.logger.info("    登录模式: Common")
            cookie = self.login_common()
            requests.utils.add_dict_to_cookiejar(self._session.cookies, cookie)

        if not self.check_session_status():
            raise RuntimeError("登录状态错误, 请检查用户名和密码")
        self.logger.info("退出登录模块")

    def login_common(self):
        cookie = login(self.username, self.password, self.urls["Login"], self.logger)
        return cookie

    def _build_payload(self, payload=None):
        if payload is None:
            payload = {}
        payload.update(self.shared_payload)
        payload["ts"] = int(time.time())
        items = list(payload.items())
        items.sort()
        payload["sign"] = md5(urlencode(items).encode('ascii') + self.appsecret.encode('ascii')).hexdigest()
        return payload

    def check_access_token(self):
        payload = self._build_payload({"access_token": self.access_key})
        res = self._session.get(self.urls["OAuthInfo"], params=payload)
        data = res.json()
        if data.get("code") != 0:
            self.logger.warning("    载入令牌失败, 尝试刷新令牌")
            return False
        self.logger.info("    载入令牌成功! 令牌有效期: {}".format(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(
            int(data.get('ts')) + int(data.get('data')['expires_in'])))))
        return int(data.get('data')['expires_in']) > 86400

    def refresh_access_token(self):
        if self.refresh_key == "":
            return False
        payload = self._build_payload({"access_token": self.access_key, "refresh_token": self.refresh_key})
        res = self._session.post(self.urls, data=payload)
        data = res.json()
        if data.get("code") != 0:
            self.logger.warning("    刷新令牌失败, 尝试 OAuth 登录")
            return False
        self.logger.info("    刷新令牌成功, 登录完成!")
        config = ConfigParser()
        config.read(self.config_file)
        config.set("PAYLOAD", "access_key", self.access_key)
        config.set("PAYLOAD", "refresh_key", self.refresh_key)
        with open(self.config_file, "w") as wfile:
            config.write(wfile)
        return True

    def login_oauth(self):
        payload = self._build_payload()
        res = self._session.post(self.urls["OAuthKey"], data=payload)
        data = res.json()
        if data.get("code") != 0:
            self.logger.error("    获取公钥失败, 错误信息: {}".format(data.get("message")))
            raise RuntimeError("错误信息: {}".format(data.get["message"]))
        self.logger.info("    获取公钥成功!")
        key1 = data.get("data")['hash'].encode("ascii")
        key = RSA.importKey(data.get("data")['key'].encode("ascii"))
        cipher = PKCS1_v1_5.new(key)
        password = base64.b64encode(cipher.encrypt(key1+self.password.encode('ascii')))
        payload = self._build_payload(
            {"subid": '1', 'permission': 'ALL', 'username': self.username, 'password': password, 'captcha': ''})
        res = self._session.post(self.urls["OAuthLogin"], data=payload)
        data = res.json()
        if data.get("code") != 0:
            self.logger.error("    OAuth 登录失败, 错误信息: {}".format(data.get("message")))
            raise RuntimeError("错误信息: {}".format(data.get("message")))
        self.logger.info("    OAuth 登录成功!")
        self.logger.info(data)
        config = ConfigParser()
        config.read(self.config_file)
        config.set("PAYLOAD", "access_key", data.get("data")["token_info"]["access_token"])
        config.set("PAYLOAD", "refresh_key", data.get("data")["token_info"]["refresh_token"])
        with open(self.config_file, "w") as wfile:
            config.write(wfile)
        self._session.get(self.urls["LiveIndex"])

    def oauth_sso(self):
        payload = self._build_payload({"appkey": self.appkey, "gourl": self.urls["LiveIndex"]})
        self._session.get(self.urls["OAuthSSO"], params=payload)
        self.logger.info("    获取 Cookies 成功!")

    def get_room_info(self):
        payload = self._build_payload()
        res = self._session.get(self.urls["myInfo"], params=payload)
        data = res.json()
        try:
            self.uid = data["mid"]
        except KeyError:
            self.logger.error("    获取个人信息失败, 取消过期礼物清理任务")
            return False
        self.logger.info("    获取个人信息成功, UID: {}".format(self.uid))

        payload = self._build_payload({'id': self.room_id})
        res = self._session.get(self.urls["roomInfo"], params=payload)
        data = res.json()
        if data.get("code") != 0:
            self.logger.error("    获取直播间信息失败, 取消过期礼物清理任务")
            return False
        self.room_uid = data.get("data")["uid"]
        self.room_id = data.get("data")["room_id"]
        self.logger.info("    获取房间信息成功, RoomUID: {}, RoomID {}".format(self.room_uid, self.room_id))
        self.logger.info("    生成直播间信息成功!")
        return True

    def list_gift_bag(self):
        payload = self._build_payload()
        res = self._session.get(self.urls["bag_list"], params=payload)
        data = res.json()
        if data.get("code") != 0:
            self.logger.warning("    查看礼物库存失败")
            return []
        self.logger.info("    查看礼物库存成功, 共计 {} 件礼物".format(len(data.get("data")["list"])))
        return data.get("data")["list"]

    def send_gift(self, gift):
        raw_payload = {
            'coin_type': 'sliver',
            'gift_id': gift["gift_id"],
            'ruid': self.room_uid,
            'uid': self.uid,
            'biz_id': self.room_id,
            'gift_num': gift["gift_num"],
            'data_source_id': '',
            'data_behavior_id': '',
            'bag_id': gift['bag_id']
        }
        payload = self._build_payload(raw_payload)
        res = self._session.post(self.urls["sendGift"], data=payload)
        data = res.json()
        if data.get("code") != 0:
            self.logger.warning("    投喂失败, 原因: {}".format(data.get("message")))
            return False
        self.logger.info("    投喂 {} x {} 到 {} 直播间~".format(gift["gift_name"], gift["gift_num"], self.room_id))
        return True

    def gift(self):
        self.logger.info("过期礼物处理模块启动")
        if self.uid == 0 or self.room_uid == 0:
            self.logger.info("    未检测到个人信息或直播间信息, 尝试生成")
            if not self.get_room_info():
                self.logger.info("退出过期礼物处理模块")
                return False

        gift_list = self.list_gift_bag()
        if len(gift_list) == 0:
            self.logger.info("退出过期礼物处理模块")
            return True

        self.logger.info("    开始赠送 24 小时内过期礼物")
        for gift in gift_list:
            ts = int(time.time())
            if gift["expire_at"] - ts < 86400:
                self.send_gift(gift)
        self.logger.info("    24 小时内过期礼物处理完成")
        self.logger.info("退出过期礼物处理模块")
        return True

    def get_group_list(self):
        payload = self._build_payload()
        res = self._session.get(self.urls["group_list"], params=payload)
        data = res.json()
        if data.get("code") != 0:
            self.logger.error("    获取应援团信息失败")
            return []
        self.logger.info("    查询到 {} 个应援团".format(len(data.get("data")["list"])))
        return data.get("data")["list"]

    def group_sign(self, group):
        payload = self._build_payload({"group_id": group["group_id"], "owner_id": group["owner_uid"]})
        res = self._session.get(self.urls["group_signin"], params=payload)
        data = res.json()
        if data.get("code") != 0:
            self.logger.warning("    应援失败, 原因: {}".format(data.get("message")))
            return False
        if data.get("data")["status"] == 0:
            self.logger.info("    {} 应援成功~ 获得 {} 点徽章亲密度".format(group["fans_medal_name"], data.get("data")["add_num"]))
        else:
            self.logger.info("    {} 今天已经为主播应援了~".format(group["fans_medal_name"]))
        return True

    def group(self):
        self.logger.info("应援模块启动")
        group_list = self.get_group_list()
        if len(group_list) == 0:
            self.logger.info("退出应援模块")
            return True

        self.logger.info("    开始应援")
        for group in group_list:
            self.group_sign(group)
        self.logger.info("    应援完成")
        self.logger.info("退出应援模块")
        return True

    def silver_to_coin(self):
        if self.sliver2coin == 0:
            return True

        self.logger.info("银瓜子兑换硬币模块启动")
        if self.sliver2coin == 1:
            payload = self._build_payload()
            res = self._session.get(self.urls["sliver2coin_app"], params=payload)
            data = res.json()
            self.logger.info(res.content.decode("u8"))
            if data.get("code") != 0:
                self.logger.error("    移动端银瓜子兑换硬币失败, 原因: {}".format(data.get("message")))
            else:
                self.logger.info("    移动端银瓜子兑换硬币成功, 银瓜子 -700, 硬币 +1")
        else:
            payload = self._build_payload()
            res = self._session.get(self.urls["sliver2coin_web"], params=payload)
            data = res.json()
            self.logger.info(res.content.decode("u8"))
            if data.get("code") != 0:
                self.logger.error("    网页端银瓜子兑换硬币失败, 原因: {}".format(data.get("message")))
            else:
                self.logger.info("    网页端银瓜子兑换硬币成功, 银瓜子 -700, 硬币 +1")
        self.logger.info("退出银瓜子兑换硬币模块")

    def raffle_callback(self, room_id):
        pass

    def test(self):
        payload = self._build_payload({"group_id": 221033522, "owner_id": 372418})
        res = self._session.get(self.urls["group_signin"], params=payload)
        self.logger.info(res.content.decode('u8'))


class BilibiliBulletScreen:
    def __init__(self, host, origin, room_id, logger, keyword, raffle_callback, silent=True):
        websocket.enableTrace(True)
        self.host = host
        self.origin = origin
        self.room_id = room_id
        self.logger = logger
        self.keywords = keyword
        self.raffle_callback = raffle_callback
        self.silent = silent
        self._ws = websocket.WebSocketApp(host,
                                          on_message=self.on_message,
                                          on_error=self.on_error,
                                          on_open=self.on_open,
                                          on_close=self.on_close)

        self.status = 0
        self.hot = 0
        self.stop = 0

    def run_forever(self):
        return self._ws.run_forever(host=self.host, origin=self.origin)

    @staticmethod
    def pack_msg(payload, opt):
        return struct.pack(">IHHII", 0x10 + len(payload), 0x10, 0x01, opt, 0x01) + payload.encode('u8')

    def process_msg(self, msg):
        if msg[3] == 3:
            self.hot = int.from_bytes(msg[-1], byteorder='big')
            print("hot: {}".format(self.hot))
            return True
        if msg[3] == 5:
            data = json.loads(msg[-1].decode("utf-8"))
            import os
            if not os.path.exists("json_data/danmu/{}.json".format(data["cmd"])):
                with open("json_data/danmu/{}.json".format(data["cmd"]), 'w') as wfile:
                    wfile.write(str(data))
            if data["cmd"] == "DANMU_MSG":
                if not self.silent:
                    medal = "" if len(data["info"][3]) == 0 else "[{}] ".format(data["info"][3][1])
                    self.logger.info("    {}{} 说: {}".format(medal, data["info"][2][1], data["info"][1]))
                return True
            if data["cmd"] == "SYS_MSG":
                msg = data["msg"].split(":?")
                for keyword in self.keywords:
                    if keyword in msg[-1]:
                        self.logger.info("    系统消息: 检测到 {} 出现 {}".format(data["real_roomid"], keyword))
                        self.raffle_callback(data["real_roomid"])
                return True
            if data["cmd"] == "SEND_GIFT":
                if not self.silent:
                    self.logger.info("    {} 投喂了 {} x {}".format(data["data"]["uname"], data["data"]["giftName"],
                                                                 data["data"]["num"]))
                return True
            return True
        if msg[3] == 8:
            self.logger.info("    服务器允许连接!")
            self.status = 1
            return True

    def heart(self):
        while not self.status:
            print("等待服务器允许连接")
            time.sleep(1)

        while not self.stop:
            print("发送心跳包")
            data = self.pack_msg("", 0x2)
            print("data: {}".format(data))
            self._ws.send(data)
            time.sleep(30)

    def on_open(self, ws):
        raw_payload = {
            'uid': 0,
            'roomid': self.room_id,
            'protover': 1,
            'platform': 'web',
            'clientver': '1.4.1'
        }
        data = self.pack_msg(json.dumps(raw_payload), 0x7)
        self._ws.send(data)
        thread.start_new_thread(self.heart, ())

    def on_message(self, ws, msg):
        while len(msg) != 0:
            pkt_length = int.from_bytes(msg[:4], byteorder='big')
            pkt = struct.unpack(">IHHII{}s{}s".format(pkt_length-16, len(msg)-pkt_length), msg)
            self.process_msg(pkt[:-1])
            msg = pkt[-1]

    def on_error(self, ws, err):
        self.logger.error("    错误原因: {}".format(err))

    def on_close(self, ws):
        self.stop = 1
        self.logger.info("    WebSocket 连接已关闭")

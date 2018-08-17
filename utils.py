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
import threading
import random

from collections import deque
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
        self.logger.info("[主线程] Bilibili Live AFK Bot 启动~")

        self._session = requests.Session()

        self.logger.info("[主线程] 载入配置文件...")
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
        self.room_id = self.get_real_roomid(config["USER"]["roomID"])
        if not self.room_id:
            self.room_id = int(config["USER"]["roomID"])
        self.silver2coin = int(config["USER"]["silver2coin"])
        self.raffle_keyword = config["GENERAL"]["raffle_keyword"].split("_")
        self.enable_raffle = int(config["USER"]["enable_raffle"])
        self.drop_rate = int(config["USER"]["drop_rate"])
        self.SCKEY = config["USER"]["SCKEY"]
        self.logger.info("[主线程] 配置文件载入完成")

        self.uid = 0
        self.room_uid = 0
        self.realname = 0
        self.vip = 0
        self.uname = ""
        self.bullet_screen_client = BilibiliBulletScreen(
            self.urls["bulletscreen_host"],
            self.urls["bulletscreen_origin"],
            self.room_id,
            self.logger,
            self.raffle_keyword,
            self.raffle_callback,
            False
        )
        self.thread_pool = ThreadPool(5, 10)
        self.is_sign = False
        self.is_gift = False
        self.is_group = False
        self.is_silver2coin = False
        self.is_silver = False
        self.is_task = False
        self.is_watch = 0
        self.heart_threading = threading.Thread(target=self.heart, args=())
        self.query_queue = []

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
        res = self._session.get(self.urls["Sign"])
        data = res.json()
        if data["msg"] == "OK":
            self.logger.info("[每日任务] 签到成功, 获得 {}".format(data["data"]["text"]))
            return True
        self.logger.warning("[每日任务] 签到失败, 原因: {}".format(data.get("message")))
        if data.get("message") == "今天已签到过":
            return True
        return False

    def check_session_status(self):
        res = self._session.get(self.urls["userInfo"])
        data = res.json()
        if data.get("code") != 0:
            return False
        self.logger.info("[主线程] 当前会话用户: {}".format(data.get("data")["uname"]))
        return True

    def login(self):
        if self.login_mode == 1:
            self.logger.info("[登录] 登录模式: OAuth")
            if self.access_key == "":
                self.logger.info("[登录] 未检测到 ACCESS_KEY, 尝试 OAuth 登录")
                self.login_oauth()
            else:
                self.logger.info("[登录] 检测到 ACCESS_KEY, 尝试载入令牌")
                if not self.check_access_token():
                    if not self.refresh_access_token():
                        self.login_oauth()
            self.oauth_sso()

        if self.login_mode == 2:
            self.logger.info("[登录] 登录模式: Common")
            cookie = self.login_common()
            requests.utils.add_dict_to_cookiejar(self._session.cookies, cookie)

        if not self.check_session_status():
            raise RuntimeError("登录状态错误, 请检查用户名和密码")

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
            self.logger.warning("[登录] 载入令牌失败, 尝试刷新令牌")
            return False
        self.logger.info("[登录] 载入令牌成功! 令牌有效期: {}".format(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(
            int(data.get('ts')) + int(data.get('data')['expires_in'])))))
        return int(data.get('data')['expires_in']) > 86400

    def refresh_access_token(self):
        if self.refresh_key == "":
            return False
        payload = self._build_payload({"access_token": self.access_key, "refresh_token": self.refresh_key})
        res = self._session.post(self.urls, data=payload)
        data = res.json()
        if data.get("code") != 0:
            self.logger.warning("[登录] 刷新令牌失败, 尝试 OAuth 登录")
            return False
        self.logger.info("[登录] 刷新令牌成功, 登录完成!")
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
            self.logger.error("[登录] 获取公钥失败, 错误信息: {}".format(data.get("message")))
            raise RuntimeError("错误信息: {}".format(data.get["message"]))
        self.logger.info("[登录] 获取公钥成功!")
        key1 = data.get("data")['hash'].encode("ascii")
        key = RSA.importKey(data.get("data")['key'].encode("ascii"))
        cipher = PKCS1_v1_5.new(key)
        password = base64.b64encode(cipher.encrypt(key1+self.password.encode('ascii')))
        payload = self._build_payload(
            {"subid": '1', 'permission': 'ALL', 'username': self.username, 'password': password, 'captcha': ''})
        res = self._session.post(self.urls["OAuthLogin"], data=payload)
        data = res.json()
        if data.get("code") != 0:
            self.logger.error("[登录] OAuth 登录失败, 错误信息: {}".format(data.get("message")))
            raise RuntimeError("错误信息: {}".format(data.get("message")))
        self.logger.info("[登录] OAuth 登录成功!")
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
        self.logger.info("[登录] 获取 Cookies 成功!")

    def get_room_info(self):
        payload = self._build_payload()
        res = self._session.get(self.urls["myInfo"], params=payload)
        data = res.json()
        try:
            self.uid = data["mid"]
        except KeyError:
            self.logger.error("[礼物] 获取个人信息失败, 取消过期礼物清理任务")
            return False
        self.logger.info("[礼物] 获取个人信息成功, UID: {}".format(self.uid))

        payload = self._build_payload({'id': self.room_id})
        res = self._session.get(self.urls["roomInfo"], params=payload)
        data = res.json()
        if data.get("code") != 0:
            self.logger.error("[礼物] 获取直播间信息失败, 取消过期礼物清理任务")
            return False
        self.room_uid = data.get("data")["uid"]
        self.room_id = data.get("data")["room_id"]
        self.logger.info("[礼物] 获取房间信息成功, RoomUID: {}, RoomID {}".format(self.room_uid, self.room_id))
        self.logger.info("[礼物] 生成直播间信息成功!")
        return True

    def list_gift_bag(self):
        payload = self._build_payload()
        res = self._session.get(self.urls["bag_list"], params=payload)
        data = res.json()
        if data.get("code") != 0:
            self.logger.warning("[礼物] 查看礼物库存失败")
            return []
        self.logger.info("[礼物] 查看礼物库存成功, 共计 {} 件礼物".format(len(data.get("data")["list"])))
        return data.get("data")["list"]

    def send_gift(self, gift):
        raw_payload = {
            'coin_type': 'silver',
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
            self.logger.warning("[礼物] 投喂失败, 原因: {}".format(data.get("message")))
            return False
        self.logger.info("[礼物] 投喂 {} x {} 到 {} 直播间~".format(gift["gift_name"], gift["gift_num"], self.room_id))
        return True

    def gift(self):
        if self.is_gift:
            return True

        if self.uid == 0 or self.room_uid == 0:
            self.logger.info("[礼物] 未检测到个人信息或直播间信息, 尝试生成")
            if not self.get_room_info():
                return False

        gift_list = self.list_gift_bag()
        if len(gift_list) == 0:
            return True

        self.logger.info("[礼物] 开始赠送 24 小时内过期礼物")
        for gift in gift_list:
            ts = int(time.time())
            if gift["expire_at"] - ts < 86400:
                self.send_gift(gift)
        self.logger.info("[礼物] 24 小时内过期礼物处理完成")
        self.is_gift = True
        return True

    def get_group_list(self):
        payload = self._build_payload()
        res = self._session.get(self.urls["group_list"], params=payload)
        data = res.json()
        if data.get("code") != 0:
            self.logger.error("[应援团] 获取应援团信息失败")
            return []
        self.logger.info("[应援团] 查询到 {} 个应援团".format(len(data.get("data")["list"])))
        return data.get("data")["list"]

    def group_sign(self, group):
        payload = self._build_payload({"group_id": group["group_id"], "owner_id": group["owner_uid"]})
        res = self._session.get(self.urls["group_signin"], params=payload)
        data = res.json()
        if data.get("code") != 0:
            self.logger.warning("[应援团] 应援失败, 原因: {}".format(data.get("message")))
            return False
        if data.get("data")["status"] == 0:
            self.logger.info("[应援团] {} 应援成功~ 获得 {} 点徽章亲密度".format(group["fans_medal_name"], data.get("data")["add_num"]))
        else:
            self.logger.info("[应援团] {} 今天已经为主播应援了~".format(group["fans_medal_name"]))
        return True

    def group(self):
        group_list = self.get_group_list()
        if len(group_list) == 0:
            self.is_group = True
            return True

        self.logger.info("[应援团] 开始应援")
        for group in group_list:
            self.group_sign(group)
        self.logger.info("[应援团] 应援完成")
        self.is_group = True
        return True

    def silver_to_coin(self):
        if self.is_silver2coin:
            return True

        if self.silver2coin == 0:
            return True

        if self.silver2coin == 1:
            payload = self._build_payload()
            res = self._session.get(self.urls["silver2coin_app"], params=payload)
            data = res.json()
            if data.get("code") != 0:
                self.logger.error("[兑换] 移动端银瓜子兑换硬币失败, 原因: {}".format(data.get("message")))
            else:
                self.logger.info("[兑换] 移动端银瓜子兑换硬币成功, 银瓜子 -700, 硬币 +1")
                self.is_silver2coin = True
        else:
            payload = self._build_payload()
            res = self._session.get(self.urls["silver2coin_web"], params=payload)
            data = res.json()
            if data.get("code") != 0:
                self.logger.error("[兑换] 网页端银瓜子兑换硬币失败, 原因: {}".format(data.get("message")))
            else:
                self.logger.info("[兑换] 网页端银瓜子兑换硬币成功, 银瓜子 -700, 硬币 +1")
                self.is_silver2coin = True

    def raffle_callback(self, room_id):
        if not self.enable_raffle:
            return True
        if random.randint(0, 99) > self.drop_rate:
            self.logger.info("[抽奖] 随机丢弃直播间 {} 抽奖 x 1".format(room_id))
            return True
        real_roomid = self.get_real_roomid(room_id)
        if not real_roomid:
            return False
        self.logger.info("[抽奖] 已进入直播间 {} 准备抽奖".format(real_roomid))
        payload = self._build_payload({"room_id": real_roomid})
        self._session.get(self.urls["RoomEntryAction"], params=payload)

        payload = self._build_payload({"roomid": real_roomid})
        res = self._session.get(self.urls["appRaffleCheck"], params=payload)
        data = res.json()
        if data.get("code") != 0:
            return False
        if data.get("data")["lotteryInfo"]:
            self.logger.info(res.json())
            self.logger.info(
                "[抽奖] 移动端检测到直播间 {} 出现 {}, 抽奖ID: {}".format(real_roomid, data.get("data")["lotteryinfo"]["title"],
                                                        data.get("data")["lotteryinfo"]["raffleId"]))
            self.thread_pool.submit(self.commit_raffle, ("app", real_roomid, data.get("data")["lotteryinfo"]["raffleId"]))
            return True

        payload = self._build_payload({"roomid": real_roomid})
        res = self._session.get(self.urls["webRaffleCheck"], params=payload)
        data = res.json()
        if data.get("code") != 0:
            return False
        if data.get("data")["list"]:
            for item in data.get("data")["list"]:
                self.logger.info("[抽奖] 网页端检测到直播间 {} 出现 {}, 抽奖ID: {}, 已加入抽奖队列".format(real_roomid, item["title"], item["raffleId"]))
                self.thread_pool.submit(self.commit_raffle, ("web", real_roomid, item["raffleId"]))
            return True

        return True

    def commit_raffle(self, mode, room_id, raffle_id):
        if mode == "app":
            time.sleep(random.randint(5, 10))
            payload = self._build_payload({"event_type": raffle_id, "room_id": room_id})
            res = self._session.get(self.urls["appRaffleJoin"], params=payload)
            data = res.json()
            self.logger.info(data)
            if data.get("code") != 0:
                self.logger.warning("[抽奖] 移动端参与直播间 {} 抽奖 {} 失败, 失败原因: {}".format(room_id, raffle_id, data.get("message")))
                return False
            # TODO
            #self.logger.info("[抽奖] 移动端参与直播间 {} 抽奖 {} 成功".format(room_id, raffle_id))
            #self.query_queue.append((raffle_id, 2))
            return True

        if mode == "web":
            time.sleep(random.randint(5, 10))
            payload = self._build_payload({"raffleId": raffle_id, "roomid": room_id})
            res = self._session.get(self.urls["webRaffleJoin"], params=payload)
            data = res.json()
            if data.get('code') != 0:
                self.logger.warning("[抽奖] 网页端参与直播间 {} 抽奖 {} 失败, 失败原因: {}".format(room_id, raffle_id, data.get("message")))
                return False
            self.logger.info("[抽奖] 网页端参与直播间 {} 抽奖 {} 成功".format(room_id, raffle_id))
            self.query_queue.append((raffle_id, data.get("data")["type"], time.time()+int(data.get("data")["time"])))
            self.query_raffle()
            return True

    def query_raffle(self):
        done = []
        for record in self.query_queue:
            if time.time() < record[2]:
                print("skip")
                continue
            payload = self._build_payload({"type": record[1], "raffleId": record[0]})
            res = self._session.get(self.urls["RaffleQuery"], params=payload)
            data = res.json()
            if data.get("code") != 0:
                self.logger.warning("[抽奖] 查询抽奖结果失败")
                continue
            if data.get("data")["status"] == 3:
                continue
            if data.get("data")["status"] == 2:
                self.logger.info("[抽奖] 网页端在抽奖ID: {} 获得 {} x {}".format(record[0], data.get("data")["gift_name"], data.get("data")["gift_num"]))
                if data.get("data")["gift_name"] != "辣条" and data.get("data")["gift_name"] != "":
                    self.logger.info("[抽奖] 抽到了奇怪的东西!!!!!!")
                    self.server_chan("抽奖获得了奇怪的东西!", "在抽奖{}获得了{}x{},请及时查收".format(record[0], data.get("data")["gift_name"], data.get("data")["gift_num"]))
                done.append(record)
        for record in done:
            self.query_queue.remove(record)

    def bullet_screen(self):
        if self.bullet_screen_client.stop:
            print(self.bullet_screen_client.main.isAlive())
            self.bullet_screen_client.main.start()

    def check_user_info(self):
        self.logger.info("[抽奖] 正在获取用户信息")
        payload = self._build_payload()
        res = self._session.get(self.urls["RealnameCheck"], params=payload)
        data = res.json()
        if data.get("code") != 0:
            self.logger.warning("[抽奖] 检测实名信息失败, 默认无实名")
        else:
            if data.get("data")["memberPerson"]["realname"] != "":
                self.realname = 1
                self.logger.info("[抽奖] 检测实名信息成功, 用户已完成实名认证")
            else:
                self.logger.info("[抽奖] 检测实名信息成功, 用户未完成实名验证")
        payload = self._build_payload()
        res = self._session.get(self.urls["vipcheck"], params=payload)
        data = res.json()
        if data.get("msg") != "success":
            self.logger.warning("[抽奖] 检测老爷信息失败, 默认非老爷")
        else:
            if data.get("data")["vip"] or data.get("data")["svip"]:
                self.vip = 1
            self.logger.info("[抽奖] 检测老爷信息成功")
            self.uname = data.get("data")["uname"]
        self.logger.info("[抽奖] 获取用户信息成功")

    def get_real_roomid(self, room_id):
        payload = {"id": room_id}
        res = self._session.get(self.urls["getRealRoomID"], params=payload)
        data = res.json()
        if data.get("code") != 0:
            return False
        if data.get("data")["is_hidden"] or data.get("data")["is_locked"] or data.get("data")["encrypted"]:
            return False
        return int(data.get("data")["room_id"])

    def server_chan(self, text, desp=""):
        if self.SCKEY == "":
            self.logger.error("[Server酱] 未检测到 SCKEY, 放弃推送任务")
            return False
        payload = {"text": text, "desp":desp}
        res = requests.get("https://sc.ftqq.com/{}.send".format(self.SCKEY), params=payload)
        data = res.json()
        if data.get("errno") != 0:
            self.logger.error("[Server酱] 消息推送失败, 错误原因: {}".format(data.get("errmsg")))
            return False
        self.logger.info("[Server酱] 消息推送成功, 标题: {}".format(text))
        return True

    def task(self):
        if not self.is_task:
            payload = self._build_payload()
            res = self._session.get(self.urls["check_task"], params=payload)
            data = res.json()
            if data.get("code") != 0:
                self.logger.warning("[每日任务] 每日任务检查失败")
                return False
            if data.get("data")["sign_info"]["status"] == 1:
                self.logger.info("[每日任务] 每日签到任务已完成")
                self.is_sign = True
            if data.get("data")["double_watch_info"]["status"] == 1:
                self.logger.info("[每日任务] 双端观看任务已完成")
                self.is_watch = 1
            if data.get("data")["double_watch_info"]["status"] == 2:
                self.logger.info("[每日任务] 双端观看任务已完成")
                self.is_watch = 2
            if data.get("data")["box_info"]["freeSilverFinish"]:
                self.logger.info("[每日任务] 今日免费银瓜子已全部领取完毕")
                self.is_silver = 1
            self.is_task = self.is_sign and self.is_silver and self.is_watch
            self.logger.info("[每日任务] 每日任务检查成功")
        else:
            self.logger.info("[每日任务] 今日任务已全部完成 (不包括直播任务)")
            return True

        if not self.is_sign:
            if self.sign():
                self.is_sign = True

        if not (self.is_silver and self.is_watch):
            if not self.heart_threading.isAlive():
                self.heart_threading.setDaemon(True)
                self.heart_threading.start()

        if self.is_watch == 1:
            payload = self._build_payload({"task_id": "double_watch_task"})
            res = self._session.post(self.urls["taskreward"], payload)
            data = res.json()
            if data.get("code") != 0:
                self.logger.warning("[每日任务] 双端观看任务奖励领取失败, 原因: {}".format(data.get("message")))
            else:
                self.logger.info("[每日任务] 双端观看任务奖励领取成功")

    def heart(self):
        while not (self.is_silver and self.is_watch):
            payload = self._build_payload({"room_id": self.room_id})
            res = self._session.post(self.urls["webHeart"], data=payload)
            data = res.json()
            if data.get("code") != 0:
                self.logger.warning("[心跳] 网页端直播间心跳包异常")
            else:
                self.logger.info("[心跳] 网页端心跳正常")

            payload = self._build_payload({"room_id": self.room_id})
            res = self._session.post(self.urls["appHeart"], data=payload)
            data = res.json()
            if data.get("code") != 0:
                self.logger.warning("[心跳] 移动端直播间心跳包异常")
            else:
                self.logger.info("[心跳] 移动端心跳正常")
            self.silver()
            time.sleep(300)

    def silver(self):
        payload = self._build_payload()
        res = self._session.get(self.urls["silverQuery"], params=payload)
        data = res.json()
        if data.get("code") != 0:
            if data.get("code") == -10017:
                self.is_silver = 1
                self.logger.info("[免费宝箱] 今日宝箱已领取完毕")
            else:
                self.logger.info("[免费宝箱] 宝箱状态查询失败, 原因: {}".format(data.get("message")))
            return True
        if time.time() < data.get("data")["time_end"]:
            return False
        now = data.get("data")["times"]
        total = data.get("data")["max_times"]
        payload = self._build_payload()
        res = self._session.get(self.urls["silverClaim"], params=payload)
        data = res.json()
        if data.get('code') != 0:
            self.logger.warning("[免费宝箱] 宝箱领取失败, 原因: {}".format(data.get("message")))
            return False
        self.logger.info("[免费宝箱] {} / {} 轮宝箱领取成功, 获得 银瓜子 x {}".format(now, total, data.get("data")["awardSilver"]))
        return True

    def quit(self):
        self.is_silver = True
        self.is_watch = 2
        if self.bullet_screen_client.stop == 0:
            self.bullet_screen_client.quit()
        self.thread_pool.stop()


class BilibiliBulletScreen(websocket.WebSocketApp):
    def __init__(self, host, origin, room_id, logger, keyword, raffle_callback, silent=True):
        super().__init__(host)
        self.host = host
        self.origin = origin
        self.room_id = int(room_id)
        self.logger = logger
        self.keywords = keyword
        self.raffle_callback = raffle_callback
        self.silent = silent
        self.status = 0
        self.hot = 0
        self.stop = 1
        self.daemon = threading.Thread(target=self.heart, args=())
        self.main = threading.Thread(target=self.run_forever, args=(None, None, 0, None, None, None, None, None, False, self.host, self.origin, None, False))

    @staticmethod
    def pack_msg(payload, opt):
        return struct.pack(">IHHII", 0x10 + len(payload), 0x10, 0x01, opt, 0x01) + payload.encode('u8')

    def process_msg(self, msg):
        if msg[3] == 3:
            self.hot = int.from_bytes(msg[-1], byteorder='big')
            self.logger.info("[弹幕姬] 当前直播间人气: {}".format(self.hot))
            return True
        if msg[3] == 5:
            data = json.loads(msg[-1].decode("utf-8"))
            if data["cmd"] == "DANMU_MSG":
                if not self.silent:
                    medal = "" if len(data["info"][3]) == 0 else "[{}] ".format(data["info"][3][1])
                    self.logger.info("[弹幕姬] {}{} 说: {}".format(medal, data["info"][2][1], data["info"][1]))
                return True
            if data["cmd"] == "SYS_MSG":
                msg = data["msg"].split(":?")
                for keyword in self.keywords:
                    if keyword in msg[-1]:
                        self.logger.info("[弹幕姬] 系统消息: 检测到 {} 出现 {}".format(data["real_roomid"], keyword))
                        self.raffle_callback(data["real_roomid"])
                return True
            if data["cmd"] == "SEND_GIFT":
                if not self.silent:
                    self.logger.info("[弹幕姬] {} 投喂了 {} x {}".format(data["data"]["uname"], data["data"]["giftName"],
                                                                 data["data"]["num"]))
                return True
            return True
        if msg[3] == 8:
            self.logger.info("[弹幕姬] 已连接到直播间 {}".format(self.room_id))
            self.status = 1
            return True

    def heart(self):
        while not self.status:
            time.sleep(1)

        while not self.stop:
            data = self.pack_msg("", 0x2)
            self.send(data)
            time.sleep(30)

    def on_open(self):
        self.stop = 0
        raw_payload = {
            'uid': 0,
            'roomid': self.room_id,
            'protover': 1,
            'platform': 'web',
            'clientver': '1.4.1'
        }
        data = self.pack_msg(json.dumps(raw_payload), 0x7)
        self.send(data)
        self.daemon.setDaemon(True)
        self.daemon.start()

    def on_message(self, msg):
        while len(msg) != 0:
            pkt_length = int.from_bytes(msg[:4], byteorder='big')
            pkt = struct.unpack(">IHHII{}s{}s".format(pkt_length-16, len(msg)-pkt_length), msg)
            self.process_msg(pkt[:-1])
            msg = pkt[-1]

    def on_error(self, err):
        self.logger.error("[弹幕姬] 错误原因: {}".format(err))

    def on_close(self):
        self.logger.info("[弹幕姬] WebSocket 连接已关闭")
        self.stop = 1
        self.daemon.join()
        self.logger.info("[弹幕姬] 心跳包已停止发送")

    def quit(self):
        if self.stop == 0:
            self.stop = 1
            self.close()
            self.main.join()
        return True


class ThreadPool:
    def __init__(self, max_worker, max_queue):
        self.max_worker = max_worker
        self.max_queue = max_queue

        self.pool = []
        self.run = True
        self.queue = deque(maxlen=self.max_queue)
        self.daemon = threading.Thread(target=self.check, args=())
        self.daemon.start()

    def submit(self, func, args):
        self.queue.append((func, args))

    def check(self):
        while self.run:
            for thread in self.pool:
                if not thread.isAlive():
                    self.pool.remove(thread)
            if (len(self.pool) != self.max_worker) and (len(self.queue) != 0):
                task = self.queue.pop()
                if task:
                    self.pool.append(threading.Thread(target=task[0], args=task[1]))
                    self.pool[-1].start()
            time.sleep(1)

    def stop(self):
        self.run = False
        self.daemon.join()

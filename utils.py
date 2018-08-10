import re
import base64
import requests
import numpy as np
import time
import logging
import coloredlogs
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
        self.logger.info("配置文件载入完成")

        self._session = requests.Session()
        self.login()

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
            self.logger.info("    登录模式: OAUTH")
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

    def _build_payload(self, payload):
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
        self.logger.info("    载入令牌成功! 令牌有效期: {}".format(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(data.get('ts'))+int(data.get('data')['expires_in'])))))
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
        payload = self._build_payload({})
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
        payload = self._build_payload({"subid": '1', 'permission': 'ALL', 'username': self.username, 'password': password, 'captcha': ''})
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

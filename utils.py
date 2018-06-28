import re
import base64
import requests


urls = {
    "LiveIndex": "https://live.bilibili.com",
    "Captcha": "https://api.live.bilibili.com/lottery/v1/SilverBox/getCaptcha"
}


class Bilibili:
    def __init__(self, cookies=None):
        self._session = requests.Session()
        if cookies:
            self._session.cookies.update(cookies)
        self._session.get(urls["LiveIndex"])

    def _get_captcha(self):
        data = self._session.get(urls["Captcha"]).json()
        if "msg" not in data.keys():
            raise RuntimeError("获取验证码失败, 错误原因: 返回值错误, 请检查网络连接")
        if data["msg"] != "ok":
            raise RuntimeError("获取验证码失败, 错误原因: {}".format(data["msg"]))
        regex = re.compile(r"^data:image/(png|jpeg);base64,(.*)$")
        img_type, img_data = regex.findall(data["data"]["img"])[0]
        wfile = open(".captcha.{}".format(img_type), "wb")
        wfile.write(base64.b64decode(img_data))
        wfile.close()
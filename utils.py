import re
import base64
import requests
import numpy as np
from PIL import Image
from skimage import morphology, filters


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

    def _get_captcha(self, filename=".captcha."):
        try:
            data = self._session.get(urls["Captcha"]).json()
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

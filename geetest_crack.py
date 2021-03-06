# -*- coding:utf-8 -*-
import time
import re
import random
import os
from selenium import webdriver
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver import ActionChains
from bs4 import BeautifulSoup
from urllib.request import urlretrieve
from PIL import Image


class CrackGeetest:
    def __init__(self, logger):
        self.browser = webdriver.Chrome(executable_path="chromedriver")
        self.wait = WebDriverWait(self.browser, 10)
        self.logger = logger

    @staticmethod
    def mk_img_dir():
        """
        创建图片目录文件
        :return:
        """
        if not os.path.exists('Image'):
            os.mkdir('Image')

    def get_geetest_image(self):
        """
        获取验证码图片
        :return: 图片location信息
        """
        bg = []
        fullgb = []

        while bg == [] and fullgb == []:
            soup = BeautifulSoup(self.browser.page_source, 'lxml')
            bg = soup.find_all('div', class_='gt_cut_bg_slice')
            fullgb = soup.find_all('div', class_='gt_cut_fullbg_slice')

        bg_url = re.findall('url\(\"(.*?)\"\);', bg[0].get('style'))[0].replace('webp', 'jpg')
        fullgb_url = re.findall('url\(\"(.*?)\"\);', fullgb[0].get('style'))[0].replace('webp', 'jpg')
        bg_location_list = []
        fullgb_location_list = []

        for each_bg in bg:
            location = dict()
            location['x'] = int(re.findall('background-position: (.*)px (.*)px;', each_bg.get('style'))[0][0])
            location['y'] = int(re.findall('background-position: (.*)px (.*)px;', each_bg.get('style'))[0][1])
            bg_location_list.append(location)

        for each_fullgb in fullgb:
            location = dict()
            location['x'] = int(re.findall('background-position: (.*)px (.*)px;', each_fullgb.get('style'))[0][0])
            location['y'] = int(re.findall('background-position: (.*)px (.*)px;', each_fullgb.get('style'))[0][1])
            fullgb_location_list.append(location)

        self.mk_img_dir()
        urlretrieve(url=bg_url, filename='Image/bg.jpg')
        self.logger.info('    缺口图片下载完成！')
        urlretrieve(url=fullgb_url, filename='Image/fullgb.jpg')
        self.logger.info('    背景图片下载完成！')
        return bg_location_list, fullgb_location_list

    @staticmethod
    def get_merge_image(filename, location_list):
        """
        根据图片位置合并还原
        :param filename: 图片
        :param location_list: 位置
        :return:合并后的图片对象
        """
        im = Image.open(filename)
        new_im = Image.new('RGB', (260, 116))
        im_list_upper = []
        im_list_lower = []

        for location in location_list:
            if location['y'] == -58:
                im_list_upper.append(im.crop((abs(location['x']), 58, abs(location['x'])+10, 116)))
            if location['y'] == 0:
                im_list_lower.append(im.crop((abs(location['x']), 0, abs(location['x'])+10, 58)))

        x_offset = 0
        for img in im_list_upper:
            new_im.paste(img, (x_offset, 0))
            x_offset += img.size[0]

        x_offset = 0
        for img in im_list_lower:
            new_im.paste(img, (x_offset, 58))
            x_offset += img.size[0]

        new_im.save('Image/'+re.split('[./]', filename)[1]+'1.jpg')
        return new_im

    @staticmethod
    def is_px_equal(img1, img2, x, y):
        """
        判断两个像素是否相同
        :param img1: 图片1
        :param img2:图片2
        :param x:位置1
        :param y:位置2
        :return:像素是否相同
        """
        pix1 = img1.load()[x, y]
        pix2 = img2.load()[x, y]
        threshold = 60

        if abs(pix1[0]-pix2[0]) < threshold and abs(pix1[1]-pix2[1]) < threshold and abs(pix1[2]-pix2[2]) < threshold:
            return True
        else:
            return False

    def get_gap(self, img1, img2):
        """
        获取缺口偏移量
        :param img1: 不带缺口图片
        :param img2: 带缺口图片
        :return:
        """
        left = 60
        for i in range(left, img1.size[0]):
            for j in range(img1.size[1]):
                if not self.is_px_equal(img1, img2, i, j):
                    left = i
                    return left
        return left

    @staticmethod
    def get_track(distance):
        """
        根据偏移量和手动操作模拟计算移动轨迹
        :param distance: 偏移量
        :return: 移动轨迹
        """
        # 移动轨迹
        tracks = []
        # 当前位移
        current = 0
        # 减速阈值
        mid = distance * 4 / 5
        # 时间间隔
        t = 0.2
        # 初始速度
        v = 0

        while current < distance:
            if current < mid:
                a = random.uniform(2, 5)
            else:
                a = -(random.uniform(12.5, 13.5))
            v0 = v
            v = v0 + a * t
            x = v0 * t + 1 / 2 * a * t * t
            current += x

            if 0.6 < current - distance < 1:
                x = x - 0.53
                tracks.append(round(x, 2))

            elif 1 < current - distance < 1.5:
                x = x - 1.4
                tracks.append(round(x, 2))
            elif 1.5 < current - distance < 3:
                x = x - 1.8
                tracks.append(round(x, 2))

            else:
                tracks.append(round(x, 2))

        return tracks

    def get_slider(self):
        """
        获取滑块
        :return:滑块对象
        """
        try:
            slider = self.wait.until(
                ec.element_to_be_clickable(
                    (By.XPATH, '//div[@class="gt_slider"]/div[contains(@class,"gt_slider_knob")]')))
            return slider
        except TimeoutError:
            self.logger.error('    验证码加载超时')

    def move_to_gap(self, slider, tracks):
        """
        将滑块移动至偏移量处
        :param slider: 滑块
        :param tracks: 移动轨迹
        :return:
        """
        action = ActionChains(self.browser)
        action.click_and_hold(slider).perform()
        for x in tracks:
            action.move_by_offset(xoffset=x, yoffset=-1).perform()
            action = ActionChains(self.browser)
        time.sleep(0.6)
        action.release().perform()

    def success_check(self):
        """
        验证是否成功
        :return:
        """
        try:
            if re.findall('gt_success', self.browser.page_source, re.S):
                self.browser.get("https://live.bilibili.com")
                cookie = [item["name"] + ":" + item["value"] for item in self.browser.get_cookies()]
                self.logger.info('    验证码测试成功！')
                return True, cookie
            else:
                self.browser.get("https://live.bilibili.com")
                cookie = [item["name"] + ":" + item["value"] for item in self.browser.get_cookies()]
                self.logger.warning('    验证码测试失败！')
                return False, cookie
        except TimeoutError:
            self.logger.error('    验证码加载超时')
        finally:
            self.browser.close()


def login(username, password, url, logger):
    cnt = 1
    while True:
        logger.info("    ==================== 第 {} 次尝试 ====================".format(cnt))
        cnt += 1
        crack = CrackGeetest(logger)
        crack.browser.get(url)
        WebDriverWait(crack.browser, 30, 1).until(
            ec.presence_of_element_located((By.CSS_SELECTOR, ".gt_slider_knob.gt_show")))
        WebDriverWait(crack.browser, 30, 1).until(
            ec.presence_of_element_located((By.CSS_SELECTOR, ".gt_cut_bg.gt_show")))
        WebDriverWait(crack.browser, 30, 1).until(
            ec.presence_of_element_located((By.CSS_SELECTOR, ".gt_cut_fullbg.gt_show")))

        elem_user = crack.browser.find_element_by_id("login-username")
        elem_user.send_keys(username)
        elem_pwd = crack.browser.find_element_by_id("login-passwd")
        elem_pwd.send_keys(password)

        bg_location_list, fullgb_location_list = crack.get_geetest_image()
        img1 = crack.get_merge_image('Image/fullgb.jpg', fullgb_location_list)
        img2 = crack.get_merge_image('Image/bg.jpg', bg_location_list)

        distance = crack.get_gap(img1, img2) * 1.138
        slider = crack.get_slider()
        tracks = crack.get_track(distance)
        crack.move_to_gap(slider, tracks)
        time.sleep(1)
        success, cookie = crack.success_check()
        if success:
            break

    cook_map = {}
    for item in cookie:
        s = item.split(':')
        cook_map[s[0]] = s[1]
    logger.info("    获取 Cookie 成功!")
    return cook_map

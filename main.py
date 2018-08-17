import datetime
import sys
import signal
import time
import threading

from utils import Bilibili
from configparser import ConfigParser


def signal_handler(sig, frame):
    global keep_running
    keep_running = 0
    client.logger.warning("检测到 SIGINT 信号, 程序即将退出")
    client.logger.warning("正在清理环境, 请稍候")


def in_time(time_list):
    now = datetime.datetime.now()
    value = now.hour * 100 + now.minute
    for item in time_list:
        if item[0] < value < item[1]:
            return True
    return False


def run():
    while (today == datetime.datetime.now().day) and keep_running:
        if in_time(schedule):
            client.bullet_screen()
        else:
            client.bullet_screen_client.quit()
        client.task()
        client.gift()
        client.group()
        client.silver_to_coin()
        time.sleep(60)
    client.quit()


signal.signal(signal.SIGINT, signal_handler)

if len(sys.argv) < 2:
    print("使用方法: python {} <配置文件>".format(sys.argv[0]))
    sys.exit(0)

config = ConfigParser()
config.read(sys.argv[1])

schedule = []
for item in config["USER"]["schedule"].split("_"):
    data = item.split("-")
    schedule.append((int(data[0]), int(data[1])))

keep_running = 1
today = datetime.datetime.now().day

client = Bilibili(sys.argv[1])
client.login()
run_thread = threading.Thread(target=run, args=())
run_thread.start()
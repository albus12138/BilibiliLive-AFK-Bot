# coding:utf-8
import os
import base64
import string
import random
import shutil
import requests
import numpy as np
import tensorflow as tf
from skimage import io
from utils import Bilibili


HEIGHT = 40
WIDTH = 120
CAPTCHA_LENGTH = 4
FILENAME_DICT = string.ascii_letters+string.digits
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'


def __gen_random_name():
    return "tmp/" + "".join(random.sample(FILENAME_DICT, 8)) + ".bmp"


def get_bilibili_captcha(num):
    global bilibili
    ans = 0
    while ans < num:
        status = bilibili._get_captcha()
        if status:
            bilibili._ocr()
            shutil.move(".tmp.bmp", __gen_random_name())
            ans += 1


def baidu_ocr(num):
    global access_token
    url = 'https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic?access_token=' + access_token
    if os.path.exists("list.txt"):
        with open("list.txt", "r") as rfile:
            line = rfile.readlines()
            ans = int(line[-1].split(" ")[0]) if len(line) != 0 else 0
    else:
        os.mknod("list.txt")
        ans = 0
    while ans < num:
        print("Processing {}/{}".format(ans, num))
        files = os.listdir("tmp")
        if len(files) == 0:
            get_bilibili_captcha(100)
            files = os.listdir("tmp")
        for file in files:
            flag = True
            filename = os.path.join("tmp", file)
            with open(filename, "rb") as rfile:
                img = base64.b64encode(rfile.read())
            res = requests.post(url, data={"image": img}, headers={'Content-Type': 'application/x-www-form-urlencoded'})
            content = res.json()["words_result"]
            if len(content) == 0:
                continue
            content = content[0]["words"]
            if content:
                if len(content) != 4:
                    continue
                for i in range(0, 4):
                    if i == 2 and content[i] not in "+-":
                        flag = False
                    if i != 2 and content[i] not in "1234567890":
                        flag = False
                if flag:
                    shutil.copy(filename, "train_data/{}.bmp".format(ans))
                    with open("list.txt", "a") as wfile:
                        wfile.write("{} {}\n".format(ans, content))
                    ans += 1
        for file in files:
            os.remove(os.path.join("tmp", file))


def get_train_data(num):
    rfile = open("list.txt", "r")
    lines = rfile.readlines()
    rfile.close()
    return random.sample(lines, num)


def text2vector(text):
    vector = np.zeros(4 * 12)
    vector[ord(text[0]) - 48] = 1
    vector[ord(text[1]) - 48 + 12] = 1
    if text[2] == '+':
        vector[34] = 1
    else:
        vector[35] = 1
    vector[ord(text[3]) - 48 + 36] = 1
    return vector


def vector2text(vector):
    text = ""
    for i in range(0, 10):
        if vector[i] == 1:
            text += chr(i+48)
            break
    for i in range(12, 24):
        if vector[i] == 1:
            text += chr(i+36)
            break
    text += '+' if vector[34] == 1 else '-'
    for i in range(36, 48):
        if vector[i] == 1:
            text += chr(i+12)
            break
    return text


def get_train_batch(size=64):
    global access_token
    global files
    batch_x = np.zeros([size, HEIGHT*WIDTH])
    batch_y = np.zeros([size, 48])
    files = get_train_data(size)
    for i in range(0, size):
        file = files.pop()
        text = file.split(" ")[1]
        image = io.imread(os.path.join("train_data", "{}.bmp".format(file.split(" ")[0])), as_grey=True)
        batch_x[i, :] = image.flatten()
        batch_y[i, :] = text2vector(text)
    return batch_x, batch_y


def crack_captcha_cnn(w_alpha=0.01, b_alpha=0.1):
    x = tf.reshape(X, shape=[-1, HEIGHT, WIDTH, 1])

    # 3 conv layer
    w_c1 = tf.Variable(w_alpha * tf.random_normal([3, 3, 1, 32]))
    b_c1 = tf.Variable(b_alpha * tf.random_normal([32]))
    conv1 = tf.nn.relu(tf.nn.bias_add(tf.nn.conv2d(x, w_c1, strides=[1, 1, 1, 1], padding='SAME'), b_c1))
    conv1 = tf.nn.max_pool(conv1, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='SAME')
    conv1 = tf.nn.dropout(conv1, keep_prob)

    w_c2 = tf.Variable(w_alpha * tf.random_normal([3, 3, 32, 64]))
    b_c2 = tf.Variable(b_alpha * tf.random_normal([64]))
    conv2 = tf.nn.relu(tf.nn.bias_add(tf.nn.conv2d(conv1, w_c2, strides=[1, 1, 1, 1], padding='SAME'), b_c2))
    conv2 = tf.nn.max_pool(conv2, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='SAME')
    conv2 = tf.nn.dropout(conv2, keep_prob)

    w_c3 = tf.Variable(w_alpha * tf.random_normal([3, 3, 64, 64]))
    b_c3 = tf.Variable(b_alpha * tf.random_normal([64]))
    conv3 = tf.nn.relu(tf.nn.bias_add(tf.nn.conv2d(conv2, w_c3, strides=[1, 1, 1, 1], padding='SAME'), b_c3))
    conv3 = tf.nn.max_pool(conv3, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='SAME')
    conv3 = tf.nn.dropout(conv3, keep_prob)

    # Fully connected layer
    w_d = tf.Variable(w_alpha * tf.random_normal([75 * 64, 1024]))  # 8 * 20 * 64, 1024
    b_d = tf.Variable(b_alpha * tf.random_normal([1024]))
    dense = tf.reshape(conv3, [-1, w_d.get_shape().as_list()[0]])
    dense = tf.nn.relu(tf.add(tf.matmul(dense, w_d), b_d))
    dense = tf.nn.dropout(dense, keep_prob)

    w_out = tf.Variable(w_alpha * tf.random_normal([1024, 4 * 12]))
    b_out = tf.Variable(b_alpha * tf.random_normal([4 * 12]))
    out = tf.add(tf.matmul(dense, w_out), b_out)
    # out = tf.nn.softmax(out)
    return out


def train_crack_captcha_cnn():
    output = crack_captcha_cnn()
    loss = tf.reduce_mean(tf.nn.sigmoid_cross_entropy_with_logits(logits=output, labels=Y))
    optimizer = tf.train.AdamOptimizer(learning_rate=0.001).minimize(loss)

    predict = tf.reshape(output, [-1, CAPTCHA_LENGTH, 12])
    max_idx_p = tf.argmax(predict, 2)
    max_idx_l = tf.argmax(tf.reshape(Y, [-1, CAPTCHA_LENGTH, 12]), 2)
    correct_pred = tf.equal(max_idx_p, max_idx_l)
    accuracy = tf.reduce_mean(tf.cast(correct_pred, tf.float32))

    saver = tf.train.Saver()
    with tf.Session() as sess:
        step = 0
        if os.path.exists("my_model/checkpoint"):
            checkpoint = open("my_model/checkpoint", "r")
            record = checkpoint.readline()
            saver.restore(sess, "my_model/{}".format(record.split("\"")[1]))
            step = int(record.split("\"")[1].split("-")[-1])
            checkpoint.close()
            print("Successful load checkpoint {}".format(step))
        else:
            sess.run(tf.global_variables_initializer())

        while True:
            batch_x, batch_y = get_train_batch(64)
            _, loss_ = sess.run([optimizer, loss], feed_dict={X: batch_x, Y: batch_y, keep_prob: 0.75})
            print(step, loss_)

            if step % 50 == 0:
                batch_x_test, batch_y_test = get_train_batch(100)
                acc = sess.run(accuracy, feed_dict={X: batch_x_test, Y: batch_y_test, keep_prob: 1.})
                print(step, acc)
                if acc > 0.8:
                    break
            saver.save(sess, "my_model/bilibili_captcha.model", global_step=step)
            step += 1


def test_cnn_accuracy():
    output = crack_captcha_cnn()

    predict = tf.reshape(output, [-1, CAPTCHA_LENGTH, 12])
    max_idx_p = tf.argmax(predict, 2)
    max_idx_l = tf.argmax(tf.reshape(Y, [-1, CAPTCHA_LENGTH, 12]), 2)
    correct_pred = tf.equal(max_idx_p, max_idx_l)
    accuracy = tf.reduce_mean(tf.cast(correct_pred, tf.float32))

    saver = tf.train.Saver()
    with tf.Session() as sess:
        if os.path.exists("my_model/checkpoint"):
            checkpoint = open("my_model/checkpoint", "r")
            record = checkpoint.readline()
            saver.restore(sess, "my_model/{}".format(record.split("\"")[1]))
            step = int(record.split("\"")[1].split("-")[-1])
            checkpoint.close()
            print("Successful load checkpoint {}".format(step))
        else:
            print("Checkpoint not found.")
            return 0

        batch_x_test, batch_y_test = get_train_batch(100)
        acc = sess.run(accuracy, feed_dict={X: batch_x_test, Y: batch_y_test, keep_prob: 1.})
        print(step, acc)


if __name__ == "__main__":
    mode = 2
    if mode == 0:
        cookies = {}  # bilibili cookies, key: value
        bilibili = Bilibili(cookies)
        ak = ""  # baidu ai application key
        sk = ""  # baidu ai application secret key
        host = 'https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id={}&client_secret={}'.format(ak, sk)
        req = requests.post(host, headers={'Content-Type': 'application/json; charset=UTF-8'})
        access_token = req.json()["access_token"]
        baidu_ocr(101)
    elif mode == 1:
        X = tf.placeholder(tf.float32, [None, HEIGHT * WIDTH])
        Y = tf.placeholder(tf.float32, [None, 48])
        keep_prob = tf.placeholder(tf.float32)
        train_crack_captcha_cnn()
    elif mode == 2:
        X = tf.placeholder(tf.float32, [None, HEIGHT * WIDTH])
        Y = tf.placeholder(tf.float32, [None, 48])
        keep_prob = tf.placeholder(tf.float32)
        test_cnn_accuracy()

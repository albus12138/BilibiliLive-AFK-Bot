# coding:utf-8
import os
import base64
import shutil
import requests
import numpy as np
import tensorflow as tf
from skimage import io
from utils import Bilibili


HEIGHT = 40
WIDTH = 120
CAPTCHA_LENGTH = 4
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'


def get_train_data(num, access_token):
    url = 'https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic?access_token=' + access_token
    # 二进制方式打开图文件
    ans = 0
    cookies = {
        "LIVE_BUVID": "AUTO7415301873495121",
        "finger": "49387dad",
        "buvid3": "CADB6203-7531-474F-BF03-A6A9E7E13D4965571infoc",
        "sid": "jxlhdren",
        "fts": "1530187377",
        "DedeUserID": "346167248",
        "DedeUserID__ckMd5": "bd5ef2b809d85a33",
        "SESSDATA": "4208db4f%2C1532781480%2C8a1969c1",
        "bili_jct": "fe4c568af7eaddb752ba4bb34e4265bc",
        "_dfcaptcha": "61531516def9bcddd5fb0fee61445f25"
    }
    bilibili = Bilibili(cookies)
    files = []
    while ans < num:
        flag = True
        status = bilibili._get_captcha()
        if not status:
            continue
        bilibili._ocr()
        rfile = open(r'.tmp.bmp', 'rb')
        # 参数image：图像base64编码
        img = base64.b64encode(rfile.read())
        rfile.close()
        params = {"image": img}
        req = requests.post(url, data=params, headers={'Content-Type': 'application/x-www-form-urlencoded'})
        content = req.json()["words_result"]
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
                print("{}/{} | {}".format(ans, num, content))
                shutil.copy(".tmp.bmp", "train_data/{}.bmp".format(content))
                files.append("{}.bmp".format(content))
                ans += 1
    return files


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
    files = get_train_data(size, access_token)
    for i in range(0, size):
        file = files.pop()
        text = file.split(".")[0]
        image = io.imread(os.path.join("train_data", file), as_grey=True)
        batch_x[i, :] = image.flatten()
        batch_y[i, :] = text2vector(text)
    return batch_x, batch_y


def crack_captcha_cnn(w_alpha=0.01, b_alpha=0.1):
    x = tf.reshape(X, shape=[-1, HEIGHT, WIDTH, 1])

    # w_c1_alpha = np.sqrt(2.0/(IMAGE_HEIGHT*IMAGE_WIDTH)) #
    # w_c2_alpha = np.sqrt(2.0/(3*3*32))
    # w_c3_alpha = np.sqrt(2.0/(3*3*64))
    # w_d1_alpha = np.sqrt(2.0/(8*32*64))
    # out_alpha = np.sqrt(2.0/1024)

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
    # loss
    # loss = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(output, Y))
    loss = tf.reduce_mean(tf.nn.sigmoid_cross_entropy_with_logits(logits=output, labels=Y))
    # 最后一层用来分类的softmax和sigmoid有什么不同？
    # optimizer 为了加快训练 learning_rate应该开始大，然后慢慢衰
    optimizer = tf.train.AdamOptimizer(learning_rate=0.001).minimize(loss)

    predict = tf.reshape(output, [-1, CAPTCHA_LENGTH, 12])
    max_idx_p = tf.argmax(predict, 2)
    max_idx_l = tf.argmax(tf.reshape(Y, [-1, CAPTCHA_LENGTH, 12]), 2)
    correct_pred = tf.equal(max_idx_p, max_idx_l)
    accuracy = tf.reduce_mean(tf.cast(correct_pred, tf.float32))

    saver = tf.train.Saver()
    with tf.Session() as sess:
        if os.path.exists("my_model/bilibili_captcha.model"):
            saver.restore(sess, "my_model/bilibili_captcha.model")
        else:
            sess.run(tf.global_variables_initializer())

        step = 0
        while True:
            batch_x, batch_y = get_train_batch(64)
            _, loss_ = sess.run([optimizer, loss], feed_dict={X: batch_x, Y: batch_y, keep_prob: 0.75})
            print(step, loss_)

            # 每100 step计算一次准确率
            if step % 100 == 0 and step != 0:
                batch_x_test, batch_y_test = get_train_batch(100)
                acc = sess.run(accuracy, feed_dict={X: batch_x_test, Y: batch_y_test, keep_prob: 1.})
                print(step, acc)
                # 如果准确率大于50%,保存模型,完成训练
                if acc > 0.5:
                    break
            saver.save(sess, "my_model/bilibili_captcha.model", global_step=step)
            step += 1


if __name__ == "__main__":
    ak = "noCVRz1mELyT1aCDcIOGHBI5"
    sk = "6SDEYTNZaMMOG0tlEk93muSqmWfA0z1Y"
    host = 'https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id={}&client_secret={}'.format(ak, sk)
    req = requests.post(host, headers={'Content-Type': 'application/json; charset=UTF-8'})
    access_token = req.json()["access_token"]

    X = tf.placeholder(tf.float32, [None, HEIGHT * WIDTH])
    Y = tf.placeholder(tf.float32, [None, 48])
    keep_prob = tf.placeholder(tf.float32)

    train_crack_captcha_cnn()

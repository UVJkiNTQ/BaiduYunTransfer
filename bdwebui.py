from flask import Flask, render_template, request, redirect, url_for, flash
import os
import re
import requests
import time
import urllib
import random
import string
from threading import Thread

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key')  # 从环境变量获取或使用默认值
API_KEY = 'GHkLa9AeMAwHK16C5suBKlk3'
SECRET_KEY = '2ZRL3CXd6ocjtSwwAnX9ryYf4l85RYGm'
DEFAULT_SAVE_PATH = '/转存文件'
CONFIG_FILE = 'BaiduYunTransfer.conf'

def get_or_generate_password():
    admin_password = os.getenv('ADMIN_PASSWORD')
    if not admin_password:
        # 生成16位随机密码
        chars = string.ascii_letters + string.digits + '!@#$%^&*'
        admin_password = ''.join(random.choice(chars) for _ in range(16))
        print('*' * 60)
        print('* 重要: ADMIN_PASSWORD未设置，已生成随机管理员密码:')
        print(f'* {admin_password}')
        print('* 请记录此密码或设置ADMIN_PASSWORD环境变量')
        print('*' * 60)
    return admin_password
ADMIN_PASSWORD = get_or_generate_password()

class BaiduYunTransfer:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.116 Safari/537.36',
        'Referer': 'pan.baidu.com'}

    universal_error_code = {'2': '参数错误',
                           '-6': '身份验证失败',
                           '31034': '命中接口频控',
                           '42000': '访问过于频繁',
                           '42999': '功能下线',
                           '9100': '一级封禁',
                           '9200': '二级封禁',
                           '9300': '三级封禁',
                           '9400': '四级封禁',
                           '9500': '五级封禁'}

    def __init__(self, api_key, secret_key, share_link, password, folderpath, new_name_list=None):
        if new_name_list is None:
            new_name_list = []
        self.api_key = api_key
        self.secret_key = secret_key
        self.share_link = share_link
        self.password = password
        self.folderpath = folderpath
        self.new_name_list = new_name_list

        if self.init_token() and self.get_surl() and self.get_sekey() and self.get_shareid_and_uk_and_fsidlist():
            self.mkdir()
            if self.file_transfer():
                if self.new_name_list != []:
                    self.rename()
                print('本次转存任务结束')

    def reflush_token(self):
        reflush_token_url = 'https://openapi.baidu.com/oauth/2.0/token?grant_type=refresh_token'
        params = {'refresh_token': self.refresh_token, 'client_id': self.api_key, 'client_secret': self.secret_key}
        res = requests.get(reflush_token_url, headers=self.headers, params=params)

        try:
            res_json = res.json()
        except Exception as e:
            print('请检查网络是否连通：%s' % e)
            return False

        if 'error' in res_json:
            error = res_json['error']
            print('刷新token失败：%s' % error)
            return False
        elif 'access_token' in res_json and 'refresh_token' in res_json:
            self.access_token = res_json['access_token']
            self.refresh_token = res_json['refresh_token']
            BaiduYunTransfer.save_token_to_config(self.access_token, self.refresh_token)
            return True
        return False

    def init_token(self):
        if not os.path.exists(CONFIG_FILE):
            return False
        
        try:
            with open(CONFIG_FILE, 'r') as f:
                token = f.read()
            
            lines = token.split('\n')
            if len(lines) < 6:
                return False
                
            self.access_token = lines[1]
            self.refresh_token = lines[3]
            update_time = int(lines[5])
            now_time = int(time.time())
            
            if now_time - update_time < 27 * 24 * 60 * 60:
                return True
            elif now_time - update_time > 31536000 * 10:
                return False
            else:
                return self.reflush_token()
        except Exception as e:
            print(f"读取token配置文件失败: {str(e)}")
            return False

    @staticmethod
    def save_token_to_config(access_token, refresh_token):
        token = '[access_token]\n{}\n[refresh_token]\n{}\n[update_time]\n{}'.format(
            access_token, refresh_token, int(time.time()))
        with open(CONFIG_FILE, 'w') as f:
            f.write(token)

    def mkdir(self):
        url = 'https://pan.baidu.com/rest/2.0/xpan/file?method=create'
        params = {'method': 'create', 'access_token': self.access_token}
        data = {'size': 0, 'isdir': 1, 'path': self.folderpath, 'rtype': 0}
        res = requests.post(url, headers=self.headers, params=params, data=data)
        res_json = res.json()
        errno = res_json['errno']
        if errno == 0:
            print('文件夹创建成功')
            return True
        elif errno == -8:
            print('文件夹已存在，不再创建')
            return True
        else:
            error = {'-7': '目录名错误或无权访问'}
            error.update(self.universal_error_code)

            if str(errno) in error:
                print('文件夹创建失败，错误码：{}，错误：{}\n返回JSON：{}'.format(errno, error[str(errno)], res_json))
            else:
                print('文件夹创建失败，错误码：{}，错误未知\n返回JSON：{}'.format(errno, res_json))

            return False

    def get_surl(self):
        res = re.search(r'https://pan\.baidu\.com/share/init\?surl=([0-9a-zA-Z].+?)$', self.share_link)
        if res:
            self.surl = res.group(1)
            return True
        else:
            res = requests.get(self.share_link, headers=self.headers)
            reditList = res.history
            if reditList == []:
                print('链接不存在')
                return False
            link = reditList[len(reditList) - 1].headers["location"]
            res = re.search(r'/share/init\?surl=([0-9a-zA-Z].+$)', link)
            if res:
                self.surl = res.group(1)
                return True
            else:
                print('获取surl失败')
                return False

    def get_sekey(self):
        url = 'https://pan.baidu.com/rest/2.0/xpan/share?method=verify'
        params = {'surl': self.surl, 'access_token': self.access_token}
        data = {'pwd': self.password}
        res = requests.post(url, headers=self.headers, params=params, data=data)

        res_json = res.json()
        errno = res_json['errno']
        if errno == 0:
            randsk = res_json['randsk']
            self.sekey = urllib.parse.unquote(randsk, encoding='utf-8', errors='replace')
            return True
        else:
            error = {'105': '链接地址错误',
                     '-12': '非会员用户达到转存文件数目上限',
                     '-9': 'pwd错误',
                     '2': '参数错误'}
            error.update(self.universal_error_code)

            if str(errno) in error:
                print('获取sekey失败，错误码：{}，错误：{}'.format(errno, error[str(errno)]))
            else:
                print('获取sekey失败，错误码：{}，错误未知'.format(errno))

            return False

    def get_shareid_and_uk_and_fsidlist(self):
        url = 'https://pan.baidu.com/rest/2.0/xpan/share?method=list'
        params = {"shorturl": self.surl, "page": "1", "num": "100", "root": "1", "fid": "0", "sekey": self.sekey,
                  'access_token': self.access_token}
        res = requests.get(url, headers=self.headers, params=params)
        res_json = res.json()

        res_json = res.json()
        errno = res_json['errno']
        if errno == 0:
            self.shareid = res_json['share_id']
            self.uk = res_json['uk']
            fsidlist = res_json['list']
            self.fsid_list = []
            for fs in fsidlist:
                self.fsid_list.append(int(fs['fs_id']))
            return True
        else:
            error = {'110': '有其他转存任务在进行',
                     '105': '非会员用户达到转存文件数目上限',
                     '-7': '达到高级会员转存上限'}
            error.update(self.universal_error_code)

            if str(errno) in error:
                print('获取shareid, uk, fsidlist失败，错误码：{}，错误：{}'.format(errno, error[str(errno)]))
            else:
                print('获取shareid, uk, fsidlist失败，错误码：{}，错误未知'.format(errno))

            return False

    def file_transfer(self):
        url = 'http://pan.baidu.com/rest/2.0/xpan/share?method=transfer'
        params = {'access_token': self.access_token, 'shareid': self.shareid, 'from': self.uk}
        data = {'sekey': self.sekey, 'fsidlist': str(self.fsid_list), 'path': self.folderpath}
        res = requests.post(url, headers=self.headers, params=params, data=data)

        res_json = res.json()
        errno = res_json['errno']
        if errno == 0:
            print('文件转存成功：', end=' ')
            self.file_path_list = [file['to'] for file in res_json['extra']['list']]
            print(self.file_path_list)
            return True
        else:
            error = {'111': '有其他转存任务在进行',
                     '120': '非会员用户达到转存文件数目上限',
                     '130': '达到高级会员转存上限',
                     '-33': '达到转存文件数目上限',
                     '12': '批量操作失败',
                     '-3': '转存文件不存在',
                     '-9': '密码错误',
                     '5': '分享文件夹等禁止文件'}
            error.update(self.universal_error_code)

            if str(errno) in error:
                print('文件转存失败，错误码：{}，错误：{}\n返回JSON：{}'.format(errno, error[str(errno)], res_json))
            else:
                print('文件转存失败，错误码：{}，错误未知\n返回JSON：{}'.format(errno, res_json))

            return False

    def rename(self):
        if len(self.file_path_list) != len(self.new_name_list):
            print('[ERROR] 转存页面根目录下的文件（夹）数量 与 用户提供的新文件（夹）名的数量 不相等，终止文件重命名。')
            return

        print('正在进行文件重命名：')

        for i in range(len(self.file_path_list)):
            url = "https://pan.baidu.com/rest/2.0/xpan/file?method=filemanager&access_token={}&opera=rename".format(
                self.access_token)

            payload = {'async': '0',  # 0 同步，1 自适应，2 异步
                       'filelist': '[{"path": "%s", "newname": "%s"}]' % (
                       self.file_path_list[i], self.new_name_list[i]),
                       # 示例：[{"path":"/test/123456.docx","newname":"123.docx"}]
                       'ondup': 'newcopy'  # fail(默认，直接返回失败)、newcopy(重命名文件)、overwrite、skip
                       }

            res = requests.request("POST", url, data=payload)
            res_json = res.json()
            errno = res_json['errno']
            if errno == 0:
                print('\t{} 重命名为 {}'.format(self.file_path_list[i], self.new_name_list[i]))

@app.route('/auth', methods=['GET', 'POST'])
def auth():
    if request.method == 'POST':
        code = request.form.get('auth_code')
        if not code:
            flash('请输入授权码', 'error')
            return render_template('auth.html')
        
        get_token_url = 'https://openapi.baidu.com/oauth/2.0/token?grant_type=authorization_code'
        params = {'code': code, 'client_id': API_KEY, 'client_secret': SECRET_KEY, 'redirect_uri': 'oob'}
        
        try:
            res = requests.get(get_token_url, headers=BaiduYunTransfer.headers, params=params)
            res_json = res.json()
            
            if 'error' in res_json:
                flash(f'获取token失败: {res_json.get("error_description", "未知错误")}', 'error')
                return render_template('auth.html')
            
            if 'access_token' in res_json and 'refresh_token' in res_json:
                BaiduYunTransfer.save_token_to_config(res_json['access_token'], res_json['refresh_token'])
                flash('授权成功！现在可以使用转存功能了', 'success')
                return redirect(url_for('index'))
        except Exception as e:
            flash(f'请求失败: {str(e)}', 'error')
            return render_template('auth.html')
    
    auth_url = f'https://openapi.baidu.com/oauth/2.0/authorize?response_type=code&client_id={API_KEY}&redirect_uri=oob&scope=netdisk&display=popup'
    return render_template('auth.html', auth_url=auth_url)


@app.route('/', methods=['GET', 'POST'])  # Add methods parameter
def index():
    if request.method == 'POST':
        # Handle POST request
        share_link = request.form.get('share_link')
        password = request.form.get('password')
        save_path = request.form.get('save_path', DEFAULT_SAVE_PATH)

        if share_link and '?pwd=' in share_link:
            link_parts = share_link.split('?pwd=')
            share_link = link_parts[0]
            if not password:
                password = link_parts[1]

        if not share_link or not password:
            return render_template('index.html',
                                   error="请输入分享链接和提取码",
                                   share_link=share_link,
                                   password=password,
                                   save_path=save_path)

        try:
            Thread(target=start_transfer, args=(share_link, password, save_path)).start()
            return redirect(url_for('result'))
        except Exception as e:
            return render_template('index.html',
                                   error=f"转存失败: {str(e)}",
                                   share_link=share_link,
                                   password=password,
                                   save_path=save_path)

    # Handle GET request
    return render_template('index.html', save_path=DEFAULT_SAVE_PATH)


@app.route('/result')
def result():
    return render_template('result.html')

def start_transfer(share_link, password, save_path):
    transfer = BaiduYunTransfer(API_KEY, SECRET_KEY, share_link, password, save_path)


def create_templates():
    templates_dir = 'templates'
    if not os.path.exists(templates_dir):
        os.makedirs(templates_dir)

    auth_html = '''<!DOCTYPE html>
<html>
<head>
    <title>百度云授权</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; }
        input[type="text"] { width: 100%; padding: 8px; }
        button { background: #4CAF50; color: white; padding: 10px 15px; border: none; cursor: pointer; }
        .error { color: red; }
        .success { color: green; }
        .steps { margin: 20px 0; }
        .step { margin-bottom: 10px; padding: 10px; background: #f5f5f5; border-radius: 4px; }
        a { color: #4CAF50; text-decoration: none; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <h1>百度云授权</h1>
    {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
            {% for category, message in messages %}
                <p class="{{ category }}">{{ message }}</p>
            {% endfor %}
        {% endif %}
    {% endwith %}

    <div class="steps">
        <div class="step">
            <h3>步骤1: 获取授权码</h3>
            <p>请访问下面的链接获取授权码:</p>
            <a href="{{ auth_url }}" target="_blank">{{ auth_url }}</a>
            <p>打开链接后，登录百度账号并授权，然后将获得的授权码粘贴到下方输入框中</p>
        </div>
        <div class="step">
            <h3>步骤2: 输入授权码</h3>
            <form method="POST">
                <div class="form-group">
                    <label for="auth_code">授权码:</label>
                    <input type="text" id="auth_code" name="auth_code" required placeholder="请输入从百度获取的授权码">
                </div>
                <button type="submit">授权</button>
            </form>
        </div>
    </div>
</body>
</html>'''

    with open(os.path.join(templates_dir, 'auth.html'), 'w', encoding='utf-8') as f:
        f.write(auth_html)
    index_html = '''<!DOCTYPE html>
<html>
<head>
    <title>百度云转存工具</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; }
        input[type="text"] { width: 100%; padding: 8px; }
        button { background: #4CAF50; color: white; padding: 10px 15px; border: none; cursor: pointer; }
        .error { color: red; }
        .auth-info { margin-top: 20px; padding: 10px; background: #f5f5f5; border-radius: 4px; }
        a { color: #4CAF50; text-decoration: none; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <h1>百度云转存工具</h1>
    {% if error %}<p class="error">{{ error }}</p>{% endif %}
    <form method="POST">
        <div class="form-group">
            <label for="share_link">分享链接:</label>
            <input type="text" id="share_link" name="share_link" value="{{ share_link }}" placeholder="例如: https://pan.baidu.com/s/1lYQWM8yI14wfsTwJoYJyaQ?pwd=tgn9 支持提取码自动填写" required>
        </div>
        <div class="form-group">
            <label for="password">提取码:</label>
            <input type="text" id="password" name="password" value="{{ password }}" placeholder="4位提取码" required>
        </div>
        <div class="form-group">
            <label for="save_path">转存路径:</label>
            <input type="text" id="save_path" name="save_path" value="{{ save_path }}" placeholder="例如: /转存文件">
        </div>
        <button type="submit">开始转存</button>
    </form>

    <div class="auth-info">
        <p>当前已授权应用访问您的百度网盘</p>
        <p><a href="{{ url_for('clear_auth') }}">清除授权</a></p>
    </div>
<script>
document.addEventListener('DOMContentLoaded', function() {
    const shareLinkInput = document.getElementById('share_link');
    const passwordInput = document.getElementById('password');

    shareLinkInput.addEventListener('paste', function(e) {
        setTimeout(function() {
            const pastedValue = shareLinkInput.value;
            if (pastedValue.includes('?pwd=')) {
                const parts = pastedValue.split('?pwd=');
                if (parts.length > 1) {
                    shareLinkInput.value = parts[0];
                    if (!passwordInput.value) {
                        passwordInput.value = parts[1].split('&')[0].split('#')[0];
                    }
                }
            }
        }, 0);
    });
});
</script>
</body>
</html>'''

    with open(os.path.join(templates_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(index_html)
    result_html = '''<!DOCTYPE html>
<html>
<head>
    <title>转存结果</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; text-align: center; }
        .success { background: #e8f5e9; padding: 20px; margin: 20px 0; }
        a { color: #4CAF50; text-decoration: none; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <h1>转存结果</h1>
    <div class="success">
        <h2>转存任务已提交！</h2>
        <p>请查看共享目录。</p>
    </div>
    <a href="/">返回首页</a>
</body>
</html>'''

    with open(os.path.join(templates_dir, 'result.html'), 'w', encoding='utf-8') as f:
        f.write(result_html)
    confirm_clear_html = '''<!DOCTYPE html>
<html>
<head>
    <title>清除授权确认</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; }
        input[type="password"] { width: 100%; padding: 8px; }
        button { background: #f44336; color: white; padding: 10px 15px; border: none; cursor: pointer; }
        .error { color: red; }
    </style>
</head>
<body>
    <h1>清除授权确认</h1>
    {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
            {% for category, message in messages %}
                <p class="{{ category }}">{{ message }}</p>
            {% endfor %}
        {% endif %}
    {% endwith %}

    <p>请输入管理员密码以清除授权信息:</p>

    <form method="POST">
        <div class="form-group">
            <label for="password">管理员密码:</label>
            <input type="password" id="password" name="password" required>
        </div>
        <button type="submit">确认清除</button>
        <a href="/" style="margin-left: 10px;">取消</a>
    </form>
</body>
</html>'''

    with open(os.path.join(templates_dir, 'confirm_clear.html'), 'w', encoding='utf-8') as f:
        f.write(confirm_clear_html)

@app.route('/clear-auth', methods=['GET', 'POST'])
def clear_auth():
    if request.method == 'POST':
        password = request.form.get('password')
        if password != ADMIN_PASSWORD:
            flash('密码错误', 'error')
            return render_template('confirm_clear.html')
        
        if os.path.exists(CONFIG_FILE):
            os.remove(CONFIG_FILE)
        flash('授权信息已清除，需要重新授权', 'success')
        return redirect(url_for('auth'))
    
    return render_template('confirm_clear.html')


if __name__ == '__main__':
    create_templates()
    app.run(debug=True, port=5000)

# BaiduYunTransfer
百度云网盘分享链接文件转存（基于OAuth2.0），接口很稳定，不必担心web接口经常发生变化，也无需担心输入验证码、cookie过期等问题。

## 文件说明
`BaiduYunTransfer.py`: 单文件python调用。

`bdwebui.py`：webui版本，有docker支持。默认转存文件位置 /转存文件。可以配合alist guest账户提供共享。

## 如何使用

| key        | value                       |
| ---------- | --------------------------- |
| api_key    | 应用id                      |
| secret_key | 应用secret                  |
| share_link | 分享链接                    |
| password   | 分享链接的提取码，长度为4位 |
| dir        | 转存路径，根路径为/         |
| new_name_list | 可用于批量更改转存文件（夹）的名称，具体注意事项请查阅脚本中的注释。 |

`api_key`和`secret_key`可以直接使用我程序里写好的，但是出于安全和QPS的考量，我推荐你自己再去申请一个，可以参考<https://pan.baidu.com/union/document/entrance#%E7%AE%80%E4%BB%8B>。

修改好以上几项后直接运行，第一次运行时需要你按照程序提示对应用进行授权。

# Webui相关

支持授权码填写，不再需要控制台输入。
支持清除授权，并有管理员认证防止误操作。

# WebUI Docker支持：

构建镜像:

`docker build -t baidu-transfer .`

运行容器:

使用随机密码

`docker run -p 5000:5000 -d baidu-transfer`

或者指定密码

`docker run -p 5000:5000 -e ADMIN_PASSWORD=yourpassword -d baidu-transfer`

也可以指定Flask secret key

`docker run -p 5000:5000 -e FLASK_SECRET_KEY=yoursecretkey -e ADMIN_PASSWORD=yourpassword -d baidu-transfer`

查看日志获取随机密码 (如果未设置ADMIN_PASSWORD):

`docker logs <container-id>`

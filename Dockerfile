# 使用官方Python基础镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用文件
COPY . .

# 暴露端口
EXPOSE 5000

# 设置环境变量
ENV FLASK_APP=bdwebui.py
ENV FLASK_ENV=production
ENV FLASK_SECRET_KEY=${FLASK_SECRET_KEY:-default-secret-key}

# 启动命令 - 这里会自动生成随机密码如果ADMIN_PASSWORD未设置
CMD ["sh", "-c", "python -m flask run --host=0.0.0.0 --port=5000"]

# 或者如果你想要gunicorn运行:
# RUN pip install gunicorn
# CMD ["gunicorn", "--bind", "0.0.0.0:5000", "bd:app"]

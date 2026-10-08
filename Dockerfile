# W5 部署到 HuggingFace Spaces 時使用；W4 在 Codespaces 開發用不到
FROM python:3.12-slim

# 以非 root 使用者執行（HuggingFace 建議 uid 1000）
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH
WORKDIR $HOME/app

# 先裝套件、再複製程式：只改程式時，不用重裝套件
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .

# HuggingFace Spaces 使用 7860 埠（README 開頭的 app_port）
EXPOSE 7860
CMD ["solara", "run", "app.py", "--host=0.0.0.0", "--port=7860", "--production"]

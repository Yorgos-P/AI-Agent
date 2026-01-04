FROM python:3.10.18-slim
WORKDIR /
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["streamlit", "run", "streamlit_gui.py", "--server.address=0.0.0.0", "--server.port=8080"]
FROM python:3.11-slim
WORKDIR /opt/sysmonitor
COPY conf/ ./conf/
COPY src/ ./src/
CMD ["python3", "src/monitor.py"]
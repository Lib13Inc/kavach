# Agent sandbox image. The agent code is ordinary; containment comes from
# how compose runs it (internal network, read-only FS, no caps, proxy env).
FROM python:3.12-slim
RUN pip install --no-cache-dir httpx==0.28.1 pyyaml==6.0.2 \
 && useradd -m -u 10001 agent
WORKDIR /app
COPY kavach/ kavach/
COPY agent/ agent/
USER agent
CMD ["python", "agent/agent.py", "--ticket", "2"]

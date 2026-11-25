# FedWind site agent (small: no torch). Build from the repo root:
#   docker build -f site_agent/Dockerfile -t fedwind-site-agent:0.2.0 .
# The site kit's docker-compose.yml runs it with the kit's .env, ./secrets, ./data and the token.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN pip install requests==2.32.3 cryptography==44.0.3

WORKDIR /opt
COPY site_agent /opt/site_agent
RUN rm -rf /opt/site_agent/tests

CMD ["python", "-m", "site_agent"]

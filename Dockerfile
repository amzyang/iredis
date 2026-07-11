FROM redis/redis-stack-server:latest

COPY . /iredis

RUN apt-get update --fix-missing
RUN apt-get install -yqq python3 python3-pip python-is-python3
WORKDIR /iredis
RUN pip install .
WORKDIR /
RUN rm -rf .cache /var/cache/apt
RUN rm -rf /iredis

CMD ["sh", "-c", "/opt/redis-stack/bin/redis-stack-server --daemonize yes && iredis"]

FROM debian:jessie

RUN apt-get update && apt-get install -y \
    nginx \
    sqlite3 \
    python-dev \
    python-pip \
    supervisor \
    libmemcached-dev \
    zlib1g-dev \
    libssl-dev \
    build-essential \
    uwsgi \
    uwsgi-plugin-python \
  && rm -rf /var/lib/apt/lists/*

RUN pip install pylibmc

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

RUN echo "daemon off;" >> /etc/nginx/nginx.conf
COPY doc/nginx.conf /etc/nginx/sites-enabled/default
COPY doc/docker/supervisord.conf /etc/supervisor/conf.d/

COPY . /opt/scoreboard
WORKDIR /opt/scoreboard

RUN python main.py createdb
RUN chmod 766 /tmp/scoreboard*

CMD ["/usr/bin/supervisord"]
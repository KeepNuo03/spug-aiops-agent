FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-server stress-ng prometheus-node-exporter procps \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /run/sshd \
    && sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config

# Lab-only credential; Spug uses it once to install its own SSH key.
ARG ROOT_PASSWORD=aiops-lab
RUN echo "root:${ROOT_PASSWORD}" | chpasswd

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 22 9100
CMD ["/entrypoint.sh"]

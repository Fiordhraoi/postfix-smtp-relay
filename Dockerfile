FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d \
    && apt-get update \
    && apt-get install -y --no-install-recommends postfix sasl2-bin libsasl2-modules ca-certificates openssl python3 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /etc/postfix/sasl /var/lib/postfix-tls
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY scripts/ /opt/relay/
COPY templates/ /opt/relay/templates/
RUN chmod 755 /usr/local/bin/entrypoint.sh
EXPOSE 25 587
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 CMD ["python3", "/opt/relay/healthcheck.py"]
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

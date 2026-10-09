# syntax=docker/dockerfile:1
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then printf 'Acquire::https::CaInfo "/run/secrets/proxy_ca";\n' > /etc/apt/apt.conf.d/99-build-ca; fi; \
    apt-get update && apt-get install -y --no-install-recommends asterisk sip-tester python3 ca-certificates && \
    rm -rf /var/lib/apt/lists/* /etc/apt/apt.conf.d/99-build-ca
RUN module_dir="$(find /usr/lib -type d -path '*/asterisk/modules' -print -quit)" && \
    test -n "$module_dir" && mkdir -p /usr/lib/asterisk && \
    if [ "$module_dir" != /usr/lib/asterisk/modules ]; then ln -s "$module_dir" /usr/lib/asterisk/modules; fi
USER 1000:1000
CMD ["asterisk", "-f", "-vvv"]

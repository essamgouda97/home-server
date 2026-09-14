FROM debian:trixie-slim@sha256:d7e12182ce18b85b93007c1dedf31f2d29e01ccf3182cc4017c709b6259bc132
RUN apt-get update && apt-get install -y --no-install-recommends \
    samba samba-vfs-modules smbclient tini ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1000 creative \
    && useradd -u 1000 -g creative -M -s /usr/sbin/nologin egouda
COPY entrypoint.sh /usr/local/bin/start-samba
RUN chmod 755 /usr/local/bin/start-samba
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/start-samba"]

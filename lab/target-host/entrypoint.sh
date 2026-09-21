#!/bin/sh
set -e
prometheus-node-exporter --web.listen-address=:9100 &
exec /usr/sbin/sshd -D -e

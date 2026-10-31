#!/bin/sh
# Runs after 20-envsubst-on-templates.sh has written default.conf. Like the stock image's
# 10-listen-on-ipv6-by-default.sh, listen on IPv6 only when the kernel has it: on a host booted
# with ipv6.disable=1, "listen [::]:80" would stop nginx from starting.
set -eu

if [ ! -f /proc/net/if_inet6 ]; then
    sed -i '/listen \[::\]:80;/d' /etc/nginx/conf.d/default.conf
    echo "$0: IPv6 is not available; listening on IPv4 only"
fi

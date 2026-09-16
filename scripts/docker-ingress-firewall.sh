#!/bin/bash
# Docker-published ports bypass UFW; reject WAN sources arriving on the LAN NIC.
set -euo pipefail
iptables -N HOME-SERVER-INGRESS 2>/dev/null || true
# Build once; repeated execution does not flush an active chain.
if ! iptables -C HOME-SERVER-INGRESS -i enp2s0 ! -s 10.0.0.0/24 -j DROP 2>/dev/null; then
  iptables -A HOME-SERVER-INGRESS -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
  iptables -A HOME-SERVER-INGRESS -i enp2s0 ! -s 10.0.0.0/24 -j DROP
  iptables -A HOME-SERVER-INGRESS -j RETURN
fi
iptables -C DOCKER-USER -j HOME-SERVER-INGRESS 2>/dev/null || iptables -I DOCKER-USER 1 -j HOME-SERVER-INGRESS

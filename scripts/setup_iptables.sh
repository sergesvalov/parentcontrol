#!/bin/bash
set -e

PROXY_PORT=${PROXY_PORT:-8080}

echo "Setting up iptables rules for transparent proxy..."

# Flush existing rules in mangle and nat tables
iptables -t mangle -F
iptables -t nat -F

# Create custom chains if they don't exist
iptables -t mangle -N DIVERT 2>/dev/null || iptables -t mangle -F DIVERT

# DIVERT chain: mark packets that are already established
iptables -t mangle -A DIVERT -j MARK --set-mark 1
iptables -t mangle -A DIVERT -j ACCEPT

# PREROUTING: handle already established connections
iptables -t mangle -A PREROUTING -p tcp -m socket -j DIVERT

# PREROUTING: redirect new TCP connections to transparent proxy
# Skip local traffic (lo interface)
iptables -t mangle -A PREROUTING -i lo -j ACCEPT

# Redirect TCP traffic to TPROXY
iptables -t mangle -A PREROUTING -p tcp --dport 80 -j TPROXY \
    --tproxy-mark 0x1/0x1 --on-port $PROXY_PORT
iptables -t mangle -A PREROUTING -p tcp --dport 443 -j TPROXY \
    --tproxy-mark 0x1/0x1 --on-port $PROXY_PORT

# Set up routing for TPROXY marked packets
ip rule add fwmark 1 lookup 100 2>/dev/null || true
ip route add local 0.0.0.0/0 dev lo table 100 2>/dev/null || true

# Allow forwarding
iptables -P FORWARD ACCEPT

# NAT rules for outgoing traffic
iptables -t nat -A POSTROUTING -j MASQUERADE

echo "iptables rules applied successfully"
echo "Transparent proxy listening on port $PROXY_PORT"

# Display current rules
echo ""
echo "Current mangle table rules:"
iptables -t mangle -L -n -v

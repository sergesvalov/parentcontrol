#!/bin/bash
set -e

echo "==================================================="
echo "Parent Control Gateway - Starting..."
echo "==================================================="

# Enable IP forwarding
echo "Enabling IP forwarding..."
echo 1 > /proc/sys/net/ipv4/ip_forward

# Create necessary directories
mkdir -p /app/data /app/logs

# Apply iptables rules for transparent proxy
echo "Configuring iptables rules..."
/app/scripts/setup_iptables.sh

# Start dnsmasq for DNS monitoring
echo "Starting DNS server..."
dnsmasq \
    --no-daemon \
    --listen-address=0.0.0.0 \
    --port=${DNS_PORT:-53} \
    --server=${DNS_UPSTREAM:-8.8.8.8} \
    --log-queries \
    --log-facility=/app/logs/dns.log \
    --cache-size=1000 \
    &

# Wait for DNS to start
sleep 2

# Initialize database
echo "Initializing database..."
python3 /app/src/db/init_db.py

# Start transparent proxy in background
echo "Starting transparent proxy..."
python3 /app/src/proxy/transparent_proxy.py &

# Wait for proxy to start
sleep 2

# Start API server (foreground)
echo "Starting API server..."
echo "==================================================="
echo "Gateway is ready!"
echo "API: http://localhost:${API_PORT:-8000}"
echo "==================================================="

cd /app/src/api
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port ${API_PORT:-8000} \
    --log-level ${LOG_LEVEL:-info}

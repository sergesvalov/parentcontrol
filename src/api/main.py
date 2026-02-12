"""
FastAPI application for Parent Control Gateway
"""
from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import datetime, timedelta
import asyncio
import sys

sys.path.append('/app')
from src.db.database import get_db, Connection, DNSQuery, Device, TrafficStats

app = FastAPI(
    title="Parent Control Gateway API",
    description="API for network traffic monitoring and control",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active websocket connections
active_connections: List[WebSocket] = []


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/stats/overview")
async def get_overview_stats(db: Session = Depends(get_db)):
    """Get overview statistics"""
    
    # Total devices
    total_devices = db.query(func.count(Device.id)).scalar() or 0
    
    # Active connections (last hour)
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    active_connections_count = db.query(func.count(Connection.id)).filter(
        Connection.timestamp >= one_hour_ago
    ).scalar() or 0
    
    # Total traffic today
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_traffic = db.query(
        func.sum(Connection.bytes_sent + Connection.bytes_received)
    ).filter(Connection.timestamp >= today).scalar() or 0
    
    # DNS queries today
    dns_queries_today = db.query(func.count(DNSQuery.id)).filter(
        DNSQuery.timestamp >= today
    ).scalar() or 0
    
    return {
        "total_devices": total_devices,
        "active_connections": active_connections_count,
        "total_traffic_bytes": int(today_traffic),
        "dns_queries_today": dns_queries_today,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/api/devices")
async def get_devices(db: Session = Depends(get_db)):
    """Get all known devices"""
    devices = db.query(Device).order_by(desc(Device.last_seen)).all()
    
    return [{
        "id": d.id,
        "mac_address": d.mac_address,
        "ip_address": d.ip_address,
        "hostname": d.hostname,
        "name": d.name,
        "first_seen": d.first_seen.isoformat(),
        "last_seen": d.last_seen.isoformat(),
        "total_bytes_sent": d.total_bytes_sent,
        "total_bytes_received": d.total_bytes_received,
        "connection_count": d.connection_count
    } for d in devices]


@app.get("/api/connections/recent")
async def get_recent_connections(
    limit: int = 100,
    device_ip: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get recent connections"""
    query = db.query(Connection).order_by(desc(Connection.timestamp))
    
    if device_ip:
        query = query.filter(Connection.src_ip == device_ip)
    
    connections = query.limit(limit).all()
    
    return [{
        "id": c.id,
        "timestamp": c.timestamp.isoformat(),
        "src_ip": c.src_ip,
        "src_port": c.src_port,
        "dst_ip": c.dst_ip,
        "dst_port": c.dst_port,
        "dst_domain": c.dst_domain,
        "bytes_sent": c.bytes_sent,
        "bytes_received": c.bytes_received,
        "duration": c.duration,
        "status": c.status
    } for c in connections]


@app.get("/api/dns/recent")
async def get_recent_dns_queries(
    limit: int = 100,
    device_ip: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get recent DNS queries"""
    query = db.query(DNSQuery).order_by(desc(DNSQuery.timestamp))
    
    if device_ip:
        query = query.filter(DNSQuery.client_ip == device_ip)
    
    queries = query.limit(limit).all()
    
    return [{
        "id": q.id,
        "timestamp": q.timestamp.isoformat(),
        "client_ip": q.client_ip,
        "domain": q.domain,
        "query_type": q.query_type,
        "response_ip": q.response_ip,
        "status": q.status
    } for q in queries]


@app.get("/api/stats/traffic/hourly")
async def get_hourly_traffic(
    hours: int = 24,
    device_mac: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get hourly traffic statistics"""
    start_time = datetime.utcnow() - timedelta(hours=hours)
    
    # Group connections by hour
    query = db.query(
        func.strftime('%Y-%m-%d %H:00:00', Connection.timestamp).label('hour'),
        func.sum(Connection.bytes_sent).label('bytes_sent'),
        func.sum(Connection.bytes_received).label('bytes_received'),
        func.count(Connection.id).label('connection_count')
    ).filter(Connection.timestamp >= start_time)
    
    if device_mac:
        query = query.filter(Connection.src_mac == device_mac)
    
    results = query.group_by('hour').order_by('hour').all()
    
    return [{
        "timestamp": r.hour,
        "bytes_sent": r.bytes_sent or 0,
        "bytes_received": r.bytes_received or 0,
        "total_bytes": (r.bytes_sent or 0) + (r.bytes_received or 0),
        "connection_count": r.connection_count
    } for r in results]


@app.get("/api/stats/top-domains")
async def get_top_domains(
    limit: int = 10,
    hours: int = 24,
    db: Session = Depends(get_db)
):
    """Get most accessed domains"""
    start_time = datetime.utcnow() - timedelta(hours=hours)
    
    results = db.query(
        DNSQuery.domain,
        func.count(DNSQuery.id).label('query_count')
    ).filter(
        DNSQuery.timestamp >= start_time,
        DNSQuery.domain.isnot(None)
    ).group_by(DNSQuery.domain).order_by(desc('query_count')).limit(limit).all()
    
    return [{
        "domain": r.domain,
        "query_count": r.query_count
    } for r in results]


@app.websocket("/ws/realtime")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time updates"""
    await websocket.accept()
    active_connections.append(websocket)
    
    try:
        while True:
            # Send periodic updates
            await asyncio.sleep(5)
            
            # Get latest stats (simplified for demo)
            data = {
                "type": "stats_update",
                "timestamp": datetime.utcnow().isoformat(),
                "active_connections": len(active_connections)
            }
            
            await websocket.send_json(data)
            
    except WebSocketDisconnect:
        active_connections.remove(websocket)


@app.put("/api/devices/{device_id}/name")
async def update_device_name(
    device_id: int,
    name: str,
    db: Session = Depends(get_db)
):
    """Update device name"""
    device = db.query(Device).filter(Device.id == device_id).first()
    
    if not device:
        return {"error": "Device not found"}, 404
    
    device.name = name
    db.commit()
    
    return {"success": True, "device_id": device_id, "name": name}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

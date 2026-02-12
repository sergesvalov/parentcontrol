"""
Database models for parent control gateway
"""
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, BigInteger, DateTime, Float, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

Base = declarative_base()


class Connection(Base):
    """TCP connection log"""
    __tablename__ = 'connections'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Source
    src_ip = Column(String(45), index=True)  # IPv6 support
    src_port = Column(Integer)
    src_mac = Column(String(17))
    
    # Destination
    dst_ip = Column(String(45), index=True)
    dst_port = Column(Integer)
    dst_domain = Column(String(255), index=True, nullable=True)
    
    # Traffic statistics
    bytes_sent = Column(BigInteger, default=0)
    bytes_received = Column(BigInteger, default=0)
    duration = Column(Float, default=0.0)  # seconds
    
    # Connection status
    status = Column(String(20), default='active')  # active, closed, timeout
    
    # Indexes for common queries
    __table_args__ = (
        Index('idx_timestamp_src', 'timestamp', 'src_ip'),
        Index('idx_timestamp_dst', 'timestamp', 'dst_ip'),
    )


class DNSQuery(Base):
    """DNS query log"""
    __tablename__ = 'dns_queries'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Client info
    client_ip = Column(String(45), index=True)
    client_mac = Column(String(17))
    
    # Query details
    domain = Column(String(255), index=True)
    query_type = Column(String(10))  # A, AAAA, CNAME, etc.
    
    # Response
    response_ip = Column(String(45))
    response_time = Column(Float)  # milliseconds
    
    # Status
    status = Column(String(20))  # success, blocked, nxdomain, etc.


class Device(Base):
    """Known devices on the network"""
    __tablename__ = 'devices'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    mac_address = Column(String(17), unique=True, index=True)
    
    # Device info
    ip_address = Column(String(45))
    hostname = Column(String(255), nullable=True)
    name = Column(String(255), nullable=True)  # User-assigned name
    
    # Tracking
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Statistics
    total_bytes_sent = Column(BigInteger, default=0)
    total_bytes_received = Column(BigInteger, default=0)
    connection_count = Column(Integer, default=0)


class TrafficStats(Base):
    """Aggregated traffic statistics per hour"""
    __tablename__ = 'traffic_stats'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, index=True)  # Rounded to hour
    
    # Device
    device_mac = Column(String(17), index=True, nullable=True)
    
    # Statistics
    total_connections = Column(Integer, default=0)
    total_bytes_sent = Column(BigInteger, default=0)
    total_bytes_received = Column(BigInteger, default=0)
    unique_domains = Column(Integer, default=0)
    
    __table_args__ = (
        Index('idx_timestamp_device', 'timestamp', 'device_mac'),
    )


# Database setup
DB_PATH = os.getenv('DB_PATH', '/app/data/traffic.db')
engine = create_engine(f'sqlite:///{DB_PATH}', echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_database():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)
    print(f"Database initialized at {DB_PATH}")

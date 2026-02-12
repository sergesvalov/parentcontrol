"""
Transparent TCP Proxy using TPROXY
"""
import asyncio
import socket
import struct
import logging
import os
import sys
from datetime import datetime

sys.path.append('/app')
from src.db.database import SessionLocal, Connection, Device

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('transparent_proxy')

# Constants
SO_ORIGINAL_DST = 80
PROXY_PORT = int(os.getenv('PROXY_PORT', 8080))
BUFFER_SIZE = 8192


class TransparentProxy:
    """Transparent TCP proxy with traffic logging"""
    
    def __init__(self, port=PROXY_PORT):
        self.port = port
        self.connections = {}  # Track active connections
        
    async def handle_client(self, client_socket, client_addr):
        """Handle client connection"""
        connection_id = f"{client_addr[0]}:{client_addr[1]}"
        
        try:
            # Get original destination using SO_ORIGINAL_DST
            try:
                dst = client_socket.getsockopt(
                    socket.SOL_IP, SO_ORIGINAL_DST, 16
                )
                dst_port, dst_ip = struct.unpack("!2xH4s8x", dst)
                dst_ip = socket.inet_ntoa(dst_ip)
            except Exception as e:
                logger.error(f"Failed to get original destination: {e}")
                client_socket.close()
                return
            
            logger.info(f"Connection {connection_id} -> {dst_ip}:{dst_port}")
            
            # Create connection log
            conn_log = {
                'src_ip': client_addr[0],
                'src_port': client_addr[1],
                'dst_ip': dst_ip,
                'dst_port': dst_port,
                'bytes_sent': 0,
                'bytes_received': 0,
                'start_time': datetime.utcnow()
            }
            
            # Connect to destination
            try:
                dest_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                dest_socket.settimeout(10)
                await asyncio.get_event_loop().sock_connect(
                    dest_socket, (dst_ip, dst_port)
                )
            except Exception as e:
                logger.error(f"Failed to connect to {dst_ip}:{dst_port}: {e}")
                client_socket.close()
                return
            
            # Create tasks for bidirectional forwarding
            client_to_server = asyncio.create_task(
                self.forward_data(client_socket, dest_socket, conn_log, 'sent')
            )
            server_to_client = asyncio.create_task(
                self.forward_data(dest_socket, client_socket, conn_log, 'received')
            )
            
            # Wait for both directions to complete
            await asyncio.gather(client_to_server, server_to_client, return_exceptions=True)
            
            # Log connection to database
            self.log_connection(conn_log)
            
        except Exception as e:
            logger.error(f"Error handling connection {connection_id}: {e}")
        finally:
            try:
                client_socket.close()
            except:
                pass
            try:
                dest_socket.close()
            except:
                pass
    
    async def forward_data(self, src_socket, dst_socket, conn_log, direction):
        """Forward data between sockets"""
        loop = asyncio.get_event_loop()
        
        try:
            while True:
                data = await loop.sock_recv(src_socket, BUFFER_SIZE)
                if not data:
                    break
                
                await loop.sock_sendall(dst_socket, data)
                
                # Update traffic statistics
                if direction == 'sent':
                    conn_log['bytes_sent'] += len(data)
                else:
                    conn_log['bytes_received'] += len(data)
                    
        except Exception as e:
            logger.debug(f"Forward error ({direction}): {e}")
    
    def log_connection(self, conn_log):
        """Log connection to database"""
        try:
            db = SessionLocal()
            
            # Calculate duration
            duration = (datetime.utcnow() - conn_log['start_time']).total_seconds()
            
            # Create connection record
            connection = Connection(
                src_ip=conn_log['src_ip'],
                src_port=conn_log['src_port'],
                dst_ip=conn_log['dst_ip'],
                dst_port=conn_log['dst_port'],
                bytes_sent=conn_log['bytes_sent'],
                bytes_received=conn_log['bytes_received'],
                duration=duration,
                status='closed'
            )
            
            db.add(connection)
            
            # Update or create device
            device = db.query(Device).filter(
                Device.ip_address == conn_log['src_ip']
            ).first()
            
            if device:
                device.last_seen = datetime.utcnow()
                device.total_bytes_sent += conn_log['bytes_sent']
                device.total_bytes_received += conn_log['bytes_received']
                device.connection_count += 1
            else:
                # Create new device
                device = Device(
                    ip_address=conn_log['src_ip'],
                    mac_address='unknown',  # Will be updated by ARP monitoring
                    total_bytes_sent=conn_log['bytes_sent'],
                    total_bytes_received=conn_log['bytes_received'],
                    connection_count=1
                )
                db.add(device)
            
            db.commit()
            
            logger.debug(
                f"Logged: {conn_log['src_ip']}:{conn_log['src_port']} -> "
                f"{conn_log['dst_ip']}:{conn_log['dst_port']} "
                f"({conn_log['bytes_sent']}↑/{conn_log['bytes_received']}↓)"
            )
            
        except Exception as e:
            logger.error(f"Failed to log connection: {e}")
        finally:
            db.close()
    
    async def start(self):
        """Start transparent proxy server"""
        # Create socket with IP_TRANSPARENT option
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Enable IP_TRANSPARENT (required for TPROXY)
        IP_TRANSPARENT = 19
        server.setsockopt(socket.SOL_IP, IP_TRANSPARENT, 1)
        
        server.bind(('0.0.0.0', self.port))
        server.listen(100)
        server.setblocking(False)
        
        logger.info(f"Transparent proxy listening on 0.0.0.0:{self.port}")
        
        loop = asyncio.get_event_loop()
        
        while True:
            client_socket, client_addr = await loop.sock_accept(server)
            asyncio.create_task(self.handle_client(client_socket, client_addr))


async def main():
    """Main entry point"""
    proxy = TransparentProxy()
    await proxy.start()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Transparent proxy stopped")

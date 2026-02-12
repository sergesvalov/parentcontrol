"""
DNS query monitor - parses dnsmasq logs
"""
import asyncio
import logging
import os
import sys
import re
from datetime import datetime

sys.path.append('/app')
from src.db.database import SessionLocal, DNSQuery

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('dns_monitor')

DNS_LOG_PATH = '/app/logs/dns.log'


class DNSMonitor:
    """Monitor DNS queries from dnsmasq logs"""
    
    def __init__(self, log_path=DNS_LOG_PATH):
        self.log_path = log_path
        self.position = 0
        
    def parse_dnsmasq_log(self, line):
        """Parse dnsmasq log line"""
        # Example: "Jan 12 19:00:00 dnsmasq[123]: query[A] example.com from 192.168.1.100"
        # Example: "Jan 12 19:00:00 dnsmasq[123]: reply example.com is 93.184.216.34"
        
        try:
            # Query pattern
            query_match = re.search(
                r'query\[(\w+)\]\s+([\w.-]+)\s+from\s+([\d.]+)',
                line
            )
            
            if query_match:
                query_type = query_match.group(1)
                domain = query_match.group(2)
                client_ip = query_match.group(3)
                
                return {
                    'type': 'query',
                    'query_type': query_type,
                    'domain': domain,
                    'client_ip': client_ip,
                    'timestamp': datetime.utcnow()
                }
            
            # Reply pattern
            reply_match = re.search(
                r'reply\s+([\w.-]+)\s+is\s+([\d.]+)',
                line
            )
            
            if reply_match:
                domain = reply_match.group(1)
                response_ip = reply_match.group(2)
                
                return {
                    'type': 'reply',
                    'domain': domain,
                    'response_ip': response_ip
                }
                
        except Exception as e:
            logger.debug(f"Failed to parse log line: {e}")
        
        return None
    
    def log_query(self, query_data):
        """Log DNS query to database"""
        try:
            db = SessionLocal()
            
            dns_query = DNSQuery(
                client_ip=query_data.get('client_ip'),
                domain=query_data.get('domain'),
                query_type=query_data.get('query_type'),
                response_ip=query_data.get('response_ip'),
                status='success',
                timestamp=query_data.get('timestamp', datetime.utcnow())
            )
            
            db.add(dns_query)
            db.commit()
            
            logger.debug(
                f"DNS query: {query_data.get('client_ip')} -> "
                f"{query_data.get('domain')} [{query_data.get('query_type')}]"
            )
            
        except Exception as e:
            logger.error(f"Failed to log DNS query: {e}")
        finally:
            db.close()
    
    async def monitor(self):
        """Monitor DNS log file for new queries"""
        logger.info(f"Monitoring DNS queries from {self.log_path}")
        
        # Wait for log file to be created
        while not os.path.exists(self.log_path):
            await asyncio.sleep(1)
        
        with open(self.log_path, 'r') as f:
            # Go to end of file
            f.seek(0, 2)
            self.position = f.tell()
            
            while True:
                line = f.readline()
                
                if line:
                    # Parse and log query
                    parsed = self.parse_dnsmasq_log(line)
                    if parsed and parsed['type'] == 'query':
                        self.log_query(parsed)
                    
                    self.position = f.tell()
                else:
                    # No new data, wait a bit
                    await asyncio.sleep(0.5)


async def main():
    """Main entry point"""
    monitor = DNSMonitor()
    await monitor.monitor()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("DNS monitor stopped")

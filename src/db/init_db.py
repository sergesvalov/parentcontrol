"""
Initialize database
"""
import sys
sys.path.append('/app')

from src.db.database import init_database

if __name__ == '__main__':
    init_database()

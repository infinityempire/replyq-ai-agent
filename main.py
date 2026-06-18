#!/usr/bin/env python3
"""
ReplyQ AI Agent - Main Entry Point
"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.main import app, configure_logging
import uvicorn
from config.settings import get_settings

if __name__ == "__main__":
    settings = get_settings()
    configure_logging()
    
    print(f"""
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║   ██████╗ ████████╗ ██████╗██████╗  ██████╗            ║
    ║   ██╔══██╗╚══██╔══╝██╔════╝██╔══██╗██╔═══██╗           ║
    ║   ██████╔╝   ██║   ██║     ██████╔╝██║   ██║           ║
    ║   ██╔═══╝    ██║   ██║     ██╔══██╗██║   ██║           ║
    ║   ██║        ██║   ╚██████╗██║  ██║╚██████╔╝           ║
    ║   ╚═╝        ╚═╝    ╚═════╝╚═╝  ╚═╝ ╚═════╝            ║
    ║                                                           ║
    ║   AI Agent - Customer Management & Sales                  ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )

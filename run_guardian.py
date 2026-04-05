#!/usr/bin/env python3
"""
Quick launcher for Project Guardian
Usage: python run_guardian.py
"""

import sys
import asyncio
import logging

# Setup basic logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def main():
    """Main launcher function."""
    print("=" * 60)
    print("Project Guardian - Starting...")
    print("=" * 60)
    print()
    
    try:
        # Import and run
        from project_guardian import __main__
        
        # Run async main
        exit_code = asyncio.run(__main__.main())
        
        if exit_code == 0:
            print("\nProject Guardian stopped successfully.")
        else:
            print(f"\nProject Guardian exited with code {exit_code}")
        
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        print("\n\nShutdown requested by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error starting Project Guardian: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()


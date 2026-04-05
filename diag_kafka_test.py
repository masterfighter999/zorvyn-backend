
import asyncio
import json
import os
import sys

# Add the project root to sys.path to import app modules
sys.path.append(os.getcwd())

from app.kafka.producer import send_event, TOPIC_RECORDS, get_producer, close_producer
from app.core.config import get_settings

async def test_kafka():
    settings = get_settings()
    print(f"Bootstrap Servers: {settings.KAFKA_BOOTSTRAP_SERVERS}")
    
    try:
        print("Attempting to connect and send test event...")
        payload = {"test": "data", "status": "diagnostic"}
        
        # Test sending an event
        await send_event(
            topic=TOPIC_RECORDS,
            event_type="DIAGNOSTIC_TEST",
            aggregate_type="system",
            aggregate_id=999,
            payload=payload
        )
        print("✅ Kafka event sent successfully!")
        
    except Exception as e:
        print(f"❌ Kafka diagnostic failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await close_producer()

if __name__ == "__main__":
    asyncio.run(test_kafka())

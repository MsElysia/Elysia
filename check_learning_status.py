"""Check if Elysia is learning by examining the timeline database."""

import sqlite3
from pathlib import Path

db_path = Path("elysia_timeline.db")

if not db_path.exists():
    print("❌ Timeline database not found - Elysia hasn't stored any memories yet")
    exit(1)

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

# Check total events
cursor.execute("SELECT COUNT(*) FROM timeline_events")
total_events = cursor.fetchone()[0]

# Check recent events
cursor.execute("""
    SELECT event_type, COUNT(*) as count 
    FROM timeline_events 
    GROUP BY event_type 
    ORDER BY count DESC 
    LIMIT 10
""")
event_types = cursor.fetchall()

# Check for memory-related events
cursor.execute("""
    SELECT COUNT(*) 
    FROM timeline_events 
    WHERE event_type LIKE '%memory%' 
       OR event_type LIKE '%learn%'
       OR event_type LIKE '%knowledge%'
""")
memory_events = cursor.fetchone()[0]

# Get most recent events
cursor.execute("""
    SELECT timestamp, event_type, summary, payload 
    FROM timeline_events 
    ORDER BY timestamp DESC 
    LIMIT 5
""")
recent_events = cursor.fetchall()

print("=" * 70)
print("ELYSIA LEARNING STATUS CHECK")
print("=" * 70)
print(f"\n📊 Total Timeline Events: {total_events}")
print(f"🧠 Memory-Related Events: {memory_events}")

print(f"\n📈 Top Event Types:")
for event_type, count in event_types:
    print(f"   {event_type}: {count}")

print(f"\n🕐 Most Recent Events:")
for timestamp, event_type, summary, payload in recent_events:
    print(f"   [{timestamp}] {event_type}")
    if summary:
        print(f"      Summary: {summary[:80]}")
    if payload:
        payload_preview = (payload[:80] + "...") if len(payload) > 80 else payload
        print(f"      Payload: {payload_preview}")

conn.close()

# Check if embeddings are being created (from log)
log_path = Path("elysia_unified.log")
if log_path.exists():
    with open(log_path, 'r', encoding='utf-8') as f:
        log_content = f.read()
        embedding_count = log_content.count("POST https://api.openai.com/v1/embeddings")
        print(f"\n🔗 Embedding API Calls (from log): {embedding_count}")
        
        if embedding_count > 0:
            print("   ✅ Elysia is creating embeddings (likely processing text for learning)")
        else:
            print("   ⚠️  No embedding calls found in recent log")

print("\n" + "=" * 70)
if total_events > 0:
    print("✅ Elysia is active and recording events")
else:
    print("⚠️  No events recorded yet - Elysia may not be learning")
print("=" * 70)


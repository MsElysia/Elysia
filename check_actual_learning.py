"""Check what Elysia is actually learning (excluding heartbeats)."""

import json
from pathlib import Path
from collections import Counter

print("=" * 70)
print("ELYSIA ACTUAL LEARNING ANALYSIS")
print("=" * 70)

# Check guardian_memory.json for non-heartbeat memories
guardian_mem = Path("guardian_memory.json")
if guardian_mem.exists():
    with open(guardian_mem, 'r', encoding='utf-8') as f:
        memories = json.load(f)
    
    # Filter out heartbeats
    non_heartbeat = [
        m for m in memories 
        if 'heartbeat' not in m.get('thought', '').lower() 
        and 'heartbeat' not in m.get('text', '').lower()
        and 'pulse' not in m.get('thought', '').lower()
        and 'pulse' not in m.get('text', '').lower()
    ]
    
    print(f"\n📚 Guardian Memory Analysis:")
    print(f"   Total memories: {len(memories)}")
    print(f"   Non-heartbeat memories: {len(non_heartbeat)}")
    
    if non_heartbeat:
        categories = Counter(m.get('category', 'unknown') for m in non_heartbeat)
        print(f"\n   Categories (excluding heartbeats):")
        for cat, count in categories.most_common(10):
            print(f"      {cat}: {count}")
        
        print(f"\n   Sample Learning Memories:")
        for i, mem in enumerate(non_heartbeat[-10:], 1):
            thought = mem.get('thought', mem.get('text', 'N/A'))
            category = mem.get('category', 'N/A')
            time = mem.get('time', mem.get('timestamp', 'N/A'))
            print(f"      {i}. [{time}] {category}")
            print(f"         {thought[:100]}...")
    else:
        print("\n   ⚠️  All memories are heartbeats - no actual learning content found")

# Check vector memory
vector_meta = Path("memory/vectors/metadata.json")
if vector_meta.exists():
    with open(vector_meta, 'r', encoding='utf-8') as f:
        vectors = json.load(f)
    
    non_heartbeat_vectors = [
        v for v in vectors
        if 'heartbeat' not in v.get('text', '').lower()
        and 'pulse' not in v.get('text', '').lower()
    ]
    
    print(f"\n🔗 Vector Memory Analysis:")
    print(f"   Total vectors: {len(vectors)}")
    print(f"   Non-heartbeat vectors: {len(non_heartbeat_vectors)}")
    
    if non_heartbeat_vectors:
        categories = Counter(v.get('category', 'unknown') for v in non_heartbeat_vectors)
        print(f"\n   Categories (excluding heartbeats):")
        for cat, count in categories.most_common(10):
            print(f"      {cat}: {count}")
        
        print(f"\n   Sample Learning Vectors:")
        for i, vec in enumerate(non_heartbeat_vectors[-10:], 1):
            text = vec.get('text', 'N/A')
            category = vec.get('category', 'N/A')
            timestamp = vec.get('timestamp', 'N/A')
            print(f"      {i}. [{timestamp}] {category}")
            print(f"         {text[:100]}...")

print("\n" + "=" * 70)
print("CONCLUSION")
print("=" * 70)

total_learning = len(non_heartbeat) + len(non_heartbeat_vectors) if 'non_heartbeat' in locals() and 'non_heartbeat_vectors' in locals() else 0

if total_learning > 0:
    print(f"✅ Elysia HAS learned {total_learning} non-heartbeat memories!")
    print("   These include:")
    if 'non_heartbeat' in locals() and non_heartbeat:
        categories = Counter(m.get('category', 'unknown') for m in non_heartbeat)
        print(f"   - {', '.join(categories.keys())}")
else:
    print("⚠️  Most memories are heartbeats - actual learning content is minimal")
    print("   Elysia is running but may not be actively learning new information")

print("=" * 70)


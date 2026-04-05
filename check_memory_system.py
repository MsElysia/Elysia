"""Check Elysia's memory system to see what's being learned."""

import json
from pathlib import Path
from collections import Counter
from datetime import datetime

print("=" * 70)
print("ELYSIA MEMORY SYSTEM ANALYSIS")
print("=" * 70)

# Check guardian_memory.json
guardian_mem = Path("guardian_memory.json")
if guardian_mem.exists():
    with open(guardian_mem, 'r', encoding='utf-8') as f:
        memories = json.load(f)
    
    print(f"\n📚 Guardian Memory (guardian_memory.json):")
    print(f"   Total memories: {len(memories)}")
    
    if memories and isinstance(memories, list):
        # Analyze categories
        categories = Counter(m.get('category', 'unknown') for m in memories)
        print(f"\n   Categories:")
        for cat, count in categories.most_common(10):
            print(f"      {cat}: {count}")
        
        # Show recent memories
        print(f"\n   Most Recent Memories:")
        for mem in memories[-5:]:
            thought = mem.get('thought', mem.get('text', 'N/A'))
            category = mem.get('category', 'N/A')
            time = mem.get('time', mem.get('timestamp', 'N/A'))
            print(f"      [{time}] {category}: {thought[:60]}...")
else:
    print("\n❌ guardian_memory.json not found")

# Check vector memory metadata
vector_meta = Path("memory/vectors/metadata.json")
if vector_meta.exists():
    with open(vector_meta, 'r', encoding='utf-8') as f:
        vector_data = json.load(f)
    
    print(f"\n🔗 Vector Memory (memory/vectors/metadata.json):")
    print(f"   Total vectors: {len(vector_data)}")
    
    if vector_data and isinstance(vector_data, list):
        # Analyze categories
        categories = Counter(v.get('category', 'unknown') for v in vector_data)
        print(f"\n   Categories:")
        for cat, count in categories.most_common(10):
            print(f"      {cat}: {count}")
        
        # Show recent vectors
        print(f"\n   Most Recent Vectors:")
        for vec in vector_data[-5:]:
            text = vec.get('text', 'N/A')
            category = vec.get('category', 'N/A')
            timestamp = vec.get('timestamp', 'N/A')
            print(f"      [{timestamp}] {category}: {text[:60]}...")
else:
    print("\n❌ Vector memory metadata not found")

# Check memory snapshots
snapshots_dir = Path("memory/snapshots")
if snapshots_dir.exists():
    shards = [d for d in snapshots_dir.iterdir() if d.is_dir()]
    print(f"\n💾 Memory Snapshots:")
    print(f"   Shards found: {len(shards)}")
    for shard in shards:
        files = list(shard.glob("*.json"))
        print(f"      {shard.name}: {len(files)} files")

# Summary
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

total_memories = 0
if guardian_mem.exists():
    with open(guardian_mem, 'r', encoding='utf-8') as f:
        total_memories += len(json.load(f))

if vector_meta.exists():
    with open(vector_meta, 'r', encoding='utf-8') as f:
        total_memories += len(json.load(f))

if total_memories > 0:
    print(f"✅ Elysia HAS stored {total_memories} memories!")
    print("   Memories are being stored in:")
    if guardian_mem.exists():
        print("   - guardian_memory.json")
    if vector_meta.exists():
        print("   - memory/vectors/metadata.json (with embeddings)")
else:
    print("⚠️  No memories found in storage systems")

print("=" * 70)


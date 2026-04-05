# ELYSIA_USER_GUIDE.md
# Complete User Guide for Elysia System

## 🚀 Quick Start

### Step 1: Start the System
Double-click: **INTERACT_ELYSIA.bat**

This opens an interactive menu where you can:
- Store memories
- Recall information
- Check system status
- Search your memories

---

## 📝 What Can You Do?

### 1. Store Information (Memories)
Elysia remembers everything you tell it:

```
Menu Option: 1. Store Memory
Enter memory: "I need to finish the project by Friday"
Category: tasks
```

**Why use this?**
- Keep track of important information
- Remember tasks and deadlines
- Store ideas and notes
- Build a knowledge base

### 2. Recall Information
Get back what you stored:

```
Menu Option: 2. Recall Memories
How many memories? 10
```

**Why use this?**
- Review what you've learned
- Check on tasks
- Remember past interactions
- Get context for current work

### 3. Search by Category
Find specific information:

```
Menu Option: 5. Search Memories
Category: tasks
```

**Why use this?**
- Find all tasks
- Review learning notes
- Check interactions
- Organize information

### 4. Check System Status
See how Elysia is doing:

```
Menu Option: 3. Show System Status
```

Shows:
- Total memories stored
- System health
- Uptime
- Component status

---

## 💡 Practical Examples

### Example 1: Task Management
```
1. Store Memory: "Buy groceries - milk, eggs, bread"
   Category: tasks

2. Store Memory: "Call dentist to schedule appointment"
   Category: tasks

3. Search Memories: Category "tasks"
   → See all your tasks
```

### Example 2: Learning Journal
```
1. Store Memory: "Learned about Python decorators today"
   Category: learning

2. Store Memory: "Important: decorators wrap functions"
   Category: learning

3. Recall Memories: 5
   → Review recent learning
```

### Example 3: Project Notes
```
1. Store Memory: "User requested new feature X"
   Category: project

2. Store Memory: "Feature X requires API changes"
   Category: project

3. Search Memories: Category "project"
   → Get all project-related info
```

---

## 🎯 Common Use Cases

### Use Case 1: Personal Assistant
- Store reminders and tasks
- Remember important dates
- Keep track of ideas
- Search for information when needed

### Use Case 2: Learning Companion
- Store what you learn
- Review concepts later
- Build a knowledge base
- Track your progress

### Use Case 3: Project Helper
- Store project notes
- Remember decisions made
- Track requirements
- Keep context across sessions

### Use Case 4: Development Tool
- Store code snippets
- Remember solutions
- Track bugs and fixes
- Keep development notes

---

## 🔧 Advanced Usage

### Using Python Directly

Create a file `my_script.py`:

```python
from project_guardian.core import GuardianCore

# Start Elysia
core = GuardianCore()

# Store information
core.memory.remember("Important note", category="notes")

# Get it back
memories = core.memory.recall_last(count=10)
for mem in memories:
    print(f"{mem['category']}: {mem['thought']}")

# Check status
status = core.get_system_status()
print(f"Total memories: {status['memory']['total_memories']}")

# Done
core.shutdown()
```

Run it:
```bash
python my_script.py
```

---

## 📋 Menu Reference

When you run **INTERACT_ELYSIA.bat**, you'll see:

```
1. Store Memory          → Save information
2. Recall Memories       → View recent memories
3. Show System Status    → Check system health
4. Show Startup Verification → See component status
5. Search Memories       → Find by category
6. Exit                  → Shut down safely
```

---

## 🎓 Tips for Best Results

1. **Use Categories**: Organize memories with categories like:
   - `tasks` - Things to do
   - `learning` - Things you learned
   - `ideas` - Ideas and thoughts
   - `project` - Project-related info
   - `notes` - General notes

2. **Be Specific**: Clear memories are easier to find:
   - Good: "Meeting with John at 3pm tomorrow"
   - Less useful: "Meeting"

3. **Regular Use**: The more you use it, the more useful it becomes

4. **Search Regularly**: Use search to find related information

5. **Review Often**: Recall memories to refresh your memory

---

## 🆘 Troubleshooting

**Problem**: Can't start the system
- **Solution**: Make sure Python is installed. Run `python --version` in command prompt.

**Problem**: Memories not showing up
- **Solution**: Make sure you're using the same system instance. Memories persist between sessions.

**Problem**: System seems slow
- **Solution**: This is normal on first startup. It gets faster as it loads.

**Problem**: Want to start fresh
- **Solution**: Delete `guardian_memory.json` to reset all memories (be careful!)

---

## 📚 Next Steps

1. **Try it**: Double-click **INTERACT_ELYSIA.bat** and explore
2. **Store some memories**: Start with a few test entries
3. **Recall them**: See how it works
4. **Search**: Try finding memories by category
5. **Build your knowledge base**: Use it regularly

---

## 🎉 You're Ready!

Elysia is a memory system that helps you:
- ✅ Remember information
- ✅ Organize knowledge
- ✅ Track tasks and ideas
- ✅ Build a personal knowledge base

**Start now**: Double-click **INTERACT_ELYSIA.bat** and begin!


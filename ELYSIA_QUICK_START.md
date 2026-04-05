# Elysia Quick Start Guide

## 🎯 Two Ways to Use Elysia

### 1. 🌐 Web UI Interface (Recommended)
Elysia has a beautiful web-based control panel!

**Start the UI:**
```bash
python start_ui_panel.py
```

Then open your browser to: **http://127.0.0.1:5000**

**Features:**
- 📊 Real-time dashboard
- 💬 Chat interface (if integrated)
- 🧠 Memory management
- 🔒 Security monitoring
- 📋 Task management
- 🔍 System introspection

### 2. 💬 Command-Line Chat Interface
For direct conversation with Elysia:

**Start the chat:**
```bash
python chat_with_elysia.py
```

## 🔑 API Keys Setup

Your API keys are automatically loaded from the `API keys` folder!

**Available API Keys:**
- ✅ ChatGPT API (for AI understanding)
- ✅ OpenRouter API
- ✅ Cohere API
- ✅ Hugging Face API
- ✅ Replicate API
- ✅ Alpha Vantage API

**To manually load API keys:**
```bash
python load_api_keys.py
```

## 🚀 Quick Start

1. **Load API keys** (automatic, but you can verify):
   ```bash
   python load_api_keys.py
   ```

2. **Start the UI**:
   ```bash
   python start_ui_panel.py
   ```

3. **Or start the chat**:
   ```bash
   python chat_with_elysia.py
   ```

## 📝 What Changed

✅ **Enhanced Chat Interface:**
- Now uses AI understanding (if OpenAI API key is available)
- Learns from conversations over time
- Maintains conversation context
- Falls back to keyword matching if AI not available

✅ **API Key Integration:**
- Automatically loads API keys from `API keys` folder
- Sets environment variables for all services
- Works with ChatGPT, OpenRouter, Cohere, etc.

✅ **UI Interface:**
- Web-based control panel at http://127.0.0.1:5000
- Real-time updates
- Full system monitoring and control

## 🎓 How Elysia Learns

**With AI Enabled:**
- Remembers your conversation style
- Learns your preferences
- Builds context from past interactions
- Improves responses over time

**Memory System:**
- Stores all conversations
- Categorizes memories
- Recalls relevant context
- Builds knowledge base

## 💡 Tips

- The UI and chat can run simultaneously
- API keys are loaded automatically when you run any script
- Elysia learns more the more you chat with it
- Use `help` command in chat for available commands
- Check the UI dashboard for system status

## 🆘 Troubleshooting

**UI won't start:**
- Check if port 5000 is already in use
- Install Flask: `pip install flask flask-socketio`

**Chat doesn't understand:**
- Make sure API keys are loaded
- Check if OpenAI API key is valid
- AI mode requires `openai` package: `pip install openai`

**API keys not loading:**
- Verify files exist in `API keys` folder
- Check file names match exactly
- Run `python load_api_keys.py` to see status


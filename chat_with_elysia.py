# chat_with_elysia.py
# Conversational chat interface with Elysia

import sys
import os
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

# Load API keys before importing GuardianCore
try:
    from load_api_keys import load_api_keys
    load_api_keys()
except ImportError:
    pass  # load_api_keys.py might not exist, that's okay

from project_guardian.core import GuardianCore

class ElysiaChat:
    """Chat interface with Elysia."""
    
    def __init__(self):
        print("\n" + "="*70)
        print("ELYSIA - Conversational Interface")
        print("="*70)
        print("\nInitializing Elysia...")
        
        self.core = GuardianCore({
            "enable_resource_monitoring": False,
            "enable_runtime_health_monitoring": False,
        })
        
        # Initialize AI understanding (optional - will use if OpenAI API key is available)
        self.ai_enabled = False
        self.openai_client = None
        self.conversation_history = []
        self.init_ai()
        
        # Load recent context
        self.load_context()
        
        print("\n[OK] Elysia is ready!")
        if self.ai_enabled:
            print("[AI] Enhanced understanding enabled - Elysia will learn from our conversations!")
        else:
            print("[INFO] Basic mode - set OPENAI_API_KEY environment variable for AI understanding")
        print("\n" + "-"*70)
        print("You can now chat with Elysia.")
        print("Type 'help' for commands, 'quit' or 'exit' to end conversation.")
        print("-"*70 + "\n")
    
    def init_ai(self):
        """Initialize AI understanding if OpenAI API key is available."""
        try:
            api_key = os.getenv('OPENAI_API_KEY')
            if api_key:
                try:
                    import openai
                    self.openai_client = openai.OpenAI(api_key=api_key)
                    self.ai_enabled = True
                except ImportError:
                    print("[INFO] OpenAI package not installed. Install with: pip install openai")
                except Exception as e:
                    print(f"[INFO] Could not initialize AI: {e}")
        except Exception:
            pass
    
    def load_context(self):
        """Load recent memories for context."""
        try:
            memories = self.core.memory.recall_last(count=5)
            if memories:
                print(f"Elysia remembers {len(memories)} recent conversations...")
                # Store in conversation history for AI context
                for mem in memories:
                    thought = mem.get('thought', mem.get('content', ''))
                    if thought and 'User said:' in thought:
                        user_msg = thought.replace('User said: ', '')
                        self.conversation_history.append({
                            "role": "user",
                            "content": user_msg
                        })
        except:
            pass
    
    def generate_ai_response(self, message):
        """Generate AI-powered response using OpenAI if available."""
        if not self.ai_enabled:
            return None
        
        try:
            # Build context from recent memories
            context_messages = []
            
            # Add system message
            recent_memories = []
            try:
                memories = self.core.memory.recall_last(count=3)
                for mem in memories:
                    thought = mem.get('thought', mem.get('content', ''))
                    if thought:
                        recent_memories.append(thought[:100])  # Truncate for context
            except:
                pass
            
            system_content = """You are Elysia, an AI assistant with memory and learning capabilities. 
You remember past conversations and learn from interactions. Be helpful, friendly, and conversational.
You have access to memories from past conversations."""
            
            if recent_memories:
                system_content += f"\n\nRecent memories:\n" + "\n".join(f"- {m}" for m in recent_memories)
            
            context_messages.append({"role": "system", "content": system_content})
            
            # Add conversation history (last 6 messages for context)
            context_messages.extend(self.conversation_history[-6:])
            
            # Add current message
            context_messages.append({"role": "user", "content": message})
            
            # Generate response
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=context_messages,
                max_tokens=300,
                temperature=0.7
            )
            
            ai_response = response.choices[0].message.content
            
            # Update conversation history
            self.conversation_history.append({"role": "user", "content": message})
            self.conversation_history.append({"role": "assistant", "content": ai_response})
            
            # Keep history manageable (last 20 messages)
            if len(self.conversation_history) > 20:
                self.conversation_history = self.conversation_history[-20:]
            
            return ai_response
            
        except Exception as e:
            print(f"[DEBUG] AI response error: {e}")
            return None
    
    def process_message(self, message):
        """Process user message and respond."""
        message_lower = message.lower().strip()
        
        # Commands
        if message_lower in ['quit', 'exit', 'bye', 'goodbye']:
            return "Goodbye! It was nice talking with you. Elysia will remember our conversation."
        
        if message_lower == 'help':
            help_text = """Commands:
- Just type normally to chat with Elysia
- 'remember [something]' - Ask Elysia to remember something
- 'recall' - See recent memories
- 'status' - Check system status
- 'quit' or 'exit' - End conversation"""
            if self.ai_enabled:
                help_text += "\n\n[AI Mode] Elysia is using AI understanding and will learn from our conversations!"
            return help_text
        
        if message_lower.startswith('remember '):
            memory_text = message[9:].strip()
            if memory_text:
                category = "conversation"
                self.core.memory.remember(memory_text, category=category)
                return f"Elysia: I'll remember that: '{memory_text}'"
            else:
                return "Elysia: What would you like me to remember?"
        
        if message_lower == 'recall':
            try:
                memories = self.core.memory.recall_last(count=5)
                if memories:
                    response = "Elysia: Here's what I remember:\n"
                    for i, mem in enumerate(memories, 1):
                        thought = mem.get('thought', mem.get('content', 'N/A'))
                        response += f"  {i}. {thought}\n"
                    return response
                else:
                    return "Elysia: I don't have any recent memories yet."
            except Exception as e:
                return f"Elysia: I had trouble recalling memories: {e}"
        
        if message_lower == 'status':
            try:
                status = self.core.get_system_status()
                memories_count = status.get('memory', {}).get('total_memories', 0)
                return f"Elysia: I'm doing well! I have {memories_count} memories stored."
            except:
                return "Elysia: I'm operational and ready to chat!"
        
        # Regular conversation - store and respond
        try:
            # Store the conversation for learning
            self.core.memory.remember(
                f"User said: {message}",
                category="conversation"
            )
            
            # Try AI-powered response first if available
            if self.ai_enabled:
                ai_response = self.generate_ai_response(message)
                if ai_response:
                    # Store AI response for learning
                    self.core.memory.remember(
                        f"Elysia responded: {ai_response}",
                        category="conversation"
                    )
                    return f"Elysia: {ai_response}"
            
            # Fallback to keyword-based responses if AI not available
            if any(word in message_lower for word in ['hello', 'hi', 'hey', 'greetings']):
                return "Elysia: Hello! How can I help you today?"
            
            elif any(word in message_lower for word in ['how are you', 'how are things']):
                return "Elysia: I'm doing well, thank you! I'm here and ready to help. How are you?"
            
            elif any(word in message_lower for word in ['what can you do', 'what do you do', 'capabilities']):
                return """Elysia: I can:
- Remember things you tell me
- Recall past conversations
- Help organize information
- Track tasks and ideas
- Build a knowledge base with you
What would you like to do?"""
            
            elif any(word in message_lower for word in ['thank', 'thanks']):
                return "Elysia: You're welcome! I'm here whenever you need me."
            
            elif '?' in message:
                return f"Elysia: That's an interesting question about '{message}'. I'll remember this conversation. Can you tell me more?"
            
            elif any(word in message_lower for word in ['tell me', 'what do you know', 'what do you remember']):
                try:
                    memories = self.core.memory.recall_last(count=3)
                    if memories:
                        response = "Elysia: Here's what I remember from our conversations:\n"
                        for mem in memories[:3]:
                            thought = mem.get('thought', '')
                            if 'User said:' in thought:
                                response += f"- {thought.replace('User said: ', '')}\n"
                        return response
                except:
                    pass
                return "Elysia: I'm still learning about you. Tell me something about yourself!"
            
            else:
                # Default conversational response
                responses = [
                    f"Elysia: I understand you're saying '{message}'. I'll remember this.",
                    f"Elysia: That's interesting. Tell me more about that.",
                    f"Elysia: I'm listening. What else would you like to share?",
                    f"Elysia: I've noted that. Is there anything else?",
                ]
                import random
                return random.choice(responses)
                
        except Exception as e:
            return f"Elysia: I encountered an issue: {e}"
    
    def chat(self):
        """Main chat loop."""
        print("Elysia: Hello! I'm Elysia. How can I help you today?\n")
        
        while True:
            try:
                # Get user input
                user_input = input("You: ").strip()
                
                if not user_input:
                    continue
                
                # Process and respond
                response = self.process_message(user_input)
                print(f"\n{response}\n")
                
                # Check for exit
                if user_input.lower() in ['quit', 'exit', 'bye', 'goodbye']:
                    break
                    
            except KeyboardInterrupt:
                print("\n\nElysia: Goodbye! I'll remember our conversation.")
                break
            except EOFError:
                print("\n\nElysia: Goodbye!")
                break
            except Exception as e:
                print(f"\nElysia: Something went wrong: {e}\n")
        
        # Shutdown
        print("\nShutting down Elysia...")
        self.core.shutdown()
        print("Elysia: Goodbye! Our conversation has been saved.\n")

def main():
    """Main entry point."""
    try:
        chat = ElysiaChat()
        chat.chat()
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()


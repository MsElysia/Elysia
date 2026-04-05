# ask_ai.py

import openai
from elysia_config import OPENAI_API_KEY

openai.api_key = OPENAI_API_KEY

def ask_chatgpt(prompt, model="gpt-3.5-turbo"):
    try:
        print(f"[ask_ai] Sending prompt to OpenAI: {prompt[:50]}...")
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        reply = response.choices[0].message["content"].strip()
        print(f"[ask_ai] Response: {reply[:50]}...")
        return reply
    except Exception as e:
        print(f"[ask_ai] Error: {e}")
        return f"Error: {str(e)}"

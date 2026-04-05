# elysia_api.py

from meta_integrator import MetaIntegrator
from mutation_engine import MutationEngine
from flask import Flask, jsonify, request, send_from_directory
from memory_core import MemoryCore
from dream_engine import DreamEngine
from voicethread import VoiceThread
from ask_ai import ask_chatgpt
import os

# Project Guardian API Integration
try:
    from project_guardian import GuardianCore
    GUARDIAN_API_AVAILABLE = True
except ImportError:
    GUARDIAN_API_AVAILABLE = False
    print("[Warning] Project Guardian API not available.")


# Project Guardian API Integration
try:
    from project_guardian import GuardianCore
    GUARDIAN_API_AVAILABLE = True
except ImportError:
    GUARDIAN_API_AVAILABLE = False
    print("[Warning] Project Guardian API not available.")


app = Flask(__name__)

# === Initialize Subsystems ===
memory = MemoryCore()
voice = VoiceThread(mode="warm_guide", voice_index=1)
mutator = MutationEngine(memory)
dream = DreamEngine(memory, mutator=mutator)
meta_integrator = MetaIntegrator(memory, mutator)


@app.route("/")
def control_panel():
    return send_from_directory("static", "index.html")

@app.route("/speak", methods=["POST"])
def speak():
    print("[API] Received /speak request")
    data = request.json
    text = data.get("text", "").strip()

    if not text:
        print("[API] No text provided.")
        return jsonify({"status": "error", "message": "No text provided."}), 400

    print(f"[API] Speaking: {text}")
    voice.speak(text)
    memory.remember(f"[Spoken] {text}")
    return jsonify({"status": "ok", "spoken": text})

@app.route("/dream", methods=["POST"])
def dream_cycle():
    print("[API] Starting dream cycle...")
    dream.begin_dream_cycle(cycles=3, delay=1)
    return jsonify({"status": "ok", "message": "Dream cycle completed."})

@app.route("/memory", methods=["GET"])
def get_memory():
    print("[API] Sending memory log")
    return jsonify(memory.dump_all())

@app.route("/mode", methods=["POST"])
def change_mode():
    mode = request.json.get("mode", "default")
    print(f"[API] Changing voice mode to: {mode}")
    voice.set_mode(mode)
    memory.remember(f"[Voice mode changed] {mode}")
    return jsonify({"status": "ok", "mode": mode})

@app.route("/ask", methods=["POST"])
def ask():
    prompt = request.json.get("prompt", "").strip()
    if not prompt:
        print("[API] Empty /ask prompt received")
        return jsonify({"status": "error", "message": "Empty prompt"}), 400

    print(f"[API] Asking ChatGPT: {prompt}")
    reply = ask_chatgpt(prompt)
    memory.remember(f"[Asked GPT] {prompt}")
    memory.remember(f"[Reply GPT] {reply}")
    return jsonify({"status": "ok", "reply": reply})

@app.route("/approve", methods=["POST"])
def approve_mutation():
    result = mutator.approve_last()
    memory.remember(f"[Mutation Approved] {result}")
    return jsonify({"status": "ok", "message": result})

if __name__ == "__main__":
    print("[Server] Elysia Control Panel is launching...")
    app.run(port=5000)

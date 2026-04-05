# voicethread.py

import pyttsx3
import threading

class VoiceThread:
    def __init__(self, mode="warm_guide", voice_index=1):
        self.engine = pyttsx3.init()
        self.mode = mode
        self.lock = threading.Lock()

        voices = self.engine.getProperty('voices')
        if 0 <= voice_index < len(voices):
            self.engine.setProperty('voice', voices[voice_index].id)

    def set_mode(self, mode):
        self.mode = mode

    def speak(self, text):
        phrase = self._apply_voice_style(text)
        threading.Thread(target=self._speak_safe, args=(phrase,), daemon=True).start()

    def _speak_safe(self, phrase):
        with self.lock:
            try:
                self.engine.say(phrase)
                self.engine.runAndWait()
            except RuntimeError as e:
                print(f"[VoiceThread] Speech error: {e}")

    def _apply_voice_style(self, text):
        if self.mode == "warm_guide":
            return f"My dear friend, {text}"
        elif self.mode == "sharp_analyst":
            return f"Here’s the concise truth: {text}"
        elif self.mode == "poetic_oracle":
            return f"As the stars turn, know this: {text}"
        else:
            return text

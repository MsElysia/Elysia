"""CI-only stub so Guardian can import VoiceThread without writing SpeechLib caches."""

def init(*_a, **_k):
    return Engine()


class Engine:
    def say(self, *_a, **_k):
        return None

    def runAndWait(self):
        return None

    def stop(self):
        return None

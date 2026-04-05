# web_reader.py

import requests
from bs4 import BeautifulSoup

class WebReader:
    def __init__(self, memory):
        self.memory = memory

    def fetch(self, url):
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            }
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code != 200:
                self.memory.remember(f"[WebReader] Failed to fetch: {url} (status {response.status_code})")
                return None

            soup = BeautifulSoup(response.text, "html.parser")
            paragraphs = soup.find_all("p")
            text = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
            self.memory.remember(f"[Observation] {url} →\n{text[:1000]}")
            return text

        except Exception as e:
            error = f"[WebReader Error] {str(e)}"
            self.memory.remember(error)
            return None

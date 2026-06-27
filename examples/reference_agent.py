# Dummy LlamaIndex pipeline example

class ReferenceAgent:
    def __init__(self):
        pass

    def run(self, query: str) -> str:
        """Simple echo pipeline for demonstration purposes."""
        return f"You asked: {query}"

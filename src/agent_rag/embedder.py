from sentence_transformers import SentenceTransformer


class LocalEmbedder:
    """Generates vector embeddings using a lightweight local model."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None

    def load(self) -> None:
        if not self._model:
            print(f"Loading embedding model '{self.model_name}'...")
            self._model = SentenceTransformer(self.model_name)

    def embed(self, text: str) -> list[float]:
        self.load()
        # Returns a numpy array, we convert to standard python floats for JSON/ES
        vector = self._model.encode(text)
        return vector.tolist()

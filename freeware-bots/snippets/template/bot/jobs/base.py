class Job:
    """Interface every job implements. Replies are dicts with at least "text"."""
    name = "base"

    def __init__(self, bot):
        self.bot = bot

    def health(self):
        return {}

    def handle_text(self, channel, user, text):
        return {"text": "This bot does not handle text messages."}

    def handle_photo(self, channel, user, data, filename=None):
        return {"text": "This bot does not handle photos.", "status": "unsupported"}

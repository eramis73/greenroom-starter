import dspy
import os

def configure_dspy():
    """Configure DSPy with Claude as the language model."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    lm = dspy.LM(
        model="claude-sonnet-4-6",
        api_key=api_key,
        max_tokens=2000,
    )
    dspy.configure(lm=lm)
    return lm

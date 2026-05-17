import dspy
import os


def configure_dspy():
    """
    Configure DSPy with the model specified via environment variables.
    DSPY_MODEL  — e.g. "claude-sonnet-4-6" or "openai/gpt-4o"
    DSPY_API_KEY — the key for whichever provider is selected
    """
    model = os.environ.get("DSPY_MODEL", "claude-sonnet-4-6")
    api_key = os.environ.get("DSPY_API_KEY", "")

    # Normalise OpenAI model names — DSPy expects the "openai/" prefix
    if model.startswith("gpt-") and not model.startswith("openai/"):
        model = f"openai/{model}"

    # Fall back to legacy env vars when DSPY_API_KEY is not set
    if not api_key:
        if "openai" in model:
            api_key = os.environ.get("OPENAI_API_KEY", "")
        else:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    lm = dspy.LM(model=model, api_key=api_key, max_tokens=2000)
    dspy.configure(lm=lm)
    return lm

# Package marker only — avoid importing app.main here so unit tests can
# import submodules (e.g. app.ai.summarizer) without loading the full ASGI app.

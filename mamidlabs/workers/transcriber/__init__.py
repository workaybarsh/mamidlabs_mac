"""MamidLabs local speech + sound event transcription pipeline.

Modules:
    config   tier = selected profile (lite/pro); VRAM is only a fallback (select_profile_for/select_profile)
    audio    conversion to 16 kHz mono WAV + chunking
    vad      Silero VAD speech ranges
    asr      faster-whisper (Whisper large-v3-tr), hallucination filters
    events   AudioSet/AST sound event labels
    diarize  pyannote speaker diarisation (optional)
    merge    chronological merge -> text
    main     runs the pipeline; writes txt + json
"""
# Package (agent\transcriber) version; INDEPENDENT of the application version
# (packaging\windows\mamidlabs.iss MyAppVersion) and does not have to match it.
__version__ = '1.0.0'

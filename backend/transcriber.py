import os

_model = None

def get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        model_size = os.getenv("WHISPER_MODEL", "base.en")
        print(f"Loading Whisper model '{model_size}' on CPU...")
        # Load whisper model on CPU with int8 quantization for speed & memory optimization
        _model = WhisperModel(model_size, device="cpu", compute_type="int8")
        print("Whisper model loaded successfully.")
    return _model

def transcribe_audio(audio_path: str, job_description: str = None) -> str:
    model = get_model()
    # Use the job description/context as an initial prompt to help Whisper with terminology/jargon
    initial_prompt = None
    if job_description:
        initial_prompt = f"This is an interview transcript. Context/Vocabulary: {job_description}"
    # Run transcription with beam_size=1 for 2x-3x CPU speedup, and restrict to English
    segments, info = model.transcribe(audio_path, beam_size=1, language="en", initial_prompt=initial_prompt)
    
    text_segments = []
    for segment in segments:
        text_segments.append(segment.text)
        
    return " ".join(text_segments).strip()

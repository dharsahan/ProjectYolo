import os
import sys

# Try to import faster_whisper. If it fails, we might be in the wrong environment.
try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

class LocalWhisper:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LocalWhisper, cls).__new__(cls)
            cls._instance.model = None
        return cls._instance
    
    def get_model(self):
        if self.model is None:
            if WhisperModel is None:
                raise ImportError("faster-whisper is not installed in the current environment.")
            
            # Using 'base' for a balance of speed and accuracy. 
            # 'tiny' is faster but less accurate.
            model_size = os.getenv("LOCAL_WHISPER_MODEL", "base")
            
            # device="cpu", compute_type="int8" is best for most non-GPU setups
            # if GPU is available, it would be device="cuda", compute_type="float16"
            self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
        return self.model

def transcribe_local(audio_path: str) -> str:
    """Transcribe an audio file using local faster-whisper."""
    try:
        lw = LocalWhisper()
        model = lw.get_model()
        
        segments, info = model.transcribe(audio_path, beam_size=5)
        
        text = ""
        for segment in segments:
            text += segment.text
            
        return text.strip()
    except Exception as e:
        return f"[Local Transcription Error: {str(e)}]"

if __name__ == "__main__":
    # Quick test if run directly
    if len(sys.argv) > 1:
        print(transcribe_local(sys.argv[1]))
    else:
        print("Usage: python whisper_local.py <audio_path>")

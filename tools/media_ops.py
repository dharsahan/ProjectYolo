import os
import datetime
from pathlib import Path
from openai import OpenAI
from tools.registry import register_tool
from tools.base import YOLO_ARTIFACTS, audit_log

@register_tool()
def transcribe_audio(file_path: str) -> str:
    """
    Transcribe an audio file (mp3, webm, wav, m4a, etc.) using the configured AI pipeline.
    If the file is not found at the provided path, it will also check the artifacts/uploads directory.
    """
    try:
        # 1. Resolve path
        path = Path(file_path)
        if not path.exists():
            # Check uploads directory
            uploads_dir = Path(YOLO_ARTIFACTS) / "uploads"
            path = uploads_dir / file_path.split("/")[-1]
            if not path.exists():
                return f"Error: Audio file not found at `{file_path}` or in uploads."

        # 2. Get configuration
        use_local = os.getenv("USE_LOCAL_WHISPER", "false").lower() == "true"
        
        if use_local:
            try:
                from whisper_local import transcribe_local
                text = transcribe_local(str(path))
            except Exception as le:
                return f"Error: Local transcription failed: {str(le)}. Check if faster-whisper is installed in the .venv."
        else:
            api_key = os.getenv("OPENAI_API_KEY")
            base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
            model_name = os.getenv("TRANSCRIPTION_MODEL_NAME", "whisper-1")

            if not api_key:
                return "Error: OPENAI_API_KEY is not set. Cannot transcribe audio via API."

            # 3. Call OpenAI/Whisper
            client = OpenAI(api_key=api_key, base_url=base_url)
            
            with open(path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model=model_name,
                    file=audio_file
                )
            
            text = getattr(transcript, "text", str(transcript))
        
        audit_log("transcribe_audio", {"file": str(path)}, "success")
        return f"### Transcription of {path.name}:\n\n{text.strip()}"
    except Exception as e:
        audit_log("transcribe_audio", {"file": file_path}, "error", str(e))
        return f"Error transcribing audio: {str(e)}"


@register_tool()
def generate_image(prompt: str) -> str:
    """
    Generate an image based on a prompt using DALL-E 3.
    The image is saved to the artifacts directory and sent to the UI.
    """
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return "Error: OPENAI_API_KEY is not set. Cannot generate image."

        client = OpenAI(api_key=api_key, base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
        
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )

        image_url = response.data[0].url
        
        # Download image to artifacts
        import httpx
        from tools.base import YOLO_ARTIFACTS
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"gen_{timestamp}.png"
        path = YOLO_ARTIFACTS / filename
        
        with httpx.Client() as h_client:
            resp = h_client.get(image_url)
            resp.raise_for_status()
            path.write_bytes(resp.content)
            
        audit_log("generate_image", {"prompt": prompt, "file": filename}, "success")
        return f"__SEND_FILE__:{path.resolve()}"
        
    except Exception as e:
        audit_log("generate_image", {"prompt": prompt}, "error", str(e))
        return f"Error generating image: {e}"

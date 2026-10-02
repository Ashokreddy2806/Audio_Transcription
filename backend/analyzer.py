import os
import time
import requests

# Load environment variables from .env file (check root and backend folders)
for folder in [
    os.path.dirname(os.path.abspath(__file__)),                  # backend folder
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # root folder
]:
    env_path = os.path.join(folder, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip().strip('"').strip("'")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def get_mime_type(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    mapping = {
        '.mp3': 'audio/mp3',
        '.wav': 'audio/wav',
        '.m4a': 'audio/m4a',
        '.webm': 'audio/webm',
        '.ogg': 'audio/ogg'
    }
    return mapping.get(ext, 'application/octet-stream')

def upload_audio_to_gemini(file_path: str, mime_type: str, api_key: str) -> tuple[str, str]:
    file_size = os.path.getsize(file_path)
    filename = os.path.basename(file_path)
    print(f"Uploading {filename} ({file_size} bytes) to Gemini File API...")
    
    # 1. Start resumable upload session
    if api_key.startswith("AQ."):
        url = "https://generativelanguage.googleapis.com/upload/v1beta/files"
        headers = {
            "x-goog-api-key": api_key,
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(file_size),
            "X-Goog-Upload-Header-Content-Type": mime_type,
            "Content-Type": "application/json"
        }
    else:
        url = f"https://generativelanguage.googleapis.com/upload/v1beta/files?key={api_key}"
        headers = {
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(file_size),
            "X-Goog-Upload-Header-Content-Type": mime_type,
            "Content-Type": "application/json"
        }
    metadata = {"file": {"display_name": filename}}
    
    response = requests.post(url, headers=headers, json=metadata, timeout=30)
    response.raise_for_status()
    upload_url = response.headers.get("X-Goog-Upload-URL")
    if not upload_url:
        raise RuntimeError("Failed to get upload URL from Gemini API.")
        
    # 2. Upload the file content
    with open(file_path, "rb") as f:
        headers_upload = {
            "X-Goog-Upload-Command": "upload, finalize",
            "X-Goog-Upload-Offset": "0",
            "Content-Length": str(file_size)
        }
        if api_key.startswith("AQ."):
            headers_upload["x-goog-api-key"] = api_key
        res_upload = requests.post(upload_url, headers=headers_upload, data=f, timeout=300)
    res_upload.raise_for_status()
    
    file_info = res_upload.json()
    file_uri = file_info["file"]["uri"]
    file_name_api = file_info["file"]["name"]  # resource name e.g., files/abc123xyz
    print(f"File uploaded successfully. URI: {file_uri}")
    return file_uri, file_name_api

def call_gemini_interactions_api(input_parts: list, api_key: str, model: str = "gemini-3.7-flash") -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/interactions"
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "input": input_parts
    }
    
    print(f"Calling Gemini Interactions API with model {model}...")
    response = requests.post(url, headers=headers, json=payload, timeout=600)
    if response.status_code != 200:
        print(f"Gemini Interactions API Error (Status {response.status_code}): {response.text}")
    response.raise_for_status()
    data = response.json()
    
    # Parse the response text from the steps
    text_parts = []
    try:
        for step in data.get("steps", []):
            for content in step.get("content", []):
                if content.get("role") == "model":
                    for part in content.get("parts", []):
                        if "text" in part:
                            text_parts.append(part["text"])
    except Exception as e:
        print(f"Error parsing interactions response: {e}")
        raise RuntimeError("Failed to parse response from Gemini Interactions API.")
        
    if not text_parts:
        print("Warning: Could not parse text using standard steps path. Full response:", data)
        raise RuntimeError("Empty response from Gemini Interactions API.")
        
    return "".join(text_parts)

def process_audio_and_jd_with_gemini(file_uri: str, file_name_api: str, mime_type: str, job_description: str, api_key: str) -> tuple[str, str]:
    jd_section = f"\nTarget Job Description:\n{job_description}\n" if job_description else "No target Job Description was provided."
    prompt = f"""You are an expert interview coach and transcription system.
First, listen to the uploaded audio and generate a highly accurate, word-for-word transcript.
Second, analyze the candidate's performance in the interview, comparing their responses against the target Job Description if provided.

{jd_section}

Your response MUST follow this exact format:
=== TRANSCRIPT ===
[Insert the complete word-for-word transcript of the interview here]

=== ANALYSIS ===
Provide detailed, constructive feedback in Markdown. You MUST include these three sections:
1. **Key Issues**: What were the main challenges, problems, or concerns raised during the interview? (Highlight any gaps relative to the Job Description).
2. **Mistakes Made**: What mistakes did the candidate make (e.g. lack of clarity, rambling, incorrect answers, communication style, etc.)?
3. **Actionable Improvements**: How can the candidate improve for future interviews? Provide clear, actionable advice.
"""

    if api_key.startswith("AQ."):
        print("Asking Gemini 3.7 Flash (via Interactions API) to transcribe and analyze the audio...")
        poll_url = f"https://generativelanguage.googleapis.com/v1beta/{file_name_api}"
        headers = {"x-goog-api-key": api_key}
        for _ in range(15):
            check_res = requests.get(poll_url, headers=headers, timeout=10)
            check_res.raise_for_status()
            state = check_res.json().get("file", {}).get("state")
            if state == "ACTIVE":
                break
            print(f"Waiting for audio file processing, current state: {state}...")
            time.sleep(2)

        input_parts = [
            {
                "type": "user_input",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "audio", "uri": file_uri, "mime_type": mime_type}
                ]
            }
        ]
        response_text = call_gemini_interactions_api(input_parts, api_key, model="gemini-3.7-flash")
        
        try:
            delete_url = f"https://generativelanguage.googleapis.com/v1beta/{file_name_api}"
            requests.delete(delete_url, headers={"x-goog-api-key": api_key}, timeout=10)
            print("Cleaned up file from Gemini API storage.")
        except Exception as e:
            print(f"Warning: Failed to delete remote file from Gemini API: {e}")
    else:
        print("Asking Gemini 1.5 Flash to transcribe and analyze the audio...")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        payload = {
            "contents": [{
                "parts": [
                    {"file_data": {"file_uri": file_uri, "mime_type": mime_type}},
                    {"text": prompt}
                ]
            }]
        }
        headers = {"Content-Type": "application/json"}
        
        poll_url = f"https://generativelanguage.googleapis.com/v1beta/{file_name_api}?key={api_key}"
        for _ in range(15):
            check_res = requests.get(poll_url, timeout=10)
            check_res.raise_for_status()
            state = check_res.json().get("file", {}).get("state")
            if state == "ACTIVE":
                break
            print(f"Waiting for audio file processing, current state: {state}...")
            time.sleep(2)
            
        response = requests.post(url, headers=headers, json=payload, timeout=600)
        response.raise_for_status()
        data = response.json()
        
        try:
            delete_url = f"https://generativelanguage.googleapis.com/v1beta/{file_name_api}?key={api_key}"
            requests.delete(delete_url, timeout=10)
            print("Cleaned up file from Gemini API storage.")
        except Exception as e:
            print(f"Warning: Failed to delete remote file from Gemini API: {e}")
            
        try:
            response_text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as e:
            print(f"Error parsing Gemini response: {e}")
            raise RuntimeError("Invalid response structure from Gemini API.")
        
    transcript = ""
    analysis = ""
    
    if "=== TRANSCRIPT ===" in response_text and "=== ANALYSIS ===" in response_text:
        parts = response_text.split("=== ANALYSIS ===")
        analysis = parts[1].strip()
        transcript_part = parts[0].replace("=== TRANSCRIPT ===", "").strip()
        transcript = transcript_part
    else:
        if "=== TRANSCRIPT ===" in response_text:
            transcript = response_text.replace("=== TRANSCRIPT ===", "").strip()
            analysis = "Analysis could not be separated. See transcript section."
        elif "=== ANALYSIS ===" in response_text:
            transcript = "Transcript could not be separated."
            analysis = response_text.replace("=== ANALYSIS ===", "").strip()
        else:
            transcript = "[Transcribed and analyzed by Gemini]"
            analysis = response_text
        
    return transcript, analysis

def analyze_transcript_with_ollama(prompt: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False
    }
    
    print(f"Sending transcript to local Ollama model '{OLLAMA_MODEL}' on CPU...")
    print("NOTE: On CPU, large interview transcripts can take several minutes to analyze. Please wait...")
    
    response = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=None)
    response.raise_for_status()
    data = response.json()
    return data.get("response", "No response received from local Ollama model.")

def analyze_transcript_with_gemini(prompt: str, api_key: str) -> str:
    if api_key.startswith("AQ."):
        input_parts = [
            {
                "type": "user_input",
                "content": [
                    {"type": "text", "text": prompt}
                ]
            }
        ]
        return call_gemini_interactions_api(input_parts, api_key, model="gemini-3.7-flash")
        
    print("Sending transcript to Google Gemini API (Gemini 1.5 Flash)...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{
            "parts": [{
                "text": prompt
            }]
        }]
    }
    
    response = requests.post(url, headers=headers, json=payload, timeout=90)
    response.raise_for_status()
    data = response.json()
    
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        print(f"Error parsing Gemini response structure: {e}")
        raise RuntimeError("Invalid response structure from Gemini API.")

def analyze_transcript(transcript: str, job_description: str = None) -> str:
    if not transcript:
        return "No transcript content provided for analysis."

    jd_section = f"\nTarget Job Description:\n{job_description}\n" if job_description else "No target Job Description was provided."

    prompt = f"""You are an expert interview coach. Below is a transcript of an interview.
Analyze the transcript and compare the candidate's answers against the target Job Description if provided.

{jd_section}

Your analysis MUST include the following three sections:
1. **Key Issues**: What were the main challenges, problems, or concerns raised during the interview? (Highlight any gaps relative to the Job Description).
2. **Mistakes Made**: What mistakes did the candidate make (e.g. lack of clarity, rambling, incorrect answers, communication style, etc.)?
3. **Actionable Improvements**: How can the candidate improve for future interviews? Provide clear, actionable advice on how to align responses with the Job Description.

Format your output in clean, readable Markdown with bullet points.

---
TRANSCRIPT:
{transcript}
---
"""

    if GEMINI_API_KEY:
        try:
            return analyze_transcript_with_gemini(prompt, GEMINI_API_KEY)
        except Exception as e:
            print(f"Gemini API analysis failed: {e}. Falling back to local Ollama...")
            
    try:
        return analyze_transcript_with_ollama(prompt)
    except requests.exceptions.RequestException as e:
        print(f"Error calling local Ollama API: {e}")
        raise RuntimeError(
            f"Failed to communicate with local Ollama service. "
            f"Error details: {e}"
        )

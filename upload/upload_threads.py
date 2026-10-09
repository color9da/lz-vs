"""
Threads Upload
Uploads video to Threads if credentials and account are active.
Includes safe error handling for suspended accounts and avoids committing media files to git.
"""

import os
import requests
import time
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)


def host_video_on_tmpfiles(video_path_obj):
    """Upload to tmpfiles.org and return a direct download URL (fallback host)."""
    with open(video_path_obj, 'rb') as video_file:
        files = {'file': ('video.mp4', video_file, 'video/mp4')}
        temp_response = requests.post(
            'https://tmpfiles.org/api/v1/upload',
            files=files,
            timeout=180
        )

    if temp_response.status_code != 200:
        raise Exception(f"tmpfiles.org upload failed: {temp_response.status_code}")

    temp_data = temp_response.json()
    if temp_data.get('status') != 'success':
        raise Exception(f"tmpfiles.org failed: {temp_data}")

    temp_url = temp_data.get('data', {}).get('url', '')
    video_url = temp_url.replace('tmpfiles.org/', 'tmpfiles.org/dl/').replace('http://', 'https://')
    return video_url


def upload_to_threads(video_path, text):
    """
    Upload video to Threads with graceful failure handling.
    """
    print("\n" + "=" * 60)
    print("THREADS UPLOAD")
    print("=" * 60)

    access_token = os.getenv('THREADS_ACCESS_TOKEN')
    user_id = os.getenv('THREADS_USER_ID')

    def mask(s): return f"{s[:4]}...{s[-4:]}" if s and len(s) > 8 else ("PLACEHOLDER" if s == "***" else "MISSING")
    print(f"[threads] User ID: {user_id}")
    print(f"[threads] Access Token: {mask(access_token)}")

    if not access_token or not user_id:
        print("[threads] Skipping - THREADS_ACCESS_TOKEN or THREADS_USER_ID not configured")
        return {'status': 'skipped', 'reason': 'Missing credentials', 'platform': 'threads'}

    video_path_obj = Path(video_path)
    if not video_path_obj.exists():
        print(f"[threads] Video file not found: {video_path}")
        return {'status': 'failed', 'reason': 'Video not found', 'platform': 'threads'}

    file_size_mb = video_path_obj.stat().st_size / (1024 * 1024)
    print(f"[threads] Video size: {file_size_mb:.2f} MB")

    text_limited = text[:500] if len(text) > 500 else text

    try:
        print("[threads] Preparing temporary public media URL...")
        video_url = host_video_on_tmpfiles(video_path_obj)
        print(f"[threads] Media URL ready: {video_url}")

        print("[threads] Creating Threads video container...")
        container_url = f"https://graph.threads.net/v1.0/{user_id}/threads"
        container_params = {
            'media_type': 'VIDEO',
            'video_url': video_url,
            'text': text_limited,
            'access_token': access_token
        }

        container_resp = requests.post(container_url, params=container_params, timeout=60)
        
        if container_resp.status_code != 200:
            err_data = container_resp.json() if container_resp.text else {}
            err_msg = err_data.get('error', {}).get('message', container_resp.text[:300])
            err_code = err_data.get('error', {}).get('code', 'N/A')
            print(f"[threads] ⚠️ Threads container creation failed (code {err_code}): {err_msg}")
            print("[threads] Note: If this account was suspended/restricted by Meta, API requests will fail.")
            return {'status': 'failed', 'reason': err_msg, 'platform': 'threads'}

        container_id = container_resp.json().get('id')
        print(f"[threads] Container created: {container_id}")

        print("[threads] Waiting for Threads video processing...")
        max_wait = 120
        waited = 0
        while waited < max_wait:
            time.sleep(10)
            waited += 10
            status_url = f"https://graph.threads.net/v1.0/{container_id}"
            status_resp = requests.get(status_url, params={'fields': 'status', 'access_token': access_token}, timeout=30)
            status = status_resp.json().get('status', 'UNKNOWN') if status_resp.status_code == 200 else 'CHECK_FAILED'
            print(f"[threads] Processing status: {status} (waited {waited}s)")
            if status == 'FINISHED':
                break
            elif status == 'ERROR':
                print("[threads] ⚠️ Threads video processing reported ERROR")
                return {'status': 'failed', 'reason': 'Processing error', 'platform': 'threads'}

        if waited >= max_wait:
            print("[threads] ⚠️ Threads video processing timed out")
            return {'status': 'timeout', 'reason': 'Timed out', 'platform': 'threads'}

        print("[threads] Publishing to Threads...")
        publish_url = f"https://graph.threads.net/v1.0/{user_id}/threads_publish"
        publish_resp = requests.post(publish_url, params={'creation_id': container_id, 'access_token': access_token}, timeout=60)
        
        if publish_resp.status_code == 200:
            thread_id = publish_resp.json().get('id')
            print(f"[threads] 🎉 SUCCESS! Published to Threads: ID {thread_id}")
            return {'id': thread_id, 'platform': 'threads', 'status': 'success'}
        else:
            err_msg = publish_resp.json().get('error', {}).get('message', publish_resp.text[:200])
            print(f"[threads] ⚠️ Threads publishing failed: {err_msg}")
            return {'status': 'failed', 'reason': err_msg, 'platform': 'threads'}

    except Exception as e:
        print(f"[threads] ⚠️ Threads exception occurred: {e}")
        return {'status': 'failed', 'reason': str(e), 'platform': 'threads'}
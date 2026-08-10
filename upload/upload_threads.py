""" Threads Upload - Enhanced Debugging Version
Uploads video to GitHub raw (preferred) or tmpfiles.org fallback.
"""

import os
import requests
import time
import shutil
import subprocess
from pathlib import Path

GITHUB_REPO = "color9da/lz-vs"
GITHUB_RAW = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/lz_vs_short.mp4"


def host_video_on_github(video_path_obj):
    """
    Commit the video into the repo at lz_vs_short.mp4 and return its
    raw.githubusercontent.com URL. Requires GH_TOKEN (a PAT) in the environment.
    """
    gh_token = os.getenv("GH_TOKEN") or os.getenv("GH_PAT")
    if not gh_token:
        raise ValueError("GH_TOKEN/GH_PAT not set for GitHub video hosting")

    print("[threads] Step 1a: Hosting video on GitHub raw...")
    dest = Path("lz_vs_short.mp4")
    shutil.copyfile(video_path_obj, dest)

    env = dict(os.environ, GH_TOKEN=gh_token)
    cmds = [
        ["git", "config", "--global", "user.email", "github-actions[bot]@users.noreply.github.com"],
        ["git", "config", "--global", "user.name", "github-actions[bot]"],
        ["git", "add", "-f", "lz_vs_short.mp4"],
    ]
    for c in cmds:
        subprocess.run(c, capture_output=True, env=env)

    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True, env=env)
    if diff.returncode == 0:
        print("[threads] Media unchanged on GitHub, reusing URL")
    else:
        subprocess.run(["git", "commit", "-m", "chore: update thread media [skip ci]"], capture_output=True, env=env)
        subprocess.run(["git", "config", "http.extraHeader", f"AUTHORIZATION: bearer {gh_token}"], capture_output=True, env=env)
        # Pull latest first, then normal push (never force-push, which breaks history)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], capture_output=True, env=env)
        push = subprocess.run(["git", "push", "origin", "HEAD:main"], capture_output=True, env=env, text=True)
        if push.returncode != 0:
            raise ValueError(f"git push failed: {push.stderr[-300:]}")
        subprocess.run(["git", "config", "--unset", "http.extraHeader"], capture_output=True, env=env)

    print(f"[threads] GitHub URL: {GITHUB_RAW}")
    return GITHUB_RAW


def host_video_on_tmpfiles(video_path_obj):
    """
    Upload to tmpfiles.org and return a direct download URL (fallback host).
    """
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
    print(f"[threads] Temporary URL created: {video_url}")
    return video_url


def upload_to_threads(video_path, text):
    """
    Upload video to Threads via a reliable public URL.
    """
    print("\n" + "=" * 60)
    print("THREADS UPLOAD STARTING")
    print("=" * 60)

    access_token = os.getenv('THREADS_ACCESS_TOKEN')
    user_id = os.getenv('THREADS_USER_ID')

    def mask(s): return f"{s[:4]}...{s[-4:]}" if s and len(s) > 8 else ("PLACEHOLDER (***)" if s == "***" else "MISSING")
    print(f"[threads] User ID: {user_id}")
    print(f"[threads] Access Token: {mask(access_token)}")

    if not access_token:
        error_msg = "THREADS_ACCESS_TOKEN not set"
        print(f"[threads] {error_msg}")
        raise ValueError(error_msg)

    if not user_id:
        error_msg = "THREADS_USER_ID not set"
        print(f"[threads] {error_msg}")
        raise ValueError(error_msg)

    print("[threads] Credentials loaded")

    video_path_obj = Path(video_path)
    if not video_path_obj.exists():
        error_msg = f"Video file not found: {video_path}"
        print(f"[threads] {error_msg}")
        raise FileNotFoundError(error_msg)

    file_size_mb = video_path_obj.stat().st_size / (1024 * 1024)
    print(f"[threads] Video file found: {video_path}")
    print(f"[threads] Video size: {file_size_mb:.2f} MB")

    text_limited = text[:500] if len(text) > 500 else text
    print(f"[threads] Text length: {len(text_limited)} characters")

    video_url = None

    # Step 1: Host the video on a reliable public URL.
    # Preferred: commit it to the GitHub repo (raw.githubusercontent.com is
    # reliable for Threads to fetch). Fallback: tmpfiles.org temporary host.
    try:
        video_url = host_video_on_github(video_path_obj)
    except Exception as gh_err:
        print(f"[threads] GitHub hosting failed: {gh_err}")
        print("[threads] Falling back to tmpfiles.org...")
        video_url = host_video_on_tmpfiles(video_path_obj)

    if not video_url:
        raise Exception("Failed to obtain a public video URL")

    try:
        print(f"[threads] Temporary URL ready: {video_url}")

        # Step 2: Create Threads container with video URL
        print("[threads] Step 2: Creating Threads container...")

        api_versions = ['v1.0', 'v18.0']
        container_id = None

        for api_version in api_versions:
            print(f"[threads] Trying API version: {api_version}")

            container_url = f"https://graph.threads.net/{api_version}/{user_id}/threads"
            container_params = {
                'media_type': 'VIDEO',
                'video_url': video_url,
                'text': text_limited,
                'access_token': access_token
            }

            print(f"[threads] Request URL: {container_url}")
            print(f"[threads] Parameters: media_type=VIDEO, video_url={video_url[:50]}..., text length={len(text_limited)}")

            container_response = requests.post(container_url, params=container_params, timeout=60)

            print(f"[threads] Response status: {container_response.status_code}")
            print(f"[threads] Response headers: {dict(container_response.headers)}")
            print(f"[threads] Response body: {container_response.text}")

            if container_response.status_code == 200:
                response_data = container_response.json()
                container_id = response_data.get('id')
                if container_id:
                    print(f"[threads] Container created with API {api_version}: {container_id}")
                    break
            else:
                error_data = container_response.json() if container_response.text else {}
                error_msg = error_data.get('error', {}).get('message', 'Unknown error')
                error_code = error_data.get('error', {}).get('code', 'N/A')
                error_type = error_data.get('error', {}).get('type', 'N/A')
                error_subcode = error_data.get('error', {}).get('error_subcode', 'N/A')

                print(f"[threads] API {api_version} failed:")
                print(f"[threads]    Error type: {error_type}")
                print(f"[threads]    Error code: {error_code}")
                print(f"[threads]    Error subcode: {error_subcode}")
                print(f"[threads]    Error message: {error_msg}")

        if not container_id:
            error_msg = "Failed to create container with all API versions"
            print(f"[threads] {error_msg}")
            raise Exception(error_msg)

        # Step 3: Wait for processing
        print("[threads] Step 3: Waiting for video processing...")
        max_wait = 120
        waited = 0

        while waited < max_wait:
            status_url = f"https://graph.threads.net/v1.0/{container_id}"
            status_params = {
                'fields': 'status',
                'access_token': access_token
            }

            status_response = requests.get(status_url, params=status_params, timeout=30)
            status_data = status_response.json()
            status = status_data.get('status', 'UNKNOWN')

            print(f"[threads] Status: {status} (waited {waited}s)")

            if status == 'FINISHED':
                print("[threads] Video processing complete!")
                break
            elif status == 'ERROR':
                error_msg = status_data.get('error_message', 'Video processing failed')
                print(f"[threads] {error_msg}")
                raise Exception(error_msg)

            time.sleep(10)
            waited += 10

        if waited >= max_wait:
            error_msg = "Video processing timed out"
            print(f"[threads] {error_msg}")
            raise Exception(error_msg)

        # Step 4: Publish
        print("[threads] Step 4: Publishing to Threads...")
        publish_url = f"https://graph.threads.net/v1.0/{user_id}/threads_publish"
        publish_params = {
            'creation_id': container_id,
            'access_token': access_token
        }

        publish_response = requests.post(publish_url, params=publish_params, timeout=60)

        if publish_response.status_code != 200:
            error_data = publish_response.json() if publish_response.text else {}
            error_msg = error_data.get('error', {}).get('message', 'Unknown error')
            print(f"[threads] Publish failed: {error_msg}")
            raise Exception(f"Threads Publish Error: {error_msg}")

        thread_id = publish_response.json().get('id')

        print("[threads] SUCCESS! Video published to Threads!")
        print(f"[threads] Thread ID: {thread_id}")
        print("[threads] Check your Threads profile to see the post!")
        print("=" * 60)

        return {
            'id': thread_id,
            'platform': 'threads',
            'status': 'success'
        }

    except Exception as e:
        print("[threads] ERROR!")
        print(f"[threads] {str(e)}")
        print("=" * 60)
        raise


if __name__ == '__main__':
    video_file = Path('output/final_video.mp4')
    if video_file.exists():
        try:
            result = upload_to_threads(str(video_file), "Test upload")
            print(f"\nSuccess! Result: {result}")
        except Exception as e:
            print(f"\nFailed: {e}")
    else:
        print(f"Video not found: {video_file}")
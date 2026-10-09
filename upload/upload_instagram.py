"""
Instagram Reels & Stories Upload
Direct Resumable Upload via Meta Graph API v21.0 (No third-party host / No GitHub API required)
"""
import os
import requests
import time
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)


def upload_to_instagram(video_path, caption, is_story=False):
    media_type = 'STORIES' if is_story else 'REELS'
    
    print("\n" + "=" * 60)
    print(f"INSTAGRAM {media_type} UPLOAD (Direct Resumable API v21.0)")
    print("=" * 60)
    
    access_token = os.getenv('INSTAGRAM_ACCESS_TOKEN') or os.getenv('FACEBOOK_ACCESS_TOKEN')
    user_id = os.getenv('INSTAGRAM_ACCOUNT_ID') or os.getenv('IG_USER_ID')
    
    def mask(s): return f"{s[:10]}...{s[-4:]}" if s and len(s) > 10 else ("PLACEHOLDER" if s == "***" else "MISSING")
    print(f"[instagram] User ID Provided: {user_id}")
    print(f"[instagram] Access Token: {mask(access_token)}")

    if not access_token:
        print("[instagram] Skipping - no token provided")
        return {'status': 'skipped', 'reason': 'Missing credentials', 'platform': 'instagram'}
    
    api_base = "https://graph.facebook.com/v21.0"

    # Auto-resolve Instagram Business Account ID if Page Token (EAAM...) is used
    if access_token.startswith('EAAM'):
        print("[instagram] EAAM Page token detected, resolving connected Instagram Business Account ID...")
        try:
            me_resp = requests.get(f"{api_base}/me?fields=id,name&access_token={access_token}", timeout=15)
            if me_resp.status_code == 200:
                page_id = me_resp.json().get('id')
                print(f"[instagram] Facebook Page ID: {page_id}")
                ig_resp = requests.get(f"{api_base}/{page_id}?fields=instagram_business_account&access_token={access_token}", timeout=15)
                if ig_resp.status_code == 200:
                    ig_account = ig_resp.json().get('instagram_business_account')
                    if ig_account:
                        ig_id = ig_account.get('id')
                        if ig_id != user_id:
                            print(f"[instagram] Resolved Instagram Business Account ID: {ig_id} (configured: {user_id})")
                            user_id = ig_id
                    else:
                        print("[instagram] Warning: No Instagram Business Account connected to this Page")
        except Exception as e:
            print(f"[instagram] Warning while resolving IG ID: {e}")

    if not user_id:
        print("[instagram] Skipping - no Instagram user ID available")
        return {'status': 'skipped', 'reason': 'Missing user ID', 'platform': 'instagram'}

    video_path_obj = Path(video_path)
    if not video_path_obj.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    
    file_size = video_path_obj.stat().st_size
    file_size_mb = file_size / (1024 * 1024)
    print(f"[instagram] Video: {video_path} ({file_size_mb:.2f} MB)")
    
    caption_limited = caption[:2200] if len(caption) > 2200 else caption
    print(f"[instagram] Caption length: {len(caption_limited)} chars")

    # Step 1: Create Resumable Upload Container
    print(f"[instagram] Step 1: Creating resumable {media_type} container...")
    container_params = {
        'media_type': media_type,
        'upload_type': 'resumable',
        'access_token': access_token
    }
    
    if not is_story:
        container_params['share_to_feed'] = 'false'
        container_params['caption'] = caption_limited

    container_resp = requests.post(f"{api_base}/{user_id}/media", params=container_params, timeout=60)
    if container_resp.status_code != 200:
        error_info = container_resp.json() if container_resp.text else {}
        error_msg = error_info.get('error', {}).get('message', container_resp.text[:300])
        raise Exception(f"Container creation failed ({container_resp.status_code}): {error_msg}")

    container_data = container_resp.json()
    container_id = container_data.get('id')
    upload_url = container_data.get('uri')

    if not container_id:
        raise Exception(f"No container ID returned: {container_data}")

    print(f"[instagram] ✅ Container created: {container_id}")

    # Step 2: Transfer raw video bytes directly to Meta
    print(f"[instagram] Step 2: Streaming video bytes to Meta servers...")
    if not upload_url:
        upload_url = f"https://rupload.facebook.com/ig-reels/{container_id}"

    headers = {
        'Authorization': f'OAuth {access_token}',
        'offset': '0',
        'file_size': str(file_size),
        'Content-Type': 'application/octet-stream'
    }

    with open(video_path, 'rb') as f:
        upload_resp = requests.post(upload_url, headers=headers, data=f, timeout=300)

    if upload_resp.status_code not in (200, 201):
        raise Exception(f"Binary upload failed ({upload_resp.status_code}): {upload_resp.text[:400]}")

    print("[instagram] ✅ Video bytes transferred successfully!")

    # Step 3: Wait for Meta processing
    print("[instagram] Step 3: Waiting for Meta to process container...")
    max_wait = 240
    waited = 0
    poll_interval = 15

    while waited < max_wait:
        time.sleep(poll_interval)
        waited += poll_interval

        status_resp = requests.get(f"{api_base}/{container_id}", params={
            'fields': 'status_code,status',
            'access_token': access_token
        }, timeout=30)

        if status_resp.status_code != 200:
            print(f"[instagram] Status check failed ({status_resp.status_code}): {status_resp.text[:200]}")
            continue

        status_data = status_resp.json()
        status_code = status_data.get('status_code') or status_data.get('status', 'UNKNOWN')
        print(f"[instagram] Processing status: {status_code} (waited {waited}s)")

        if status_code == 'FINISHED':
            print("[instagram] ✅ Processing complete!")
            break
        elif status_code == 'ERROR':
            err_msg = status_data.get('error_message', 'Processing error')
            raise Exception(f"Meta processing failed: {err_msg}")

    if waited >= max_wait:
        raise TimeoutError("Meta container processing timed out after 240s")

    time.sleep(5)

    # Step 4: Publish container
    print(f"[instagram] Step 4: Publishing {media_type}...")
    max_publish_attempts = 4
    media_id = None

    for attempt in range(1, max_publish_attempts + 1):
        pub_resp = requests.post(f"{api_base}/{user_id}/media_publish", params={
            'creation_id': container_id,
            'access_token': access_token
        }, timeout=60)

        if pub_resp.status_code == 200:
            media_id = pub_resp.json().get('id')
            print(f"[instagram] 🎉 SUCCESS! Media ID: {media_id}")
            break
        else:
            err_txt = pub_resp.text[:300]
            print(f"[instagram] Publish attempt {attempt} failed: {err_txt}")
            if attempt < max_publish_attempts:
                time.sleep(15)

    if not media_id:
        raise Exception(f"Failed to publish after {max_publish_attempts} attempts: {pub_resp.text[:400]}")

    print("=" * 60)
    return {'id': media_id, 'platform': 'instagram', 'status': 'success'}


if __name__ == '__main__':
    test_vid = Path('lz_vs_short.mp4')
    if test_vid.exists():
        try:
            res = upload_to_instagram(str(test_vid), "Test upload")
            print(f"Result: {res}")
        except Exception as e:
            print(f"Failed: {e}")
    else:
        print("No test video found.")

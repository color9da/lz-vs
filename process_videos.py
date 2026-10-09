"""
Video Processor - Quality Enhancement (Video + Audio)
1. Upscale video to 1080x1920 (Full HD 1080p) with crisp quality enhancement
2. Remove watermark (bottom-right corner)
3. ENHANCE AUDIO (normalize volume, improve clarity) or synthesize silent track for Meta compatibility
4. Bitrate & size optimization: High quality CRF 20 + 6.5 Mbps maxrate cap to keep file ~8-15 MB (strictly under 30MB)
"""
import os
import subprocess
import sys
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

input_dir = "Videos"
output_dir = "Processed_Videos"

if not os.path.exists(output_dir):
    os.makedirs(output_dir)


def process_single_video(video_path):
    if not os.path.exists(video_path):
        print(f"Error: Video not found: {video_path}")
        return None

    filename = os.path.basename(video_path)
    out_path = os.path.join(output_dir, filename)

    if os.path.exists(out_path):
        print(f"Skipping {filename} - already processed")
        return out_path

    # Probe resolution
    cmd_probe = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0",
        video_path
    ]
    try:
        res = subprocess.check_output(cmd_probe).decode("utf-8").strip()
        width, height = map(int, res.split("x"))
    except Exception as e:
        print(f"Failed to get resolution for {video_path}: {e}")
        return None

    # Probe audio
    cmd_audio = [
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0",
        video_path
    ]
    try:
        audio_check = subprocess.check_output(cmd_audio).decode("utf-8").strip()
        has_audio = bool(audio_check)
    except:
        has_audio = False

    print(f"Original size: {width}x{height}")
    print(f"Has audio: {'Yes' if has_audio else 'No'}")

    w_delogo = 180
    h_delogo = 80
    x_delogo = 1080 - w_delogo - 5
    y_delogo = 1920 - h_delogo - 5

    print(f"Processing {filename}...")
    print(f"  Target Resolution: 1080x1920 (Full HD 1080p)")
    print(f"  Removing watermark at: x={x_delogo}, y={y_delogo}, w={w_delogo}, h={h_delogo}")
    print(f"  Video: 1080p Quality Enhanced (crisp sharpening + CRF 20 + 6.5M cap)")

    vf_filter = f"[0:v]scale=1080:1920:flags=lanczos,unsharp=3:3:0.6:3:3:0.0,delogo=x={x_delogo}:y={y_delogo}:w={w_delogo}:h={h_delogo}[v]"

    if has_audio:
        print(f"  Audio: ENHANCED (normalize volume + improve clarity)")
        af_filter = f"[0:a]loudnorm=I=-16:TP=-1.5:LRA=11,dynaudnorm=50:3:0.5[a]"
        
        cmd_ffmpeg = [
            "ffmpeg", "-y", "-i", video_path,
            "-filter_complex", f"{vf_filter};{af_filter}",
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-maxrate", "6500k", "-bufsize", "13000k",
            "-profile:v", "high", "-level", "4.2", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            "-movflags", "+faststart",
            out_path
        ]
    else:
        print(f"  Audio: Synthesizing silent AAC stereo track for Meta Reels compatibility")
        cmd_ffmpeg = [
            "ffmpeg", "-y", "-i", video_path,
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-filter_complex", vf_filter,
            "-map", "[v]",
            "-map", "1:a",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-maxrate", "6500k", "-bufsize", "13000k",
            "-profile:v", "high", "-level", "4.2", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            "-shortest",
            "-movflags", "+faststart",
            out_path
        ]

    print("  Encoding 1080p video...")
    result = subprocess.run(cmd_ffmpeg, capture_output=True, text=True)

    if result.returncode == 0:
        first_size_mb = os.path.getsize(out_path) / (1024 * 1024)
        print(f"✅ Initial 1080p pass saved: {out_path} ({first_size_mb:.2f} MB)")
        
        # Step: Double video duration by concatenating with itself
        print(f"\n  Doubling video duration (concatenating video with itself)...")
        doubled_path = os.path.join(output_dir, "doubled_" + filename)
        
        cmd_concat = [
            "ffmpeg", "-y",
            "-i", out_path,
            "-i", out_path,
            "-filter_complex", "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]",
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-maxrate", "6500k", "-bufsize", "13000k",
            "-profile:v", "high", "-level", "4.2", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            "-movflags", "+faststart",
            doubled_path
        ]
        
        concat_result = subprocess.run(cmd_concat, capture_output=True, text=True)
        
        if concat_result.returncode == 0:
            os.remove(out_path)
            os.rename(doubled_path, out_path)
            final_size_mb = os.path.getsize(out_path) / (1024 * 1024)
            print(f"✅ Video doubled successfully (1080p Full HD, size: {final_size_mb:.2f} MB)")
            return out_path
        else:
            print(f"⚠️ Doubling failed, keeping initial 1080p file: {concat_result.stderr[:200]}")
            return out_path
    else:
        print(f"❌ Failed: {result.stderr[:400]}")
        return None


def main():
    specific_video = sys.argv[1] if len(sys.argv) > 1 else None

    if specific_video:
        result = process_single_video(specific_video)
        if result:
            print("\n" + "=" * 60)
            print(f"🎉 VIDEO PROCESSING COMPLETE: {result}")
            print("=" * 60)
        else:
            print("\n❌ Video processing failed")
            sys.exit(1)
    else:
        if not os.path.exists(input_dir):
            print(f"Input directory not found: {input_dir}")
            sys.exit(1)

        videos = [f for f in os.listdir(input_dir) if f.endswith(('.mp4', '.mov', '.avi'))]
        if not videos:
            print(f"No videos found in {input_dir}")
            return

        print(f"Found {len(videos)} video(s) to process\n")
        for i, video in enumerate(videos, 1):
            print(f"\n[{i}/{len(videos)}] Processing: {video}")
            video_path = os.path.join(input_dir, video)
            process_single_video(video_path)

        print("\n" + "=" * 60)
        print("🎉 ALL VIDEOS PROCESSED")
        print("=" * 60)


if __name__ == "__main__":
    main()

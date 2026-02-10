#!/usr/bin/env python3
"""
Stock Video Downloader - Multi-API Support
Searches and downloads stock videos from multiple APIs
"""

import os
import requests
import time
from typing import List, Dict, Optional
from datetime import datetime


class StockVideoDownloader:
    """
    Download stock videos from multiple APIs

    Supported APIs:
    - Pexels
    - Pixabay
    - (More can be added)
    """

    def __init__(self, apis: List[str] = None):
        """
        Initialize with list of APIs to use

        Args:
            apis: List of API names (e.g., ['pexels', 'pixabay'])
        """
        self.apis = apis or ['pexels']

        # API keys from environment
        self.pexels_api_key = os.getenv('PEXELS_API_KEY', '')
        self.pixabay_api_key = os.getenv('PIXABAY_API_KEY', '')

    def search_and_download(
        self,
        query: str,
        min_duration: float = 5.0,
        output_dir: str = 'media_library/stock_videos'
    ) -> str:
        """
        Search for and download a stock video

        Args:
            query: Search query
            min_duration: Minimum video duration in seconds
            output_dir: Output directory

        Returns:
            str: Path to downloaded video

        Raises:
            Exception: If no video found or download fails
        """
        os.makedirs(output_dir, exist_ok=True)

        # Try each API in order
        for api in self.apis:
            try:
                if api == 'pexels':
                    return self._search_pexels(query, min_duration, output_dir)
                elif api == 'pixabay':
                    return self._search_pixabay(query, min_duration, output_dir)
                else:
                    print(f"⚠️  Unknown API: {api}")
            except Exception as e:
                print(f"⚠️  {api.capitalize()} failed: {e}")
                continue

        raise Exception(f"No stock video found for query: {query}")

    def _search_pexels(
        self,
        query: str,
        min_duration: float,
        output_dir: str
    ) -> str:
        """
        Search and download from Pexels

        Args:
            query: Search query
            min_duration: Minimum duration
            output_dir: Output directory

        Returns:
            str: Path to downloaded video
        """
        if not self.pexels_api_key:
            raise Exception("PEXELS_API_KEY not set in environment")

        # Search for videos
        url = "https://api.pexels.com/videos/search"
        headers = {"Authorization": self.pexels_api_key}
        params = {
            "query": query,
            "per_page": 15,
            "orientation": "landscape"
        }

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()

        data = response.json()

        if not data.get('videos'):
            raise Exception(f"No videos found on Pexels for: {query}")

        # Find suitable video
        for video in data['videos']:
            duration = video.get('duration', 0)

            # Check if duration meets requirement
            if duration >= min_duration:
                # Get best quality video file
                video_files = video.get('video_files', [])

                # Prefer HD quality
                hd_files = [f for f in video_files if f.get('quality') in ['hd', 'sd']]
                if hd_files:
                    video_file = hd_files[0]
                elif video_files:
                    video_file = video_files[0]
                else:
                    continue

                # Download video
                video_url = video_file['link']
                return self._download_video(video_url, output_dir, f"pexels_{video['id']}")

        raise Exception(f"No suitable video found on Pexels (min duration: {min_duration}s)")

    def _search_pixabay(
        self,
        query: str,
        min_duration: float,
        output_dir: str
    ) -> str:
        """
        Search and download from Pixabay

        Args:
            query: Search query
            min_duration: Minimum duration
            output_dir: Output directory

        Returns:
            str: Path to downloaded video
        """
        if not self.pixabay_api_key:
            raise Exception("PIXABAY_API_KEY not set in environment")

        # Search for videos
        url = "https://pixabay.com/api/videos/"
        params = {
            "key": self.pixabay_api_key,
            "q": query,
            "per_page": 15,
            "video_type": "all"
        }

        response = requests.get(url, params=params)
        response.raise_for_status()

        data = response.json()

        if not data.get('hits'):
            raise Exception(f"No videos found on Pixabay for: {query}")

        # Find suitable video
        for video in data['hits']:
            duration = video.get('duration', 0)

            # Check if duration meets requirement
            if duration >= min_duration:
                # Get video files
                videos_data = video.get('videos', {})

                # Try to get medium or large quality
                video_url = None
                for quality in ['medium', 'large', 'small']:
                    if quality in videos_data:
                        video_url = videos_data[quality]['url']
                        break

                if video_url:
                    return self._download_video(video_url, output_dir, f"pixabay_{video['id']}")

        raise Exception(f"No suitable video found on Pixabay (min duration: {min_duration}s)")

    def _download_video(
        self,
        url: str,
        output_dir: str,
        filename_prefix: str
    ) -> str:
        """
        Download video from URL

        Args:
            url: Video URL
            output_dir: Output directory
            filename_prefix: Filename prefix

        Returns:
            str: Path to downloaded video
        """
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename_prefix}_{timestamp}.mp4"
        output_path = os.path.join(output_dir, filename)

        # Download
        print(f"   📥 Downloading: {url}")
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()

        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"   ✅ Downloaded: {output_path}")
        return output_path

    def trim_video_if_needed(
        self,
        video_path: str,
        target_duration: float,
        output_path: str = None
    ) -> str:
        """
        Trim video to target duration if longer than 10 seconds

        Args:
            video_path: Input video path
            target_duration: Target duration (5 or 10 seconds)
            output_path: Output path (optional)

        Returns:
            str: Path to trimmed video
        """
        import subprocess

        if not output_path:
            base, ext = os.path.splitext(video_path)
            output_path = f"{base}_trimmed{ext}"

        # Get video duration
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        duration = float(result.stdout.strip())

        # If video is longer than target, trim it
        if duration > target_duration:
            print(f"   ✂️  Trimming video from {duration:.1f}s to {target_duration:.1f}s")

            cmd = [
                'ffmpeg',
                '-y',
                '-i', video_path,
                '-t', str(target_duration),
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-crf', '28',
                '-c:a', 'aac',
                '-b:a', '192k',
                output_path
            ]

            subprocess.run(cmd, check=True, capture_output=True)
            return output_path
        else:
            # Video is already short enough
            return video_path


if __name__ == "__main__":
    # Test
    downloader = StockVideoDownloader(apis=['pexels'])

    try:
        video_path = downloader.search_and_download(
            query="business meeting",
            min_duration=5.0,
            output_dir="test_output"
        )
        print(f"\n✅ Test successful! Downloaded: {video_path}")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")

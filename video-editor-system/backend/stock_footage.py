#!/usr/bin/env python3
"""
Stock Footage Fetcher for Pexels API
Fetch and download stock videos and photos from Pexels
"""

import requests
import os
import re
from pathlib import Path


PEXELS_API_URL = "https://api.pexels.com/v1"
PEXELS_VIDEO_URL = "https://api.pexels.com/videos"


def extract_keywords_from_script(script_text, max_keywords=5):
    """
    Extract relevant keywords from script for stock search
    Uses simple frequency analysis

    Args:
        script_text: Full script content
        max_keywords: Maximum number of keywords to extract

    Returns:
        List of keywords
    """

    # Common words to ignore
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                  'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
                  'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
                  'should', 'could', 'may', 'might', 'must', 'can', 'this', 'that',
                  'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'what',
                  'which', 'who', 'when', 'where', 'why', 'how'}

    # Tokenize and count
    words = re.findall(r'\b[a-z]{4,}\b', script_text.lower())
    word_freq = {}

    for word in words:
        if word not in stop_words:
            word_freq[word] = word_freq.get(word, 0) + 1

    # Get top N keywords
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    keywords = [word for word, freq in sorted_words[:max_keywords]]

    return keywords


def fetch_stock_videos(api_key, query, count=5, orientation='landscape'):
    """
    Fetch stock videos from Pexels

    Args:
        api_key: Pexels API key
        query: Search query
        count: Number of videos
        orientation: 'landscape', 'portrait', or 'square'

    Returns:
        List of video info dicts
    """

    headers = {'Authorization': api_key}

    params = {
        'query': query,
        'per_page': count,
        'orientation': orientation,
        'size': 'large'  # Get HD videos
    }

    response = requests.get(
        f"{PEXELS_VIDEO_URL}/search",
        headers=headers,
        params=params
    )

    response.raise_for_status()
    data = response.json()

    videos = []

    for video in data.get('videos', []):
        # Find HD file (1920x1080)
        hd_file = None
        for file in video.get('video_files', []):
            if file.get('width') == 1920 and file.get('height') == 1080:
                hd_file = file
                break

        # Fallback to largest available
        if not hd_file and video.get('video_files'):
            hd_file = max(video['video_files'], key=lambda x: x.get('width', 0))

        if hd_file:
            videos.append({
                'id': video['id'],
                'url': hd_file['link'],
                'duration': video.get('duration', 0),
                'width': hd_file.get('width'),
                'height': hd_file.get('height'),
                'thumbnail': video.get('image'),
                'type': 'video'
            })

    return videos


def fetch_stock_photos(api_key, query, count=5, orientation='landscape'):
    """
    Fetch stock photos from Pexels

    Args:
        api_key: Pexels API key
        query: Search query
        count: Number of photos
        orientation: 'landscape', 'portrait', or 'square'

    Returns:
        List of photo info dicts
    """

    headers = {'Authorization': api_key}

    params = {
        'query': query,
        'per_page': count,
        'orientation': orientation
    }

    response = requests.get(
        f"{PEXELS_API_URL}/search",
        headers=headers,
        params=params
    )

    response.raise_for_status()
    data = response.json()

    photos = []

    for photo in data.get('photos', []):
        # Get large size (1920x1080 or similar)
        large_url = photo['src'].get('large2x') or photo['src'].get('large')

        photos.append({
            'id': photo['id'],
            'url': large_url,
            'width': photo.get('width'),
            'height': photo.get('height'),
            'thumbnail': photo['src'].get('medium'),
            'photographer': photo.get('photographer'),
            'type': 'image'
        })

    return photos


def download_stock_media(media_list, output_dir):
    """
    Download stock media files

    Args:
        media_list: List of media dicts from fetch functions
        output_dir: Where to save files

    Returns:
        List of local file paths
    """

    os.makedirs(output_dir, exist_ok=True)

    downloaded = []

    for i, media in enumerate(media_list):
        ext = 'mp4' if media['type'] == 'video' else 'jpg'
        filename = f"stock_{i+1:03d}.{ext}"
        filepath = os.path.join(output_dir, filename)

        # Download
        response = requests.get(media['url'], stream=True)
        response.raise_for_status()

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        downloaded.append(filepath)

    return downloaded


def fetch_and_download_stock(api_key, query_or_script, count, media_type='both',
                             auto_extract=True, output_dir='output/stock'):
    """
    Complete workflow: extract keywords (if auto), fetch, and download

    Args:
        api_key: Pexels API key
        query_or_script: Search query OR full script text
        count: Number of items to fetch
        media_type: 'videos', 'photos', or 'both'
        auto_extract: If True, extract keywords from query_or_script
        output_dir: Where to save

    Returns:
        Dict with media info and downloaded paths
    """

    # Extract keywords if auto mode
    if auto_extract:
        keywords = extract_keywords_from_script(query_or_script, max_keywords=3)
        query = ' '.join(keywords)
        print(f"📝 Extracted keywords: {query}")
    else:
        query = query_or_script

    all_media = []

    # Fetch based on type
    if media_type in ['videos', 'both']:
        videos = fetch_stock_videos(
            api_key,
            query,
            count=count if media_type == 'videos' else count//2
        )
        all_media.extend(videos)

    if media_type in ['photos', 'both']:
        photos = fetch_stock_photos(
            api_key,
            query,
            count=count if media_type == 'photos' else count//2
        )
        all_media.extend(photos)

    # Download all
    print(f"⬇️ Downloading {len(all_media)} items...")
    downloaded = download_stock_media(all_media, output_dir)

    print(f"✅ Downloaded {len(downloaded)} files")

    return {
        'media_info': all_media,
        'downloaded_paths': downloaded,
        'query': query,
        'count': len(downloaded)
    }

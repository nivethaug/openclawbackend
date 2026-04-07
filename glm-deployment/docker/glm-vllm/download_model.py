from huggingface_hub import snapshot_download
import shutil
import os
import sys
import time

def download_with_retries(repo_id, cache_dir, max_retries=3):
    """Download model with retry logic."""
    for attempt in range(max_retries):
        try:
            print(f'Download attempt {attempt + 1}/{max_retries}...')
            cache_path = snapshot_download(
                repo_id,
                cache_dir=cache_dir,
                resume_download=True
            )
            print(f'Downloaded to cache: {cache_path}')
            return cache_path
        except Exception as e:
            print(f'Attempt {attempt + 1} failed: {str(e)}', file=sys.stderr)
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 10
                print(f'Retrying in {wait_time} seconds...')
                time.sleep(wait_time)
            else:
                raise

try:
    cache_path = download_with_retries(
        'FayeQuant/GLM-4.7-Flash-GPTQ-4bit',
        '/tmp/hf_cache'
    )
    
    # Copy files to destination
    for f in os.listdir(cache_path):
        src = os.path.join(cache_path, f)
        dst = os.path.join('/opt/glm-model', f)
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    
    # Verify files copied
    files = os.listdir('/opt/glm-model')
    print(f'Copied {len(files)} files to /opt/glm-model')
    
    # Verify config.json exists
    if 'config.json' not in files:
        raise Exception('config.json not found in model files')
        
except Exception as e:
    print(f'Error: {str(e)}', file=sys.stderr)
    sys.exit(1)

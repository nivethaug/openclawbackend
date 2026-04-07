from huggingface_hub import snapshot_download
import shutil
import os
import sys

try:
    cache_path = snapshot_download(
        'FayeQuant/GLM-4.7-Flash-GPTQ-4bit',
        cache_dir='/tmp/hf_cache',
        resume_download=True
    )
    print(f'Downloaded to cache: {cache_path}')

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
except Exception as e:
    print(f'Error: {str(e)}', file=sys.stderr)
    sys.exit(1)

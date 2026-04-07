from huggingface_hub import snapshot_download
import shutil
import os

cache_path = snapshot_download(
    'FayeQuant/GLM-4.7-Flash-GPTQ-4bit',
    cache_dir='/tmp/hf_cache'
)
print(f'Downloaded to cache: {cache_path}')

for f in os.listdir(cache_path):
    src = os.path.join(cache_path, f)
    dst = os.path.join('/opt/glm-model', f)
    if os.path.isdir(src):
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)

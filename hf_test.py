from huggingface_hub import HfApi
from huggingface_hub import ModelCard
from tqdm import tqdm

api = HfApi()
models = api.list_models()
card = ModelCard.load("gumbojustice/efficientnet_test")
card2 = ModelCard.load("litert-community/DeepSeek-R1-Distill-Qwen-1.5B")

libraries = {}
tags = {}

count = 0

for m in tqdm(models):
    libraries[m.library_name] = libraries.get(m.library_name, 0) + 1
    for t in m.tags:
        tags[t] = tags.get(t, 0) + 1
    count += 1

print(f"Total models on Hugging Face Hub: {count}")




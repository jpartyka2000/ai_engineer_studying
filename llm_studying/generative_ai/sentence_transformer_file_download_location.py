When the `SentenceTransformers` library downloads initialization files (such as model configuration `.json` files or weights `.bin` files), they are typically stored in a local cache directory managed by the `transformers` library, which is used internally.

By default, the files are stored in the following locations depending on your operating system:

### Default Cache Location:
- **Linux and macOS:**  
  `~/.cache/huggingface/transformers/`
  
- **Windows:**  
  `C:\\Users\\<YourUsername>\\.cache\\huggingface\\transformers\\`

Within this directory, the files are organized by the model name or identifier. For example, if you load `all-MiniLM-L6-v2`, the files for that model will be stored in a subdirectory under `~/.cache/huggingface/transformers/`.

### Customizing the Cache Location:
You can change the default cache directory by setting the `TRANSFORMERS_CACHE` environment variable to a custom path:

```bash
export TRANSFORMERS_CACHE=/path/to/custom/cache
```

In Python, you can set this dynamically before initializing the model:

```python
import os
os.environ["TRANSFORMERS_CACHE"] = "/path/to/custom/cache"
```

This ensures the files are stored in a directory of your choice.

### Identifying Downloaded Files:
The downloaded files typically include:
- **Model Weights:** A `.bin` file with the pre-trained weights.
- **Config Files:** A `.json` file describing the model architecture.
- **Tokenizer Files:** Files such as `vocab.txt`, `tokenizer_config.json`, or merges for tokenization.

You can inspect the directory to see all cached files for your model.

### Verifying Cache Location in Code:
You can use the `transformers` library to verify the cache location programmatically:

```python
from transformers.file_utils import default_cache_path

print(default_cache_path)  # Prints the default cache directory
``` 

This setup ensures that once the files are downloaded, they are reused without needing to re-download them.
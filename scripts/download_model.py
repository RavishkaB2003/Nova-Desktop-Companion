"""
Project NOVA - Offline Acoustic Model Setup Helper
Downloads the default Vosk offline model (vosk-model-small-en-us-0.15) into models/
"""

import os
import sys
import urllib.request
import zipfile

MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
MODEL_NAME = "vosk-model-small-en-us-0.15"

def setup_model():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    models_dir = os.path.join(repo_root, "models")
    target_dir = os.path.join(models_dir, MODEL_NAME)
    archive_path = os.path.join(models_dir, f"{MODEL_NAME}.zip")

    if os.path.exists(target_dir):
        print(f"Model already present at: {target_dir}")
        return

    os.makedirs(models_dir, exist_ok=True)
    print(f"Downloading {MODEL_NAME} from {MODEL_URL}...")
    try:
        urllib.request.urlretrieve(MODEL_URL, archive_path)
        print("Extracting acoustic model archive...")
        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            zip_ref.extractall(models_dir)
        if os.path.exists(archive_path):
            os.remove(archive_path)
        print(f"Successfully installed offline acoustic model: {target_dir}")
    except Exception as exc:
        print(f"Failed to download model automatically: {exc}", file=sys.stderr)
        print("You can manually download the model from https://alphacephei.com/vosk/models and extract it to models/", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    setup_model()
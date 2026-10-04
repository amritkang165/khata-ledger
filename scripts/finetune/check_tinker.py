from __future__ import annotations

import os

from dotenv import load_dotenv


load_dotenv()
if not os.getenv("TINKER_PROJECT_ID"):
    os.environ.pop("TINKER_PROJECT_ID", None)


def main() -> None:
    import tinker

    client = tinker.ServiceClient()
    try:
        capabilities = client.get_server_capabilities()
        models = sorted(
            (model.model_name, model.trainable, model.sampleable)
            for model in capabilities.supported_models
            if model.model_name
        )
        audio_or_whisper = [model for model in models if "whisper" in model[0].lower() or "audio" in model[0].lower()]
        print(f"Tinker reports {len(models)} supported models")
        if audio_or_whisper:
            print("Audio/Whisper candidates:")
            for name, trainable, sampleable in audio_or_whisper:
                print(f"- {name} trainable={trainable} sampleable={sampleable}")
        else:
            print("No Whisper or audio model appears in the live supported-model list")
            print("Do not claim a Tinker Whisper fine-tune without provider confirmation")
    finally:
        client.close("success", detail="capability check complete").result()


if __name__ == "__main__":
    main()

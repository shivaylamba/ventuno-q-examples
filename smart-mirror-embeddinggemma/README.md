# Smart Mirror · EmbeddingGemma 2

A separate App Lab project based on **Smart Mirror · Laptop**. It keeps the Arduino-inspired welcome screen, live board-camera preview, automatic presence scan, spoken Qwen style tip, and 20-second reset. After Qwen describes the outfit, EmbeddingGemma runs alongside speech synthesis and ranks similar dresses from a local catalog.

## What runs where

- **Qwen 2.5-VL 7B** still sees the outfit and writes the style tip. EmbeddingGemma does not replace Qwen or generate advice.
- **EmbeddingGemma 2 740M** embeds the outfit image and Qwen's style intent, then compares that query with on-device text embeddings for dresses. The model and similarity ranking run on VENTUNO Q. The browser only displays the cards.
- **YOLOX-Nano QNN** detects presence. Piper creates speech, which the browser plays on the laptop.
- The captured frame stays in memory except for a temporary image file used by LiteRT-LM; that file is removed after embedding. No outfit photo or identity is retained.

The initial Qwen scan remains the main wait. EmbeddingGemma does not speed up Qwen. It is run concurrently with speech synthesis. The app builds the dress index in the background after startup, then caches it; the cache is invalidated when the catalog or model changes. The first idle period after starting a 100-item catalog may use noticeable CPU while that index is prepared.

## Model setup on VENTUNO Q

Model weights are excluded from the repository. This project uses the generic 485 MB `.litertlm` model from the [EmbeddingGemma 2 LiteRT-LM repository](https://huggingface.co/litert-community/embeddinggemma-2-740m-litert-lm):

```text
data/models/embeddinggemma-2-740m.litertlm
```

Download that exact generic file from Hugging Face and place it at the path above in this app's directory on VENTUNO Q. App Lab installs `litert-lm-api` from `python/requirements.txt`. On the Linux runtime currently exercised with App Lab, the generic artifact initializes on the **CPU/XNNPACK** backend. A text embedding and a synthetic-image embedding both returned 768-dimensional vectors in about four seconds including model initialization.

The QCS8275-specific artifact is not the configured model. The current `litert-lm-api` `Backend.NPU()` path reported that NPU support is only available for Intel OpenVINO on Windows; the QCS8275 model also needs a Qualcomm LiteRT dispatch library that is not present in the base App Lab container. Therefore this project makes no claim that EmbeddingGemma runs on the VENTUNO Q NPU. The separate YOLOX and Qwen runners continue to use the board's Qualcomm-accelerated runtimes.

## Amazon dress catalog

`python/catalog.json` is a 13-style illustrative fallback, not Amazon inventory. It contains no retailer images, verified product listings, or prices; fallback cards use local artwork and search links.

The included `tools/import_amazon_catalog.py` uses Amazon's official Creators API to collect 100 real dress listings with their primary image URLs and detail-page links. It writes `smart-mirror-embeddinggemma/data/amazon-catalog.json`, which the app reads instead of the fallback when it is valid and contains at least 100 items. Amazon data is treated as temporary and the app falls back after 23 hours. Do not scrape Amazon product pages or commit the generated catalog.

Amazon Creators API access requires an accepted Associates account and qualified sales. If you have access, set these variables in a PowerShell session and run the importer from the repository root. Credentials are read from the environment and are never written into the catalog:

```powershell
$env:AMAZON_CREATORS_CLIENT_ID = "..."
$env:AMAZON_CREATORS_CLIENT_SECRET = "..."
$env:AMAZON_PARTNER_TAG = "..."
$env:AMAZON_MARKETPLACE = "www.amazon.in"
python tools/import_amazon_catalog.py
```

Choose the marketplace where your Associates account is registered; replace `www.amazon.in` if yours is elsewhere. The catalog must be copied to this app's `data/amazon-catalog.json` on the board and the app restarted. Refer to [Amazon's Creators API onboarding](https://affiliate-program.amazon.com/creatorsapi/docs/en-us/onboarding/register-for-creators-api), [SearchItems API](https://affiliate-program.amazon.com/creatorsapi/docs/en-us/api-reference/operations/search-items), and [image resource rules](https://affiliate-program.amazon.com/creatorsapi/docs/en-us/api-reference/resources/images).

## App Lab

The project folder is `smart-mirror-embeddinggemma`, with an app ID separate from `smart-mirror-laptop`. The original Smart Mirror project remains unchanged. Import this project's ZIP from `dist/` or run it directly from its App Lab entry. Only one mirror app can run at a time because both use the same camera and web port.

The browser UI is available at `http://localhost:7000` when the board is connected over USB and the app is running. Model weights and the temporary Amazon catalog are not included in this repository or in the source ZIP.

## License

The original Smart Mirror assets and adapted files retain the Arduino MPL-2.0 notices. LiteRT-LM and EmbeddingGemma 2 have separate upstream licenses; check the [model repository](https://huggingface.co/litert-community/embeddinggemma-2-740m-litert-lm) before redistributing model files.

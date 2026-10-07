# Smart Mirror · EmbeddingGemma 2

A separate App Lab project based on **Smart Mirror · Laptop**. It keeps the Arduino-inspired welcome screen, live board-camera preview, automatic presence scan, spoken Qwen style tip, and 20-second reset. After Qwen describes the outfit, EmbeddingGemma runs alongside speech synthesis and ranks similar dresses from a catalog with real product photos and product pages.

## What runs where

- **Qwen 2.5-VL 7B** still sees the outfit and writes the style tip. EmbeddingGemma does not replace Qwen or generate advice.
- **EmbeddingGemma 2 740M** embeds the outfit image and Qwen's style intent, then compares that query with on-device text embeddings for dresses. The model and similarity ranking run on VENTUNO Q. The browser only displays the cards.
- **YOLOX-Nano QNN** detects presence. Piper creates speech, which the browser plays on the laptop.
- The captured frame stays in memory except for a temporary image file used by LiteRT-LM; that file is removed after embedding. No outfit photo or identity is retained.

The initial Qwen scan remains the main wait. EmbeddingGemma does not speed up Qwen. It is run concurrently with speech synthesis. The app builds the dress index in the background after startup, then caches it; the cache is invalidated when the catalog or model changes. The first idle period after starting a 100-item catalog may use noticeable CPU while that index is prepared.

## Model setup on VENTUNO Q

Model weights are excluded from the repository. CPU mode uses the generic 485 MB `.litertlm` model from the [EmbeddingGemma 2 LiteRT-LM repository](https://huggingface.co/litert-community/embeddinggemma-2-740m-litert-lm):

```text
data/models/embeddinggemma-2-740m.litertlm
```

Download that exact generic file from Hugging Face and place it at the path above in this app's directory on VENTUNO Q. App Lab installs `litert-lm-api` from `python/requirements.txt`. On the Linux runtime currently exercised with App Lab, the generic artifact initializes on the **CPU/XNNPACK** backend. A text embedding and a synthetic-image embedding both returned 768-dimensional vectors in about four seconds including model initialization.

The model card separately reports the 740M model running on the VENTUNO Q NPU (13.6 ms text and 135 ms text-plus-vision, averaged over five iterations). This confirms the hardware/model combination is supported; it does not mean this App Lab project is currently using the NPU.

For an NPU attempt, put the QCS8275-specific artifact at:

```text
data/models/embeddinggemma-2-740m_Qualcomm_QCS8275.litertlm
```

and set `EMBEDDING_BACKEND=NPU`. The app then selects this board-specific artifact automatically. `EMBEDDINGGEMMA_MODEL_PATH` can override the selected path. The backend is reported as NPU only after LiteRT-LM initializes it successfully; a requested-but-uninitialized backend is reported as such and does not silently fall back to CPU.

**The current App Lab Python runtime is CPU-only for this embedding path.** Its `litert-lm-api==0.18.0` wheel does not provide a usable Qualcomm NPU backend in this Linux container, and the main app container lacks LiteRT's Qualcomm dispatch library and the QAIRT runtime files. Setting `EMBEDDING_BACKEND=NPU` by itself will therefore fail initialization. Google's documented Qualcomm NPU deployment requires a built LiteRT-LM runtime/dispatch library plus the matching QAIRT libraries, model, and `LD_LIBRARY_PATH`/`ADSP_LIBRARY_PATH` configuration; these components have not been integrated into the App Lab app image yet. YOLOX presence detection and Qwen continue to use their separate board-accelerated runners.

Consequently, the running demo still performs these dress embeddings on CPU. The model-card NPU latency is a benchmark reference, not a measurement of this app. The generic CPU model and working app remain available while the native Qualcomm runtime is prepared.

## Dress catalog and real product photos

The current catalog contains **151 real dress products** from the [Livostyle Women's Fashion Catalog open dataset](https://github.com/arturayupov/womens-fashion-catalog-open-data), snapshot `2026-09-27`. Each recommendation is matched from its product description and displays the catalog photo, product type, snapshot price, and product page link. Photos load from Livostyle's Shopify CDN at 480-pixel width; the repository contains catalog metadata and image links, not image files. The laptop browser needs internet access to show photos.

We checked Amazon Berkeley Objects before choosing this source; its current snapshot had only four records classified under dress categories, too few for useful recommendations. The Livostyle snapshot had 151 records in its exact Dresses category. This provides enough real products for the demo, but they are from Livostyle, not Amazon.

The dataset repository declares MIT licensing. Product pages show current availability; snapshot prices can change. The catalog retains the source attribution and license link. To refresh it from the dataset's latest weekly snapshot, run from the repository root:

```powershell
python tools/import_livostyle_dresses.py
python tools/package_apps.py
```

Then update/reimport `dist/smart-mirror-embeddinggemma.zip` in App Lab and restart the app. The first run after a catalog refresh rebuilds the local EmbeddingGemma text index; later runs reuse its cache.

## App Lab

The project folder is `smart-mirror-embeddinggemma`, with an app ID separate from `smart-mirror-laptop`. The original Smart Mirror project remains unchanged. Import this project's ZIP from `dist/` or run it directly from its App Lab entry. Only one mirror app can run at a time because both use the same camera and web port.

The browser UI is available at `http://localhost:7000` when the board is connected over USB and the app is running. Model weights and generated embedding indexes are not included in this repository or in the source ZIP.

## License

The original Smart Mirror assets and adapted files retain the Arduino MPL-2.0 notices. LiteRT-LM and EmbeddingGemma 2 have separate upstream licenses; check the [model repository](https://huggingface.co/litert-community/embeddinggemma-2-740m-litert-lm) before redistributing model files.

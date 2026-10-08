# Smart Mirror · EmbeddingGemma 2

A separate App Lab project based on **Smart Mirror · Laptop**. It keeps the Arduino-inspired welcome screen, live board-camera preview, automatic presence scan, spoken Qwen style tip, and 20-second reset. After Qwen describes the outfit, EmbeddingGemma runs alongside speech synthesis and ranks similar apparel and footwear from a balanced catalog of 400 product images.

## What runs where

- **Qwen 2.5-VL 7B** still sees the outfit and writes the style tip. EmbeddingGemma does not replace Qwen or generate advice.
- **EmbeddingGemma 2 740M** compares the camera image directly against an image embedding for every catalog product. It also compares Qwen's outfit description with catalog text embeddings; visual image similarity has the larger weight, while text and a private garment-audience estimate refine ranking. Qwen's audience estimate (men, women, unisex, or unknown) describes the clothes, not the wearer's gender, and is never shown in the UI. The dedicated worker runs image and text embedding on VENTUNO Q's Qualcomm NPU; the main App Lab container sends requests over the private Docker network. The browser only displays the cards.
- LiteRT-LM's image and text embedding backends use the Qualcomm NPU. Its bundled audio branch is assigned to CPU because the app does not use audio embeddings and the model's audio operations are not all supported by the NPU delegate.
- **YOLOX-Nano QNN** detects presence. Piper creates speech, which the browser plays on the laptop.
- The captured frame is sent only to the local worker and briefly written to a temporary image file for LiteRT-LM; the file is automatically removed. No outfit photo or identity is retained.

The initial Qwen scan remains the main wait. EmbeddingGemma does not speed up Qwen. Retrieval runs concurrently with speech synthesis. After startup, the app builds image and text vectors for the catalog in the background and saves them on the board; interrupted image indexing resumes from its checkpoint. The initial image-index build can take time because it embeds all 400 product photos. Later starts reuse the cached vectors unless the catalog changes.

## NPU setup on VENTUNO Q

This separate project uses the board-specific QCS8275 model through a dedicated NPU worker container. Keep the model weights and Qualcomm SDK libraries out of Git; App Lab installs `litert-lm-api==0.18.0` from `python/requirements.txt`.

Place the model from the [EmbeddingGemma 2 LiteRT-LM repository](https://huggingface.co/litert-community/embeddinggemma-2-740m-litert-lm) here:

```text
data/models/embeddinggemma-2-740m_Qualcomm_QCS8275.litertlm
```

The worker needs the following local runtime files. It exports `LD_LIBRARY_PATH`, `ADSP_LIBRARY_PATH`, and `LITERT_DISPATCH_LIB_DIR` before loading LiteRT:

```text
runtime/npu/lib/libLiteRtDispatch_Qualcomm.so
runtime/npu/lib/libQnnSystem.so
runtime/npu/lib/libQnnHtp.so
runtime/npu/lib/libQnnHtpPrepare.so
runtime/npu/lib/libQnnHtpV75Stub.so
runtime/npu/lib/libQnnHtpV75Skel.so
runtime/npu/lib/libQnnIr.so
runtime/npu/lib/libQnnSaver.so
runtime/npu/lib/libcdsprpc.so
runtime/npu/lib/libadsprpc.so
runtime/npu/lib/libdmabufheap.so.0
runtime/npu/dsp/fastrpc_shell_unsigned_3
runtime/npu/dsp/fastrpc_shell_3
```

Use the matching **QAIRT 2.50.0.260828** AArch64 Linux files from Qualcomm’s SDK. Build `libLiteRtDispatch_Qualcomm.so` from LiteRT commit `26895c9fbcc25c43faa8c1a98cd1fd28951602c3`, the revision pinned by LiteRT-LM 0.18.0. Keep the QNN libraries, DSP skeleton, and dispatch library in `runtime/npu/lib`. The App Lab container also needs the board’s FastRPC host libraries in that directory and the CDSP firmware files in `runtime/npu/dsp`; the worker exports both directories. Do not substitute the board’s older 2.46 QAIRT package for this runtime.

The worker receives only FastRPC and DMA heap device nodes; it does not bind the host's full `/dev`, which blocked QNN session creation in the main camera container. It also mounts `/usr/share/qcom` and the board device-tree model file and sets unlimited memlock. YOLOX presence detection and Qwen continue to use their separate board-accelerated runners.

The worker is packaged as the app-local custom Brick `embeddinggemma_npu`. Its `brick_compose.yaml` defines the worker container, and its Python module sends embedding requests to `embedding-npu-worker:7010`. Because the Brick is listed in `app.yaml`, App Lab starts the worker as part of the app; no separate Compose command is needed. Custom Bricks are local to this app and are included in its export ZIP.
## Apparel catalog

The starter catalog contains **200 men-targeted and 200 women-targeted product images**, selected from the [Fashion Product Images Small dataset on Kaggle](https://www.kaggle.com/datasets/paramaggarwal/fashion-product-images-small). Its styles.csv metadata labels the product's target gender and garment type; the selection excludes beauty/personal-care items and spans apparel and footwear categories. Images are included locally under assets/fashion-catalog/, so showing recommendation cards does not depend on a third-party image CDN. The Kaggle dataset page declares an MIT license. The dataset is Myntra-sourced; the links in the cards open Myntra search results rather than a guaranteed live product listing.

The original women-only Livostyle catalog remains available as python/catalog.json for reference. The active catalog is python/fashion-catalog.json. After changing it, reimport the updated ZIP in App Lab and restart the app. The first run rebuilds the local EmbeddingGemma text index; later runs reuse its cache.

## App Lab

The project folder is `smart-mirror-embeddinggemma`, with an app ID separate from `smart-mirror-laptop`. The original Smart Mirror project remains unchanged. Import this project's ZIP from `dist/` or run it directly from its App Lab entry. Only one mirror app can run at a time because both use the same camera and web port.

The browser UI is available at `http://localhost:7000` when the board is connected over USB and the app is running. Model weights and generated embedding indexes are not included in this repository or in the source ZIP.

## License

The original Smart Mirror assets and adapted files retain the Arduino MPL-2.0 notices. LiteRT-LM and EmbeddingGemma 2 have separate upstream licenses; check the [model repository](https://huggingface.co/litert-community/embeddinggemma-2-740m-litert-lm) before redistributing model files.

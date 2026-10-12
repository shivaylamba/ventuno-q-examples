"""QNN is accepted only after strict sessions and per-kernel profiling pass."""
import json
from pathlib import Path
import numpy as np


class OrtNet:
    def __init__(self, model, library, profile_path):
        import onnxruntime as ort
        if "QNNExecutionProvider" not in ort.get_available_providers():
            raise RuntimeError("Installed ONNX Runtime has no QNNExecutionProvider")
        options = ort.SessionOptions()
        options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
        options.enable_profiling = True
        options.profile_file_prefix = str(profile_path)
        options.log_severity_level = 3
        options.intra_op_num_threads = 2
        self.session = ort.InferenceSession(str(model), options, providers=[("QNNExecutionProvider", {
            "backend_path": str(library), "htp_performance_mode": "burst",
            "enable_htp_fp16_precision": "1", "htp_graph_finalization_optimization_mode": "3",
        })])
        self.session.disable_fallback()
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = tuple(sorted(out.name for out in self.session.get_outputs()))
        shape = self.session.get_inputs()[0].shape
        if any(not isinstance(dim, int) for dim in shape):
            raise RuntimeError(f"QNN model requires fixed input dimensions: {shape}")
        self.session.run(list(self.output_names), {self.input_name: np.zeros(shape, dtype=np.float32)})
        self.session.run(list(self.output_names), {self.input_name: np.zeros(shape, dtype=np.float32)})
        profile = Path(self.session.end_profiling())
        nodes = [e for e in json.loads(profile.read_text()) if e.get("cat") == "Node" and e.get("args", {}).get("provider")]
        providers = {e["args"]["provider"] for e in nodes}
        if providers != {"QNNExecutionProvider"}:
            raise RuntimeError(f"NPU assignment not proven by ORT kernel profile: {sorted(providers)}")
        self.proof = {"profile": str(profile), "providers": sorted(providers), "profiled_kernel_events": len(nodes), "cpu_fallback_disabled": True}

    def setPreferableBackend(self, _):
        pass

    def setPreferableTarget(self, _):
        pass

    def setInput(self, value):
        self.input = np.ascontiguousarray(value, dtype=np.float32)

    def getUnconnectedOutLayersNames(self):
        return self.output_names

    def forward(self, names):
        return self.session.run(list(names), {self.input_name: self.input})


def install_qnn(tracker, root, config, metrics):
    library = Path(config["qnn_library"])
    if not library.is_absolute():
        library = root / library
    if not library.is_file():
        raise RuntimeError("QNN backend not installed. CPU fallback active; see scripts/setup-npu.sh")
    proofs, nets = {}, {}
    (root / "runs").mkdir(exist_ok=True)
    for name in ("palm", "hand"):
        net = OrtNet(root / "models" / (name + ".onnx"), library, root / "runs" / ("qnn_" + name))
        nets[name], proofs[name] = net, net.proof
    tracker.palm.model, tracker.hand.model = nets["palm"], nets["hand"]
    tracker.provider = "QNN HTP / NPU (FP16, strict)"
    metrics.metadata["qnn_proof"] = proofs

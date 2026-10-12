"""Use Arduino's quantized MediaPipe models and matching QNN runtime image."""
import importlib
import sys
import time
import cv2
import numpy as np
from gestures.state import Packet
from perception.pipeline import decode_hand


class ArduinoTracker:
    def __init__(self, config, metrics):
        self.config, self.metrics = config, metrics
        cv2.setNumThreads(config["cpu_threads"])
        self.provider = "TFLite / CPU"
        self.fallback_reason = ""
        requested = config.get("provider", "auto")
        # These models and their preprocessing ship in the pinned Arduino image.
        import utils.tf as tf
        original = tf.load_qnn_delegate
        strict_delegates = []
        def strict_load(*args, **kwargs):
            delegates = original(*args, **kwargs)
            if not delegates:
                raise RuntimeError("QNN TFLite delegate unavailable")
            strict_delegates.extend(delegates)
            return delegates
        tf.load_qnn_delegate = (lambda *a,**kw: []) if requested=="cpu" else strict_load
        try:
            self.module = importlib.import_module("perception.arduino_inference")
        except Exception as exc:
            if requested=="qnn": raise
            self.fallback_reason=str(exc)
            sys.modules.pop("perception.arduino_inference",None)
            tf.load_qnn_delegate=lambda *a,**kw: []
            self.module=importlib.import_module("perception.arduino_inference")
        m=self.module
        m.MIN_DETECTOR_BOX_SCORE=config["palm_confidence"]
        m.MIN_LANDMARK_SCORE=config["hand_confidence"]
        proof={}
        for name, model in [("palm",m.hand_detector),("landmarks",m.landmark_detector)]:
            detail=model.get_input_details()[0]
            model.set_tensor(detail["index"],np.zeros(detail["shape"],dtype=detail["dtype"]))
            model.invoke()
            delegated=sum(op["op_name"]=="DELEGATE" for op in model._get_ops_details())
            attached=len(getattr(model,"_delegates",[]))
            proof[name]={"delegate_attached":attached,"delegate_partitions":delegated,"warm_invoke_succeeded":True}
        active=all(p["delegate_attached"]>0 and p["delegate_partitions"]>0 for p in proof.values())
        if requested=="qnn" and not active: raise RuntimeError(f"NPU delegation unproven: {proof}")
        if active:
            self.provider="QNN HTP / NPU palm + landmarks; CPU classifier"
        elif requested!="cpu" and not self.fallback_reason:
            self.fallback_reason="TFLite accepted no QNN partitions; CPU is active"
        metrics.metadata.update(provider=self.provider,qnn_proof=proof,fallback_reason=self.fallback_reason,
                                model_family="Arduino quantized MediaPipe hand gesture (w8a8)",classifier_provider="CPU")

    def infer(self, frame):
        start=time.monotonic()
        rgb=cv2.cvtColor(frame.image,cv2.COLOR_BGR2RGB)
        _, metadata=self.module.inference_callback(rgb)
        hands=[]
        for data in metadata.get("hands",[])[:self.config["max_hands"]]:
            result=np.zeros(132,np.float32)
            result[4:67]=np.asarray(data["landmarks"],np.float32).reshape(-1)
            result[130]=float(data["hand"]=="right")
            result[131]=data["landmark_confidence"]
            hand=decode_hand(result,frame.image.shape[1],frame.image.shape[0])
            # Classification augments geometric checks but is not required for pinch.
            if data["confidence"]>=.75:
                hand.open=hand.open or data["gesture"]=="Open_Palm"
                hand.fist=hand.fist or data["gesture"]=="Closed_Fist"
            hands.append(hand)
        completed=time.monotonic()
        latency=(completed-start)*1000
        self.metrics.mark("inference",completed)
        self.metrics.add("inference_ms",latency)
        return Packet(frame.sequence,frame.captured_at,completed,hands,self.provider,latency)

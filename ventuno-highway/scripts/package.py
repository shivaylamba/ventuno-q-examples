from pathlib import Path
import zipfile
root=Path(__file__).resolve().parents[1]
target=root.parent/'ventuno-highway-applab.zip'
blocked={'.pyc','.pyo','.bin','.onnx','.ort','.pt','.pth','.ckpt','.safetensors',
         '.gguf','.ggml','.tflite','.pb','.dlc','.qnn','.h5','.hdf5','.npz',
         '.npy','.litertlm','.so','.zip','.tar','.tgz','.wav','.log','.pem','.key'}
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(root.rglob('*')):
        relative=path.relative_to(root)
        if path.is_file() and not any(p in {'__pycache__','runtime','runs','.git','models','model-cache','model_downloads','captures','recordings'} for p in relative.parts) and path.suffix.lower() not in blocked and not path.name.startswith('.env') and not path.name.endswith('.tar.gz'):
            archive.write(path,'ventuno-highway/'+relative.as_posix())
print(target)

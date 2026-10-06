"""Create three App Lab import archives from source, without model files."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent.parent
APPS = ('smart-mirror-laptop', 'ai-object-story-booth', 'ai-balance-challenge')
BLOCKED = {'.bin', '.onnx', '.ort', '.pt', '.pth', '.ckpt', '.safetensors', '.gguf',
           '.ggml', '.tflite', '.pb', '.dlc', '.qnn', '.h5', '.hdf5', '.npz', '.npy',
           '.zip', '.tar', '.tgz', '.wav', '.log', '.elf', '.hex', '.pem', '.key'}
SKIP = {'__pycache__', '.cache', '.venv', 'venv', 'node_modules', 'build',
        'models', 'model-cache', 'model_downloads', 'captures', 'recordings'}

def package():
    destination = ROOT / 'dist'
    destination.mkdir(exist_ok=True)
    for name in APPS:
        app = ROOT / name
        assert (app / 'app.yaml').is_file(), f'Missing app.yaml: {name}'
        target = destination / (name + '.zip')
        with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(app.rglob('*')):
                if not path.is_file() or any(part in SKIP for part in path.relative_to(app).parts) or path.suffix in {'.pyc', '.pyo'}:
                    continue
                if path.suffix.lower() in BLOCKED or path.name.startswith('.env') or path.name.endswith('.tar.gz'):
                    raise ValueError(f'Non-source file cannot be packaged: {path.relative_to(ROOT)}')
                archive.write(path, path.relative_to(ROOT).as_posix())
        with zipfile.ZipFile(target) as archive:
            assert archive.testzip() is None
            print(f'{target.relative_to(ROOT)}: {len(archive.namelist())} files')

if __name__ == '__main__':
    package()

Place private model weights in this directory.

Expected default filenames:

- `crack_detect.pt`
- `puddle_detect.pt`
- `fod_detect.pt`

Do not commit model binaries. The repository ignore rules keep common weight
and export formats private, including `.pt`, `.pth`, `.onnx`, `.engine`,
`.tflite`, `.torchscript`, and `.ncnn`.

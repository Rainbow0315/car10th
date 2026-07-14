Place private model weights in this directory.

Expected default filenames:

- `road_inspection_6class.pt` (current patrol model: road defect / water / foreign object classes)

Legacy split-model filenames:

- `crack_detect.pt`
- `puddle_detect.pt`
- `fod_detect.pt`

Do not commit model binaries. The repository ignore rules keep common weight
and export formats private, including `.pt`, `.pth`, `.onnx`, `.engine`,
`.tflite`, `.torchscript`, and `.ncnn`.

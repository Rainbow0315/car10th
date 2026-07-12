"""
YOLOv7 模型定义（自包含，无需外部仓库依赖）

从 YOLOv7 官方仓库提取的核心模块:
https://github.com/WongKinYiu/yolov7

支持:
- yolov7.yaml (完整版): SPPCSPC + RepConv
- yolov7-tiny-silu.yaml (轻量版): SP + MP
"""

import torch
import torch.nn as nn
import numpy as np


# ==================== 基础层 ====================

def autopad(k, p=None, d=1):
    """自动计算 padding 使输出尺寸与输入相同（stride=1 时）"""
    if d > 1:
        k = d * (k - 1) + 1 if isinstance(k, int) else [d * (x - 1) + 1 for x in k]
    if p is None:
        p = k // 2 if isinstance(k, int) else [x // 2 for x in k]
    return p


class Conv(nn.Module):
    """标准卷积: Conv2d + BatchNorm2d + SiLU/LeakyReLU"""
    def __init__(self, c1, c2, k=1, s=1, p=None, g=1, act=True):
        super().__init__()
        self.conv = nn.Conv2d(c1, c2, k, s, autopad(k, p), groups=g, bias=False)
        self.bn = nn.BatchNorm2d(c2)
        self.act = nn.SiLU() if act is True else (act if isinstance(act, nn.Module) else nn.Identity())

    def forward(self, x):
        return self.act(self.bn(self.conv(x)))


# ==================== YOLOv7-tiny 专用模块 ====================

class MP(nn.Module):
    """MaxPool + 分支卷积（YOLOv7-tiny 下采样模块）"""
    def __init__(self, k=2):
        super().__init__()
        self.m = nn.MaxPool2d(kernel_size=k, stride=k)

    def forward(self, x):
        return self.m(x)


class SP(nn.Module):
    """Spatial Pooling（YOLOv7-tiny 空间池化）"""
    def __init__(self, k=3, s=1):
        super().__init__()
        self.m = nn.MaxPool2d(kernel_size=k, stride=s, padding=k // 2)

    def forward(self, x):
        return self.m(x)


# ==================== YOLOv7 完整版专用模块 ====================

class SPPCSPC(nn.Module):
    """Spatial Pyramid Pooling Cross Stage Partial Connection"""
    def __init__(self, c1, c2, k=(5, 9, 13)):
        super().__init__()
        c_ = c1 // 2  # hidden channels
        self.cv1 = Conv(c1, c_, 1, 1)
        self.cv2 = Conv(c1, c_, 1, 1)
        self.cv3 = Conv(c_, c_, 3, 1)
        self.cv4 = Conv(c_, c_, 1, 1)
        self.m = nn.ModuleList([nn.MaxPool2d(kernel_size=x, stride=1, padding=x // 2) for x in k])
        self.cv5 = Conv(4 * c_, c_, 1, 1)
        self.cv6 = Conv(c_, c_, 3, 1)
        self.cv7 = Conv(2 * c_, c2, 1, 1)

    def forward(self, x):
        x1 = self.cv4(self.cv3(self.cv1(x)))
        y1 = self.cv6(self.cv5(torch.cat([x1] + [m(x1) for m in self.m], 1)))
        y2 = self.cv2(x)
        return self.cv7(torch.cat((y1, y2), dim=1))


class RepConv(nn.Module):
    """Reparameterizable Convolution（训练时多分支，推理时可融合为单分支）"""
    def __init__(self, c1, c2, k=3, s=1, p=None, g=1, act=True, deploy=False):
        super().__init__()
        self.deploy = deploy
        self.groups = g
        self.in_channels = c1
        self.out_channels = c2

        assert k == 3
        assert autopad(k, p) == 1

        padding_11 = autopad(k, p) - k // 2

        if deploy:
            self.rbr_reparam = nn.Conv2d(c1, c2, k, s, autopad(k, p), groups=g, bias=True)
        else:
            self.rbr_identity = nn.BatchNorm2d(num_features=c1) if c2 == c1 and s == 1 else None
            self.rbr_dense = nn.Sequential(
                nn.Conv2d(c1, c2, k, s, autopad(k, p), groups=g, bias=False),
                nn.BatchNorm2d(c2),
            )
            self.rbr_1x1 = nn.Sequential(
                nn.Conv2d(c1, c2, 1, s, padding_11, groups=g, bias=False),
                nn.BatchNorm2d(c2),
            )

        self.act = nn.SiLU() if act is True else (act if isinstance(act, nn.Module) else nn.Identity())

    def forward(self, inputs):
        if self.deploy:
            return self.act(self.rbr_reparam(inputs))

        if self.rbr_identity is None:
            id_out = 0
        else:
            id_out = self.rbr_identity(inputs)

        return self.act(self.rbr_dense(inputs) + self.rbr_1x1(inputs) + id_out)


# ==================== 通用模块 ====================

class Concat(nn.Module):
    """沿 channel 维度拼接多个特征图"""
    def __init__(self, dimension=1):
        super().__init__()
        self.d = dimension

    def forward(self, x):
        return torch.cat(x, self.d)


# ==================== 检测头 ====================

class Detect(nn.Module):
    """YOLOv7 检测头（三层输出，对应三个不同尺度）"""
    stride = None  # 在模型构建时根据输入尺寸计算
    onnx_dynamic = False
    export = False

    def __init__(self, nc=80, anchors=(), ch=(), inplace=True):
        super().__init__()
        self.nc = nc  # 类别数
        self.no = nc + 5  # 每 anchor 输出数 (xywh + obj + cls)
        self.nl = len(anchors)  # 检测层数
        self.na = len(anchors[0]) // 2  # 每层 anchor 数
        self.grid = [torch.empty(0)] * self.nl
        self.anchor_grid = [torch.empty(0)] * self.nl
        self.register_buffer('anchors', torch.tensor(anchors).float().view(self.nl, -1, 2))
        self.m = nn.ModuleList(nn.Conv2d(x, self.no * self.na, 1) for x in ch)
        self.inplace = inplace

    def forward(self, x):
        z = []
        for i in range(self.nl):
            x[i] = self.m[i](x[i])
            bs, _, ny, nx = x[i].shape
            x[i] = x[i].view(bs, self.na, self.no, ny, nx).permute(0, 1, 3, 4, 2).contiguous()

            if not self.training:
                if self.grid[i].shape[2:4] != x[i].shape[2:4]:
                    self.grid[i], self.anchor_grid[i] = self._make_grid(nx, ny, i)

                y = x[i].sigmoid()
                y[..., 0:2] = (y[..., 0:2] * 2.0 - 0.5 + self.grid[i]) * self.stride[i]  # xy
                y[..., 2:4] = (y[..., 2:4] * 2) ** 2 * self.anchor_grid[i]  # wh
                z.append(y.view(bs, -1, self.no))

        return x if self.training else (torch.cat(z, 1), x)

    def _make_grid(self, nx=20, ny=20, i=0):
        d = self.anchors[i].device
        t = self.anchors[i].dtype
        shape = 1, self.na, ny, nx, 2
        y, x = torch.arange(ny, device=d, dtype=t), torch.arange(nx, device=d, dtype=t)
        yv, xv = torch.meshgrid(y, x, indexing='ij')
        grid = torch.stack((xv, yv), 2).expand(shape) - 0.5
        anchor_grid = (self.anchors[i].clone() * self.stride[i]) \
            .view((1, self.na, 1, 1, 2)).expand(shape).float()
        return grid, anchor_grid


# ==================== 模型构建 ====================

class YOLOModel(nn.Module):
    """
    根据 YAML 配置构建 YOLOv7 模型
    支持加载 .pt 检查点进行推理
    """
    def __init__(self, cfg_dict, ch=3, nc=None, anchors=None):
        super().__init__()
        self.yaml = cfg_dict

        # 解析配置
        if isinstance(cfg_dict, dict):
            self.yaml = cfg_dict
        else:
            import yaml
            with open(cfg_dict, 'r') as f:
                self.yaml = yaml.safe_load(f)

        # 模型深度/宽度缩放
        self.depth_multiple = self.yaml.get('depth_multiple', 1.0)
        self.width_multiple = self.yaml.get('width_multiple', 1.0)

        # anchors
        if anchors:
            self.anchors = anchors
        elif 'anchors' in self.yaml:
            self.anchors = self.yaml['anchors']

        # 构建模型
        self.model, self.save = self._parse_model(self.yaml, ch=[ch])
        self.names = [str(i) for i in range(nc)] if nc else (self.yaml.get('names', [f'class{i}' for i in range(80)]))

        # 初始化权重（仅对新创建的层，加载检查点时会被覆盖）
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)

    def _parse_model(self, d, ch):
        """解析 YAML 配置构建层序列"""
        anchors = d.get('anchors', [[10, 13, 16, 30, 33, 23], [30, 61, 62, 45, 59, 119], [116, 90, 156, 198, 373, 326]])
        na = (len(anchors[0]) // 2) if isinstance(anchors, list) else anchors
        no = 5 + (d.get('nc', 80))

        layers, save, c2 = [], [], ch[-1]
        for i, (f, n, m, args) in enumerate(d['backbone'] + d['head']):
            m = eval(m) if isinstance(m, str) else m
            for j, a in enumerate(args):
                try:
                    args[j] = eval(a) if isinstance(a, str) else a
                except:
                    pass

            n = n if n > 0 else 1
            n = max(round(n * self.depth_multiple), 1) if n > 1 else n

            if m in [Conv, RepConv]:
                c1, c2 = ch[f], args[0]
                if c2 != no:  # 非检测头通道
                    c2 = int(c2 * self.width_multiple / 8) * 8  # 调整为 8 的倍数
                args = [c1, c2, *args[1:]]
                if m is RepConv:
                    args.insert(2, 3)  # kernel_size=3
            elif m is SPPCSPC:
                c1, c2 = ch[f], args[0]
                c2 = int(c2 * self.width_multiple / 8) * 8
                args = [c1, c2, *args[1:]]
            elif m is Detect:
                # 收集检测层输入通道
                args.append([ch[x] for x in f])
            elif m is Concat:
                c2 = sum(ch[x] for x in f)
            elif m is MP:
                c2 = ch[f]
            elif m is SP:
                c2 = ch[f]
            else:
                c2 = ch[f]

            if isinstance(args[0], (list, tuple)):
                m_ = m(*args[0])
            else:
                m_ = m(*args)

            layers.append(m_)
            ch.append(c2)
            save.extend(x % i for x in ([f] if isinstance(f, int) else f) if x != -1)

        return nn.Sequential(*layers), sorted(save)

    def forward(self, x, augment=False, profile=False):
        y, dt = [], []
        for m in self.model:
            if m.f != -1:
                x = y[m.f] if isinstance(m.f, int) else [x if j == -1 else y[j] for j in m.f]

            x = m(x)
            y.append(x if m.i in self.save else None)

        return x


def get_model_cfg_from_checkpoint(checkpoint):
    """
    从 .pt 检查点中提取模型配置，构建模型实例

    Args:
        checkpoint: torch.load() 加载的字典，或 .pt 文件路径

    Returns:
        model: YOLOModel 实例
        checkpoint: 检查点字典
    """
    if isinstance(checkpoint, str):
        checkpoint = torch.load(checkpoint, map_location='cpu', weights_only=False)

    if isinstance(checkpoint, dict) and 'model' in checkpoint:
        ckpt = checkpoint
        model_state = ckpt['model']
    else:
        ckpt = {'model': checkpoint}
        model_state = checkpoint

    # 从模型对象中提取配置
    if hasattr(model_state, 'yaml'):
        cfg = model_state.yaml
        if isinstance(cfg, dict):
            nc = cfg.get('nc', 80)
            anchors = cfg.get('anchors', None)
        else:
            nc = 80
            anchors = None

        model = YOLOModel(cfg, nc=nc, anchors=anchors)

        # 加载权重
        if hasattr(model_state, 'state_dict'):
            state_dict = model_state.state_dict()
        elif hasattr(model_state, 'float'):
            state_dict = model_state.float().state_dict()
        else:
            state_dict = model_state

        model.load_state_dict(state_dict, strict=False)
    else:
        raise ValueError("无法从检查点中提取模型配置")

    return model, ckpt


def load_yolov7_model(weights_path, device='cpu'):
    """
    加载 YOLOv7 模型（支持 yolov7.pt 和 best_ben_sgd.pt 等变体）

    Args:
        weights_path: .pt 权重文件路径
        device: 'cpu' 或 'cuda'

    Returns:
        model: 加载了权重的 YOLOModel
        names: 类别名称列表
        stride: 模型步长
    """
    checkpoint = torch.load(weights_path, map_location=device, weights_only=False)

    if isinstance(checkpoint, dict) and 'model' in checkpoint:
        model_state = checkpoint.get('ema') or checkpoint['model']
    else:
        model_state = checkpoint

    # When the original YOLOv7 repository modules are on PYTHONPATH,
    # torch.load restores the pickled Model object directly. Prefer using it
    # because custom training configs may include layers not covered by the
    # lightweight parser below.
    if hasattr(model_state, 'float') and hasattr(model_state, 'eval') and hasattr(model_state, 'forward'):
        model = model_state.float()
        if hasattr(model, 'fuse'):
            try:
                model = model.fuse()
            except Exception:
                pass
        model = model.eval().to(device)

        names = getattr(model, 'names', None)
        if names is None and hasattr(model, 'yaml') and isinstance(model.yaml, dict):
            names = model.yaml.get('names')
        if names is None and isinstance(checkpoint, dict):
            names = checkpoint.get('names')
        if isinstance(names, dict):
            names = [names[i] for i in range(len(names))]
        if names is None:
            nc = getattr(model, 'nc', None)
            if nc is None and hasattr(model, 'yaml') and isinstance(model.yaml, dict):
                nc = model.yaml.get('nc', 80)
            names = [f'class{i}' for i in range(int(nc or 80))]

        stride = 32
        if hasattr(model, 'stride'):
            try:
                stride = int(model.stride.max())
            except Exception:
                stride = int(model.stride)
        return model, names, stride

    if hasattr(model_state, 'yaml'):
        # YOLOv7 ??????? yaml ??
        cfg = model_state.yaml
        if isinstance(cfg, dict):
            nc = cfg.get('nc', 80)
            anchors = cfg.get('anchors', None)
            names = cfg.get('names', [f'class{i}' for i in range(nc)])
            if isinstance(names, dict):
                names = [names[i] for i in range(len(names))]
        else:
            nc = 80
            anchors = None
            names = [f'class{i}' for i in range(nc)]

        model = YOLOModel(cfg, nc=nc, anchors=anchors)

        # ????
        if hasattr(model_state, 'state_dict'):
            state_dict = model_state.state_dict()
        elif hasattr(model_state, 'float'):
            state_dict = model_state.float().state_dict()
        else:
            state_dict = model_state

        model.load_state_dict(state_dict, strict=False)

        # ?? stride
        stride = 32  # ????????????
        if hasattr(model_state, 'stride'):
            stride = int(model_state.stride.max())
    else:
        raise ValueError("??????????????????")

    model = model.to(device).eval()
    return model, names, stride

"""
YOLOv7 models.yolo 模块定义

提供 torch.load() 反序列化所需的 Detect 类和 Model 类。
"""

import torch
import torch.nn as nn
import numpy as np
from pathlib import Path


class Detect(nn.Module):
    """YOLOv7 检测头"""
    stride = None
    onnx_dynamic = False
    export = False

    def __init__(self, nc=80, anchors=(), ch=(), inplace=True):
        super().__init__()
        self.nc = nc
        self.no = nc + 5
        self.nl = len(anchors)
        self.na = len(anchors[0]) // 2
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
                # 每次都重新计算 grid（避免 pickle 恢复后的缓存兼容问题）
                grid_i, anchor_grid_i = self._make_grid(nx, ny, i)

                y = x[i].sigmoid()
                y[..., 0:2] = (y[..., 0:2] * 2.0 - 0.5 + grid_i) * self.stride[i]
                y[..., 2:4] = (y[..., 2:4] * 2) ** 2 * anchor_grid_i
                z.append(y.view(bs, -1, self.no))

        return x if self.training else (torch.cat(z, 1), x)

    def _make_grid(self, nx=20, ny=20, i=0):
        """生成网格和 anchor 网格（注意：不是静态方法，需要 self 访问 anchors 和 stride）"""
        d = self.anchors[i].device
        t = self.anchors[i].dtype
        shape = 1, self.na, ny, nx, 2

        y, x = torch.arange(ny, device=d, dtype=t), torch.arange(nx, device=d, dtype=t)
        yv, xv = torch.meshgrid(y, x, indexing='ij')
        grid = torch.stack((xv, yv), 2).expand(shape) - 0.5  # [-0.5, nx-0.5]

        # anchor_grid = anchors * stride, 展开到网格尺寸
        anchor_grid = (self.anchors[i].clone() * self.stride[i]) \
            .view((1, self.na, 1, 1, 2)).expand(shape).float()
        return grid, anchor_grid


class Model(nn.Module):
    """YOLOv7 完整模型 (兼容 torch.load 反序列化)

    注意: 当通过 pickle (torch.load) 加载时, __init__ 不会被调用,
    属性直接从保存的 __dict__ 恢复。这里的 __init__ 仅用于手动构建场景。
    """
    def __init__(self, cfg='yolov7.yaml', ch=3, nc=None, anchors=None):
        super().__init__()

        if isinstance(cfg, dict):
            self.yaml = cfg
        else:
            self.yaml = str(cfg)

        if nc is not None and isinstance(self.yaml, dict):
            self.yaml['nc'] = nc
        if anchors and isinstance(self.yaml, dict):
            self.yaml['anchors'] = anchors

        self.model = nn.Sequential()
        self.save = []
        self.nc = nc or (self.yaml.get('nc', 80) if isinstance(self.yaml, dict) else 80)
        self.names = [f'class{i}' for i in range(self.nc)]

    def forward(self, x, augment=False, profile=False):
        """YOLOv7 前向传播 (支持跳跃连接路由)"""
        y, dt = [], []
        for i, m in enumerate(self.model):
            if m.f != -1:  # 路由: -1 表示上一层, 其他值表示跳跃连接
                x = y[m.f] if isinstance(m.f, int) else \
                    [x if j == -1 else y[j] for j in m.f]

            # profile
            if profile:
                import time
                t = time.time()

            x = m(x)  # 执行当前层

            if profile:
                dt.append(time.time() - t)

            # 保存输出供后续跳跃连接使用
            y.append(x if m.i in self.save else None)

        return x

"""
YOLOv7 推理工具函数

通用预处理、后处理、NMS、可视化功能。
供 demo_puddle.py 和 demo_fod.py 共用。
"""

import cv2
import torch
import numpy as np
from PIL import Image, ImageDraw, ImageFont


# ==================== 图像预处理 ====================

def letterbox(img, new_shape=640, color=(114, 114, 114), auto=True, stride=32):
    """
    等比例缩放并填充至目标尺寸（YOLOv7 标准预处理）

    Args:
        img: 输入图像 (H, W, C)
        new_shape: 目标尺寸
        color: 填充颜色
        auto: 自动调整填充为 stride 的倍数
        stride: 模型步长

    Returns:
        img: 处理后的图像
        ratio: 缩放比例
        dw, dh: 填充宽度/高度
    """
    shape = img.shape[:2]
    if isinstance(new_shape, int):
        new_shape = (new_shape, new_shape)

    # 计算缩放比例
    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    ratio = r, r  # width, height ratios

    new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))
    dw, dh = new_shape[1] - new_unpad[0], new_shape[0] - new_unpad[1]

    if auto:  # 调整为 stride 的倍数
        dw, dh = np.mod(dw, stride), np.mod(dh, stride)

    dw /= 2
    dh /= 2

    if shape[::-1] != new_unpad:
        img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)

    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)

    return img, ratio, (dw, dh)


# ==================== 后处理 ====================

def non_max_suppression(prediction, conf_thres=0.25, iou_thres=0.45,
                         classes=None, agnostic=False, multi_label=False,
                         max_det=300):
    """
    对 YOLO 输出进行非极大值抑制(NMS)

    Args:
        prediction: 模型原始输出 [batch, num_anchors, 5+nc]
        conf_thres: 置信度阈值
        iou_thres: NMS IoU 阈值
        classes: 仅保留这些类别
        agnostic: 类别无关 NMS
        multi_label: 每个 anchor 允许多标签
        max_det: 最大检测数

    Returns:
        List[torch.Tensor]: 每个图像的检测结果 [N, 6] (x1, y1, x2, y2, conf, cls)
    """
    nc = prediction.shape[2] - 5  # 类别数
    xc = prediction[..., 4] > conf_thres  # 物体置信度筛选

    # 检查配置
    assert 0 <= conf_thres <= 1
    assert 0 <= iou_thres <= 1

    max_wh = 7680  # 最大宽高 (用于合并 NMS)
    max_nms = 30000  # NMS 前最大候选框数
    multi_label &= nc > 1  # 单类别时不需要多标签

    output = [torch.zeros((0, 6), device=prediction.device)] * prediction.shape[0]
    for xi, x in enumerate(prediction):
        x = x[xc[xi]]  # 筛选置信度

        if not x.shape[0]:
            continue

        # 置信度 = obj_conf * cls_conf
        x[:, 5:] *= x[:, 4:5]

        # 框坐标 (center_x, center_y, width, height) → (x1, y1, x2, y2)
        box = xywh2xyxy(x[:, :4])

        if multi_label:
            i, j = (x[:, 5:] > conf_thres).nonzero(as_tuple=False).T
            x = torch.cat((box[i], x[i, j + 5, None], j[:, None].float()), 1)
        else:
            conf, j = x[:, 5:].max(1, keepdim=True)
            x = torch.cat((box, conf, j.float()), 1)[conf.view(-1) > conf_thres]

        # 按类别筛选
        if classes is not None:
            x = x[(x[:, 5:6] == torch.tensor(classes, device=x.device)).any(1)]

        n = x.shape[0]
        if not n:
            continue
        elif n > max_nms:
            x = x[x[:, 4].argsort(descending=True)[:max_nms]]

        # 批量 NMS
        c = x[:, 5:6] * (0 if agnostic else max_wh)
        boxes, scores = x[:, :4] + c, x[:, 4]
        i = _nms(boxes, scores, iou_thres)

        if i.shape[0] > max_det:
            i = i[:max_det]

        output[xi] = x[i]

    return output


def xywh2xyxy(x):
    """[x, y, w, h] → [x1, y1, x2, y2]"""
    y = x.clone() if isinstance(x, torch.Tensor) else np.copy(x)
    y[:, 0] = x[:, 0] - x[:, 2] / 2  # top left x
    y[:, 1] = x[:, 1] - x[:, 3] / 2  # top left y
    y[:, 2] = x[:, 0] + x[:, 2] / 2  # bottom right x
    y[:, 3] = x[:, 1] + x[:, 3] / 2  # bottom right y
    return y


def scale_boxes(img1_shape, boxes, img0_shape, ratio_pad=None):
    """
    将预测框从 letterbox 尺寸缩放回原图尺寸

    Args:
        img1_shape: 模型输入尺寸 (h, w)
        boxes: 预测框 [N, 4] (x1, y1, x2, y2)
        img0_shape: 原图尺寸 (h, w)
        ratio_pad: (ratio, pad) 从 letterbox 返回

    Returns:
        boxes: 缩放后的框
    """
    if ratio_pad is None:
        gain = min(img1_shape[0] / img0_shape[0], img1_shape[1] / img0_shape[1])
        pad = ((img1_shape[1] - img0_shape[1] * gain) / 2,
               (img1_shape[0] - img0_shape[0] * gain) / 2)
    else:
        gain = ratio_pad[0][0]
        pad = ratio_pad[1]

    boxes[:, [0, 2]] -= pad[0]  # x padding
    boxes[:, [1, 3]] -= pad[1]  # y padding
    boxes[:, :4] /= gain
    clip_boxes(boxes, img0_shape)
    return boxes


def clip_boxes(boxes, shape):
    """将框裁剪到图像边界内"""
    if isinstance(boxes, torch.Tensor):
        boxes[:, 0].clamp_(0, shape[1])
        boxes[:, 1].clamp_(0, shape[0])
        boxes[:, 2].clamp_(0, shape[1])
        boxes[:, 3].clamp_(0, shape[0])
    else:
        boxes[:, 0] = np.clip(boxes[:, 0], 0, shape[1])
        boxes[:, 1] = np.clip(boxes[:, 1], 0, shape[0])
        boxes[:, 2] = np.clip(boxes[:, 2], 0, shape[1])
        boxes[:, 3] = np.clip(boxes[:, 3], 0, shape[0])


# ==================== NMS (纯 Python 实现) ====================

def _nms(boxes, scores, iou_thres):
    """
    纯 PyTorch NMS 实现（不依赖 torchvision）

    Args:
        boxes: Tensor [N, 4] (x1, y1, x2, y2)
        scores: Tensor [N]
        iou_thres: IoU 阈值

    Returns:
        keep: LongTensor of kept box indices
    """
    if boxes.numel() == 0:
        return torch.empty(0, dtype=torch.long, device=boxes.device)

    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)

    # 按分数降序排列
    _, order = scores.sort(descending=True)

    keep = []
    while order.numel() > 0:
        if order.numel() == 1:
            keep.append(order.item())
            break

        i = order[0]
        keep.append(i.item())

        # 计算当前框与剩余框的 IoU
        xx1 = torch.max(x1[i], x1[order[1:]])
        yy1 = torch.max(y1[i], y1[order[1:]])
        xx2 = torch.min(x2[i], x2[order[1:]])
        yy2 = torch.min(y2[i], y2[order[1:]])

        w = (xx2 - xx1).clamp(min=0)
        h = (yy2 - yy1).clamp(min=0)
        inter = w * h

        union = areas[i] + areas[order[1:]] - inter
        iou = inter / union

        # 保留 IoU 低于阈值的框
        mask = iou <= iou_thres
        order = order[1:][mask]

    return torch.tensor(keep, dtype=torch.long, device=boxes.device)


# ==================== 可视化 ====================

# 预定义颜色（BGR 格式, 用于 OpenCV 绘图）
COLORS_BGR = [
    (255, 80, 80),    # 蓝 (BGR)
    (80, 255, 80),    # 绿
    (80, 80, 255),    # 红
    (255, 255, 80),   # 青
    (255, 80, 255),   # 品红
    (80, 255, 255),   # 黄
    (0, 140, 255),    # 橙
    (255, 0, 140),    # 紫
    (255, 140, 0),    # 天蓝
    (0, 255, 140),    # 黄绿
]

# 水洼检测专用色系 (BGR)
PUDDLE_COLORS = {
    'L00': (180, 60, 60),   # 深蓝
    'L01': (220, 100, 60),  # 蓝
    'R02': (200, 60, 160),  # 紫蓝
    'R03': (180, 120, 60),  # 浅蓝
}


def draw_boxes(image, detections, names, conf_thres=0.25, color_mode=None):
    """
    在图像上绘制检测框（OpenCV 实现，效果与 Ultralytics 一致）

    Args:
        image: numpy array (BGR)
        detections: torch.Tensor [N, 6] (x1,y1,x2,y2,conf,cls)
        names: 类别名称列表
        conf_thres: 显示阈值
        color_mode: 'puddle' 使用水洼蓝色系, None 使用默认多彩色系

    Returns:
        image: 带标注的 PIL Image (RGB)
    """
    # 确保是 numpy BGR 数组
    if isinstance(image, Image.Image):
        image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    else:
        image = image.copy()

    if detections is None or len(detections) == 0:
        return Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

    for det in detections:
        if len(det) == 0:
            continue
        *xyxy, conf, cls = det.tolist()
        if conf < conf_thres:
            continue

        x1, y1, x2, y2 = map(int, xyxy)
        cls = int(cls)
        name = names[cls] if cls < len(names) else f'cls_{cls}'

        # 颜色选择
        if color_mode == 'puddle':
            color = PUDDLE_COLORS.get(name, (200, 80, 50))
        else:
            color = COLORS_BGR[cls % len(COLORS_BGR)]

        label = f"{name} {conf:.2f}"

        # ---- 画半透明填充框 ----
        overlay = image.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
        cv2.addWeighted(overlay, 0.12, image, 0.88, 0, image)

        # ---- 画边框 (粗线) ----
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 3)

        # ---- 画标签 ----
        (tw, th), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        label_y = y1 - 6 if y1 - 6 > th else y1 + th + 6

        # 标签背景
        cv2.rectangle(image, (x1, label_y - th - 4), (x1 + tw + 8, label_y + 4), color, -1)
        # 标签文字 (白色)
        cv2.putText(image, label, (x1 + 4, label_y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, (255, 255, 255), 2, cv2.LINE_AA)

    # 转回 PIL RGB
    return Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseDetector(ABC):
    def __init__(self, *, conf: float, iou: float, device: str) -> None:
        self.conf = conf
        self.iou = iou
        self.device = device

    @abstractmethod
    def load_model(self, weight_path: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def detect(self, image_path: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

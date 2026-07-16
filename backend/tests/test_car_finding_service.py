import unittest
from unittest.mock import patch

from apps.web_api.services.car_finding_service import CarFindingService


class CarFindingServiceTests(unittest.TestCase):
    def test_normalize_plate_keeps_chinese_prefix(self):
        service = CarFindingService()

        self.assertEqual(service.normalize_plate("\u6CAA A-12345"), "\u6CAAA12345")

    def test_extract_plate_candidates_reads_plate_extra(self):
        service = CarFindingService()
        detection = {
            "results": {
                "plate": {
                    "detections": [
                        {
                            "label": "plate",
                            "confidence": 0.91,
                            "extra": {"plate_number": "\u6CAAA12345"},
                        }
                    ]
                }
            }
        }

        self.assertEqual(service.extract_plate_candidates(detection), ["\u6CAAA12345"])

    def test_extract_plate_candidates_ignores_cloud_ocr_backend(self):
        service = CarFindingService()
        detection = {
            "results": {
                "plate": {
                    "detections": [
                        {
                            "label": "license_plate",
                            "confidence": 0.91,
                            "extra": {
                                "plate_number": "",
                                "ocr_backend": "cloud",
                                "ocr_candidates": [
                                    {"text": "\u6CAA A-12345", "score": 0.92}
                                ],
                            },
                        }
                    ]
                }
            }
        }

        self.assertEqual(service.extract_plate_candidates(detection), ["\u6CAA A-12345"])

    def test_verify_compares_detected_plate_with_record(self):
        service = CarFindingService()
        service.park_at_spot_one("demo_user", "\u6CAAA12345")
        detection = {
            "results": {
                "plate": {
                    "detections": [
                        {
                            "label": "plate",
                            "confidence": 0.91,
                            "extra": {"plate_number": "\u6CAA A-12345"},
                        }
                    ]
                }
            }
        }

        with patch(
            "apps.web_api.services.car_finding_service.inspection_service.detect_ros_plate",
            return_value=detection,
        ):
            result = service.verify_at_spot_one("demo_user", "/image_raw", 1.0, "robot_001", "usb_cam")

        self.assertTrue(result["matched"])
        self.assertEqual(result["expected_normalized_plate"], "\u6CAAA12345")

    def test_verify_plate_compares_input_directly(self):
        service = CarFindingService()
        detection = {
            "results": {
                "plate": {
                    "detections": [
                        {
                            "label": "plate",
                            "confidence": 0.91,
                            "extra": {"plate_number": "\u6CAA A-12345"},
                        }
                    ]
                }
            }
        }

        with patch(
            "apps.web_api.services.car_finding_service.inspection_service.detect_ros_plate",
            return_value=detection,
        ):
            result = service.verify_plate("\u6CAAA12345", "/image_raw", 1.0, "robot_001", "usb_cam")

        self.assertTrue(result["matched"])
        self.assertEqual(result["expected_plate"], "\u6CAAA12345")
        self.assertEqual(result["detected_plates"], ["\u6CAA A-12345"])


if __name__ == "__main__":
    unittest.main()
